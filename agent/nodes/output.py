"""Output workflow node."""

from __future__ import annotations

import re

from .contracts import OutputInput, OutputResult


def _nest_resume_headings(markdown: str) -> str:
    """Nest resume headings below the output contract's top-level headings.

    The Gradio renderer currently splits the final document on ``# Heading``.
    A generated resume commonly starts with ``# Candidate Name``; leaving that
    heading at level one would make the renderer treat it as a new result
    section and show an empty ``Optimized Resume`` card.  Convert only headings
    outside fenced code blocks so the candidate's content remains intact.
    """

    lines = markdown.strip().splitlines()
    nested: list[str] = []
    fence: str | None = None
    for line in lines:
        fence_match = re.match(r"^\s*(`{3,}|~{3,})", line)
        if fence_match:
            marker = fence_match.group(1)[0]
            if fence is None:
                fence = marker
            elif marker == fence:
                fence = None
            nested.append(line)
            continue
        if fence is None and re.match(r"^#\s+", line):
            nested.append(f"#{line}")
        else:
            nested.append(line)
    return "\n".join(nested).strip()


def _prepare_optimized_resume(markdown: str, *, nest_headings: bool = False) -> str:
    """Return a safe non-empty resume body for the final Markdown contract."""

    prepared = _nest_resume_headings(markdown) if nest_headings else markdown.strip()
    return prepared or "_No optimized resume was returned._"


def _single_line(value: str) -> str:
    """Keep model-provided list entries inside their output contract section."""

    return re.sub(r"\s+", " ", value).strip()


def _model_text(value: object) -> str:
    """Normalize an optional model scalar without rendering Python ``None``."""

    return "" if value is None else _single_line(str(value))


def _render_explanations(items: list[dict[str, object]]) -> str:
    """Render structured editorial reasons without trusting model headings."""

    rendered: list[str] = []
    for index, item in enumerate(items[:8], start=1):
        section = _model_text(item.get("section")) or f"修改 {index}"
        original = _model_text(item.get("original"))
        optimized = _model_text(item.get("optimized"))
        reason = _model_text(item.get("why_changed", item.get("whyChanged")))
        alignment_value = item.get("jd_alignment", item.get("jdAlignment", []))
        if isinstance(alignment_value, (list, tuple)):
            alignment = "、".join(
                _model_text(value)
                for value in alignment_value
                if _model_text(value)
            )
        else:
            alignment = _model_text(alignment_value)
        rendered.append(f"### {section}")
        if original:
            rendered.append(f"- 原文：{original}")
        if optimized:
            rendered.append(f"- 优化后：{optimized}")
        if reason:
            rendered.append(f"- 修改原因：{reason}")
        if alignment:
            rendered.append(f"- 与目标岗位匹配：{alignment}")
        rendered.append("")
    return "\n".join(rendered).strip()


class OutputNode:
    """Render typed workflow results as the UI's final Markdown document."""

    def run(self, node_input: OutputInput) -> OutputResult:
        """Format score, skills, suggestions, and optimized resume in order."""
        history_rows = []
        for record in node_input.score_history:
            change = f"{record.change:+d}" if record.iteration > 1 else "-"
            history_rows.append(
                f"| {record.iteration} | {record.score} | {change} | {record.action} |"
            )
        history_markdown = "\n".join(history_rows) or "| - | - | - | No score recorded |"
        sources = node_input.knowledge_sources or ["No knowledge files matched."]
        sources_markdown = "\n".join(f"- `{source}`" for source in sources)
        missing = node_input.match_result.missing_skills or ["None identified"]
        suggestions = node_input.optimization.suggestions or ["No additional suggestions returned."]
        missing_markdown = "\n".join(f"- {_single_line(item)}" for item in missing)
        suggestions_markdown = "\n".join(f"- {_single_line(item)}" for item in suggestions)
        highlights = (
            node_input.optimization_highlights
            or node_input.optimization.optimization_highlights
            or []
        )
        highlights_markdown = "\n".join(
            f"- {_single_line(item)}" for item in highlights[:4]
        )
        explanations_markdown = _render_explanations(
            node_input.optimization.optimization_explanations
        )
        rationale = _nest_resume_headings(node_input.match_result.rationale)
        score_line = str(node_input.match_result.score)
        if rationale:
            score_line += f"\n\n{rationale}"
        optimized_resume = _prepare_optimized_resume(
            node_input.optimization.optimized_resume_markdown
        )
        original_resume = _prepare_optimized_resume(
            node_input.original_resume_text,
            nest_headings=True,
        )
        optional_sections = ""
        if original_resume and original_resume != "_No optimized resume was returned._":
            optional_sections += f"# Original Resume\n\n{original_resume}\n\n"
        if highlights_markdown:
            optional_sections += f"# Optimization Highlights\n\n{highlights_markdown}\n\n"
        if explanations_markdown:
            optional_sections += f"# Why It Changed\n\n{explanations_markdown}\n\n"
        markdown = (
            f"# Score History\n\n"
            f"| Iteration | Score | Change | Action |\n"
            f"| ---: | ---: | ---: | --- |\n"
            f"{history_markdown}\n\n"
            f"# Knowledge Used\n\n{sources_markdown}\n\n"
            f"# Resume Score\n\n{score_line}\n\n"
            f"# Missing Skills\n\n{missing_markdown}\n\n"
            f"# Suggestions\n\n{suggestions_markdown}\n\n"
            f"{optional_sections}"
            f"# Optimized Resume\n\n{optimized_resume}"
        )
        return OutputResult(markdown=markdown)
