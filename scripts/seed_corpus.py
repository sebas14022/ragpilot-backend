"""Seed the RagPilot demo corpus (a single large markdown document) for a user.

This bypasses HTTP auth (like scripts/seed.py) by using the service-role client
directly: it chunks, embeds, and inserts document rows + document_chunks with
the real pipeline functions, so the corpus is immediately queryable via the UI.

The demo uses ONE large document (docs/sample_document_large.md) so the RAG vs
full-document contrast is the whole point: RAG retrieves a single chunk while the
full-doc baseline stuffs the entire file.

Usage:
    .venv\\Scripts\\python.exe -m scripts.seed_corpus <user_email> [doc_path]
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.chunking import chunk_text  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import get_supabase  # noqa: E402
from app.embeddings import embed_texts, format_vector  # noqa: E402


def resolve_user_id(sb, email: str) -> str | None:
    try:
        res = sb.auth.admin.list_users()
        for u in (res.users or []):
            if u.email == email:
                return u.id
    except Exception as exc:
        print(f"Could not list users: {exc}")
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.seed_corpus <user_email> [doc_path]")
        sys.exit(1)

    email = sys.argv[1]
    doc_path = (
        Path(sys.argv[2]) if len(sys.argv) > 2 else Path("docs/sample_document_large.md")
    )

    if not doc_path.is_file():
        print(f"Not a file: {doc_path}")
        sys.exit(1)

    sb = get_supabase()
    user_id = resolve_user_id(sb, email)
    if not user_id:
        print(f"No user found for {email}")
        sys.exit(1)

    text = doc_path.read_text(encoding="utf-8").strip()
    if not text:
        print(f"Empty file: {doc_path}")
        sys.exit(1)

    budget = get_settings().max_document_chars
    if len(text) > budget:
        print(
            f"Aborted: {doc_path.name} has {len(text)} characters, above the "
            f"{budget} character limit (~6K tokens) so the full-doc baseline "
            f"fits its token budget. Trim the document and re-run the seed."
        )
        sys.exit(1)

    filename = doc_path.name
    print(f"Seeding single document {filename} for {email} ({user_id})")

    doc_id = str(uuid.uuid4())
    sb.table("documents").insert(
        {
            "id": doc_id,
            "user_id": user_id,
            "filename": filename,
            "status": "processing",
            "chunks": 0,
        }
    ).execute()

    chunks = chunk_text(text)
    if not chunks:
        sb.table("documents").update({"status": "indexed", "chunks": 0}).eq(
            "id", doc_id
        ).execute()
        print(f"Done. No chunks indexed for {filename}.")
        sys.exit(0)

    vectors = embed_texts(chunks)
    rows = [
        {
            "id": str(uuid.uuid4()),
            "document_id": doc_id,
            "user_id": user_id,
            "chunk_index": i,
            "content": chunk,
            "embedding": format_vector(vectors[i]),
        }
        for i, chunk in enumerate(chunks)
    ]
    sb.table("document_chunks").insert(rows).execute()
    sb.table("documents").update({"status": "indexed", "chunks": len(chunks)}).eq(
        "id", doc_id
    ).execute()

    print(f"  - {filename}: {len(chunks)} chunks")
    print(f"Done. Indexed 1 document, {len(chunks)} chunks total.")


if __name__ == "__main__":
    main()
