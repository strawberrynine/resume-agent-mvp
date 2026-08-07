"""Local knowledge-base loading and lightweight retrieval service."""

from dataclasses import dataclass
import logging
from pathlib import Path
import re

from services.pdf_parser import extract_pdf_text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved knowledge fragment with its source and lexical score."""

    source: str
    content: str
    score: float


class KnowledgeBase:
    """Load supported local files and retrieve relevant text fragments."""

    SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}

    def __init__(
        self,
        root_dir: Path | None = None,
        chunk_size: int = 1200,
        chunk_overlap: int = 150,
    ) -> None:
        """Initialize a file-backed knowledge base with bounded text chunks."""
        self.root_dir = root_dir or Path(__file__).resolve().parents[1] / "knowledge"
        if chunk_size <= 0 or chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_size must be positive and larger than chunk_overlap.")
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self._chunks = self._load_chunks()

    def retrieve(self, query: str, top_k: int = 4) -> list[RetrievedChunk]:
        """Return the highest-overlap knowledge chunks for a query."""
        if top_k <= 0:
            return []
        query_terms = _terms(query)
        if not self._chunks:
            logger.warning("Knowledge base is empty: %s", self.root_dir)
            return []

        scored = []
        for source, content in self._chunks:
            content_terms = _terms(content)
            overlap = len(query_terms & content_terms)
            phrase_bonus = 1 if query.strip().lower() in content.lower() else 0
            score = (overlap / max(len(query_terms), 1)) + phrase_bonus
            scored.append(RetrievedChunk(source=source, content=content, score=score))

        scored.sort(key=lambda chunk: chunk.score, reverse=True)
        selected = [chunk for chunk in scored if chunk.score > 0][:top_k]
        return selected or scored[:top_k]

    def _load_chunks(self) -> list[tuple[str, str]]:
        """Read supported files and split each document into overlapping chunks."""
        if not self.root_dir.exists():
            return []

        chunks: list[tuple[str, str]] = []
        for path in sorted(self.root_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in self.SUPPORTED_SUFFIXES:
                continue
            try:
                text = _read_supported_file(path).strip()
            except (OSError, ValueError) as exc:
                logger.warning("Skipping knowledge file %s: %s", path, exc)
                continue
            for chunk in _chunk_text(text, self.chunk_size, self.chunk_overlap):
                chunks.append((str(path.relative_to(self.root_dir)), chunk))
        logger.info("Loaded %d knowledge chunks from %s", len(chunks), self.root_dir)
        return chunks


def _read_supported_file(path: Path) -> str:
    """Read text from a PDF, Markdown, or plain-text knowledge file."""
    if path.suffix.lower() == ".pdf":
        return extract_pdf_text(str(path))
    return path.read_text(encoding="utf-8")


def _chunk_text(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    """Split text into bounded overlapping character windows."""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end].strip())
        if end == len(text):
            break
        start = end - chunk_overlap
    return [chunk for chunk in chunks if chunk]


def _terms(text: str) -> set[str]:
    """Normalize Unicode words and common technology tokens for matching."""
    return set(re.findall(r"[\w+#.-]+", text.lower()))
