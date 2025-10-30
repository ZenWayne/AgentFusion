from autogen_agentchat.base import Handoff
from autogen_core.tools import BaseTool
from pydantic import BaseModel, Field
from autogen_core.tools import FunctionTool
from autogen_ext.tools.mcp import StdioMcpToolAdapter, SseMcpToolAdapter
from autogen_ext.tools.mcp import StreamableHttpMcpToolAdapter

from autogen_ext.tools.mcp import StdioServerParams, SseServerParams, StreamableHttpServerParams
from autogen_ext.tools.mcp import create_mcp_server_session
from autogen_ext.tools.mcp import McpServerParams
from mcp import ClientSession
from enum import StrEnum
from typing import Callable, Any
from mcp.types import ListToolsResult, Tool
from autogen_core.tools._base import ToolSchema

from base.handoff import ToolType, HandoffFunctionToolWithType

class HandoffWithType(Handoff):
    handoff_type : ToolType=Field(default=ToolType.HANDOFF_TOOL)
    
    @property
    def handoff_tool(self) -> BaseTool[BaseModel, BaseModel]:
        """Create a handoff tool from this handoff configuration."""

        if self.handoff_type == ToolType.HANDOFF_TOOL_CODE:
            def _handoff_tool() -> str:
                return self.message

            return HandoffFunctionToolWithType(
                _handoff_tool, 
                name=self.name,
                description=self.description, 
                strict=True,
                type=ToolType.HANDOFF_TOOL_CODE,
                target=self.target
            )
        else:
            def _handoff_tool() -> str:
                return self.message

            return HandoffFunctionToolWithType(
                _handoff_tool, 
                name=self.name,
                description=self.description, 
                strict=True,
                type=ToolType.HANDOFF_TOOL,
                target=self.target
            )