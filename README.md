# doddle2dollars Internal Helpdesk Assistant — V2

A FastAPI-based internal helpdesk that answers policy questions and raises support tickets. V2 adds a writable document store with BM25 retrieval (RAG) so answers are grounded in company documents and sources are cited.

## Setup

```bash
pip install -r requirements.txt
export DEEPSEEK_API_KEY=your_key_here   # Windows: set DEEPSEEK_API_KEY=your_key_here
```

## Run

```bash
uvicorn main:app --reload
```

API at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

---

## curl examples

### POST /ask — normal business query

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "How many casual leaves do I get per year?"}' | python -m json.tool
```

Expected:
```json
{
  "answer": "You get 12 casual leaves per year.",
  "intent": "knowledge",
  "action_taken": null,
  "action_result": null,
  "sources": [
    {"text": "...", "origin": "seeded", "filename": "leave_policy.txt"}
  ]
}
```

### POST /ask — challenging query (implicit action + urgency)

```bash
curl -s -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "My laptop won'\''t turn on and I have a demo in an hour."}' | python -m json.tool
```

Expected:
```json
{
  "answer": "I've raised a high-priority IT ticket for you. Someone will be in touch shortly.",
  "intent": "action",
  "action_taken": "create_ticket",
  "action_result": {
    "ticket_id": "TKT-0001",
    "status": "open",
    "summary": "Laptop won't turn on; demo in one hour.",
    "category": "IT",
    "priority": "high"
  },
  "sources": []
}
```

The assistant infers action intent without any explicit keyword, classifies it as IT, and sets priority `high` from the urgency signal — governed by `rules.yaml`, not hardcoded logic.

### POST /docs — upload a document

```bash
curl -s -X POST http://localhost:8000/docs \
  -H "Content-Type: application/json" \
  -d '{"title": "Parental Leave Policy", "content": "Primary caregivers receive 6 months paid parental leave. Secondary caregivers receive 4 weeks paid parental leave."}' | python -m json.tool
```

### GET /docs — list all documents

```bash
curl -s http://localhost:8000/docs | python -m json.tool
```

Returns all seeded and uploaded documents with their id, title, filename, and origin.

---

## V2 improvement explanation

**V1 limitation:** V1 can only answer from the small `rules.yaml` file, which is loaded whole into every prompt. It does not scale past a screen of policy, it burns tokens on every call regardless of what the user asked, and there is no way for a user to add knowledge without editing the source file directly.

**V2 adds three things:**

1. **`POST /docs` endpoint** — users can add knowledge as typed text, persisted as plain files in `docs/uploaded/`. A few seeded docs ship in `docs/seeded/` so retrieval works out of the box.

2. **Retrieval before generation** — on every `/ask` request, `rag.py` reads the whole `docs/` tree, chunks it, scores chunks against the question using BM25 (`rank-bm25`), and injects only the top-k relevant chunks into the prompt. The knowledge base can grow without bloating the prompt.

3. **Cited sources** — every knowledge answer returns the chunks it used in the `sources` field, tagged by origin (`seeded` or `uploaded`) and filename, so any answer can be traced back to a document.

**What did not change:** `rules.yaml` is still loaded whole on every request and is authoritative. Retrieved documents are supplementary only — if an uploaded document contradicts a rule, the rule wins. Tool calling still drives ticket creation and is enforced entirely in application code.

---

## File layout

```
main.py              FastAPI app — /ask, POST /docs, GET /docs
agent.py             Retrieve-then-generate flow, intent routing
rules.py             Load rules.yaml, build prompt sections, enforce guardrails
rag.py               BM25 chunking, indexing, and retrieval        [V2]
ingest.py            Save uploaded docs to disk, trigger reindex   [V2]
tools.py             create_ticket and JSON-backed mock ticket store
schemas.py           Pydantic request and response models
rules.yaml           Editable source of truth for all policy
docs/seeded/         Company docs shipped with the app             [V2]
docs/uploaded/       User-added docs, persisted across restarts    [V2]
tickets.json         Auto-created; persists tickets across restarts
```
