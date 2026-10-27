"""Unit tests for the documents router (upload / list / delete).

All tests call the router functions directly with a fake Supabase client; no
network, storage, Gemini, or real auth is involved.
"""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.auth import UserContext
from app.routers import documents as doc_router


class _Result:
    def __init__(self, data=None):
        self.data = data


class _Builder:
    """Fluent fake for supabase table() chains (select/eq/order/insert/...)."""

    def __init__(self, table_name, sb, result_rows=None):
        self._table = table_name
        self._sb = sb
        self._result_rows = result_rows
        self._single = False
        self.ops = []

    def insert(self, rows):
        self._sb.ops.append(("insert", self._table, rows))
        return self

    def update(self, values):
        self._sb.ops.append(("update", self._table, values))
        return self

    def delete(self):
        self._sb.ops.append(("delete", self._table))
        return self

    def select(self, cols):
        self.ops.append(("select", cols))
        return self

    def eq(self, col, val):
        self.ops.append(("eq", col, val))
        return self

    def in_(self, col, values):
        self.ops.append(("in_", col, values))
        return self

    def order(self, col, desc=None):
        self.ops.append(("order", col, desc))
        return self

    def maybe_single(self):
        self._single = True
        return self

    def execute(self):
        rows = self._result_rows
        if self._single:
            # Supabase maybe_single() -> .data is the first row dict or None.
            data = rows[0] if rows else None
        else:
            data = rows
        return _Result(data)


class _StorageBucket:
    def __init__(self, sb):
        self._sb = sb

    def upload(self, **kwargs):
        self._sb.ops.append(("storage_upload", kwargs))
        return self

    def remove(self, paths):
        self._sb.ops.append(("storage_remove", paths))
        return self


class _Storage:
    def __init__(self, sb):
        self._sb = sb

    def from_(self, bucket):
        return _StorageBucket(self._sb)


class _FakeSb:
    def __init__(self):
        self.ops = []
        self.storage = _Storage(self)
        self._rows = {}

    def set_rows(self, table, rows):
        self._rows[table] = rows

    def table(self, name):
        return _Builder(name, self, self._rows.get(name))


USER = UserContext(user_id="user-1", email="u@example.com")


@pytest.fixture
def sb(monkeypatch):
    fake = _FakeSb()
    settings_double = type(
        "_S", (), {"storage_bucket": "ragpilot-docs", "max_document_chars": 24000}
    )()
    monkeypatch.setattr("app.routers.documents.get_settings", lambda: settings_double)
    monkeypatch.setattr("app.routers.documents.get_supabase", lambda: fake)
    return fake


class _FakeUploadFile:
    filename = "doc.pdf"
    content_type = "application/pdf"

    async def read(self):
        return b"%PDF-1.4 fake"


# ---- upload_document ---------------------------------------------------------

async def test_upload_document_embeds_and_indexes_chunks(sb, monkeypatch):
    monkeypatch.setattr("app.routers.documents.uuid.uuid4", lambda: "doc-1")
    monkeypatch.setattr(
        "app.routers.documents.extract_text", lambda content, name: "some text"
    )
    monkeypatch.setattr(
        "app.routers.documents.chunk_text", lambda text: ["chunk one", "chunk two"]
    )
    monkeypatch.setattr(
        "app.routers.documents.embed_texts", lambda chunks: [[0.1], [0.2]]
    )
    monkeypatch.setattr("app.routers.documents.format_vector", lambda v: "[0.1]")

    result = await doc_router.upload_document(_FakeUploadFile(), USER)

    assert result.id == "doc-1"
    assert result.status == "indexed"
    assert result.chunks == 2

    # Document row inserted (processing) then updated (indexed).
    inserts = [o for o in sb.ops if o[0] == "insert"]
    assert any(t == "documents" for _, t, _ in inserts)

    # Storage upload happened under /{user}/{doc}.pdf
    uploads = [o for o in sb.ops if o[0] == "storage_upload"]
    assert uploads, "expected a storage upload"
    assert uploads[0][1]["path"] == "user-1/doc-1.pdf"

    # Chunks were inserted into document_chunks.
    chunk_inserts = [o for o in sb.ops if o[0] == "insert" and o[1] == "document_chunks"]
    assert chunk_inserts and len(chunk_inserts[0][2]) == 2


async def test_upload_document_empty_chunks_indexes_zero(sb, monkeypatch):
    monkeypatch.setattr("app.routers.documents.uuid.uuid4", lambda: "doc-2")
    monkeypatch.setattr(
        "app.routers.documents.extract_text", lambda content, name: ""
    )
    monkeypatch.setattr("app.routers.documents.chunk_text", lambda text: [])

    result = await doc_router.upload_document(_FakeUploadFile(), USER)

    assert result.id == "doc-2"
    assert result.status == "indexed"
    assert result.chunks == 0


async def test_upload_document_storage_failure_returns_500(sb, monkeypatch):
    monkeypatch.setattr("app.routers.documents.uuid.uuid4", lambda: "doc-x")
    monkeypatch.setattr(
        "app.routers.documents.extract_text", lambda content, name: "some text"
    )

    class _BrokenBucket:
        def upload(self, **kwargs):
            raise RuntimeError("bucket down")

        def remove(self, paths):
            return self

    class _BrokenStorage:
        def from_(self, bucket):
            return _BrokenBucket()

    sb.storage = _BrokenStorage()

    with pytest.raises(HTTPException) as exc:
        await doc_router.upload_document(_FakeUploadFile(), USER)
    assert exc.value.status_code == 500
    assert "Storage upload failed" in exc.value.detail


async def test_upload_document_bad_format_returns_400(sb, monkeypatch):
    monkeypatch.setattr("app.routers.documents.uuid.uuid4", lambda: "doc-y")

    from app.text_extraction import UnsupportedFormatError

    def boom(content, name):
        raise UnsupportedFormatError("Unsupported file type: x.xyz")

    monkeypatch.setattr("app.routers.documents.extract_text", boom)

    class _BadFile:
        filename = "x.xyz"
        content_type = "text/plain"

        async def read(self):
            return b"data"

    with pytest.raises(HTTPException) as exc:
        await doc_router.upload_document(_BadFile(), USER)
    assert exc.value.status_code == 400


async def test_upload_document_embedding_failure_returns_502(sb, monkeypatch):
    monkeypatch.setattr("app.routers.documents.uuid.uuid4", lambda: "doc-z")
    monkeypatch.setattr(
        "app.routers.documents.extract_text", lambda content, name: "text"
    )
    monkeypatch.setattr(
        "app.routers.documents.chunk_text", lambda text: ["chunk"]
    )
    monkeypatch.setattr(
        "app.routers.documents.embed_texts", lambda chunks: (_ for _ in ()).throw(RuntimeError("embed down"))
    )

    with pytest.raises(HTTPException) as exc:
        await doc_router.upload_document(_FakeUploadFile(), USER)
    assert exc.value.status_code == 502
    assert "Embedding failed" in exc.value.detail


async def test_upload_document_rejects_text_over_the_prompt_budget(sb, monkeypatch):
    """The gate must match what the baseline rebuilds, not just the raw text."""
    monkeypatch.setattr(
        "app.routers.documents.extract_text", lambda content, name: "x" * 24000
    )

    with pytest.raises(HTTPException) as exc:
        await doc_router.upload_document(_FakeUploadFile(), USER)

    assert exc.value.status_code == 422
    assert "full-doc baseline" in exc.value.detail
    # Nothing was persisted for a document the comparison could never run.
    assert sb.ops == []


# ---- list_documents ----------------------------------------------------------

def test_list_documents_maps_rows(sb, monkeypatch):
    from datetime import datetime, timezone

    docs = [
        {
            "id": "d1",
            "filename": "a.pdf",
            "status": "indexed",
            "chunks": 3,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "storage_path": "user-1/d1.pdf",
        }
    ]
    sb.set_rows("documents", docs)

    result = doc_router.list_documents(USER)

    assert result.total == 1
    assert result.documents[0].filename == "a.pdf"
    assert result.documents[0].status == "indexed"
    assert result.documents[0].chunks == 3
    assert result.documents[0].storage_path == "user-1/d1.pdf"
    assert result.documents[0].model_dump(by_alias=True)["storagePath"] == "user-1/d1.pdf"


def test_list_documents_empty(sb, monkeypatch):
    sb.set_rows("documents", [])
    result = doc_router.list_documents(USER)
    assert result.total == 0
    assert result.documents == []


# ---- delete_document ---------------------------------------------------------

def test_delete_document_removes_chunks_storage_and_row(sb, monkeypatch):
    sb.set_rows(
        "documents",
        [{"id": "d1", "storage_path": "user-1/d1.pdf", "user_id": "user-1"}],
    )

    doc_router.delete_document("d1", USER)

    dels = [o for o in sb.ops if o[0] == "delete"]
    assert dels, "expected delete operations"
    removes = [o for o in sb.ops if o[0] == "storage_remove"]
    assert removes and removes[0][1] == ["user-1/d1.pdf"]


def test_delete_document_not_found_404(sb, monkeypatch):
    sb.set_rows("documents", [])
    with pytest.raises(HTTPException) as exc:
        doc_router.delete_document("missing", USER)
    assert exc.value.status_code == 404


def test_delete_document_storage_failure_logs_and_continues(sb, monkeypatch, caplog):
    import logging

    sb.set_rows(
        "documents",
        [{"id": "d1", "storage_path": "user-1/d1.pdf", "user_id": "user-1"}],
    )

    class _BrokenBucket:
        def upload(self, **kwargs):
            return self

        def remove(self, paths):
            raise RuntimeError("bucket down")

    class _BrokenStorage:
        def from_(self, bucket):
            return _BrokenBucket()

    sb.storage = _BrokenStorage()

    with caplog.at_level(logging.WARNING, logger="app.routers.documents"):
        doc_router.delete_document("d1", USER)

    # Deletion still proceeded (document row deleted) and the failure was logged.
    dels = [o for o in sb.ops if o[0] == "delete"]
    assert any(t == "documents" for _, t in dels)
    assert any("Failed to remove storage object" in r.message for r in caplog.records)
