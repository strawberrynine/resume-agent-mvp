"""Typed inputs and outputs shared by workflow nodes."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ResumeParserInput:
    """Input required by the resume parser node."""

    pdf_path: str


@dataclass(frozen=True)
class ResumeParserOutput:
    """Extracted resume content passed to downstream nodes."""

    resume_text: str


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


@dataclass(frozen=True)
class ResumeOptimizerOutput:
    """Suggestions and truthful rewritten resume from the optimizer node."""

    suggestions: list[str] = field(default_factory=list)
    optimized_resume_markdown: str = ""


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


@dataclass(frozen=True)
class OutputResult:
    """Final markdown returned to the Gradio UI."""

    markdown: str
