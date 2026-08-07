"""Resume Matcher workflow node."""

import json

from services.llm_client import LLMClient

from .contracts import JDAnalyzerOutput, ResumeMatcherInput, ResumeMatcherOutput
from .prompt_loader import load_prompt
from .response_parser import parse_json_object, string_list


class ResumeMatcherNode:
    """Score a resume against the structured job requirements."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Inject the model adapter for provider-independent matching."""
        self.llm_client = llm_client
        self.system_prompt = load_prompt("resume_matcher.md")

    def run(self, node_input: ResumeMatcherInput) -> ResumeMatcherOutput:
        """Return a 0-100 score, gaps, strengths, and a concise rationale."""
        jd_payload = json.dumps(node_input.jd_analysis.__dict__, ensure_ascii=False)
        response = self.llm_client.complete(
            system_prompt=self.system_prompt,
            user_prompt=f"RESUME:\n{node_input.resume_text}\n\nJOB_REQUIREMENTS_JSON:\n{jd_payload}",
        )
        data = parse_json_object(response)
        try:
            score = max(0, min(100, int(data.get("score", 0))))
        except (TypeError, ValueError) as exc:
            raise ValueError("The matcher returned an invalid score.") from exc
        return ResumeMatcherOutput(
            score=score,
            missing_skills=string_list(data.get("missing_skills")),
            strengths=string_list(data.get("strengths")),
            rationale=str(data.get("rationale", "")).strip(),
        )
