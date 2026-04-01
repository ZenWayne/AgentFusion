"""
ContextSearchTool: A FunctionToolWithType that searches the in-memory ContextManager
using regex multi-keyword patterns (similar to grep).

Registered at the same level as BashFunctionTool.
Operates on the ContextManager instance shared with SliceToChunkTool.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

from base.handoff import FunctionToolWithType, ToolType

if TYPE_CHECKING:
    from agents.search_agent.context_manager import ContextManager

# Module-level ContextManager reference, injected at agent build time.
_context_manager: ContextManager | None = None


def set_context_manager(cm: ContextManager) -> None:
    global _context_manager
    _context_manager = cm


async def _context_search(
    pattern: Annotated[
        str,
        "Regex pattern to search. Supports multi-keyword: '.*word_a|.*word_b'. "
        "Case-insensitive by default.",
    ],
    scope: Annotated[
        str,
        "Search scope: 'all' (default), 'chunks', or 'summaries'",
    ] = "all",
    max_results: Annotated[
        int,
        "Maximum number of matching lines to return (default 50)",
    ] = 50,
) -> str:
    """Search in-memory context using regex multi-keyword patterns like grep.

    Searches all article chunks and/or summaries stored in ContextManager.
    Returns matching lines in grep-style format: chunk_id:line_number: matched_line

    Example patterns:
      '.*attention mechanism'   - lines containing 'attention mechanism'
      '.*transformer|.*BERT'    - lines containing 'transformer' OR 'BERT'
      '.*loss.*0\\.0[0-9]'      - lines with 'loss' followed by a small decimal
    """
    if _context_manager is None:
        return "[error] ContextManager not initialized. Agent must be built with context_search_enable=true."

    if not pattern:
        return "[error] Pattern must be a non-empty string."

    scope = scope.strip().lower()
    if scope not in ("all", "chunks", "summaries"):
        scope = "all"

    matches = _context_manager.search(pattern, scope=scope, max_results=max_results)

    if not matches:
        return f"No matches found for pattern: {pattern!r}"

    if matches and "error" in matches[0]:
        return matches[0]["error"]

    lines: list[str] = []
    for m in matches:
        lines.append(
            f"{m['chunk_id']}:{m['line_number']}: {m['matched_line']}"
        )

    header = f"Found {len(matches)} match(es) for {pattern!r}:\n"
    return header + "\n".join(lines)


class ContextSearchTool(FunctionToolWithType):
    """FunctionToolWithType that searches in-memory context via regex patterns.

    Works on the shared ContextManager instance. Register alongside BashFunctionTool.
    """

    def __init__(self, context_manager: ContextManager | None = None, **kwargs: object) -> None:
        if context_manager is not None:
            set_context_manager(context_manager)
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "context_search")
        kwargs.setdefault(
            "description",
            "Search in-memory article context using regex patterns "
            "(supports multi-keyword: '.*a|.*b'). "
            "Searches chunks and/or summaries. Returns grep-style output.",
        )
        kwargs.setdefault("strict", False)
        super().__init__(_context_search, **kwargs)
