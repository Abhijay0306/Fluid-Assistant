from pathlib import Path

import yaml

RULES_PATH = Path(__file__).parent / "rules.yaml"


def load_rules() -> dict:
    """Return merged rules: static yaml base overlaid with Supabase dynamic entries."""
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        rules = yaml.safe_load(f) or {}

    dynamic = _load_dynamic_knowledge()
    if dynamic:
        knowledge = rules.setdefault("knowledge", {})
        for key, value in dynamic.items():
            if value == "__REMOVED__":
                knowledge.pop(key, None)
            else:
                knowledge[key] = value

    return rules


def _load_dynamic_knowledge() -> dict:
    try:
        from supabase_client import get_supabase
        sb = get_supabase()
        result = sb.table("knowledge_entries").select("key,value").execute()
        return {r["key"]: r["value"] for r in (result.data or [])}
    except Exception:
        return {}


def build_knowledge_prompt(rules: dict) -> str:
    knowledge = rules.get("knowledge", {})
    sections = "\n\n".join(
        f"[{key.upper()}]\n{_fmt(val)}" for key, val in knowledge.items()
    )
    return f"COMPANY POLICY KNOWLEDGE BASE (FAQ):\n{sections}"


def build_action_rules_prompt(rules: dict) -> str:
    ar = rules.get("action_rules", {})
    categories = ", ".join(ar.get("categories", []))
    priorities = ", ".join(ar.get("priorities", []))
    policies = "\n".join(f"- {p}" for p in ar.get("policies", []))
    return (
        f"TICKET ACTION RULES:\n"
        f"Valid categories: {categories}\n"
        f"Valid priorities: {priorities}\n"
        f"Policies:\n{policies}"
    )


def enforce_action_rules(args: dict, rules: dict) -> list[str]:
    ar = rules.get("action_rules", {})
    violations = []

    valid_categories = ar.get("categories", [])
    valid_priorities  = ar.get("priorities", [])
    required_fields   = ar.get("required_fields", [])

    for field in required_fields:
        if not args.get(field):
            violations.append(f"Missing required field: {field}")

    category = args.get("category", "")
    if category and category not in valid_categories:
        violations.append(
            f"Invalid category '{category}'. Must be one of: {', '.join(valid_categories)}"
        )

    priority = args.get("priority", "")
    if priority and priority not in valid_priorities:
        violations.append(
            f"Invalid priority '{priority}'. Must be one of: {', '.join(valid_priorities)}"
        )

    return violations


def _fmt(val) -> str:
    if isinstance(val, dict):
        return "\n".join(f"  {k}: {v}" for k, v in val.items())
    return str(val).strip()
