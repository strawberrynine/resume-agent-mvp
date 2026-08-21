"""Typed inputs and outputs shared by workflow nodes.

The workflow intentionally keeps the optimized resume in Markdown for the
current Gradio UI.  ``structured_resume`` is an additive, optional payload so
future clients can render sections (or offer side-by-side editing) without
changing the node boundary again.
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ResumeParserInput:
    """Input required by the resume parser node."""

    file_path: str = ""
    # Kept for compatibility with the first PDF-only MVP contract.
    pdf_path: str = ""


@dataclass(frozen=True)
class ResumeParserOutput:
    """Extracted resume content passed to downstream nodes."""

    resume_text: str
    original_file: dict[str, Any] = field(default_factory=dict)
    working_file: str = ""
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class JDAnalyzerInput:
    """Input required by the job-description analyzer node."""

    job_description: str


@dataclass(frozen=True)
class JDAnalyzerOutput:
    """Normalized job requirements produced by the analyzer node."""

    required_skills: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ResumeMatcherInput:
    """Inputs required by the resume matcher node."""

    resume_text: str
    jd_analysis: JDAnalyzerOutput


@dataclass(frozen=True)
class ResumeMatcherOutput:
    """Evidence-based match assessment produced by the matcher node."""

    score: int
    missing_skills: list[str] = field(default_factory=list)
    strengths: list[str] = field(default_factory=list)
    rationale: str = ""


@dataclass(frozen=True)
class ResumeOptimizerInput:
    """Inputs required by the resume optimizer node."""

    resume_text: str
    jd_analysis: JDAnalyzerOutput
    match_result: ResumeMatcherOutput
    knowledge_context: list[str] = field(default_factory=list)
    source_resume_text: str = ""


@dataclass(frozen=True)
class ResumeOptimizerOutput:
    """Suggestions and truthful rewritten resume from the optimizer node."""

    suggestions: list[str] = field(default_factory=list)
    optimized_resume_markdown: str = ""
    structured_resume: dict[str, Any] = field(default_factory=dict)
    optimization_highlights: list[str] = field(default_factory=list)
    optimization_explanations: list[dict[str, Any]] = field(default_factory=list)
    used_fallback: bool = False


@dataclass(frozen=True)
class ResumeSectionOptimizerInput:
    """Inputs required to rewrite one section without changing the full resume."""

    original_resume_text: str
    current_resume_markdown: str
    section_title: str
    section_markdown: str
    job_description: str
    instruction: str


@dataclass(frozen=True)
class ResumeSectionOptimizerOutput:
    """A single truthful rewritten section and a concise change summary."""

    section_markdown: str
    highlight: str = ""


@dataclass(frozen=True)
class ScoreRecord:
    """One score observation made by the Agent Loop."""

    iteration: int
    score: int
    change: int
    action: str


@dataclass(frozen=True)
class AgentLoopResult:
    """Final node results and score history returned by the loop."""

    resume_text: str
    match_result: ResumeMatcherOutput
    optimization: ResumeOptimizerOutput
    score_history: list[ScoreRecord] = field(default_factory=list)


@dataclass(frozen=True)
class OutputInput:
    """Inputs required by the final output node."""

    match_result: ResumeMatcherOutput
    optimization: ResumeOptimizerOutput
    score_history: list[ScoreRecord] = field(default_factory=list)
    knowledge_sources: list[str] = field(default_factory=list)
    # Optional fields keep the original MVP call sites source-compatible while
    # enabling a future original/optimized comparison view.
    original_resume_text: str = ""
    optimization_highlights: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OutputResult:
    """Final markdown returned to the Gradio UI."""

    markdown: str
