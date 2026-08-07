"""Helpers for parsing provider responses into node contracts."""

import json
from typing import Any


def parse_json_object(response_text: str) -> dict[str, Any]:
    """Parse a JSON object from plain text or a fenced Markdown response."""
    cleaned = response_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.removeprefix("```").removeprefix("json").removesuffix("```").strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start, end = cleaned.find("{"), cleaned.rfind("}")
        if start < 0 or end <= start:
            raise ValueError("The LLM response was not a JSON object.")
        parsed = json.loads(cleaned[start : end + 1])

    if not isinstance(parsed, dict):
        raise ValueError("The LLM response must be a JSON object.")
    return parsed


def string_list(value: Any) -> list[str]:
    """Convert a model-provided list into clean strings."""
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]
