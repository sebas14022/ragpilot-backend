"""Document upload, listing and deletion."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile


from ..auth import require_user, UserContext
from ..chunking import chunk_text
from ..config import get_settings
from ..db import get_supabase
from ..embeddings import embed_texts, format_vector
from ..schemas import DocumentList, DocumentSummary, UploadResult
from ..text_extraction import UnsupportedFormatError, extract_text

router = APIRouter()
logger = logging.getLogger(__name__)


def _bucket() -> str:
    return get_settings().storage_bucket


@router.post("/documents", response_model=UploadResult, status_code=201)
async def upload_document(
    file: UploadFile = File(...),
    user: UserContext = Depends(require_user),
) -> UploadResult:
    sb = get_supabase()
    settings = get_settings()
    content = await file.read()

    doc_id = str(uuid.uuid4())
    ext = file.filename.rsplit(".", 1)[-1].lower()
    storage_path = f"{user.user_id}/{doc_id}.{ext}"

    # 0. Extract text and enforce the per-document budget BEFORE creating the
    # row or uploading to storage: oversized docs must not leave failed rows or
    # orphaned files. The full-doc baseline stuffs the whole document into a
    # single prompt, so it must fit the LLM token budget.
    try:
        text = extract_text(content, file.filename or "")
    except UnsupportedFormatError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Could not read document: {exc}")

    # The baseline wraps every document in a "--- name ---" header, so reserve
    # that overhead: the upload gate must never accept a document the
    # comparison would later reject.
    baseline_overhead = len(f"--- {file.filename or 'document'} ---\n\n")
    if len(text) + baseline_overhead > settings.max_document_chars:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Document too large: {len(text)} characters, above the "
                f"{settings.max_document_chars}-character budget for the full-doc "
                "baseline (~6K tokens). Trim the document and try again."
            ),
        )

    # 1. Create the document row (status processing).
    sb.table("documents").insert(
        {
            "id": doc_id,
            "user_id": user.user_id,
            "filename": file.filename,
            "storage_path": storage_path,
            "status": "processing",
            "chunks": 0,
        }
    ).execute()

    # 2. Upload the file to Storage.
    try:
        sb.storage.from_(_bucket()).upload(
            path=storage_path,
            file=content,
            file_options={"content-type": file.content_type or "application/octet-stream"},
        )
    except Exception as exc:
        sb.table("documents").update({"status": "failed"}).eq("id", doc_id).execute()
        raise HTTPException(status_code=500, detail=f"Storage upload failed: {exc}")

    # 3. Chunk, embed and store chunks (text was already extracted in step 0).
    chunks = chunk_text(text)
    if not chunks:
        sb.table("documents").update({"status": "indexed", "chunks": 0}).eq("id", doc_id).execute()
        return UploadResult(id=doc_id, filename=file.filename or "", status="indexed", chunks=0)

    try:
        vectors = embed_texts(chunks)
    except Exception as exc:
        sb.table("documents").update({"status": "failed"}).eq("id", doc_id).execute()
        raise HTTPException(status_code=502, detail=f"Embedding failed: {exc}")

    rows = [
        {
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "user_id": user.user_id,
            "chunk_index": i,
            "content": chunk,
            "embedding": format_vector(vectors[i]),
        }
        for i, chunk in enumerate(chunks)
    ]
    sb.table("document_chunks").insert(rows).execute()

    sb.table("documents").update({"status": "indexed", "chunks": len(chunks)}).eq("id", doc_id).execute()

    return UploadResult(id=doc_id, filename=file.filename or "", status="indexed", chunks=len(chunks))


@router.get("/documents", response_model=DocumentList)
def list_documents(user: UserContext = Depends(require_user)) -> DocumentList:
    sb = get_supabase()
    res = (
        sb.table("documents")
        .select("id, filename, status, chunks, created_at, storage_path")
        .eq("user_id", user.user_id)
        .order("created_at", desc=True)
        .execute()
    )
    rows = res.data or []
    docs = [
        DocumentSummary(
            id=r["id"],
            filename=r["filename"],
            status=r["status"],
            chunks=int(r.get("chunks") or 0),
            createdAt=r.get("created_at"),
            storage_path=r.get("storage_path"),
        )
        for r in rows
    ]
    return DocumentList(documents=docs, total=len(docs))


@router.post("/documents/{doc_id}/delete", status_code=204)
def delete_document(doc_id: str, user: UserContext = Depends(require_user)) -> None:
    sb = get_supabase()
    row = (
        sb.table("documents")
        .select("id, storage_path, user_id")
        .eq("id", doc_id)
        .eq("user_id", user.user_id)
        .maybe_single()
        .execute()
    )
    if not row.data:
        raise HTTPException(status_code=404, detail="Document not found")

    sb.table("document_chunks").delete().eq("document_id", doc_id).execute()
    if row.data.get("storage_path"):
        try:
            sb.storage.from_(_bucket()).remove([row.data["storage_path"]])
        except Exception as exc:
            logger.warning(
                "Failed to remove storage object %s for document %s: %s",
                row.data["storage_path"],
                doc_id,
                exc,
            )
    sb.table("documents").delete().eq("id", doc_id).execute()
