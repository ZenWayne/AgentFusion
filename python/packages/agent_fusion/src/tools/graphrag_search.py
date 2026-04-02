"""
GraphRAGSearchTool: Semantic search over a GraphRAG knowledge graph.

Supports local search (entity/relationship-level) and global search
(community-report-level cross-document summaries).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd

from base.handoff import FunctionToolWithType, ToolType

_output_dir: str = "graphrag_output"
_graphrag_config = None
_cached_data: dict[str, pd.DataFrame] | None = None


def set_search_config(output_dir: str, config: object | None = None) -> None:
    global _output_dir, _graphrag_config
    _output_dir = output_dir
    if config is not None:
        _graphrag_config = config


def invalidate_cache() -> None:
    global _cached_data
    _cached_data = None


def _load_parquet_data(output_dir: str) -> dict[str, pd.DataFrame]:
    global _cached_data
    if _cached_data is not None:
        return _cached_data

    base = Path(output_dir)
    required = ["entities", "communities", "text_units", "relationships"]
    optional = ["community_reports"]
    data: dict[str, pd.DataFrame] = {}

    for name in required:
        path = base / f"{name}.parquet"
        if not path.exists():
            raise FileNotFoundError(f"Parquet file not found: {path}. Has graphrag_index been run?")
        data[name] = pd.read_parquet(path)

    for name in optional:
        path = base / f"{name}.parquet"
        data[name] = pd.read_parquet(path) if path.exists() else pd.DataFrame()

    _cached_data = data
    return _cached_data


def _get_config():
    """Get or build a GraphRagConfig for search queries."""
    if _graphrag_config is not None:
        return _graphrag_config
    raise RuntimeError(
        "GraphRAG search config not initialized. "
        "Set graphrag_embedding_model in the agent config so the correct embedding model is used for search."
    )


async def _graphrag_search(
    query: Annotated[str, "Search query in natural language"],
    mode: Annotated[str, "Search mode: 'local' for entity-level detail, 'global' for cross-document summary"] = "local",
    community_level: Annotated[int, "Community hierarchy level (higher = broader). Default 2"] = 2,
    response_type: Annotated[str, "Response format hint: 'Multiple Paragraphs', 'Single Paragraph', 'List'"] = "Multiple Paragraphs",
) -> str:
    """Search the GraphRAG knowledge graph using semantic queries.

    - local: fine-grained entity/relationship queries (specific concepts, methods, results)
    - global: macro-level cross-document summaries (trends, consensus, overview)
    """
    if not query:
        return "[error] Query must be non-empty."

    mode = mode.strip().lower()
    if mode not in ("local", "global"):
        mode = "local"

    try:
        data = _load_parquet_data(_output_dir)
    except FileNotFoundError as e:
        return f"[error] {e}"

    # Verify vector store is populated before searching
    try:
        import lancedb as _lancedb
        from pathlib import Path as _Path
        _vec_dir = str(_Path(_output_dir) / "vectors")
        _db = _lancedb.connect(_vec_dir)
        if not _db.table_names():
            return (
                "[error] Vector store is empty — the index has not been built yet "
                "or the previous indexing failed. Please run graphrag_index first."
            )
    except Exception:
        pass

    config = _get_config()

    from graphrag.api import global_search, local_search

    try:
        if mode == "local":
            response, context_data = await local_search(
                config=config,
                entities=data["entities"],
                communities=data["communities"],
                community_reports=data["community_reports"],
                text_units=data["text_units"],
                relationships=data["relationships"],
                covariates=None,
                community_level=community_level,
                response_type=response_type,
                query=query,
            )
        else:
            response, context_data = await global_search(
                config=config,
                entities=data["entities"],
                communities=data["communities"],
                community_reports=data["community_reports"],
                community_level=community_level,
                dynamic_community_selection=False,
                response_type=response_type,
                query=query,
            )
    except Exception as e:
        err_str = str(e)
        if "doesn't match the column vector" in err_str and "dim" in err_str:
            return (
                f"[error] Embedding dimension mismatch — the current embedding model produces "
                f"vectors with a different dimension than those stored in the index. "
                f"This happens when the embedding model is changed after indexing. "
                f"Fix: delete '{_output_dir}/vectors/' and re-run graphrag_index to rebuild "
                f"the vector store with the current embedding model.\n"
                f"Detail: {err_str}"
            )
        return f"[error] GraphRAG {mode} search failed: {e}"

    # Format output
    parts = [f"## GraphRAG {mode.title()} Search\n**Query**: {query}\n"]

    if isinstance(response, str):
        parts.append(response)
    else:
        parts.append(str(response))

    # Append entity summary from context_data
    if isinstance(context_data, dict):
        entities_df = context_data.get("entities")
        if entities_df is not None and isinstance(entities_df, pd.DataFrame) and not entities_df.empty:
            entity_col = "entity" if "entity" in entities_df.columns else "title"
            if entity_col in entities_df.columns:
                entities_list = entities_df[entity_col].tolist()[:10]
                parts.append(f"\n**Key entities**: {', '.join(str(e) for e in entities_list)}")

    return "\n".join(parts)


class GraphRAGSearchTool(FunctionToolWithType):
    """FunctionToolWithType for semantic search over GraphRAG knowledge graph."""

    def __init__(
        self,
        output_dir: str = "graphrag_output",
        config: object | None = None,
        **kwargs: object,
    ) -> None:
        set_search_config(output_dir, config)
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "graphrag_search")
        kwargs.setdefault(
            "description",
            "Semantic search over GraphRAG knowledge graph. "
            "mode='local' for entity-level detail, mode='global' for cross-document summary.",
        )
        kwargs.setdefault("strict", False)
        super().__init__(_graphrag_search, **kwargs)
