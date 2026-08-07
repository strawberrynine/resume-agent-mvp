"""Output workflow node."""

from .contracts import OutputInput, OutputResult


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
        missing_markdown = "\n".join(f"- {item}" for item in missing)
        suggestions_markdown = "\n".join(f"- {item}" for item in suggestions)
        rationale = node_input.match_result.rationale
        score_line = str(node_input.match_result.score)
        if rationale:
            score_line += f"\n\n{rationale}"
        markdown = (
            f"# Score History\n\n"
            f"| Iteration | Score | Change | Action |\n"
            f"| ---: | ---: | ---: | --- |\n"
            f"{history_markdown}\n\n"
            f"# Knowledge Used\n\n{sources_markdown}\n\n"
            f"# Resume Score\n\n{score_line}\n\n"
            f"# Missing Skills\n\n{missing_markdown}\n\n"
            f"# Suggestions\n\n{suggestions_markdown}\n\n"
            f"# Optimized Resume\n\n{node_input.optimization.optimized_resume_markdown}"
        )
        return OutputResult(markdown=markdown)
