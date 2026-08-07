"""JD Analyzer workflow node."""

from services.llm_client import LLMClient

from .contracts import JDAnalyzerInput, JDAnalyzerOutput
from .prompt_loader import load_prompt
from .response_parser import parse_json_object, string_list


class JDAnalyzerNode:
    """Extract structured requirements from a job description."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Inject the model adapter so providers can be swapped later."""
        self.llm_client = llm_client
        self.system_prompt = load_prompt("jd_analyzer.md")

    def run(self, node_input: JDAnalyzerInput) -> JDAnalyzerOutput:
        """Analyze the JD and return normalized skills, duties, and keywords."""
        response = self.llm_client.complete(
            system_prompt=self.system_prompt,
            user_prompt=node_input.job_description.strip(),
        )
        data = parse_json_object(response)
        return JDAnalyzerOutput(
            required_skills=string_list(data.get("required_skills")),
            responsibilities=string_list(data.get("responsibilities")),
            keywords=string_list(data.get("keywords")),
        )
