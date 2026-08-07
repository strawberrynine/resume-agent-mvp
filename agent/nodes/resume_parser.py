"""Resume Parser workflow node."""

from services.pdf_parser import extract_pdf_text

from .contracts import ResumeParserInput, ResumeParserOutput


class ResumeParserNode:
    """Convert an uploaded PDF into text for downstream analysis."""

    def run(self, node_input: ResumeParserInput) -> ResumeParserOutput:
        """Extract text from the supplied PDF path."""
        return ResumeParserOutput(resume_text=extract_pdf_text(node_input.pdf_path))
