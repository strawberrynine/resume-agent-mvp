"""Bounded score-and-optimize loop for the Resume Agent."""

from dataclasses import dataclass
import logging

from .nodes.contracts import (
    AgentLoopResult,
    JDAnalyzerOutput,
    ResumeMatcherInput,
    ResumeMatcherOutput,
    ResumeOptimizerInput,
    ResumeOptimizerOutput,
    ScoreRecord,
)
from .nodes.resume_matcher import ResumeMatcherNode
from .nodes.resume_optimizer import ResumeOptimizerNode

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AgentLoopConfig:
    """Safety limits for iterative optimization cycles."""

    target_score: int = 80
    max_iterations: int = 5
    # Even a strong resume should receive one complete rewrite so the UI can
    # show an actionable optimized document instead of echoing the source.
    always_optimize_once: bool = True


class AgentLoop:
    """Repeat matching and optimization until a target score or limit is reached."""

    def __init__(self, config: AgentLoopConfig | None = None) -> None:
        """Create a bounded loop with a target score and maximum optimization cycles."""
        self.config = config or AgentLoopConfig()
        if not 0 <= self.config.target_score <= 100:
            raise ValueError("target_score must be between 0 and 100.")
        if self.config.max_iterations < 1:
            raise ValueError("max_iterations must be at least 1.")

    def run(
        self,
        resume_text: str,
        jd_analysis: JDAnalyzerOutput,
        matcher: ResumeMatcherNode,
        optimizer: ResumeOptimizerNode,
        knowledge_context: list[str] | None = None,
    ) -> AgentLoopResult:
        """Run score -> optimize -> re-score iterations and return complete history."""
        current_resume = resume_text
        current_match = self._score(matcher, current_resume, jd_analysis)
        history = [
            ScoreRecord(
                iteration=1,
                score=current_match.score,
                change=0,
                action="Initial resume score",
            )
        ]
        logger.info("Agent loop iteration=1 score=%d action=initial_score", current_match.score)

        optimization = ResumeOptimizerOutput(
            suggestions=["Preparing a truthful role-aligned rewrite."],
            optimized_resume_markdown=current_resume,
        )
        best_optimized_resume = ""
        best_optimized_match: ResumeMatcherOutput | None = None
        best_optimization: ResumeOptimizerOutput | None = None

        optimization_iterations = 0
        while (
            (
                current_match.score < self.config.target_score
                or (
                    self.config.always_optimize_once
                    and optimization_iterations == 0
                )
            )
            and optimization_iterations < self.config.max_iterations
        ):
            optimization_iterations += 1
            logger.info(
                "Agent loop iteration=%d action=optimize previous_score=%d",
                optimization_iterations,
                current_match.score,
            )
            optimization = optimizer.run(
                ResumeOptimizerInput(
                    resume_text=current_resume,
                    jd_analysis=jd_analysis,
                    match_result=current_match,
                    knowledge_context=knowledge_context or [],
                    source_resume_text=resume_text,
                )
            )
            current_resume = optimization.optimized_resume_markdown
            previous_score = current_match.score
            current_match = self._score(matcher, current_resume, jd_analysis)
            change = current_match.score - previous_score
            history.append(
                ScoreRecord(
                    iteration=len(history) + 1,
                    score=current_match.score,
                    change=change,
                    action="Optimized resume and re-scored",
                )
            )
            logger.info(
                "Agent loop iteration=%d score=%d change=%+d",
                len(history),
                current_match.score,
                change,
            )

            if (
                best_optimized_match is None
                or current_match.score > best_optimized_match.score
            ):
                best_optimized_resume = current_resume
                best_optimized_match = current_match
                best_optimization = optimization

            # Continue from the strongest valid optimized draft instead of
            # allowing a weaker later draft to become the next factual context.
            current_resume = best_optimized_resume
            current_match = best_optimized_match

            if optimization.used_fallback:
                logger.warning("Agent loop stopped after optimizer safety fallback")
                break

        if best_optimized_match is not None and best_optimization is not None:
            if best_optimized_resume != current_resume:
                history.append(
                    ScoreRecord(
                        iteration=len(history) + 1,
                        score=best_optimized_match.score,
                        change=best_optimized_match.score - current_match.score,
                        action="Selected best optimized version",
                    )
                )
            current_resume = best_optimized_resume
            current_match = best_optimized_match
            optimization = best_optimization

        stop_reason = (
            "target_reached"
            if current_match.score >= self.config.target_score
            else "max_optimization_cycles_reached"
        )
        logger.info(
            "Agent loop stopped reason=%s optimization_cycles=%d score_records=%d final_score=%d",
            stop_reason,
            optimization_iterations,
            len(history),
            current_match.score,
        )
        return AgentLoopResult(
            resume_text=current_resume,
            match_result=current_match,
            optimization=optimization,
            score_history=history,
        )

    @staticmethod
    def _score(
        matcher: ResumeMatcherNode,
        resume_text: str,
        jd_analysis: JDAnalyzerOutput,
    ) -> ResumeMatcherOutput:
        """Evaluate the current resume against the same analyzed JD."""
        return matcher.run(ResumeMatcherInput(resume_text=resume_text, jd_analysis=jd_analysis))
