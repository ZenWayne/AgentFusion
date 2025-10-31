"""
Handoff tool implementations for AgentFusion.

This module contains specialized handoff tools for different use cases:
- HandoffCodeWithType: Executes Python code before handing off
- HandoffWithTypeRaw: Basic handoff without code execution
"""

from typing import Annotated
from pydantic import Field

from .handoffcode import HandoffCodeWithType, HandoffCodeFunctionToolWithType
from .handoffraw import HandoffWithTypeRaw
from base.handoff import ToolType

__all__ = [
    'HandoffCodeWithType',
    'HandoffWithTypeRaw',
    'HandoffCodeFunctionToolWithType',
    'HandoffType',
    'ToolType'
]

HandoffType = Annotated[
    HandoffWithTypeRaw
    | HandoffCodeWithType, Field(default=ToolType.HANDOFF_TOOL, discriminator="handoff_type")]