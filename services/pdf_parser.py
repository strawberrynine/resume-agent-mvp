"""PDF text extraction service."""

import pymupdf


def extract_pdf_text(pdf_path: str) -> str:
    """Extract text from every page of a PDF and validate that it is not empty."""
    document = pymupdf.open(pdf_path)
    try:
        text = "\n\n".join(page.get_text() for page in document).strip()
    finally:
        document.close()

    if not text:
        raise ValueError("The PDF does not contain extractable text.")
    return text
