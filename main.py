import base64
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from agent import run_agent
from ingest import (
    delete_document,
    extract_structured_chunks,
    extract_text,
    list_documents,
    save_document,
    text_to_chunks,
)
from rules import load_rules
from schemas import AskRequest, AskResponse, DocRequest, DocResponse, UploadB64Request
from tools import list_tickets

app = FastAPI(
    title="doddle2dollars Helpdesk Assistant",
    version="2.0.0",
    docs_url="/swagger",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)


# ── Ask ─────────────────────────────────────────────────────────────

@app.post("/api/ask", response_model=AskResponse)
def ask(request: AskRequest) -> AskResponse:
    rules = load_rules()
    result = run_agent(request.question, rules)
    return AskResponse(**result)


# ── Documents (text paste) ───────────────────────────────────────────

@app.post("/api/docs", response_model=DocResponse, status_code=201)
def add_doc(request: DocRequest) -> DocResponse:
    chunks = text_to_chunks(request.content)
    entry = save_document(title=request.title, chunks=chunks)
    return DocResponse(**entry)


@app.get("/api/docs", response_model=list[DocResponse])
def list_docs() -> list[DocResponse]:
    return [DocResponse(**d) for d in list_documents()]


@app.delete("/api/docs/{doc_id}", status_code=204)
def delete_doc(doc_id: str):
    delete_document(doc_id)


# ── Document file upload (base64 JSON — works on Vercel serverless) ──

ALLOWED_EXTENSIONS = {"pdf", "txt", "md", "docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@app.post("/api/upload", response_model=DocResponse, status_code=201)
def upload_file(request: UploadB64Request) -> DocResponse:
    ext = request.filename.rsplit(".", 1)[-1].lower() if "." in request.filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(422, f"Unsupported file type .{ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    try:
        data = base64.b64decode(request.content_b64)
    except Exception:
        raise HTTPException(422, "Invalid base64 content")

    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(422, "File exceeds 10 MB limit")

    if not extract_text(data, request.filename).strip():
        raise HTTPException(422, "Could not extract text from file")

    chunks = extract_structured_chunks(data, request.filename)
    doc_title = request.title.strip() or request.filename.rsplit(".", 1)[0].replace("_", " ").title()
    entry = save_document(title=doc_title, chunks=chunks, filename=request.filename)
    return DocResponse(**entry)


# ── Debug: test retrieval for a query ────────────────────────────────

@app.get("/api/search")
def search(q: str, top_k: int = 6, min_sim: float = 0.0):
    """Debug endpoint: shows what chunks would be retrieved for a query."""
    from supabase_client import get_supabase
    from rag import embed
    query_embedding = embed([q])[0]
    sb = get_supabase()
    result = sb.rpc(
        "match_chunks",
        {"query_embedding": query_embedding, "match_count": top_k, "min_similarity": min_sim},
    ).execute()
    rows = result.data or []
    return [
        {
            "filename": r.get("filename"),
            "section": r.get("section"),
            "page": r.get("page_number"),
            "similarity": round(r.get("similarity", 0), 4),
            "text": r.get("chunk_text", "")[:200],
        }
        for r in rows
    ]


# ── Tickets ──────────────────────────────────────────────────────────

@app.get("/api/tickets")
def get_tickets():
    return list_tickets()


# ── Knowledge base (rules.yaml) ──────────────────────────────────────

@app.get("/api/rules")
def get_rules():
    return load_rules()


# ── Error handler ────────────────────────────────────────────────────

@app.exception_handler(Exception)
async def generic_exception_handler(request, exc):
    import traceback
    return JSONResponse(
        status_code=500,
        content={
            "detail": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(),
            "answer": "An unexpected error occurred. Please try again.",
            "intent": "clarify",
            "action_taken": None,
            "action_result": None,
            "sources": [],
        },
    )
