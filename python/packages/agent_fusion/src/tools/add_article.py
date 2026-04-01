"""
AddArticleTool: FunctionToolWithType that stores a full Markdown article
into the ArticleStore for later GraphRAG indexing.

Replaces SliceToChunkTool — no manual chunking, GraphRAG handles it.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Annotated

from base.handoff import FunctionToolWithType, ToolType

if TYPE_CHECKING:
    from agents.search_agent.article_store import ArticleStore

_article_store: ArticleStore | None = None


def set_article_store(store: ArticleStore) -> None:
    global _article_store
    _article_store = store


async def _add_article_for_graph(
    article_name: Annotated[str, "Name/title of the article"],
    source_url: Annotated[str, "Source URL of the article"],
    doc_path: Annotated[str, "Path to the OCR markdown file of the article"],
) -> str:
    """Store a complete markdown article for GraphRAG knowledge graph indexing.

    Call this after OCR produces the article markdown file. The file is read
    and stored as-is — GraphRAG will handle token chunking, entity extraction,
    and community detection during the index build phase.
    """
    if _article_store is None:
        return "[error] ArticleStore not initialized. Agent must be built with graphrag_index_enable=true."

    if not article_name:
        return "[error] article_name must be non-empty."

    path = Path(doc_path)
    if not path.exists():
        return f"[error] File not found: {doc_path}"

    full_markdown = path.read_text(encoding="utf-8")
    if not full_markdown:
        return f"[warning] Empty markdown file for '{article_name}'. Nothing stored."

    _article_store.add_article(article_name, source_url, full_markdown)

    current = _article_store.list_articles()
    return (
        f"Stored article '{article_name}' ({len(full_markdown)} chars) from {doc_path}.\n"
        f"Total articles in store: {len(current)}\n"
        f"Articles: {', '.join(current)}"
    )


class AddArticleTool(FunctionToolWithType):
    """FunctionToolWithType that stores a full article for GraphRAG indexing."""

    def __init__(self, article_store: ArticleStore | None = None, **kwargs: object) -> None:
        if article_store is not None:
            set_article_store(article_store)
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "add_article_for_graph")
        kwargs.setdefault(
            "description",
            "Store a markdown article file for GraphRAG knowledge graph indexing. "
            "Pass the file path to the OCR output. GraphRAG handles chunking internally.",
        )
        kwargs.setdefault("strict", False)
        super().__init__(_add_article_for_graph, **kwargs)
