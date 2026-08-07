"""Resume Agent workflow orchestration."""

from services.llm_client import LLMClient

from .agent_loop import AgentLoop
from .nodes.contracts import (
    JDAnalyzerInput,
    OutputInput,
    ResumeParserInput,
)
from .nodes.jd_analyzer import JDAnalyzerNode
from .nodes.knowledge_retriever import KnowledgeRetrieverInput, KnowledgeRetrieverNode
from .nodes.output import OutputNode
from .nodes.resume_matcher import ResumeMatcherNode
from .nodes.resume_optimizer import ResumeOptimizerNode
from .nodes.resume_parser import ResumeParserNode


class ResumeAgent:
    """Coordinate independent nodes in the resume analysis workflow."""

    def __init__(self, llm_client: LLMClient | None = None) -> None:
        """Build the workflow with one injectable OpenAI-compatible model adapter."""
        client = llm_client or LLMClient()
        self.resume_parser = ResumeParserNode()
        self.jd_analyzer = JDAnalyzerNode(client)
        self.knowledge_retriever = KnowledgeRetrieverNode()
        self.resume_matcher = ResumeMatcherNode(client)
        self.resume_optimizer = ResumeOptimizerNode(client)
        self.agent_loop = AgentLoop()
        self.output = OutputNode()

    def analyze(self, pdf_path: str | None, job_description: str) -> str:
        """Run Parser -> JD Analyzer -> Agent Loop -> Output."""
        if not pdf_path:
            return "Please upload a PDF resume before starting analysis."
        if not job_description or not job_description.strip():
            return "Please paste a job description before starting analysis."

        try:
            resume = self.resume_parser.run(ResumeParserInput(pdf_path=pdf_path))
            jd = self.jd_analyzer.run(JDAnalyzerInput(job_description=job_description))
            knowledge = self.knowledge_retriever.run(
                KnowledgeRetrieverInput(
                    query=f"{job_description}\n{resume.resume_text}",
                )
            )
            knowledge_context = [
                f"SOURCE: {chunk.source}\n{chunk.content}" for chunk in knowledge.chunks
            ]
            loop_result = self.agent_loop.run(
                resume_text=resume.resume_text,
                jd_analysis=jd,
                matcher=self.resume_matcher,
                optimizer=self.resume_optimizer,
                knowledge_context=knowledge_context,
            )
            return self.output.run(
                OutputInput(
                    match_result=loop_result.match_result,
                    optimization=loop_result.optimization,
                    score_history=loop_result.score_history,
                    knowledge_sources=[chunk.source for chunk in knowledge.chunks],
                )
            ).markdown
        except Exception as exc:  # Surface actionable errors in the demo UI.
            return f"Analysis failed: {exc}"
