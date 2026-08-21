"""Resume Agent workflow orchestration."""

import logging

from services.llm_client import LLMClient

from .agent_loop import AgentLoop
from .nodes.contracts import (
    JDAnalyzerInput,
    OutputInput,
    ResumeParserInput,
    ResumeSectionOptimizerInput,
    ResumeSectionOptimizerOutput,
)
from .nodes.jd_analyzer import JDAnalyzerNode
from .nodes.knowledge_retriever import KnowledgeRetrieverInput, KnowledgeRetrieverNode
from .nodes.output import OutputNode
from .nodes.resume_matcher import ResumeMatcherNode
from .nodes.resume_optimizer import ResumeOptimizerNode
from .nodes.resume_parser import ResumeParserNode
from .nodes.resume_section_optimizer import ResumeSectionOptimizerNode


logger = logging.getLogger(__name__)


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
        self.resume_section_optimizer = ResumeSectionOptimizerNode(client)
        self.agent_loop = AgentLoop()
        self.output = OutputNode()

    def analyze(
        self,
        file_path: str | None = None,
        job_description: str = "",
        *,
        pdf_path: str | None = None,
    ) -> str:
        """Parse one supported resume and run the complete Agent workflow."""

        resolved_path = file_path or pdf_path
        if not resolved_path:
            return "Please upload a resume before starting analysis."
        if not job_description or not job_description.strip():
            return "Please paste a job description before starting analysis."

        try:
            resume = self.resume_parser.run(ResumeParserInput(file_path=resolved_path))
            return self.analyze_text(resume.resume_text, job_description)
        except Exception as exc:  # Surface actionable errors in the demo UI.
            logger.exception("Resume Agent workflow failed")
            return f"Analysis failed: {exc}"

    def analyze_text(self, resume_text: str, job_description: str) -> str:
        """Run the Agent workflow for already validated and parsed resume text."""

        if not resume_text or not resume_text.strip():
            return "Analysis failed: 文档中没有可解析的简历文字。"
        if not job_description or not job_description.strip():
            return "Please paste a job description before starting analysis."
        try:
            jd = self.jd_analyzer.run(JDAnalyzerInput(job_description=job_description))
            knowledge = self.knowledge_retriever.run(
                KnowledgeRetrieverInput(
                    query=f"{job_description}\n{resume_text}",
                )
            )
            knowledge_context = [
                f"SOURCE: {chunk.source}\n{chunk.content}" for chunk in knowledge.chunks
            ]
            loop_result = self.agent_loop.run(
                resume_text=resume_text,
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
                    original_resume_text=resume_text,
                    optimization_highlights=loop_result.optimization.optimization_highlights,
                )
            ).markdown
        except Exception as exc:  # Surface actionable errors in the demo UI.
            logger.exception("Resume Agent workflow failed")
            return f"Analysis failed: {exc}"

    def rewrite_section(
        self,
        *,
        original_resume_text: str,
        current_resume_markdown: str,
        section_title: str,
        section_markdown: str,
        job_description: str,
        instruction: str,
    ) -> ResumeSectionOptimizerOutput:
        """Run the independent focused-rewrite node for one selected section."""

        return self.resume_section_optimizer.run(
            ResumeSectionOptimizerInput(
                original_resume_text=original_resume_text,
                current_resume_markdown=current_resume_markdown,
                section_title=section_title,
                section_markdown=section_markdown,
                job_description=job_description,
                instruction=instruction,
            )
        )
