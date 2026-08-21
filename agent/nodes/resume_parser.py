"""Resume Parser workflow node."""

from services.document_parser import parse_resume_document

from .contracts import ResumeParserInput, ResumeParserOutput


class ResumeParserNode:
    """Convert an uploaded PDF, DOC, or DOCX into downstream text."""

    def run(self, node_input: ResumeParserInput) -> ResumeParserOutput:
        """Extract text and retain original-file metadata for later export."""

        file_path = node_input.file_path or node_input.pdf_path
        parsed = parse_resume_document(file_path)
        return ResumeParserOutput(
            resume_text=parsed.resume_text,
            original_file=parsed.document.to_state(),
            working_file=parsed.working_file,
            warnings=list(parsed.warnings),
        )
