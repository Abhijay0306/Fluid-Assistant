"""
RAG layer: OpenRouter embeddings (text-embedding-3-small, 1536-dim)
+ Supabase pgvector similarity search.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
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


@lru_cache(maxsize=512)
def _embed_single_cached(text: str) -> tuple:
    """Cached single-text embedding — avoids re-calling the API for repeated queries."""
    return tuple(embed([text])[0])


def retrieve(query: str, top_k: int = TOP_K) -> list[dict]:
    """Embed query (cached) and return top-k chunks sorted newest-first so the LLM
    sees the most recent upload first when policies conflict."""
    query_embedding = list(_embed_single_cached(query))
    sb = get_supabase()
    result = sb.rpc(
        "match_chunks",
        {"query_embedding": query_embedding, "match_count": top_k, "min_similarity": 0.1},
    ).execute()
    rows = result.data or []

    chunks = [
        {
            "text": r["chunk_text"],
            "origin": r["origin"],
            "filename": r["filename"],
            "page_number": r.get("page_number"),
            "section": r.get("section"),
            "doc_created_at": r.get("doc_created_at"),
        }
        for r in rows
    ]

    # Newest document first — when two chunks conflict the LLM sees the
    # more recent one earlier and the system prompt tells it to prefer it.
    chunks.sort(key=lambda c: c.get("doc_created_at") or "", reverse=True)
    return chunks


def ingest_document(document_id: str, chunks: list[dict], origin: str, filename: str) -> int:
    """Embed pre-chunked [{text, page_number, section}] dicts and store in document_chunks."""
    if not chunks:
        return 0

    texts = [c["text"] for c in chunks]
    embeddings = embed(texts)
    sb = get_supabase()

    rows = [
        {
            "document_id": document_id,
            "chunk_index": i,
            "chunk_text": c["text"],
            "embedding": emb,
            "origin": origin,
            "filename": filename,
            "page_number": c.get("page_number"),
            "section": c.get("section"),
        }
        for i, (c, emb) in enumerate(zip(chunks, embeddings))
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
