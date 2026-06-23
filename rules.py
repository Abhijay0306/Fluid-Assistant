from pathlib import Path
from typing import Any

import yaml

RULES_PATH = Path(__file__).parent / "rules.yaml"


def load_rules() -> dict:
    with open(RULES_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_knowledge_prompt(rules: dict) -> str:
    knowledge = rules.get("knowledge", {})
    sections = "\n\n".join(
        f"[{key.upper()}]\n{text.strip()}" for key, text in knowledge.items()
    )
    return f"COMPANY POLICY KNOWLEDGE BASE:\n{sections}"


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
    """Return a list of violation messages; empty means all good."""
    ar = rules.get("action_rules", {})
    violations = []

    valid_categories = ar.get("categories", [])
    valid_priorities = ar.get("priorities", [])
    required_fields = ar.get("required_fields", [])

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
