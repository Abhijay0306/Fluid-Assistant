import json
import os
from typing import Optional

from openai import OpenAI

import rag
from rules import build_action_rules_prompt, build_knowledge_prompt, enforce_action_rules
from schemas import Source
from tools import TOOL_SCHEMA, create_ticket

_client: Optional[OpenAI] = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("DEEPSEEK_API_KEY")
        if not api_key:
            raise RuntimeError("DEEPSEEK_API_KEY environment variable not set")
        _client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    return _client


def run_agent(question: str, rules: dict) -> dict:
    """
    Retrieve-then-generate flow:
    1. Retrieve relevant doc chunks from the document store.
    2. Build a system prompt from rules (authoritative) + retrieved chunks (supplementary).
    3. Call the LLM with the create_ticket tool available.
    4. Route by response: tool call → action path, text → knowledge path.
    """
    chunks = rag.retrieve(question)
    system_prompt = _build_system_prompt(rules, chunks)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    client = _get_client()

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            tools=[TOOL_SCHEMA],
            tool_choice="auto",
        )
    except Exception as e:
        return _clarify(f"LLM call failed: {e}")

    message = response.choices[0].message

    # ── Action path ────────────────────────────────────────────────────────
    if message.tool_calls:
        tool_call = message.tool_calls[0]
        if tool_call.function.name != "create_ticket":
            return _clarify(f"Unexpected tool call: {tool_call.function.name}")

        try:
            args = json.loads(tool_call.function.arguments)
        except json.JSONDecodeError:
            return _clarify("Malformed tool arguments from LLM")

        violations = enforce_action_rules(args, rules)
        if violations:
            return _clarify("Action rule violation: " + "; ".join(violations))

        result = create_ticket(
            summary=args["summary"],
            category=args["category"],
            priority=args["priority"],
        )

        messages.append(message.model_dump(exclude_unset=True))
        messages.append({
            "role": "tool",
            "tool_call_id": tool_call.id,
            "content": json.dumps(result),
        })

        try:
            followup = client.chat.completions.create(
                model="deepseek-chat",
                messages=messages,
            )
            answer = followup.choices[0].message.content or "Ticket created."
        except Exception:
            answer = (
                f"Ticket {result['ticket_id']} created "
                f"({result['category']}, {result['priority']} priority)."
            )

        return {
            "answer": answer,
            "intent": "action",
            "action_taken": "create_ticket",
            "action_result": result,
            "sources": [],          # action responses don't cite knowledge chunks
        }

    # ── Knowledge / clarify path ───────────────────────────────────────────
    content = message.content or ""
    if not content.strip():
        return _clarify("No response from LLM")

    sources = [
        Source(text=c["text"], origin=c["origin"], filename=c["filename"])
        for c in chunks
    ]

    return {
        "answer": content,
        "intent": "knowledge",
        "action_taken": None,
        "action_result": None,
        "sources": [s.model_dump() for s in sources],
    }


# ── Prompt construction ────────────────────────────────────────────────────

def _build_system_prompt(rules: dict, chunks: list[dict]) -> str:
    knowledge_section = build_knowledge_prompt(rules)
    action_section = build_action_rules_prompt(rules)
    retrieval_section = _format_chunks(chunks)

    return f"""You are an internal helpdesk assistant for doddle2dollars. Your job is to either:
1. Answer policy/information questions based on the knowledge provided.
2. Create a support ticket when the user needs hands-on help or action.

{knowledge_section}

{retrieval_section}

{action_section}

INSTRUCTIONS:
- Rules above are authoritative. Retrieved documents are supplementary — if they conflict with a rule, the rule wins.
- If the user is asking for information, answer from the knowledge base and retrieved documents.
- If the user has a problem that requires someone to act, call create_ticket.
- If the request is too vague to answer or act on, ask for clarification.
- Never invent policy not in the knowledge base or retrieved documents.
- Do not call create_ticket for pure information questions.
"""


def _format_chunks(chunks: list[dict]) -> str:
    if not chunks:
        return "RETRIEVED DOCUMENTS:\n(no relevant documents found)"

    parts = []
    for c in chunks:
        tag = f"[{c['origin'].upper()} — {c['filename']}]"
        parts.append(f"{tag}\n{c['text']}")

    return "RETRIEVED DOCUMENTS (supplementary, use to ground your answer):\n\n" + "\n\n---\n\n".join(parts)


# ── Helpers ────────────────────────────────────────────────────────────────

def _clarify(message: str) -> dict:
    return {
        "answer": message,
        "intent": "clarify",
        "action_taken": None,
        "action_result": None,
        "sources": [],
    }
