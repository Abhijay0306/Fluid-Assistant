"""
RAG layer: OpenRouter embeddings (text-embedding-3-small, 1536-dim)
+ Supabase pgvector similarity search.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from openai import OpenAI

from supabase_client import get_supabase

CHUNK_SIZE = 400
CHUNK_OVERLAP = 80
TOP_K = 4
EMBED_MODEL = "openai/text-embedding-3-small"

_embed_client: Optional[OpenAI] = None


def _get_embed_client() -> OpenAI:
    global _embed_client
    if _embed_client is None:
        key = os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY environment variable not set")
        _embed_client = OpenAI(
            api_key=key,
            base_url="https://openrouter.ai/api/v1",
        )
    return _embed_client


# ── Public interface ────────────────────────────────────────────────

def embed(texts: list[str]) -> list[list[float]]:
    """Return embeddings for a list of texts via OpenRouter."""
    client = _get_embed_client()
    response = client.embeddings.create(model=EMBED_MODEL, input=texts)
    return [e.embedding for e in response.data]


def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """Embed query and return top-k similar chunks from Supabase."""
    query_embedding = embed([query])[0]
    sb = get_supabase()
    result = sb.rpc(
        "match_chunks",
        {"query_embedding": query_embedding, "match_count": top_k},
    ).execute()
    rows = result.data or []
    return [
        {"text": r["chunk_text"], "origin": r["origin"], "filename": r["filename"]}
        for r in rows
    ]


def ingest_document(document_id: str, text: str, origin: str, filename: str) -> int:
    """Chunk text, embed all chunks, and store in document_chunks. Returns chunk count."""
    chunks = chunk_text(text)
    if not chunks:
        return 0

    embeddings = embed(chunks)
    sb = get_supabase()

    rows = [
        {
            "document_id": document_id,
            "chunk_index": i,
            "chunk_text": chunk,
            "embedding": emb,
            "origin": origin,
            "filename": filename,
        }
        for i, (chunk, emb) in enumerate(zip(chunks, embeddings))
    ]
    sb.table("document_chunks").insert(rows).execute()
    return len(rows)


# ── Chunking helpers ────────────────────────────────────────────────

def chunk_text(text: str) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n{2,}", text) if p.strip()]
    chunks: list[str] = []
    current = ""

    for para in paragraphs:
        if len(current) + len(para) + 2 <= CHUNK_SIZE:
            current = (current + "\n\n" + para).strip()
        else:
            if current:
                chunks.append(current)
            if len(para) > CHUNK_SIZE:
                for piece in _hard_split(para):
                    chunks.append(piece)
                current = chunks[-1][-CHUNK_OVERLAP:] if chunks else ""
            else:
                current = para

    if current:
        chunks.append(current)

    return chunks


def _hard_split(text: str) -> list[str]:
    pieces = []
    start = 0
    while start < len(text):
        pieces.append(text[start : start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return pieces
