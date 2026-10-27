"""Extract plain text from uploaded files (PDF, TXT, MD, JSON, CSV)."""

from __future__ import annotations

import csv
import io
import json

from pypdf import PdfReader


class UnsupportedFormatError(ValueError):
    pass


def extract_text(content: bytes, filename: str) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        return _extract_pdf(content)
    if name.endswith((".md", ".txt")):
        return content.decode("utf-8", errors="replace")
    if name.endswith(".json"):
        return _extract_json(content)
    if name.endswith(".csv"):
        return _extract_csv(content)
    raise UnsupportedFormatError(f"Unsupported file type: {filename}")


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    pages = []
    for page in reader.pages:
        pages.append(page.extract_text() or "")
    return "\n\n".join(pages)


def _extract_json(content: bytes) -> str:
    try:
        data = json.loads(content)
        return json.dumps(data, ensure_ascii=False, indent=2)
    except json.JSONDecodeError:
        return content.decode("utf-8", errors="replace")


def _extract_csv(content: bytes) -> str:
    text = content.decode("utf-8", errors="replace")
    try:
        rows = list(csv.reader(io.StringIO(text)))
        return "\n".join(" | ".join(row) for row in rows)
    except Exception:
        return text
