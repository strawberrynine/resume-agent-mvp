"""Resume Optimizer workflow node.

The optimizer is deliberately tolerant of provider response formatting.  The
preferred response is a JSON object, but OpenAI-compatible providers can still
return fenced JSON or plain Markdown.  In all cases this node returns a
non-empty, truthful Markdown resume so a formatting variation cannot silently
produce an empty UI section.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from services.llm_client import LLMClient
from services.resume_validation import unsupported_fact_anchor_issues

from .contracts import ResumeOptimizerInput, ResumeOptimizerOutput
from .prompt_loader import load_prompt
from .response_parser import parse_json_object, string_list


logger = logging.getLogger(__name__)


# Providers and prompt revisions have used both snake_case and camelCase names.
# Accepting both keeps the node contract stable while models are switched.
_MARKDOWN_KEYS = (
    "optimized_resume_markdown",
    "optimizedResumeMarkdown",
    "optimized_resume",
    "optimizedResume",
    "resume_markdown",
    "resumeMarkdown",
    "markdown",
)
_STRUCTURED_KEYS = (
    "structured_resume",
    "structuredResume",
    "optimized_resume_data",
    "optimizedResumeData",
)
_SUGGESTION_KEYS = ("suggestions", "recommendations", "optimizationSuggestions")
_HIGHLIGHT_KEYS = (
    "optimization_highlights",
    "optimizationHighlights",
    "highlights",
)
_EXPLANATION_KEYS = (
    "optimization_explanations",
    "optimizationExplanations",
    "change_explanations",
    "changeExplanations",
)
_SECTION_CUE_GROUPS = (
    ("工作经历", "工作经验", "职业经历", "experience", "employment"),
    ("项目经历", "项目经验", "projects", "project experience"),
    ("教育经历", "教育背景", "education"),
    ("技能", "专业技能", "skills", "technical skills"),
    ("证书", "认证", "certifications", "certificates"),
    ("语言", "languages"),
)


def _first_present(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    """Return the first non-empty value for a list of compatible field names."""

    for key in keys:
        value = mapping.get(key)
        if value is not None and value != "" and value != []:
            return value
    return None


def _strip_markdown_fence(value: str) -> str:
    """Remove a surrounding Markdown code fence without touching resume text."""

    lines = value.strip().splitlines()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return value.strip()


def _extract_resume_section(value: str) -> str:
    """Extract a resume section when a provider returned the full Markdown contract."""

    cleaned = _strip_markdown_fence(value)
    lines = cleaned.splitlines()
    section_start: int | None = None
    section_level = 0
    for index, line in enumerate(lines):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
        if not match:
            continue
        title = re.sub(r"[*_`]", "", match.group(2)).strip().lower()
        if title in {
            "optimized resume",
            "optimized_resume",
            "optimized resume markdown",
            "resume rewrite",
            "优化后的简历",
            "优化简历",
        }:
            section_start = index + 1
            section_level = len(match.group(1))
            break

    if section_start is None:
        return cleaned

    section_end = len(lines)
    contract_headings = {
        "resume score",
        "score history",
        "missing skills",
        "suggestions",
        "optimization highlights",
        "original resume",
        "knowledge used",
    }
    for index in range(section_start, len(lines)):
        match = re.match(r"^(#{1,6})\s+(.+?)\s*$", lines[index])
        if not match or len(match.group(1)) > section_level:
            continue
        title = re.sub(r"[*_`]", "", match.group(2)).strip().lower()
        if title in contract_headings:
            section_end = index
            break
    return "\n".join(lines[section_start:section_end]).strip()


def _as_mapping(value: Any) -> dict[str, Any]:
    """Return a mapping value or an empty mapping for malformed model data."""

    return value if isinstance(value, dict) else {}


def _as_text(value: Any) -> str:
    """Convert a scalar model value to clean text, ignoring null values."""

    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return ""
    return str(value).strip()


def _field(mapping: dict[str, Any], *names: str) -> str:
    """Read the first non-empty scalar field from snake_case/camelCase aliases."""

    for name in names:
        text = _as_text(mapping.get(name))
        if text:
            return text
    return ""


def _list_value(mapping: dict[str, Any], *names: str) -> list[Any]:
    """Read a list field while accepting a single scalar as one item."""

    for name in names:
        value = mapping.get(name)
        if isinstance(value, list):
            return value
        if isinstance(value, str) and value.strip():
            return [value.strip()]
    return []


def _render_entry(item: Any) -> list[str]:
    """Render one structured experience/project/education entry as Markdown."""

    if isinstance(item, str):
        return [f"- {item.strip()}"] if item.strip() else []
    if not isinstance(item, dict):
        return []

    title = _field(item, "title", "role", "position", "degree", "name")
    organization = _field(item, "company", "organization", "school", "institution")
    dates = _field(item, "dates", "date", "period", "duration", "start_end", "startEnd")
    heading = " | ".join(part for part in (title, organization, dates) if part)
    lines = [f"### {heading}"] if heading else []
    detail_values = _list_value(
        item,
        "bullets",
        "achievements",
        "responsibilities",
        "highlights",
        "details",
    )
    if not detail_values:
        detail = _field(item, "description", "summary", "detail")
        detail_values = [detail] if detail else []
    for detail in detail_values:
        if isinstance(detail, dict):
            detail = _field(detail, "text", "description", "detail")
        detail_text = _as_text(detail)
        if detail_text:
            lines.append(f"- {detail_text.lstrip('- ').strip()}")
    return lines


def _render_simple_items(items: list[Any]) -> list[str]:
    """Render scalar or structured list items without inventing missing fields."""

    lines: list[str] = []
    for item in items:
        rendered = _render_entry(item)
        lines.extend(rendered)
    return lines


def structured_resume_to_markdown(value: Any) -> str:
    """Render a provider's optional ``optimizedResume`` object into Markdown.

    Only fields explicitly returned by the model are rendered.  No candidate
    facts are synthesized here; an absent field simply remains absent.
    """

    data = _as_mapping(value)
    if not data:
        return ""
    direct_markdown = _field(data, "markdown", "resume_markdown", "optimized_resume_markdown")
    if direct_markdown:
        return _extract_resume_section(direct_markdown)

    basic = _as_mapping(data.get("basicInfo") or data.get("basic_info") or data.get("contact"))
    name = _field(data, "name") or _field(basic, "name", "full_name", "fullName")
    target = _field(data, "target_role", "targetRole", "headline", "title")
    contact_fields = [
        _field(basic, "phone", "mobile"),
        _field(basic, "email"),
        _field(basic, "location", "city"),
        _field(basic, "linkedin", "linkedin_url", "linkedinUrl"),
        _field(basic, "github", "github_url", "githubUrl"),
    ]
    lines: list[str] = []
    if name:
        lines.append(f"# {name}")
    if target:
        lines.append(f"**{target}**")
    if any(contact_fields):
        lines.append(" | ".join(item for item in contact_fields if item))

    summary = _field(data, "summary", "profile", "professional_summary")
    if summary:
        lines.extend(["", "## Summary", "", summary])

    for heading, names in (
        ("Experience", ("workExperience", "work_experience", "experience", "employment")),
        ("Projects", ("projects", "projectExperience", "project_experience")),
        ("Education", ("education", "educations")),
    ):
        entries: list[Any] = []
        for name_alias in names:
            if data.get(name_alias):
                entries = data[name_alias] if isinstance(data[name_alias], list) else [data[name_alias]]
                break
        if entries:
            lines.extend(["", f"## {heading}", ""])
            for entry in entries:
                lines.extend(_render_entry(entry))
                lines.append("")

    skills = _list_value(data, "skills", "technicalSkills", "technical_skills", "core_skills")
    if skills:
        skill_text: list[str] = []
        for skill in skills:
            if isinstance(skill, dict):
                category = _field(skill, "category", "type")
                values = _list_value(skill, "items", "skills", "values")
                value_text = ", ".join(_as_text(item) for item in values if _as_text(item))
                named = _field(skill, "name", "skill")
                text = ": ".join(part for part in (category, value_text or named) if part)
            else:
                text = _as_text(skill)
            if text:
                skill_text.append(text)
        if skill_text:
            lines.extend(["", "## Skills", "", ", ".join(skill_text)])

    for heading, names in (
        ("Certifications", ("certifications", "certificates", "licenses")),
        ("Languages", ("languages", "languageSkills", "language_skills")),
        ("Awards", ("awards", "honors", "achievements")),
        ("Publications", ("publications",)),
        ("Volunteer Experience", ("volunteering", "volunteerExperience", "volunteer_experience")),
    ):
        entries: list[Any] = []
        for name_alias in names:
            if data.get(name_alias):
                value = data[name_alias]
                entries = value if isinstance(value, list) else [value]
                break
        rendered_entries = _render_simple_items(entries)
        if rendered_entries:
            lines.extend(["", f"## {heading}", "", *rendered_entries])

    portfolio = _field(data, "portfolio", "portfolio_url", "portfolioUrl", "website")
    if portfolio:
        lines.extend(["", "## Portfolio", "", portfolio])

    return "\n".join(lines).strip()


def _fallback_markdown(resume_text: str) -> str:
    """Return a faithful copy when a provider omits the rewritten resume."""

    source = resume_text.strip()
    if not source:
        return ""
    # A faithful copy is preferable to an empty panel or invented candidate data.
    if re.search(r"^#\s+", source, flags=re.MULTILINE):
        return source
    return f"# Resume\n\n{source}"


def _rewrite_validation_issues(source: str, candidate: str) -> list[str]:
    """Detect high-risk fabricated anchors and obviously incomplete rewrites."""

    issues = unsupported_fact_anchor_issues(source, candidate)

    source_compact = re.sub(r"\s+", "", source)
    candidate_compact = re.sub(r"\s+", "", candidate)
    minimum_length = min(1200, max(80, int(len(source_compact) * 0.2)))
    if len(candidate_compact) < minimum_length:
        issues.append("incomplete resume length")

    source_folded = source.casefold()
    candidate_folded = candidate.casefold()
    for aliases in _SECTION_CUE_GROUPS:
        if any(alias in source_folded for alias in aliases) and not any(
            alias in candidate_folded for alias in aliases
        ):
            issues.append(f"missing source section: {aliases[0]}")
    return issues


def _parse_optimizer_response(response: str) -> tuple[dict[str, Any], Any, str]:
    """Parse one provider response into raw data, structured data, and Markdown."""

    data: dict[str, Any] = {}
    try:
        data = parse_json_object(response)
    except ValueError:
        logger.warning("Optimizer returned non-JSON output; applying Markdown fallback parser")

    structured = _first_present(data, _STRUCTURED_KEYS)
    optimized_value = _first_present(data, _MARKDOWN_KEYS)
    optimized = ""
    if isinstance(optimized_value, dict):
        structured = structured or optimized_value
        optimized = structured_resume_to_markdown(optimized_value)
    elif optimized_value is not None:
        optimized = _extract_resume_section(_as_text(optimized_value))
    if not optimized and structured:
        optimized = structured_resume_to_markdown(structured)
    if not optimized and not data:
        optimized = _extract_resume_section(response)
    return data, structured, optimized.strip()


class ResumeOptimizerNode:
    """Create actionable suggestions and a truthful Markdown resume rewrite."""

    def __init__(self, llm_client: LLMClient) -> None:
        """Inject the model adapter for provider-independent optimization."""
        self.llm_client = llm_client
        self.system_prompt = load_prompt("resume_optimizer.md")

    def run(self, node_input: ResumeOptimizerInput) -> ResumeOptimizerOutput:
        """Optimize the resume and guarantee a non-empty, displayable rewrite."""
        context = {
            "job_requirements": node_input.jd_analysis.__dict__,
            "match_result": node_input.match_result.__dict__,
            "knowledge_context": node_input.knowledge_context,
        }
        source_resume = node_input.source_resume_text.strip() or node_input.resume_text
        base_user_prompt = (
            f"ORIGINAL_RESUME:\n{source_resume}\n\n"
            f"CURRENT_DRAFT:\n{node_input.resume_text}\n\n"
            f"ANALYSIS_CONTEXT_JSON:\n{json.dumps(context, ensure_ascii=False)}\n\n"
            "Use the retrieved knowledge as guidance, not as candidate evidence."
        )
        data: dict[str, Any] = {}
        structured: Any = None
        optimized = ""
        validation_issues: list[str] = []
        for attempt in range(2):
            correction = ""
            if validation_issues:
                correction = (
                    "\n\nThe previous draft was rejected because it contained: "
                    + ", ".join(validation_issues)
                    + ". Return a complete rewrite using only original facts."
                )
            try:
                response = self.llm_client.complete(
                    system_prompt=self.system_prompt,
                    user_prompt=base_user_prompt + correction,
                )
            except RuntimeError as exc:
                if "empty response" in str(exc).casefold():
                    if attempt == 0:
                        logger.warning("Optimizer returned an empty response; retrying once")
                        continue
                    validation_issues = ["empty rewrite"]
                    optimized = ""
                    break
                raise
            data, structured, optimized = _parse_optimizer_response(response)
            validation_issues = _rewrite_validation_issues(source_resume, optimized)
            if optimized and not validation_issues:
                break
            logger.warning(
                "Rejected optimizer draft attempt=%d issues=%s",
                attempt + 1,
                validation_issues or ["empty rewrite"],
            )

        used_fallback = not optimized or bool(validation_issues)
        if used_fallback:
            optimized = _fallback_markdown(source_resume)
            data = {}
            structured = None
        if not optimized:
            raise ValueError("The resume contains no extractable text to rewrite.")

        suggestions_value = _first_present(data, _SUGGESTION_KEYS)
        suggestions = string_list(suggestions_value)
        if used_fallback:
            suggestions = [
                "模型未返回可信且完整的改写，已保留原始简历内容；请重试并核对服务状态。"
            ]
        elif not suggestions:
            suggestions = [
                "Structure and keyword alignment were adjusted from the source; verify every fact before applying."
            ]
        highlights_value = _first_present(data, _HIGHLIGHT_KEYS)
        if highlights_value is None and isinstance(structured, dict):
            highlights_value = _first_present(structured, _HIGHLIGHT_KEYS)
        highlights = string_list(highlights_value)[:4]
        explanations_value = _first_present(data, _EXPLANATION_KEYS)
        explanations = (
            [item for item in explanations_value if isinstance(item, dict)][:8]
            if isinstance(explanations_value, list)
            else []
        )
        return ResumeOptimizerOutput(
            suggestions=suggestions,
            optimized_resume_markdown=optimized,
            structured_resume=structured if isinstance(structured, dict) else {},
            optimization_highlights=highlights,
            optimization_explanations=explanations,
            used_fallback=used_fallback,
        )
