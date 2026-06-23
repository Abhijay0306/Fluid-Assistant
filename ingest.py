"""
Document ingestion: parse files into structured chunks with page/section metadata,
auto-replace existing docs with same name, store in Supabase, embed via rag.py.
Supports: .txt, .md, .pdf, .docx
"""
from __future__ import annotations

import io
import re
import uuid

import rag
from supabase_client import get_supabase


# ── Public API ──────────────────────────────────────────────────────

def save_document(
    title: str,
    chunks: list[dict],
    origin: str = "uploaded",
    filename: str = "",
) -> dict:
    """
    If a document with the same filename (uploads) or title (pastes) already exists,
    delete it first so its chunks are replaced rather than accumulated.
    chunks: list of {text, page_number, section}
    """
    sb = get_supabase()
    safe_filename = filename or _slugify(title) + ".txt"

    lookup_field = "filename" if filename else "title"
    lookup_value = safe_filename if filename else title
    existing = sb.table("documents").select("id").eq(lookup_field, lookup_value).execute()
    for row in (existing.data or []):
        sb.table("documents").delete().eq("id", row["id"]).execute()

    doc_id = str(uuid.uuid4())
    row = {"id": doc_id, "title": title, "filename": safe_filename, "origin": origin}
    sb.table("documents").insert(row).execute()

    rag.ingest_document(doc_id, chunks, origin, safe_filename)
    return row


def list_documents() -> list[dict]:
    sb = get_supabase()
    result = (
        sb.table("documents")
        .select("id,title,filename,origin,created_at")
        .order("created_at")
        .execute()
    )
    return result.data or []


def delete_document(doc_id: str) -> bool:
    sb = get_supabase()
    sb.table("documents").delete().eq("id", doc_id).execute()
    return True


# ── File parsing → structured chunks ────────────────────────────────

def extract_structured_chunks(file_bytes: bytes, filename: str) -> list[dict]:
    """Parse a file and return [{text, page_number, section}, ...]."""
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "txt"
    if ext == "pdf":
        return _pdf_to_chunks(file_bytes)
    if ext == "docx":
        return _docx_to_chunks(file_bytes)
    return text_to_chunks(file_bytes.decode("utf-8", errors="replace"))


def extract_text(file_bytes: bytes, filename: str) -> str:
    """Flat text extraction kept for validation use (strip + non-empty check)."""
    return " ".join(c["text"] for c in extract_structured_chunks(file_bytes, filename))


def text_to_chunks(text: str) -> list[dict]:
    """Split plain/markdown text into chunks; detect # headings as section names."""
    lines = text.split("\n")
    current_section: str | None = None
    current_lines: list[str] = []
    result: list[dict] = []

    def _flush():
        block = "\n".join(current_lines).strip()
        if block:
            for chunk in rag.chunk_text(block):
                result.append({"text": chunk, "page_number": None, "section": current_section})
        current_lines.clear()

    for line in lines:
        if re.match(r"^#{1,6}\s+", line):
            _flush()
            current_section = re.sub(r"^#{1,6}\s+", "", line).strip()
        else:
            current_lines.append(line)
    _flush()
    return result


# ── PDF extraction ───────────────────────────────────────────────────

def _pdf_to_chunks(data: bytes) -> list[dict]:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    result: list[dict] = []
    for page_num, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            continue
        section = _detect_pdf_section(page_text)
        for chunk in rag.chunk_text(page_text):
            result.append({"text": chunk, "page_number": page_num, "section": section})
    return result


def _detect_pdf_section(page_text: str) -> str | None:
    """First short line (≤80 chars) that looks like a heading."""
    for line in page_text.splitlines():
        line = line.strip()
        if line and len(line) <= 80 and (
            line.istitle() or line.isupper() or re.match(r"^\d+[\.\)]\s+\w", line)
        ):
            return line
    return None


# ── DOCX extraction ──────────────────────────────────────────────────

def _docx_to_chunks(data: bytes) -> list[dict]:
    from docx import Document
    doc = Document(io.BytesIO(data))
    result: list[dict] = []
    current_section: str | None = None
    current_paras: list[str] = []

    def _flush():
        block = "\n".join(current_paras).strip()
        if block:
            for chunk in rag.chunk_text(block):
                result.append({"text": chunk, "page_number": None, "section": current_section})
        current_paras.clear()

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        if para.style.name.startswith("Heading"):
            _flush()
            current_section = text
        else:
            current_paras.append(text)
    _flush()
    return result


# ── Helpers ─────────────────────────────────────────────────────────

def _slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:60]
