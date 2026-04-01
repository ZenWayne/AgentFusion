"""
GraphRAGTraceTool: Provenance tracing from GraphRAG search results.

Traces: query -> local_search -> context_data -> text_units -> document_id -> source_url
Used by Critics/Validator to verify claims against original text.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import pandas as pd

from agents.search_agent.article_store import ArticleStore
from base.handoff import FunctionToolWithType, ToolType

_output_dir: str = "graphrag_output"
_graphrag_config = None


def set_trace_config(output_dir: str, config: object | None = None) -> None:
    global _output_dir, _graphrag_config
    _output_dir = output_dir
    if config is not None:
        _graphrag_config = config


def _get_config():
    if _graphrag_config is not None:
        return _graphrag_config
    from tools.graphrag_config_builder import build_graphrag_config
    return build_graphrag_config(
        "deepseek-chat_DeepSeek",
        "deepseek-chat_DeepSeek",
        output_dir=_output_dir,
    )


async def _graphrag_trace(
    query: Annotated[str, "Claim or statement to trace back to source documents"],
    community_level: Annotated[int, "Community hierarchy level. Default 2"] = 2,
) -> str:
    """Trace a claim back to original document text for provenance verification.

    Executes a local search and extracts the provenance chain:
    query -> entities -> text_units (original chunks) -> documents -> source URLs.

    Returns original text excerpts with source attribution.
    """
    if not query:
        return "[error] Query must be non-empty."

    # Load parquet data (reuse search module's cache)
    from tools.graphrag_search import _load_parquet_data
    try:
        data = _load_parquet_data(_output_dir)
    except FileNotFoundError as e:
        return f"[error] {e}"

    config = _get_config()

    from graphrag.api import local_search

    try:
        response, context_data = await local_search(
            config=config,
            entities=data["entities"],
            communities=data["communities"],
            community_reports=data["community_reports"],
            text_units=data["text_units"],
            relationships=data["relationships"],
            covariates=None,
            community_level=community_level,
            response_type="Multiple Paragraphs",
            query=query,
        )
    except Exception as e:
        return f"[error] GraphRAG trace search failed: {e}"

    # Load article metadata for source URL resolution
    metadata_map = ArticleStore.load_metadata(_output_dir)

    # Build provenance output
    parts = [f"## Provenance Trace\n**Query**: {query}\n"]
    parts.append(f"### LLM Response\n{response}\n")

    # Extract source text units from context_data
    if isinstance(context_data, dict):
        sources_df = context_data.get("sources")
        if sources_df is None:
            sources_df = context_data.get("text_units")

        if sources_df is not None and isinstance(sources_df, pd.DataFrame) and not sources_df.empty:
            parts.append(f"### Source Citations ({len(sources_df)} text units)\n")
            for i, row in enumerate(sources_df.itertuples(), 1):
                text = getattr(row, "text", "")
                doc_id = getattr(row, "document_id", None) or getattr(row, "document_ids", "")

                # Resolve document_id to source_url
                source_url = ""
                article_name = ""
                if isinstance(doc_id, str) and doc_id in metadata_map:
                    article_name = doc_id
                    source_url = metadata_map[doc_id].get("source_url", "")
                elif isinstance(doc_id, list) and doc_id:
                    article_name = doc_id[0]
                    source_url = metadata_map.get(doc_id[0], {}).get("source_url", "")

                # Truncate long text
                excerpt = text[:500] + "..." if len(text) > 500 else text

                source_line = f"Source: {article_name}" if article_name else "Source: unknown"
                if source_url:
                    source_line += f" ({source_url})"

                parts.append(f"#### [Citation {i}] {source_line}\n> {excerpt}\n")

            if i >= 10:
                parts.append(f"_... and {len(sources_df) - 10} more text units_\n")
        else:
            parts.append("### Source Citations\nNo source text units found in context_data.\n")

        # Entity summary
        entities_df = context_data.get("entities")
        if entities_df is not None and isinstance(entities_df, pd.DataFrame) and not entities_df.empty:
            parts.append("### Matched Entities\n")
            entity_col = "entity" if "entity" in entities_df.columns else "title"
            desc_col = "description" if "description" in entities_df.columns else None
            rows = []
            for row in entities_df.head(15).itertuples():
                name = getattr(row, entity_col, "")
                desc = getattr(row, desc_col, "") if desc_col else ""
                desc_short = (desc[:80] + "...") if isinstance(desc, str) and len(desc) > 80 else desc
                rows.append(f"| {name} | {desc_short} |")
            parts.append("| Entity | Description |")
            parts.append("|--------|-------------|")
            parts.extend(rows)
            parts.append("")

        # Relationship summary
        rels_df = context_data.get("relationships")
        if rels_df is not None and isinstance(rels_df, pd.DataFrame) and not rels_df.empty:
            parts.append("### Matched Relationships\n")
            rows = []
            for row in rels_df.head(10).itertuples():
                src = getattr(row, "source", "")
                tgt = getattr(row, "target", "")
                desc = getattr(row, "description", "")
                desc_short = (desc[:60] + "...") if isinstance(desc, str) and len(desc) > 60 else desc
                rows.append(f"| {src} | {tgt} | {desc_short} |")
            parts.append("| Source | Target | Description |")
            parts.append("|--------|--------|-------------|")
            parts.extend(rows)
            parts.append("")

    return "\n".join(parts)


class GraphRAGTraceTool(FunctionToolWithType):
    """FunctionToolWithType for provenance tracing through GraphRAG."""

    def __init__(
        self,
        output_dir: str = "graphrag_output",
        config: object | None = None,
        **kwargs: object,
    ) -> None:
        set_trace_config(output_dir, config)
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "graphrag_trace")
        kwargs.setdefault(
            "description",
            "Trace a claim back to original document text for provenance verification. "
            "Returns source text excerpts, matched entities, and source URLs.",
        )
        kwargs.setdefault("strict", False)
        super().__init__(_graphrag_trace, **kwargs)
