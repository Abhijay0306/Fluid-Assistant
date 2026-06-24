"""
On document upload: call DeepSeek to extract structured policy facts,
then upsert them into the knowledge_entries Supabase table.

Rules.yaml stays as the static base; Supabase entries overlay/replace it.
Deleting a document cascades-deletes the entries it last owned.
"""
from __future__ import annotations

import json
import os

from openai import OpenAI
from supabase_client import get_supabase


def sync(text: str, document_id: str, filename: str) -> dict:
    """Extract knowledge from document text and upsert into knowledge_entries."""
    knowledge = _extract(text, filename)
    if not knowledge:
        return {}

    sb = get_supabase()
    for key, value in knowledge.items():
        sb.table("knowledge_entries").upsert(
            {
                "key": key,
                "value": str(value),
                "source_doc": filename,
                "document_id": document_id,
            },
            on_conflict="key",
        ).execute()

    return knowledge


def _extract(text: str, filename: str) -> dict:
    """Ask DeepSeek to return structured JSON knowledge from the document."""
    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )

    prompt = f"""You are updating a company FAQ knowledge base from a policy document.

The existing knowledge base sections are: leave, expenses, it.
- If this document updates one of those sections, use the SAME key (leave / expenses / it).
- For brand-new topics, use a snake_case key (e.g. remote_work, travel_allowance).
- If a policy is explicitly cancelled or removed, set its value to the string "__REMOVED__".

Extraction rules:
- Values must be concise plain-text summaries of the policy facts (no bullet markdown).
- Include specific numbers, limits, dates, and eligibility rules.
- Omit procedural steps (how to submit, who to email) — FAQs only.

Return ONLY a valid JSON object. No markdown fences, no explanation.

Document: {filename}
---
{text[:9000]}"""

    resp = client.chat.completions.create(
        model="deepseek-chat",
        messages=[{"role": "user", "content": prompt}],
    )

    raw = resp.choices[0].message.content.strip()
    # Strip accidental markdown code fences
    if "```" in raw:
        parts = raw.split("```")
        raw = parts[1] if len(parts) > 1 else parts[0]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw.strip())
    except json.JSONDecodeError:
        return {}
