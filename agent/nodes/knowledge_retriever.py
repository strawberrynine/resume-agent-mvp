"""Knowledge Retriever workflow node."""

from dataclasses import dataclass, field
from pathlib import Path

from services.knowledge_base import KnowledgeBase, RetrievedChunk


@dataclass(frozen=True)
class KnowledgeRetrieverInput:
    """Query supplied to the local knowledge retriever."""

    query: str
    top_k: int = 4


@dataclass(frozen=True)
class KnowledgeRetrieverOutput:
    """Relevant knowledge chunks returned to downstream workflow nodes."""

    chunks: list[RetrievedChunk] = field(default_factory=list)


class KnowledgeRetrieverNode:
    """Retrieve relevant guidance from the repository knowledge directory."""

    def __init__(self, knowledge_dir: Path | None = None, top_k: int = 4) -> None:
        """Initialize a reusable retriever over PDF, Markdown, and TXT files."""
        self.top_k = top_k
        self.knowledge_base = KnowledgeBase(root_dir=knowledge_dir)

    def run(self, node_input: KnowledgeRetrieverInput) -> KnowledgeRetrieverOutput:
        """Return the most relevant knowledge fragments for the supplied query."""
        return KnowledgeRetrieverOutput(
            chunks=self.knowledge_base.retrieve(node_input.query, top_k=node_input.top_k)
        )
