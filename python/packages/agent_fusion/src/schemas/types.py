"""
Core types and enums used across schemas.

This module contains base types to avoid circular imports.
"""

from enum import Enum


class ComponentType(str, Enum):
    LLM = "llm"
    AGENT = "agent"
    GROUP_CHAT = "group_chat"
    GRAPH_FLOW = "graph_flow"
    MCP = "mcp"