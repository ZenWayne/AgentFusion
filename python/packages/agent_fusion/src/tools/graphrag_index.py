"""
GraphRAGIndexTool: Builds a GraphRAG knowledge graph index from all articles
stored in ArticleStore.

Call once after all articles have been OCR'd and stored.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from base.handoff import FunctionToolWithType, ToolType

if TYPE_CHECKING:
    from agents.search_agent.article_store import ArticleStore
    from graphrag.config.models.graph_rag_config import GraphRagConfig

_article_store: ArticleStore | None = None
_graphrag_config: GraphRagConfig | None = None
_output_dir: str = "graphrag_output"


def set_index_dependencies(
    store: ArticleStore,
    config: GraphRagConfig,
    output_dir: str,
) -> None:
    global _article_store, _graphrag_config, _output_dir
    _article_store = store
    _graphrag_config = config
    _output_dir = output_dir


async def _graphrag_index() -> str:
    """Build GraphRAG knowledge graph index from all stored articles.

    Internally performs: token chunking -> entity extraction -> relationship
    extraction -> community detection -> community report generation.
    Outputs Parquet files + LanceDB vectors to the configured output directory.

    Call this ONCE after all articles have been stored via add_article_for_graph.
    """
    if _article_store is None or _graphrag_config is None:
        return "[error] GraphRAG index dependencies not initialized. Agent must be built with graphrag_index_enable=true."

    articles = _article_store.list_articles()
    if not articles:
        return "[error] No articles in store. Add articles first with add_article_for_graph."

    df = _article_store.to_dataframe()

    from graphrag.api import build_index

    results = await build_index(
        config=_graphrag_config,
        input_documents=df,
        verbose=True,
    )

    # Save article metadata for cross-agent provenance
    _article_store.save_metadata(_output_dir)

    # Invalidate any cached parquet data in search/trace modules
    try:
        from tools.graphrag_search import invalidate_cache
        invalidate_cache()
    except ImportError:
        pass

    # Summarize results
    errors = [r for r in results if r.error]
    summary_parts = [
        f"Index built for {len(articles)} article(s): {', '.join(articles)}",
        f"Workflows: {len(results)} completed, {len(errors)} with errors",
    ]
    if errors:
        for r in errors:
            summary_parts.append(f"  Errors in {r.workflow}: {r.error}")

    return "\n".join(summary_parts)


class GraphRAGIndexTool(FunctionToolWithType):
    """FunctionToolWithType that builds a GraphRAG knowledge graph index."""

    def __init__(
        self,
        article_store: ArticleStore | None = None,
        config: GraphRagConfig | None = None,
        output_dir: str = "graphrag_output",
        **kwargs: object,
    ) -> None:
        if article_store is not None and config is not None:
            set_index_dependencies(article_store, config, output_dir)
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "graphrag_index")
        kwargs.setdefault(
            "description",
            "Build GraphRAG knowledge graph index from all stored articles. "
            "Performs entity extraction, community detection, and report generation. "
            "Call ONCE after all articles are stored.",
        )
        kwargs.setdefault("strict", False)
        super().__init__(_graphrag_index, **kwargs)
