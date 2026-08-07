"""Prompt loading helper for workflow nodes."""

from pathlib import Path


def load_prompt(filename: str) -> str:
    """Read a prompt file from the repository-level prompt directory."""
    prompt_path = Path(__file__).resolve().parents[2] / "prompt" / filename
    return prompt_path.read_text(encoding="utf-8")
