from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
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
from schemas import AskRequest, AskResponse, DocRequest, DocResponse
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


# ── Document file upload ─────────────────────────────────────────────

ALLOWED_EXTENSIONS = {"pdf", "txt", "md", "docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@app.post("/api/upload", response_model=DocResponse, status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    title: str = Form(""),
):
    ext = file.filename.rsplit(".", 1)[-1].lower() if "." in (file.filename or "") else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(422, f"Unsupported file type .{ext}. Allowed: {', '.join(ALLOWED_EXTENSIONS)}")

    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        raise HTTPException(422, "File exceeds 10 MB limit")

    # validate non-empty using flat text check
    if not extract_text(data, file.filename).strip():
        raise HTTPException(422, "Could not extract text from file")

    chunks = extract_structured_chunks(data, file.filename)
    doc_title = title.strip() or file.filename.rsplit(".", 1)[0].replace("_", " ").title()
    entry = save_document(title=doc_title, chunks=chunks, filename=file.filename)
    return DocResponse(**entry)


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
    return JSONResponse(
        status_code=500,
        content={
            "answer": "An unexpected error occurred. Please try again.",
            "intent": "clarify",
            "action_taken": None,
            "action_result": None,
            "sources": [],
        },
    )
