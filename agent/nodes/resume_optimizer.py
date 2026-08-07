"""Resume Optimizer workflow node."""

import json

from services.llm_client import LLMClient

from .contracts import ResumeOptimizerInput, ResumeOptimizerOutput
from .prompt_loader import load_prompt
from .response_parser import parse_json_object, string_list


class ResumeOptimizerNode:
    """Create actionable suggestions and a truthful Markdown resume rewrite."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Inject the model adapter for provider-independent optimization."""
        self.llm_client = llm_client
        self.system_prompt = load_prompt("resume_optimizer.md")

    def run(self, node_input: ResumeOptimizerInput) -> ResumeOptimizerOutput:
        """Optimize the resume using the JD analysis and match assessment."""
        context = {
            "job_requirements": node_input.jd_analysis.__dict__,
            "match_result": node_input.match_result.__dict__,
            "knowledge_context": node_input.knowledge_context,
        }
        response = self.llm_client.complete(
            system_prompt=self.system_prompt,
            user_prompt=(
                f"RESUME:\n{node_input.resume_text}\n\n"
                f"ANALYSIS_CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False)}\n\n"
                "Use the retrieved knowledge as guidance, not as candidate evidence."
            ),
        )
        data = parse_json_object(response)
        optimized = str(data.get("optimized_resume_markdown", "")).strip()
        if not optimized:
            raise ValueError("The optimizer returned an empty rewritten resume.")
        return ResumeOptimizerOutput(
            suggestions=string_list(data.get("suggestions")),
            optimized_resume_markdown=optimized,
        )
