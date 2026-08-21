"""Helpers for parsing provider responses into node contracts."""

import json
import re
from typing import Any


def parse_json_object(response_text: str) -> dict[str, Any]:
    """Parse a JSON object from plain text, fenced output, or surrounding prose."""

    if not isinstance(response_text, str) or not response_text.strip():
        raise ValueError("The LLM response was not a JSON object.")
    cleaned = response_text.strip()
    fence = re.match(
        r"^```(?:json)?\s*\n?(.*?)\n?```\s*$",
        cleaned,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if fence:
        cleaned = fence.group(1).strip()

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as original_error:
        # raw_decode handles braces embedded in JSON string values more safely
        # than slicing from the first ``{`` to the last ``}``.
        decoder = json.JSONDecoder()
        candidates: list[dict[str, Any]] = []
        for start, character in enumerate(cleaned):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(cleaned[start:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict):
                candidates.append(candidate)
        if not candidates:
            raise ValueError("The LLM response was not a JSON object.") from original_error
        # Providers sometimes print a small schema object before the actual
        # response. The outer result is normally the richest decodable object.
        parsed = max(
            candidates,
            key=lambda item: len(json.dumps(item, ensure_ascii=False)),
        )

    if not isinstance(parsed, dict):
        raise ValueError("The LLM response must be a JSON object.")
    return parsed


def string_list(value: Any) -> list[str]:
    """Convert a model-provided list or scalar into clean strings."""

    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if not isinstance(value, (list, tuple)):
        return []
    values: list[str] = []
    for item in value:
        if isinstance(item, (dict, list, tuple)):
            continue
        text = str(item).strip()
        if text:
            values.append(text)
    return values
