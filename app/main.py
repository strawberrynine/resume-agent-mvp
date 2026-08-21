"""Single-page ResumeFlow AI Gradio app."""

from __future__ import annotations

import html
import logging
import os
import re
from collections.abc import Generator
from pathlib import Path
from types import MethodType
from typing import Any
from urllib.parse import quote

import gradio as gr

from agent.resume_agent import ResumeAgent
from services.document_input import (
    MAX_FILE_SIZE_BYTES,
    UPLOAD_MAX_AGE_SECONDS,
    DocumentValidationError,
    preserve_uploaded_document,
)
from services.document_parser import parse_resume_document
from services.resume_export import ResumeExportError, export_optimized_resume_pdf
from services.resume_markdown import (
    get_resume_section,
    list_resume_section_titles,
    replace_resume_section,
)


logger = logging.getLogger(__name__)


# Resolve assets from this module so launching from another working directory
# (or a cloud service) does not change the URLs used by the frontend.
BASE_DIR = Path(__file__).resolve().parents[1]
ASSET_DIR = BASE_DIR / "assets"
IMAGE_DIR = ASSET_DIR / "images"
CAT_IMAGE_PATH = IMAGE_DIR / "siamese-cat.png"
PLACEHOLDER_IMAGE_PATH = IMAGE_DIR / "assistant-placeholder.svg"
RUNTIME_DIR = BASE_DIR / ".runtime"
EXPORT_DIR = RUNTIME_DIR / "exports"


class UploadedResumePath(str):
    """A filepath value that keeps the browser-provided name and MIME type."""

    def __new__(
        cls,
        value: str,
        *,
        original_name: str = "",
        mime_type: str = "",
    ) -> "UploadedResumePath":
        instance = super().__new__(cls, value)
        instance.original_name = original_name
        instance.mime_type = mime_type
        return instance


def _resume_file_component(**kwargs: Any) -> gr.File:
    """Build a native Gradio File input that retains upload metadata."""

    component = gr.File(**kwargs)
    default_processor = component._process_single_file

    def process_with_metadata(_: gr.File, file_data: Any) -> str | bytes:
        """Attach browser-provided metadata to the normal filepath value."""

        processed = default_processor(file_data)
        if not isinstance(processed, str):
            return processed
        original_name = str(getattr(file_data, "orig_name", "") or Path(processed).name)
        mime_type = str(getattr(file_data, "mime_type", "") or "")
        return UploadedResumePath(
            processed,
            original_name=original_name,
            mime_type=mime_type,
        )

    component._process_single_file = MethodType(  # type: ignore[method-assign]
        process_with_metadata,
        component,
    )
    return component


def _uploaded_metadata(resume_path: object) -> tuple[str | None, str | None]:
    """Read optional original-name and MIME metadata from a Gradio upload."""

    return (
        str(getattr(resume_path, "original_name", "") or "") or None,
        str(getattr(resume_path, "mime_type", "") or "") or None,
    )

# These are the only top-level headings emitted by the output node.  Resume
# content may contain headings of its own (for example ``# Name``), so those
# headings must remain part of the Optimized Resume section.
_SECTION_ALIASES = {
    "resume score": "Resume Score",
    "score history": "Score History",
    "missing skills": "Missing Skills",
    "suggestions": "Suggestions",
    "original resume": "Original Resume",
    "optimization highlights": "Optimization Highlights",
    "why it changed": "Why It Changed",
    "optimized resume": "Optimized Resume",
    "knowledge used": "Knowledge Used",
    "简历评分": "Resume Score",
    "评分历史": "Score History",
    "缺失技能": "Missing Skills",
    "优化建议": "Suggestions",
    "原始简历": "Original Resume",
    "原版简历": "Original Resume",
    "优化亮点": "Optimization Highlights",
    "本次优化": "Optimization Highlights",
    "为什么这样改": "Why It Changed",
    "优化后的简历": "Optimized Resume",
    "参考知识库": "Knowledge Used",
}


def _asset_file_url(path: Path) -> str:
    """Return a Gradio file URL, falling back when an asset is unavailable."""

    resolved_path = path if path.is_file() else PLACEHOLDER_IMAGE_PATH
    # Keep the drive colon and path separators readable for Gradio's /file= route.
    return f"/gradio_api/file={quote(resolved_path.resolve().as_posix(), safe='/:')}"


CAT_IMAGE_SRC = _asset_file_url(CAT_IMAGE_PATH)
FALLBACK_IMAGE_SRC = _asset_file_url(PLACEHOLDER_IMAGE_PATH)


CSS = """
:root {
  --cream: #fbf8f2;
  --surface: #ffffff;
  --tea: #c69a7a;
  --tea-soft: #f3e5d8;
  --brown: #4b302b;
  --ink: #2d2826;
  --muted: #7d716b;
  --line: #eadfd7;
  --pink: #e8a8b1;
  --pink-soft: #fbeaec;
  --sage: #70877c;
}

body, .gradio-container {
  background: var(--cream) !important;
  color: var(--ink) !important;
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif !important;
}

.gradio-container {
  max-width: 100% !important;
  padding: 0 !important;
}

#page {
  min-height: 100vh;
  padding: 10px 16px 28px;
}

#shell {
  max-width: 1200px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

#topbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

#brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.brand-avatar {
  width: 38px;
  height: 38px;
  border-radius: 12px;
  object-fit: cover;
  box-shadow: 0 10px 20px rgba(75, 48, 43, 0.12);
}

.brand-copy {
  display: flex;
  flex-direction: column;
  line-height: 1.1;
}

.brand-name {
  color: var(--brown);
  font-size: 17px;
  font-weight: 780;
}

.brand-sub {
  color: var(--muted);
  font-size: 12px;
}

.top-links {
  display: flex;
  align-items: center;
  gap: 18px;
}

.top-links a {
  color: var(--brown);
  text-decoration: none;
  font-size: 13px;
  font-weight: 650;
}

.top-links a:hover {
  color: var(--tea);
}

#hero {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(300px, 0.95fr);
  gap: 24px;
  align-items: center;
  padding: 6px 0 2px;
}

.hero-copy {
  max-width: 640px;
}

.eyebrow {
  color: var(--tea);
  font-size: 12px;
  font-weight: 760;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  margin-bottom: 8px;
}

.hero-copy h1 {
  color: var(--brown);
  font-size: 44px;
  line-height: 1.05;
  letter-spacing: 0;
  margin: 0 0 10px;
}

.hero-copy p {
  color: var(--muted);
  font-size: 15px;
  line-height: 1.65;
  margin: 0 0 16px;
  max-width: 540px;
}

.hero-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.hero-cta {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 12px 18px;
  border-radius: 999px;
  background: linear-gradient(135deg, #4b302b, #5c4038);
  color: #fffaf6;
  font-size: 14px;
  font-weight: 780;
  text-decoration: none;
  box-shadow: 0 12px 24px rgba(75, 48, 43, 0.16);
}

.hero-cta:hover {
  background: linear-gradient(135deg, #5a4038, #6a4a41);
}

.hero-chip {
  display: inline-flex;
  align-items: center;
  padding: 7px 11px;
  border-radius: 999px;
  background: var(--pink-soft);
  color: var(--brown);
  font-size: 12px;
  font-weight: 700;
}

.hero-cat {
  width: min(100%, 390px);
  justify-self: end;
  background: rgba(255, 255, 255, 0.84);
  border: 1px solid var(--line);
  border-radius: 24px;
  box-shadow: 0 18px 34px rgba(75, 48, 43, 0.08);
  padding: 14px;
}

.hero-cat-img {
  display: block;
  width: 100%;
  max-height: 300px;
  object-fit: cover;
  object-position: center 42%;
  border-radius: 18px;
}

.hero-cat-tag {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  color: var(--muted);
  font-size: 12px;
}

.hero-cat-tag strong {
  color: var(--brown);
  font-size: 13px;
}

#flow {
  max-width: 100%;
}

.flow-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 24px;
  box-shadow: 0 16px 34px rgba(75, 48, 43, 0.06);
  padding: 22px;
}

.flow-title {
  color: var(--brown);
  font-size: 20px;
  font-weight: 780;
  margin: 0 0 4px;
}

.flow-subtitle {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 14px;
}

.step-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-bottom: 14px;
}

.step-row {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid #efe3da;
  border-radius: 18px;
  background: #fffdfa;
}

.step-index {
  width: 34px;
  height: 34px;
  border-radius: 12px;
  display: grid;
  place-items: center;
  background: var(--tea-soft);
  color: var(--brown);
  font-size: 12px;
  font-weight: 780;
  flex: 0 0 auto;
}

.step-copy strong {
  display: block;
  color: var(--brown);
  font-size: 14px;
  margin-bottom: 2px;
}

.step-copy span {
  display: block;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

#resume-upload {
  border: 1.5px dashed #d7c3b5;
  border-radius: 18px;
  background: #fffdfa;
  min-height: 164px;
  transition: border-color 0.2s ease, background 0.2s ease;
}

#resume-upload:hover {
  border-color: var(--tea);
  background: #fff8f1;
}

#resume-upload .file-preview,
#resume-upload .upload-container {
  border: 0 !important;
  background: transparent !important;
}

#resume-upload label span {
  color: var(--brown) !important;
  font-weight: 700 !important;
}

#job-description textarea {
  min-height: 170px !important;
  border-radius: 18px !important;
  border: 1px solid var(--line) !important;
  background: #fffdfa !important;
  color: var(--ink) !important;
  line-height: 1.65 !important;
}

#job-description,
#job-description > div,
#job-description .wrap,
#job-description .container {
  background: transparent !important;
  border: 0 !important;
  box-shadow: none !important;
}

#job-description label,
#job-description label span {
  color: var(--brown) !important;
}

#job-description textarea:focus {
  border-color: var(--tea) !important;
  box-shadow: 0 0 0 3px rgba(198, 154, 122, 0.15) !important;
}

#analyze-button {
  margin-top: 14px;
}

#analyze-button button,
button#analyze-button {
  width: 100%;
  min-height: 52px;
  border: 0 !important;
  border-radius: 18px !important;
  background: linear-gradient(135deg, #4b302b, #5b4038) !important;
  color: #fffaf6 !important;
  font-size: 14px !important;
  font-weight: 780 !important;
  box-shadow: 0 12px 24px rgba(75, 48, 43, 0.16) !important;
}

#analyze-button button:hover,
button#analyze-button:hover {
  background: linear-gradient(135deg, #5a4038, #6a4a41) !important;
}

#status {
  min-height: 24px;
  margin-top: 10px;
}

#status p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  text-align: center;
}

.status-working {
  color: var(--brown);
  font-weight: 700;
}

.status-ready {
  color: var(--sage);
  font-weight: 700;
}

.status-error {
  color: #a35656;
  font-weight: 700;
}

#results {
  width: 100%;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 14px;
}

.result-card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: 20px;
  box-shadow: 0 14px 28px rgba(75, 48, 43, 0.06);
  padding: 18px;
  overflow: hidden;
}

#summary-card {
  grid-column: 1 / -1;
  background: linear-gradient(180deg, #fffdfa 0%, #ffffff 100%);
}

#skill-card {
  grid-column: 1 / -1;
}

.result-card h3,
.result-card h4 {
  color: var(--brown);
  margin: 0 0 10px;
  font-size: 16px;
  letter-spacing: 0.01em;
}

.result-card p,
.result-card li {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}

.result-card ul {
  margin: 0;
  padding-left: 18px;
}

.result-card pre,
.result-card code {
  white-space: pre-wrap;
  word-break: break-word;
}

.metric-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin: 8px 0 12px;
}

.metric {
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #ffffff;
  padding: 12px 14px;
}

.metric-label {
  color: var(--muted);
  font-size: 12px;
  margin-bottom: 8px;
}

.metric-value {
  color: var(--brown);
  font-size: 34px;
  font-weight: 820;
  line-height: 1;
  letter-spacing: 0;
}

.metric-note {
  color: var(--muted);
  font-size: 12px;
  margin-top: 6px;
}

.summary-note,
.summary-history {
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}

.summary-history {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.summary-history strong {
  color: var(--brown);
}

.source-note {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
  color: var(--muted);
  font-size: 12px;
}

.source-note ul {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
}

.source-note li {
  background: #f5f1ec;
  color: var(--brown);
  border-radius: 999px;
  padding: 6px 10px;
  font-size: 12px;
}

#optimization-card {
  grid-column: 1 / -1;
}

#optimization-card > .wrap,
#optimization-card .optimization-inner {
  width: 100%;
}

.optimization-header {
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
}

.optimization-heading h3 {
  margin: 0 0 4px;
  color: var(--brown);
  font-size: 19px;
}

.optimization-heading p {
  margin: 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.optimization-actions {
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.optimization-actions button {
  min-height: 34px !important;
  border-radius: 10px !important;
  border: 1px solid var(--line) !important;
  background: #fffdfa !important;
  color: var(--brown) !important;
  font-size: 12px !important;
  font-weight: 700 !important;
  box-shadow: none !important;
  white-space: nowrap;
}

.optimization-actions button:hover {
  border-color: var(--tea) !important;
  background: var(--tea-soft) !important;
}

#regenerate-resume-button button {
  border-color: var(--brown) !important;
  background: var(--brown) !important;
  color: #fffaf6 !important;
}

#regenerate-resume-button button:hover {
  background: #5d4038 !important;
}

.optimization-section {
  margin-top: 16px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
}

.optimization-section h4 {
  margin: 0 0 9px;
  color: var(--brown);
  font-size: 15px;
}

#optimization-highlights {
  border-radius: 14px;
  background: #fff8f4;
  padding: 12px 14px;
}

#optimization-highlights p,
#optimization-highlights li {
  margin-top: 0;
  margin-bottom: 5px;
}

#resume-view-toggle {
  margin: 0 0 10px;
}

#resume-view-toggle fieldset {
  border: 1px solid var(--line) !important;
  border-radius: 12px !important;
  background: #fffdfa !important;
  padding: 3px !important;
}

#resume-view-toggle label {
  color: var(--muted) !important;
  font-size: 12px !important;
}

#resume-view-toggle label.selected {
  border-radius: 9px !important;
  background: var(--tea-soft) !important;
  color: var(--brown) !important;
}

#resume-preview {
  min-height: 240px;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #fffefa;
  padding: 20px 22px;
}

#resume-preview h1 {
  margin-top: 0;
  color: var(--brown);
  font-size: 25px;
}

#resume-preview h2 {
  padding-bottom: 5px;
  border-bottom: 1px solid var(--line);
  color: var(--brown);
  font-size: 16px;
}

#resume-preview h3 {
  color: var(--brown);
  font-size: 14px;
}

#resume-preview p,
#resume-preview li {
  color: var(--ink);
  font-size: 13px;
  line-height: 1.65;
}

#pdf-preview {
  margin-top: 14px;
}

.pdf-preview-shell {
  overflow: hidden;
  width: 100%;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #f5f1ec;
  box-shadow: 0 10px 22px rgba(75, 48, 43, 0.06);
}

.pdf-preview-heading {
  padding: 11px 14px;
  border-bottom: 1px solid var(--line);
  color: var(--brown);
  background: #fffdfa;
  font-size: 13px;
  font-weight: 750;
}

.pdf-preview-shell iframe {
  display: block;
  width: 100%;
  height: min(780px, 78vh);
  border: 0;
  background: #ffffff;
}

#resume-comparison-row {
  align-items: stretch;
  gap: 12px;
  margin-top: 4px;
}

.resume-compare-panel {
  min-width: 0;
  border: 1px solid var(--line);
  border-radius: 16px;
  background: #fffefa;
  padding: 18px;
}

.compare-label {
  margin-bottom: 12px;
  color: var(--brown);
  font-size: 12px;
  font-weight: 780;
}

#original-comparison,
#optimized-comparison {
  min-height: 260px;
  overflow-wrap: anywhere;
}

#original-comparison h1,
#optimized-comparison h1 {
  color: var(--brown);
  font-size: 21px;
}

#original-comparison h2,
#optimized-comparison h2 {
  padding-bottom: 5px;
  border-bottom: 1px solid var(--line);
  color: var(--brown);
  font-size: 15px;
}

#original-comparison p,
#original-comparison li,
#optimized-comparison p,
#optimized-comparison li {
  color: var(--ink);
  font-size: 12px;
  line-height: 1.65;
}

.local-optimizer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid var(--line);
  gap: 10px;
}

.local-optimizer-heading strong,
.local-optimizer-heading span {
  display: block;
}

.local-optimizer-heading strong {
  color: var(--brown);
  font-size: 15px;
}

.local-optimizer-heading span,
.apply-suggestion-label {
  margin-top: 3px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}

.apply-suggestion-label {
  margin-top: 8px;
  padding-top: 14px;
  border-top: 1px solid var(--line);
  color: var(--brown);
  font-weight: 700;
}

#section-selector,
#suggestion-selector,
#focus-selector,
#custom-instruction {
  border-radius: 12px;
}

#local-optimize-button button,
button#local-optimize-button {
  border: 1px solid var(--brown) !important;
  border-radius: 12px !important;
  background: var(--brown) !important;
  color: #fffaf6 !important;
  font-size: 12px !important;
  font-weight: 750 !important;
}

#apply-suggestion-button button,
button#apply-suggestion-button {
  border: 1px solid #d7b7a8 !important;
  border-radius: 12px !important;
  background: var(--tea-soft) !important;
  color: var(--brown) !important;
  font-size: 12px !important;
  font-weight: 750 !important;
}

#local-status {
  min-height: 22px;
}

#local-status p {
  margin: 0;
  font-size: 12px;
}

.resume-empty {
  display: grid;
  min-height: 190px;
  place-items: center;
  padding: 26px;
  border: 1px dashed #d7c3b5;
  border-radius: 14px;
  background: #fffdfa;
  color: var(--muted);
  text-align: center;
}

.resume-empty strong {
  display: block;
  margin-bottom: 6px;
  color: var(--brown);
  font-size: 15px;
}

.resume-empty span {
  display: block;
  font-size: 12px;
  line-height: 1.6;
}

#optimization-suggestions p,
#optimization-suggestions li {
  line-height: 1.65;
}

#knowledge-sources {
  margin-top: 14px;
}

#about {
  max-width: 1200px;
  margin: 0 auto;
  padding-top: 6px;
  color: var(--muted);
  text-align: center;
  font-size: 12px;
  line-height: 1.7;
}

#footer {
  max-width: 1200px;
  margin: 6px auto 0;
  color: #9c8f89;
  font-size: 11px;
  text-align: center;
}

@media (max-width: 960px) {
  #results {
    grid-template-columns: 1fr;
  }

  .metric-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  #page {
    padding: 10px 12px 24px;
  }

  #topbar {
    align-items: center;
    flex-direction: row;
    gap: 6px;
  }

  .hero-copy h1 {
    font-size: 26px;
  }

  .hero-copy p {
    font-size: 13px;
    line-height: 1.5;
  }

  #hero {
    grid-template-columns: minmax(0, 1fr) 84px;
    gap: 10px;
    align-items: center;
  }

  .hero-cat {
    width: 84px;
    padding: 6px;
    border-radius: 16px;
  }

  .hero-cat-img {
    height: 96px;
    object-position: center 42%;
    border-radius: 12px;
  }

  .hero-cat-tag {
    display: block;
    margin-top: 6px;
    text-align: center;
  }

  .hero-cat-tag strong {
    font-size: 9px;
  }

  .hero-cat-tag span {
    display: none;
  }

  .brand-name {
    white-space: nowrap;
    font-size: 14px;
  }

  .brand-sub {
    display: none;
  }

  #brand {
    gap: 6px;
  }

  .brand-avatar {
    width: 32px;
    height: 32px;
    border-radius: 10px;
  }

  .top-links {
    gap: 9px;
    flex: 0 0 auto;
  }

  .top-links a {
    font-size: 12px;
  }

  .top-links {
    gap: 12px;
  }

  .flow-card {
    padding: 18px;
  }

  .result-card {
    padding: 16px;
  }

  .optimization-header {
    flex-direction: column;
  }

  .optimization-actions {
    width: 100%;
    justify-content: flex-start;
    flex-wrap: wrap;
  }

  #resume-comparison-row {
    flex-direction: column;
  }

  #resume-upload {
    min-height: 150px;
  }

  .pdf-preview-shell iframe {
    height: min(580px, 72vh);
  }
}
"""


def _hidden_card() -> Any:
    """Hide a result card until analysis is complete."""

    return gr.update(visible=False, value="")


def _hidden_cards() -> tuple[Any, Any, Any]:
    """Return hidden states for the three dashboard cards."""

    return (_hidden_card(), _hidden_card(), _hidden_card())


def _hidden_result_cards() -> tuple[Any, Any]:
    """Return hidden states for the score and skill cards."""

    return (_hidden_card(), _hidden_card())


def _empty_resume_markdown() -> str:
    """Return a calm empty state shown before a truthful rewrite is available."""

    return (
        "<div class='resume-empty'>"
        "<div><strong>你的优化版简历将在这里生成</strong>"
        "<span>AI 会结合原始简历、目标岗位和岗位要求，重新组织真实经历。</span>"
        "<span>点击上方「重新生成」开始。</span></div>"
        "</div>"
    )


def _prepare_download_file(
    optimized_resume: str,
    document_state: dict[str, object] | None = None,
) -> tuple[str | None, str]:
    """Generate a verified optimized PDF and return its user-facing status."""

    content = optimized_resume.strip()
    if not content or not document_state:
        return None, "完成分析后将生成优化版 PDF。"
    try:
        export = export_optimized_resume_pdf(
            document_state,
            content,
            runtime_dir=RUNTIME_DIR,
            working_file=str(document_state.get("workingFile", "")) or None,
        )
    except (ResumeExportError, DocumentValidationError) as exc:
        logger.exception("Optimized PDF export failed")
        return None, f"PDF 生成失败：{exc}"
    warnings = " ".join(export.warnings)
    detail = f"{export.message} {warnings}".strip()
    return export.pdf_path, detail


def _pdf_preview_html(pdf_path: str | None) -> str:
    """Embed the exact generated PDF so web and download previews stay aligned."""

    if not pdf_path:
        return ""
    resolved = Path(pdf_path).resolve()
    source = f"/gradio_api/file={quote(resolved.as_posix(), safe='/:')}#view=FitH"
    title = html.escape(resolved.name, quote=True)
    return (
        "<div class='pdf-preview-shell'>"
        "<div class='pdf-preview-heading'>最终优化版 PDF 预览</div>"
        f"<iframe src=\"{source}\" title=\"{title}\" loading=\"lazy\"></iframe>"
        "</div>"
    )


def _canonical_section_heading(raw_heading: str) -> str | None:
    """Map a contract heading to its canonical name, if it is recognized."""

    normalized = re.sub(r"\s+", " ", raw_heading.strip()).casefold()
    return _SECTION_ALIASES.get(normalized)


def _split_sections(markdown: str) -> dict[str, str]:
    """Split only known top-level contract headings from the agent Markdown.

    The optimized resume is allowed to contain its own ``#`` headings.  Once
    that section starts, the remainder is kept intact instead of being parsed
    as additional workflow sections.
    """

    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in markdown.splitlines():
        heading = re.match(r"^#\s+(.+?)\s*$", line)
        if heading and current != "Optimized Resume":
            canonical = _canonical_section_heading(heading.group(1))
            if canonical:
                current = canonical
                sections.setdefault(current, [])
                continue
        if current is not None:
            sections[current].append(line)
    return {name: "\n".join(lines).strip() for name, lines in sections.items()}


def _extract_score_and_note(section: str) -> tuple[str, str]:
    """Extract the numeric score and any extra rationale from a score block."""

    lines = [line.strip() for line in section.splitlines() if line.strip()]
    score = next((line for line in lines if re.fullmatch(r"\d{1,3}", line)), "--")
    note = "\n".join(line for line in lines if line != score).strip()
    return score, note


def _parse_history_summary(section: str) -> str:
    """Summarize the score history table as a short sentence."""

    rows: list[tuple[int, int, str]] = []
    for line in section.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 4 or not cells[0].isdigit() or not cells[1].isdigit():
            continue
        rows.append((int(cells[0]), int(cells[1]), cells[3]))

    if not rows:
        return "暂无评分变化记录。"
    if len(rows) == 1:
        iteration, score, action = rows[0]
        return f"第 {iteration} 轮 {score} 分，{action}。"

    first = rows[0]
    last = rows[-1]
    delta = last[1] - first[1]
    sign = "+" if delta >= 0 else ""
    return f"第 {first[0]} 轮 {first[1]} 分 → 第 {last[0]} 轮 {last[1]} 分（{sign}{delta}）。"


def _parse_sources(section: str) -> list[str]:
    """Extract knowledge source names from the agent output."""

    sources: list[str] = []
    for line in section.splitlines():
        match = re.match(r"^-\s+`?(.+?)`?$", line.strip())
        if match:
            sources.append(match.group(1))
    return sources or ["暂无命中的知识库文件"]


def _strip_outer_markdown_fence(markdown: str) -> str:
    """Remove an accidental outer Markdown code fence from model output."""

    lines = markdown.strip().splitlines()
    if len(lines) >= 2 and lines[0].strip().startswith("```") and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return markdown.strip()


def _bullet_items(markdown: str) -> list[str]:
    """Extract concise bullet text for the optimization highlights."""

    items: list[str] = []
    for line in markdown.splitlines():
        match = re.match(r"^\s*[-*+]\s+(.+?)\s*$", line)
        if match:
            items.append(match.group(1).strip())
    return items


def _render_highlights(suggestions: str) -> str:
    """Render at most five high-signal changes from the suggestions section."""

    items = _bullet_items(suggestions)[:5]
    if not items:
        items = [
            "保留真实经历，仅优化表达与结构。",
            "让与目标岗位相关的关键词更容易被识别。",
        ]
    return "\n".join(f"- {item}" for item in items)


def _render_sources_markdown(sources: list[str]) -> str:
    """Render knowledge-base source names as a compact Markdown list."""

    return "\n".join(f"- `{source}`" for source in sources)


def _render_summary_card(sections: dict[str, str]) -> str:
    """Render the score summary card."""

    score, note = _extract_score_and_note(sections.get("Resume Score", ""))
    history = _parse_history_summary(sections.get("Score History", ""))
    safe_note = html.escape(note) if note else "先看岗位要求，再看你的经历表达。"
    return (
        "### Resume Score\n\n"
        "<div class='metric-grid'>"
        "<div class='metric'>"
        "<div class='metric-label'>Resume Match Score</div>"
        f"<div class='metric-value'>{score}</div>"
        "<div class='metric-note'>/ 100</div>"
        "</div>"
        "<div class='metric'>"
        "<div class='metric-label'>ATS 评分</div>"
        f"<div class='metric-value'>{score}</div>"
        "<div class='metric-note'>关键词与结构综合</div>"
        "</div>"
        "</div>"
        f"<div class='summary-note'>{safe_note}</div>"
        f"<div class='summary-history'><strong>评分变化</strong><br>{html.escape(history)}</div>"
    )


def _render_skill_card(sections: dict[str, str]) -> str:
    """Render the skill-gap analysis card."""

    content = sections.get("Missing Skills", "").strip() or "- 暂无明显缺口。"
    return f"### Skill Gap\n\n{content}"


def _format_error_message(markdown: str) -> str:
    """Translate common workflow errors into clear Chinese UI copy."""

    error_message = markdown.strip()
    if error_message.startswith("Please upload"):
        error_message = "请先上传 PDF、DOC 或 DOCX 简历。"
    elif error_message.startswith("Please paste"):
        error_message = "请先粘贴目标岗位 JD。"
    elif error_message.startswith("Analysis failed:"):
        error_message = error_message.replace("Analysis failed:", "分析失败：", 1)
    if "OPENAI_API_KEY is not configured" in error_message:
        error_message = "分析失败：尚未配置 OPENAI_API_KEY。请复制 .env.example 为 .env 并填写 API Key。"
    return error_message


def _hidden_analysis_outputs(status_message: str) -> tuple[Any, ...]:
    """Reset every result component while an analysis job is pending."""

    return (
        status_message,
        *_hidden_result_cards(),
        gr.update(visible=False),
        "",
        "",
        gr.update(value="优化后简历"),
        _empty_resume_markdown(),
        gr.update(value="", visible=False),
        gr.update(visible=False),
        "",
        "",
        "",
        gr.update(choices=[], value=None, interactive=False),
        gr.update(choices=[], value=None, interactive=False),
        "",
        gr.update(value=None, interactive=False),
        "",
        "",
        {},
    )


def _preserved_analysis_outputs(status_message: str) -> tuple[Any, ...]:
    """Update only the status while preserving all existing analysis results."""

    return (status_message, *(gr.skip() for _ in range(19)))


def _format_result(
    markdown: str,
    original_resume: str = "",
    document_state: dict[str, object] | None = None,
) -> tuple[Any, ...]:
    """Map the agent Markdown contract into dashboard and resume-preview data."""

    normalized_markdown = _strip_outer_markdown_fence(markdown or "")
    if not normalized_markdown.startswith("# "):
        error_message = _format_error_message(normalized_markdown)
        return _hidden_analysis_outputs(
            f"<span class='status-error'>{html.escape(error_message)}</span>"
        )

    sections = _split_sections(normalized_markdown)
    suggestions = sections.get("Suggestions", "").strip() or "- 暂无额外建议。"
    highlights = sections.get("Optimization Highlights", "").strip()
    explanations = sections.get("Why It Changed", "").strip()
    optimized_resume = _strip_outer_markdown_fence(
        sections.get("Optimized Resume", "").strip()
    )
    original_resume = (
        original_resume.strip()
        or _strip_outer_markdown_fence(sections.get("Original Resume", "").strip())
    )
    resume_preview = optimized_resume or _empty_resume_markdown()
    sources = _parse_sources(sections.get("Knowledge Used", ""))
    section_titles = list_resume_section_titles(optimized_resume)
    suggestion_items = _bullet_items(suggestions)
    download_path, export_message = _prepare_download_file(
        optimized_resume,
        document_state,
    )
    highlights_output = highlights or _render_highlights(suggestions)
    if explanations:
        highlights_output += f"\n\n### 为什么这样改\n\n{explanations}"
    if document_state:
        highlights_output += f"\n\n> PDF 导出：{export_message}"
    status_message = (
        "<span class='status-ready'>🐾 分析完成，优化版 PDF 已生成。</span>"
        if download_path
        else (
            f"<span class='status-error'>分析完成，但 {html.escape(export_message)}</span>"
            if document_state
            else "<span class='status-ready'>🐾 分析完成，可以查看结果。</span>"
        )
    )
    return (
        status_message,
        gr.update(visible=True, value=_render_summary_card(sections)),
        gr.update(visible=True, value=_render_skill_card(sections)),
        gr.update(visible=True),
        suggestions,
        highlights_output,
        gr.update(value="优化后简历"),
        resume_preview,
        gr.update(
            value=_pdf_preview_html(download_path),
            visible=bool(download_path),
        ),
        gr.update(visible=False),
        original_resume,
        optimized_resume,
        _render_sources_markdown(sources),
        gr.update(
            choices=section_titles,
            value=section_titles[0] if section_titles else None,
            interactive=bool(section_titles),
        ),
        gr.update(
            choices=suggestion_items,
            value=suggestion_items[0] if suggestion_items else None,
            interactive=bool(suggestion_items),
        ),
        "",
        gr.update(value=download_path, interactive=bool(download_path)),
        optimized_resume,
        original_resume.strip(),
        document_state or {},
    )


def build_demo() -> gr.Blocks:
    """Build the single-page ResumeFlow AI interface."""

    agent = ResumeAgent()
    initial_status = "<span class='status-idle'>上传 PDF、DOC 或 DOCX 简历并填写 JD 后，点击开始分析。</span>"

    def start_analysis(
        resume_path: str | None,
        job_description: str,
    ) -> tuple[Any, ...]:
        """Return an immediate status update before the queued workflow starts."""

        if not resume_path:
            return _format_result("Please upload a resume before starting analysis.")
        if not job_description or not job_description.strip():
            return _format_result("Please paste a job description before starting analysis.")
        return _hidden_analysis_outputs(
            "<span class='status-working'>🐱 正在阅读你的简历...</span>"
        )

    def analyze_resume(
        resume_path: str | None,
        job_description: str,
    ) -> Generator[tuple[Any, ...], None, None]:
        """Run the agent while streaming simple loading states."""

        if not resume_path:
            yield _format_result("Please upload a resume before starting analysis.")
            return
        if not job_description or not job_description.strip():
            yield _format_result("Please paste a job description before starting analysis.")
            return

        yield _hidden_analysis_outputs(
            "<span class='status-working'>🐱 正在分析岗位需求...</span>"
        )
        yield _hidden_analysis_outputs(
            "<span class='status-working'>🐱 正在优化关键词...</span>"
        )
        yield _hidden_analysis_outputs(
            "<span class='status-working'>🐱 正在生成最终简历...</span>"
        )
        document_state: dict[str, object] = {}
        try:
            original_name, declared_mime_type = _uploaded_metadata(resume_path)
            document = preserve_uploaded_document(
                resume_path,
                runtime_dir=RUNTIME_DIR,
                original_name=original_name,
                declared_mime_type=declared_mime_type,
            )
            parsed = parse_resume_document(document, runtime_dir=RUNTIME_DIR)
            original_resume = parsed.resume_text
            document_state = parsed.document.to_state()
            document_state["workingFile"] = parsed.working_file
            result = agent.analyze_text(parsed.resume_text, job_description)
        except Exception as exc:  # Keep unexpected errors visible in the page.
            logger.exception("Resume analysis event failed")
            result = f"Analysis failed: {exc}"
            original_resume = ""
        if _strip_outer_markdown_fence(result or "").startswith("# "):
            yield _hidden_analysis_outputs(
                "<span class='status-working'>正在生成 PDF...</span>"
            )
            yield _hidden_analysis_outputs(
                "<span class='status-working'>正在保留原始排版...</span>"
            )
            yield _hidden_analysis_outputs(
                "<span class='status-working'>正在生成优化版...</span>"
            )
        yield _format_result(result, original_resume, document_state)

    def regenerate_resume(
        resume_path: str | None,
        job_description: str,
        existing_original_resume: str,
    ) -> Generator[tuple[Any, ...], None, None]:
        """Regenerate atomically so a failed request cannot erase the last result."""

        if not resume_path:
            yield _preserved_analysis_outputs(
                "<span class='status-error'>请先上传 PDF、DOC 或 DOCX 简历。</span>"
            )
            return
        if not job_description or not job_description.strip():
            yield _preserved_analysis_outputs(
                "<span class='status-error'>请先粘贴目标岗位 JD。</span>"
            )
            return
        yield _preserved_analysis_outputs(
            "<span class='status-working'>🐱 正在重新生成完整简历...</span>"
        )
        document_state: dict[str, object] = {}
        try:
            original_name, declared_mime_type = _uploaded_metadata(resume_path)
            document = preserve_uploaded_document(
                resume_path,
                runtime_dir=RUNTIME_DIR,
                original_name=original_name,
                declared_mime_type=declared_mime_type,
            )
            parsed = parse_resume_document(document, runtime_dir=RUNTIME_DIR)
            existing_original_resume = parsed.resume_text
            document_state = parsed.document.to_state()
            document_state["workingFile"] = parsed.working_file
            result = agent.analyze_text(parsed.resume_text, job_description)
        except Exception as exc:
            logger.exception("Resume regeneration event failed")
            result = f"Analysis failed: {exc}"
        normalized = _strip_outer_markdown_fence(result or "")
        if not normalized.startswith("# "):
            message = html.escape(_format_error_message(normalized))
            yield _preserved_analysis_outputs(
                f"<span class='status-error'>{message}</span>"
            )
            return
        yield _preserved_analysis_outputs(
            "<span class='status-working'>正在保留原始排版并生成 PDF...</span>"
        )
        yield _format_result(normalized, existing_original_resume, document_state)

    def start_regeneration() -> str:
        """Show immediate feedback before the queued regeneration starts."""

        return "<span class='status-working'>🐱 正在准备重新生成...</span>"

    def start_focused_rewrite(section_title: str | None) -> str:
        """Show immediate feedback before a queued section rewrite starts."""

        if not section_title:
            return "<span class='status-error'>请先选择要优化的简历模块。</span>"
        return f"<span class='status-working'>🐱 已准备优化「{html.escape(section_title)}」...</span>"

    def select_resume_view(
        view: str,
        optimized_resume: str,
        original_resume: str,
    ) -> tuple[Any, Any, str, str]:
        """Switch between optimized, original, and responsive comparison views."""

        optimized = optimized_resume.strip() or _empty_resume_markdown()
        original = original_resume.strip() or "暂时无法读取原始简历文本。"
        if view == "左右对比":
            return (
                gr.update(value=optimized, visible=False),
                gr.update(visible=True),
                original,
                optimized,
            )
        if view == "原始简历":
            return (
                gr.update(value=original, visible=True),
                gr.update(visible=False),
                original,
                optimized,
            )
        return (
            gr.update(value=optimized, visible=True),
            gr.update(visible=False),
            original,
            optimized,
        )

    def _local_progress(message: str) -> tuple[Any, ...]:
        """Update local-rewrite status without mutating the current resume."""

        return (message, *(gr.skip() for _ in range(10)))

    def _rewrite_section_impl(
        optimized_resume: str,
        original_resume: str,
        job_description: str,
        section_title: str | None,
        instruction: str,
        current_highlights: str,
        document_state: dict[str, object],
    ) -> Generator[tuple[Any, ...], None, None]:
        """Run one focused rewrite and atomically replace the selected section."""

        if not optimized_resume.strip():
            yield _local_progress(
                "<span class='status-error'>请先生成完整的优化版简历。</span>"
            )
            return
        if not section_title:
            yield _local_progress(
                "<span class='status-error'>请先选择要优化的简历模块。</span>"
            )
            return
        section = get_resume_section(optimized_resume, section_title)
        if section is None:
            yield _local_progress(
                "<span class='status-error'>没有找到所选模块，请重新生成完整简历后再试。</span>"
            )
            return

        yield _local_progress(
            f"<span class='status-working'>🐱 正在重新优化「{html.escape(section_title)}」...</span>"
        )
        try:
            rewrite = agent.rewrite_section(
                original_resume_text=original_resume,
                current_resume_markdown=optimized_resume,
                section_title=section_title,
                section_markdown=section.markdown,
                job_description=job_description,
                instruction=instruction,
            )
            updated_resume = replace_resume_section(
                optimized_resume,
                section_title,
                rewrite.section_markdown,
            )
        except Exception as exc:
            logger.exception("Focused resume rewrite failed")
            yield _local_progress(
                f"<span class='status-error'>局部优化失败：{html.escape(str(exc))}</span>"
            )
            return

        highlights = _bullet_items(current_highlights)
        if rewrite.highlight and rewrite.highlight not in highlights:
            highlights.append(rewrite.highlight)
        highlights_markdown = _render_highlights(
            "\n".join(f"- {item}" for item in highlights[-5:])
        )
        section_titles = list_resume_section_titles(updated_resume)
        yield _local_progress(
            "<span class='status-working'>正在重新生成优化版 PDF...</span>"
        )
        download_path, export_message = _prepare_download_file(
            updated_resume,
            document_state,
        )
        highlights_markdown += f"\n\n> PDF 导出：{export_message}"
        completion_status = (
            "<span class='status-ready'>✓ 当前模块和优化版 PDF 已更新。</span>"
            if download_path
            else f"<span class='status-error'>模块已更新，但 {html.escape(export_message)}</span>"
        )
        yield (
            completion_status,
            gr.update(value=updated_resume, visible=True),
            gr.update(
                value=_pdf_preview_html(download_path),
                visible=bool(download_path),
            ),
            gr.update(value="优化后简历"),
            gr.update(visible=False),
            original_resume,
            updated_resume,
            updated_resume,
            gr.update(value=download_path, interactive=bool(download_path)),
            highlights_markdown,
            gr.update(
                choices=section_titles,
                value=section_title if section_title in section_titles else None,
                interactive=bool(section_titles),
            ),
        )

    def rewrite_selected_section(
        optimized_resume: str,
        original_resume: str,
        job_description: str,
        section_title: str | None,
        focus: str,
        custom_instruction: str,
        current_highlights: str,
        document_state: dict[str, object],
    ) -> Generator[tuple[Any, ...], None, None]:
        """Translate the selected focus into one model instruction."""

        focus_instructions = {
            "更专业": "在不增加事实的前提下，让表达更专业、具体。",
            "更简洁": "删除重复和低价值措辞，让内容更简洁。",
            "更突出成果": "仅基于原文已有成果强化成果导向，不新增数字。",
            "更突出 AI 能力": "只强化原文已经存在的 AI 相关能力和经历。",
            "更符合目标岗位": "自然对齐目标岗位，但不要添加原文没有的技能或经历。",
        }
        if focus == "自定义":
            instruction = custom_instruction.strip()
            if not instruction:
                yield _local_progress(
                    "<span class='status-error'>请填写自定义优化要求。</span>"
                )
                return
        else:
            instruction = focus_instructions.get(focus, focus_instructions["更专业"])
        yield from _rewrite_section_impl(
            optimized_resume,
            original_resume,
            job_description,
            section_title,
            instruction,
            current_highlights,
            document_state,
        )

    def apply_selected_suggestion(
        optimized_resume: str,
        original_resume: str,
        job_description: str,
        section_title: str | None,
        suggestion: str | None,
        current_highlights: str,
        document_state: dict[str, object],
    ) -> Generator[tuple[Any, ...], None, None]:
        """Apply one selected suggestion to one explicitly selected section."""

        if not suggestion:
            yield _local_progress(
                "<span class='status-error'>请先选择一条要应用的建议。</span>"
            )
            return
        yield from _rewrite_section_impl(
            optimized_resume,
            original_resume,
            job_description,
            section_title,
            f"将这条建议应用到当前模块：{suggestion}",
            current_highlights,
            document_state,
        )

    with gr.Blocks(
        title="ResumeFlow AI",
        delete_cache=(60 * 60, UPLOAD_MAX_AGE_SECONDS),
    ) as demo:
        with gr.Column(elem_id="page"):
            with gr.Column(elem_id="shell"):
                gr.HTML(
                    f"""
                    <div id="topbar">
                      <div id="brand">
                        <img class="brand-avatar" src="{CAT_IMAGE_SRC}" alt="暹罗猫 Logo"
                             onerror="this.onerror=null;this.src='{FALLBACK_IMAGE_SRC}';">
                        <div class="brand-copy">
                          <div class="brand-name">ResumeFlow AI</div>
                          <div class="brand-sub">更温暖的简历智能助手</div>
                        </div>
                      </div>
                      <div class="top-links">
                        <a href="https://github.com/strawberrynine/resume-agent-mvp" target="_blank" rel="noreferrer">GitHub</a>
                        <a href="#about">About</a>
                      </div>
                    </div>
                    """
                )

                gr.HTML(
                    f"""
                    <section id="hero">
                      <div class="hero-copy">
                        <div class="eyebrow">AI 简历智能助手</div>
                        <h1>让你的经历，<br>被合适的职位看见。</h1>
                        <p>AI 帮助你分析岗位匹配度，优化简历表达。</p>
                        <div class="hero-actions">
                          <a class="hero-cta" href="#flow">开始分析</a>
                          <span class="hero-chip">温柔陪伴</span>
                        </div>
                      </div>
                      <div class="hero-cat">
                        <img class="hero-cat-img" src="{CAT_IMAGE_SRC}" alt="暹罗猫 AI 助手"
                             onerror="this.onerror=null;this.src='{FALLBACK_IMAGE_SRC}';">
                        <div class="hero-cat-tag">
                          <strong>你的 AI 求职伙伴</strong>
                          <span>温柔但专业</span>
                        </div>
                      </div>
                    </section>
                    """
                )

                with gr.Column(elem_id="flow"):
                    with gr.Column(elem_classes=["flow-card"]):
                        gr.HTML(
                            """
                            <h2 class="flow-title">开始你的简历分析</h2>
                            <p class="flow-subtitle">按顺序完成这三个动作：上传简历、输入 JD、开始分析。结果会在下方自动展开。</p>
                            <div class="step-list">
                              <div class="step-row">
                                <div class="step-index">1</div>
                                <div class="step-copy">
                                  <strong>上传简历</strong>
                                  <span>支持 PDF / DOC / DOCX，拖拽或点击均可上传。</span>
                                </div>
                              </div>
                            </div>
                            """
                        )
                        resume_file = _resume_file_component(
                            label="PDF / DOC / DOCX 简历",
                            file_types=[".pdf", ".doc", ".docx"],
                            type="filepath",
                            elem_id="resume-upload",
                        )
                        gr.HTML(
                            """
                            <div class="step-list">
                              <div class="step-row">
                                <div class="step-index">2</div>
                                <div class="step-copy">
                                  <strong>输入目标岗位 JD</strong>
                                  <span>粘贴岗位描述，AI 会理解职位重点。</span>
                                </div>
                              </div>
                            </div>
                            """
                        )
                        job_description = gr.Textbox(
                            label="目标岗位 JD",
                            lines=8,
                            placeholder="粘贴你想申请的岗位描述…",
                            elem_id="job-description",
                        )
                        gr.HTML(
                            """
                            <div class="step-list">
                              <div class="step-row">
                                <div class="step-index">3</div>
                                <div class="step-copy">
                                  <strong>开始 AI 分析</strong>
                                  <span>系统会完成解析、匹配、优化与重写。</span>
                                </div>
                              </div>
                            </div>
                            """
                        )
                        analyze_button = gr.Button(
                            "🐾 开始分析并生成优化版简历",
                            variant="primary",
                            elem_id="analyze-button",
                        )
                        status = gr.Markdown(initial_status, elem_id="status")

                with gr.Column(elem_id="results"):
                    summary_output = gr.Markdown("", elem_id="summary-card", elem_classes=["result-card"], visible=False)
                    skill_output = gr.Markdown("", elem_id="skill-card", elem_classes=["result-card"], visible=False)
                    with gr.Column(
                        elem_id="optimization-card",
                        elem_classes=["result-card"],
                        visible=False,
                    ) as optimization_panel:
                        with gr.Row(elem_classes=["optimization-header"]):
                            gr.HTML(
                                """
                                <div class="optimization-heading">
                                  <h3>优化后的简历</h3>
                                  <p>AI 已结合目标岗位，重新组织你的真实经历。</p>
                                </div>
                                """
                            )
                            with gr.Row(elem_classes=["optimization-actions"]):
                                regenerate_button = gr.Button(
                                    "重新生成",
                                    elem_id="regenerate-resume-button",
                                    size="sm",
                                )
                                copy_button = gr.Button(
                                    "复制全文",
                                    elem_id="copy-resume-button",
                                    size="sm",
                                )
                                download_button = gr.DownloadButton(
                                    "下载优化后的 PDF",
                                    elem_id="download-resume-button",
                                    size="sm",
                                    interactive=False,
                                )

                        with gr.Column(elem_classes=["optimization-inner"]):
                            gr.HTML("<div class='optimization-section'><h4>本次优化亮点</h4></div>")
                            optimization_highlights = gr.Markdown(
                                "",
                                elem_id="optimization-highlights",
                                show_label=False,
                                container=False,
                            )

                            gr.HTML("<div class='optimization-section'><h4>简历优化建议</h4></div>")
                            optimization_suggestions = gr.Markdown(
                                "",
                                elem_id="optimization-suggestions",
                                show_label=False,
                                container=False,
                            )

                            resume_view_toggle = gr.Radio(
                                ["优化后简历", "原始简历", "左右对比"],
                                value="优化后简历",
                                label="查看版本",
                                elem_id="resume-view-toggle",
                                show_label=True,
                            )
                            resume_preview = gr.Markdown(
                                _empty_resume_markdown(),
                                elem_id="resume-preview",
                                show_label=False,
                                container=False,
                                buttons=["copy"],
                                sanitize_html=True,
                                line_breaks=True,
                            )

                            pdf_preview = gr.HTML(
                                "",
                                elem_id="pdf-preview",
                                visible=False,
                            )

                            with gr.Row(
                                elem_id="resume-comparison-row",
                                visible=False,
                            ) as comparison_row:
                                with gr.Column(elem_classes=["resume-compare-panel"]):
                                    gr.HTML("<div class='compare-label'>原始简历</div>")
                                    original_comparison = gr.Markdown(
                                        "",
                                        elem_id="original-comparison",
                                        show_label=False,
                                        container=False,
                                        sanitize_html=True,
                                        line_breaks=True,
                                        buttons=["copy"],
                                    )
                                with gr.Column(elem_classes=["resume-compare-panel"]):
                                    gr.HTML("<div class='compare-label'>优化后简历</div>")
                                    optimized_comparison = gr.Markdown(
                                        "",
                                        elem_id="optimized-comparison",
                                        show_label=False,
                                        container=False,
                                        sanitize_html=True,
                                        line_breaks=True,
                                        buttons=["copy"],
                                    )

                            with gr.Column(elem_classes=["local-optimizer"]):
                                gr.HTML(
                                    """
                                    <div class='local-optimizer-heading'>
                                      <strong>局部 AI 优化</strong>
                                      <span>只重写所选模块，其他内容保持不变。</span>
                                    </div>
                                    """
                                )
                                section_selector = gr.Dropdown(
                                    choices=[],
                                    value=None,
                                    label="选择简历模块",
                                    interactive=False,
                                    elem_id="section-selector",
                                )
                                focus_selector = gr.Radio(
                                    [
                                        "更专业",
                                        "更简洁",
                                        "更突出成果",
                                        "更突出 AI 能力",
                                        "更符合目标岗位",
                                        "自定义",
                                    ],
                                    value="更专业",
                                    label="优化重点",
                                    elem_id="focus-selector",
                                )
                                custom_instruction = gr.Textbox(
                                    label="自定义要求（选择“自定义”时填写）",
                                    lines=2,
                                    placeholder="例如：压缩到 3 条要点，并突出跨团队协作。",
                                    elem_id="custom-instruction",
                                )
                                local_optimize_button = gr.Button(
                                    "AI 重新优化当前模块",
                                    elem_id="local-optimize-button",
                                    size="sm",
                                )

                                gr.HTML(
                                    "<div class='apply-suggestion-label'>将分析建议应用到当前模块</div>"
                                )
                                suggestion_selector = gr.Dropdown(
                                    choices=[],
                                    value=None,
                                    label="选择一条建议",
                                    interactive=False,
                                    elem_id="suggestion-selector",
                                )
                                apply_suggestion_button = gr.Button(
                                    "应用到简历",
                                    elem_id="apply-suggestion-button",
                                    size="sm",
                                )
                                local_status = gr.Markdown(
                                    "",
                                    elem_id="local-status",
                                    show_label=False,
                                    container=False,
                                )

                            knowledge_output = gr.Markdown(
                                "",
                                elem_id="knowledge-sources",
                                show_label=False,
                                container=False,
                            )

                    optimized_resume_state = gr.State("")
                    original_resume_state = gr.State("")
                    document_state = gr.State({})

                gr.HTML(
                    """
                    <section id="about">
                      <strong>About</strong><br>
                      ResumeFlow AI 是一个单页 AI Agent Demo，支持 PDF、DOC、DOCX 解析、JD 理解、RAG、LLM 工作流与优化版 PDF 导出。
                    </section>
                    """
                )

                gr.HTML("<div id='footer'>ResumeFlow AI · 为认真求职准备的一次温柔分析</div>")

        analysis_outputs = [
            status,
            summary_output,
            skill_output,
            optimization_panel,
            optimization_suggestions,
            optimization_highlights,
            resume_view_toggle,
            resume_preview,
            pdf_preview,
            comparison_row,
            original_comparison,
            optimized_comparison,
            knowledge_output,
            section_selector,
            suggestion_selector,
            local_status,
            download_button,
            optimized_resume_state,
            original_resume_state,
            document_state,
        ]

        start_event = analyze_button.click(
            fn=start_analysis,
            inputs=[resume_file, job_description],
            outputs=analysis_outputs,
            show_progress="hidden",
            queue=False,
        )
        start_event.then(
            fn=analyze_resume,
            inputs=[resume_file, job_description],
            outputs=analysis_outputs,
            show_progress="minimal",
            queue=True,
            stream_every=0.2,
            concurrency_id="resume-llm",
            concurrency_limit=1,
        )

        regenerate_event = regenerate_button.click(
            fn=start_regeneration,
            inputs=[],
            outputs=[status],
            show_progress="hidden",
            queue=False,
        )
        regenerate_event.then(
            fn=regenerate_resume,
            inputs=[resume_file, job_description, original_resume_state],
            outputs=analysis_outputs,
            show_progress="minimal",
            queue=True,
            stream_every=0.2,
            concurrency_id="resume-llm",
            concurrency_limit=1,
        )

        resume_view_toggle.change(
            fn=select_resume_view,
            inputs=[resume_view_toggle, optimized_resume_state, original_resume_state],
            outputs=[
                resume_preview,
                comparison_row,
                original_comparison,
                optimized_comparison,
            ],
            show_progress="hidden",
            queue=False,
        )

        local_outputs = [
            local_status,
            resume_preview,
            pdf_preview,
            resume_view_toggle,
            comparison_row,
            original_comparison,
            optimized_comparison,
            optimized_resume_state,
            download_button,
            optimization_highlights,
            section_selector,
        ]

        local_start_event = local_optimize_button.click(
            fn=start_focused_rewrite,
            inputs=[section_selector],
            outputs=[local_status],
            show_progress="hidden",
            queue=False,
        )
        local_start_event.then(
            fn=rewrite_selected_section,
            inputs=[
                optimized_resume_state,
                original_resume_state,
                job_description,
                section_selector,
                focus_selector,
                custom_instruction,
                optimization_highlights,
                document_state,
            ],
            outputs=local_outputs,
            show_progress="minimal",
            queue=True,
            concurrency_id="resume-llm",
            concurrency_limit=1,
        )

        apply_start_event = apply_suggestion_button.click(
            fn=start_focused_rewrite,
            inputs=[section_selector],
            outputs=[local_status],
            show_progress="hidden",
            queue=False,
        )
        apply_start_event.then(
            fn=apply_selected_suggestion,
            inputs=[
                optimized_resume_state,
                original_resume_state,
                job_description,
                section_selector,
                suggestion_selector,
                optimization_highlights,
                document_state,
            ],
            outputs=local_outputs,
            show_progress="minimal",
            queue=True,
            concurrency_id="resume-llm",
            concurrency_limit=1,
        )

        # Reuse Gradio's tested Markdown copy affordance. This keeps clipboard
        # access client-side and avoids duplicating browser permission handling.
        copy_button.click(
            fn=None,
            inputs=[resume_view_toggle],
            outputs=[],
            show_progress="hidden",
            queue=False,
            js="""
            (view) => {
              const selector = view === '左右对比'
                ? '#optimized-comparison'
                : '#resume-preview';
              const copyControl = document.querySelector(selector)?.querySelector('button');
              copyControl?.click();
              return [];
            }
            """,
        )

        # Keep one analysis job active at a time and flush status updates frequently.
        demo.queue(status_update_rate=0.2, default_concurrency_limit=1)

    return demo


if __name__ == "__main__":
    log_level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    build_demo().launch(
        server_name=os.getenv("GRADIO_SERVER_NAME", "127.0.0.1"),
        server_port=int(os.getenv("PORT", "7860")),
        css=CSS,
        theme=gr.themes.Base(),
        allowed_paths=[str(ASSET_DIR), str(EXPORT_DIR)],
        max_file_size=MAX_FILE_SIZE_BYTES,
    )
