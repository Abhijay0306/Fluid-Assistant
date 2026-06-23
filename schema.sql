-- Run this once in your Supabase SQL editor
-- Dashboard → SQL Editor → New query → paste → Run

-- 1. Enable pgvector
create extension if not exists vector;

-- 2. Tickets
create table if not exists tickets (
  id          bigserial primary key,
  ticket_id   text        unique not null,
  status      text        not null default 'open',
  summary     text        not null,
  category    text        not null,
  priority    text        not null,
  created_at  timestamptz not null default now()
);

-- 3. Documents (one row per file / pasted doc)
create table if not exists documents (
  id          uuid        primary key default gen_random_uuid(),
  title       text        not null,
  filename    text        not null,
  origin      text        not null default 'uploaded', -- 'seeded' | 'uploaded'
  created_at  timestamptz not null default now()
);

-- 4. Chunks + embeddings  (text-embedding-3-small → 1536 dims)
create table if not exists document_chunks (
  id           uuid    primary key default gen_random_uuid(),
  document_id  uuid    not null references documents(id) on delete cascade,
  chunk_index  int     not null,
  chunk_text   text    not null,
  embedding    vector(1536),
  origin       text    not null,
  filename     text    not null,
  page_number  int,        -- null for non-PDF / pasted text
  section      text        -- nearest heading above this chunk
);

-- HNSW index (works with small datasets; no minimum row count)
create index if not exists idx_chunks_hnsw
  on document_chunks using hnsw (embedding vector_cosine_ops);

-- 5. Similarity-search function used by rag.py
drop function if exists match_chunks(vector, integer, double precision);
create function match_chunks(
  query_embedding vector(1536),
  match_count     int   default 4,
  min_similarity  float default 0.25
)
returns table (
  id              uuid,
  chunk_text      text,
  origin          text,
  filename        text,
  page_number     int,
  section         text,
  doc_created_at  timestamptz,
  similarity      float
)
language plpgsql
as $$
begin
  return query
  select
    dc.id,
    dc.chunk_text,
    dc.origin,
    dc.filename,
    dc.page_number,
    dc.section,
    d.created_at as doc_created_at,
    1 - (dc.embedding <=> query_embedding) as similarity
  from document_chunks dc
  join documents d on d.id = dc.document_id
  where dc.embedding is not null
    and (1 - (dc.embedding <=> query_embedding)) > min_similarity
  order by dc.embedding <=> query_embedding
  limit match_count;
end;
$$;

-- ── Migration (run if table already existed) ────────────────────────
-- alter table document_chunks add column if not exists page_number int;
-- alter table document_chunks add column if not exists section text;
