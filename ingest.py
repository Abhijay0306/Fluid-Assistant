"""
Document ingestion: parse uploaded files, store metadata in Supabase,
embed chunks via rag.py.
Supports: .txt, .md, .pdf, .docx
"""
from __future__ import annotations

import io
import re
import uuid

import rag
from supabase_client import get_supabase


# ── Public API ──────────────────────────────────────────────────────

def save_document(title: str, content: str, origin: str = "uploaded", filename: str = "") -> dict:
    """Store document + embed its chunks. Returns the documents row."""
    sb = get_supabase()
    doc_id = str(uuid.uuid4())
    safe_filename = filename or _slugify(title) + ".txt"

    row = {"id": doc_id, "title": title, "filename": safe_filename, "origin": origin}
    sb.table("documents").insert(row).execute()

    rag.ingest_document(doc_id, content, origin, safe_filename)
    return row


def list_documents() -> list[dict]:
    sb = get_supabase()
    result = sb.table("documents").select("id,title,filename,origin,created_at").order("created_at").execute()
    return result.data or []


def delete_document(doc_id: str) -> bool:
    sb = get_supabase()
    sb.table("documents").delete().eq("id", doc_id).execute()
    return True


# ── File parsing ────────────────────────────────────────────────────

def extract_text(file_bytes: bytes, filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"

    if ext in ("txt", "md"):
        return file_bytes.decode("utf-8", errors="replace")

    if ext == "pdf":
        return _parse_pdf(file_bytes)

    if ext == "docx":
        return _parse_docx(file_bytes)

    return file_bytes.decode("utf-8", errors="replace")


def _parse_pdf(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _parse_docx(data: bytes) -> str:
    from docx import Document
    doc = Document(io.BytesIO(data))
    return "\n\n".join(p.text.strip() for p in doc.paragraphs if p.text.strip())


# ── Helpers ─────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]
