from supabase_client import get_supabase


def _next_ticket_id() -> str:
    sb = get_supabase()
    result = sb.table("tickets").select("id").order("id", desc=True).limit(1).execute()
    last = result.data[0]["id"] if result.data else 0
    return f"TKT-{last + 1:04d}"


def create_ticket(summary: str, category: str, priority: str) -> dict:
    sb = get_supabase()
    ticket_id = _next_ticket_id()
    row = {
        "ticket_id": ticket_id,
        "status": "open",
        "summary": summary,
        "category": category,
        "priority": priority,
    }
    sb.table("tickets").insert(row).execute()
    return row


def list_tickets() -> list[dict]:
    sb = get_supabase()
    result = (
        sb.table("tickets")
        .select("ticket_id,status,summary,category,priority,created_at")
        .order("created_at", desc=True)
        .execute()
    )
    return result.data or []


TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "create_ticket",
        "description": (
            "Create a support ticket when the user needs IT, HR, Facilities, or other help "
            "that requires action. Use only when the user clearly needs something done, "
            "not just information."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "summary": {
                    "type": "string",
                    "description": "One-sentence description of the issue.",
                },
                "category": {
                    "type": "string",
                    "description": "Ticket category: IT, HR, Facilities, or Other.",
                },
                "priority": {
                    "type": "string",
                    "description": (
                        "Ticket priority: low, medium, or high. "
                        "Set high only when there is a real urgency signal "
                        "(imminent deadline, outage, or blocked work)."
                    ),
                },
            },
            "required": ["summary", "category", "priority"],
        },
    },
}
