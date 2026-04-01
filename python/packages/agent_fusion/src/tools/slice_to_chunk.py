"""
SliceToChunkTool: A FunctionToolWithType that splits a markdown document into
chapter/section-level chunks and stores them in the in-memory ContextManager.

Registered at the same level as BashFunctionTool and ContextSearchTool.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Annotated

from base.handoff import FunctionToolWithType, ToolType

if TYPE_CHECKING:
    from agents.search_agent.context_manager import ContextManager, Chunk

# Module-level ContextManager reference, injected at agent build time.
_context_manager: ContextManager | None = None


def set_context_manager(cm: ContextManager) -> None:
    global _context_manager
    _context_manager = cm


def _split_by_headings(
    markdown: str,
    article_name: str,
    source_url: str,
) -> list:
    """
    Split markdown text into chunks at heading boundaries (#, ##, ###).

    Each heading starts a new chunk. Content before the first heading is
    grouped under the implicit section 'Introduction' if non-empty.
    """
    from agents.search_agent.context_manager import Chunk

    # Regex: match heading lines (# / ## / ### at line start)
    heading_re = re.compile(r"^(#{1,3})\s+(.+)$", re.MULTILINE)

    chunks: list[Chunk] = []
    positions = [(m.start(), m.group(2).strip()) for m in heading_re.finditer(markdown)]

    def _safe_section_name(title: str) -> str:
        safe = re.sub(r"[^\w\-_ ]", "", title).strip().replace(" ", "_")
        return safe[:80] or "section"

    def _make_chunk(section_title: str, content: str, idx: int) -> Chunk:
        section_name = _safe_section_name(section_title)
        chunk_id = f"{article_name}/{section_name}"
        # Deduplicate chunk_id if same section appears multiple times
        chunk_id = f"{chunk_id}_{idx}" if idx > 0 else chunk_id
        return Chunk(
            chunk_id=chunk_id,
            article_name=article_name,
            section_name=section_name,
            content=content.strip(),
            metadata={"source_url": source_url},
        )

    if not positions:
        # No headings found — treat entire document as one chunk
        if markdown.strip():
            chunks.append(_make_chunk("full_document", markdown, 0))
        return chunks

    # Content before first heading
    pre_content = markdown[: positions[0][0]].strip()
    if pre_content:
        chunks.append(_make_chunk("Introduction", pre_content, 0))

    seen_names: dict[str, int] = {}
    for i, (start, title) in enumerate(positions):
        end = positions[i + 1][0] if i + 1 < len(positions) else len(markdown)
        content = markdown[start:end]

        safe_name = _safe_section_name(title)
        count = seen_names.get(safe_name, 0)
        seen_names[safe_name] = count + 1

        chunks.append(_make_chunk(title, content, count))

    return chunks


async def _slice_to_chunk(
    article_name: Annotated[str, "Name/title of the article"],
    markdown_content: Annotated[str, "Full markdown text of the article to chunk"],
    source_url: Annotated[str, "Source URL of the article (optional)"] = "",
) -> str:
    """Split a markdown document into chunks by chapter/section headings (#, ##, ###).

    Chunks are stored in the in-memory ContextManager and vector-indexed via
    Chroma EphemeralClient. Call this after OCR produces the article markdown.

    Returns a summary listing created chunk IDs.
    """
    if _context_manager is None:
        return "[error] ContextManager not initialized. Agent must be built with context_search_enable=true."

    if not article_name:
        return "[error] article_name must be non-empty."

    if not markdown_content:
        return f"[warning] Empty markdown content for '{article_name}'. No chunks created."

    chunks = _split_by_headings(markdown_content, article_name, source_url)

    if not chunks:
        return f"[warning] No chunks extracted from '{article_name}' (no headings found and content empty)."

    _context_manager.add_chunks(article_name, chunks)

    section_names = [c.section_name for c in chunks]
    return (
        f"Created {len(chunks)} chunk(s) for '{article_name}':\n"
        + "\n".join(f"  - {name}" for name in section_names)
    )


class SliceToChunkTool(FunctionToolWithType):
    """FunctionToolWithType that splits a markdown article into section-level chunks
    and stores them in the shared in-memory ContextManager.

    Register alongside BashFunctionTool and ContextSearchTool.
    """

    def __init__(self, context_manager: ContextManager | None = None, **kwargs: object) -> None:
        if context_manager is not None:
            set_context_manager(context_manager)
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "slice_to_chunk")
        kwargs.setdefault(
            "description",
            "Split a markdown article into chunks by chapter/section headings (#, ##, ###). "
            "Chunks are stored in memory and vector-indexed for RAG recall. "
            "Call after OCR produces the article markdown. Returns list of created chunks.",
        )
        kwargs.setdefault("strict", False)
        super().__init__(_slice_to_chunk, **kwargs)
