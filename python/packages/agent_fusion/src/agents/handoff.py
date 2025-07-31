from autogen_agentchat.base import Handoff
from autogen_core.tools import BaseTool
from pydantic import BaseModel
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

class HandoffType(StrEnum):
    HANDOFF_TOOL = "handoff_tool"
    NORMAL_TOOL = "normal_tool"

class ToolSchemaWithType(ToolSchema):
    type: HandoffType

class FunctionToolWithType(FunctionTool):
    type: HandoffType
    def __init__(self, *args, **kwargs):
        _type = kwargs.get("type")
        _type=kwargs.pop("type")
        super().__init__(*args, **kwargs)
        self.type = HandoffType.HANDOFF_TOOL if _type is None else _type
    
    @property
    def schema(self) -> ToolSchemaWithType:
        base_ret = super().schema

        return ToolSchemaWithType(
            name=base_ret["name"],
            description=base_ret["description"],
            parameters=base_ret["parameters"],
            strict=base_ret["strict"],
            type=self.type
        )


async def mcp_server_tools_with_type(
        server_params: McpServerParams,
        session: ClientSession | None = None,
        ) :
    if session is None:
        async with create_mcp_server_session(server_params) as temp_session:
            await temp_session.initialize()

            tools = await temp_session.list_tools()
    else:
        tools = await session.list_tools()

    if isinstance(server_params, StdioServerParams):
        return [StdioMcpToolAdapter(server_params=server_params, tool=tool, session=session) for tool in tools.tools]
    elif isinstance(server_params, SseServerParams):
        return [SseMcpToolAdapter(server_params=server_params, tool=tool, session=session) for tool in tools.tools]
    elif isinstance(server_params, StreamableHttpServerParams):
        return [
            StreamableHttpMcpToolAdapter(server_params=server_params, tool=tool, session=session)
            for tool in tools.tools
        ]
    raise ValueError(f"Unsupported server params type: {type(server_params)}")

class HandoffWithType(Handoff):
    
    @property
    def handoff_tool(self) -> BaseTool[BaseModel, BaseModel]:
        """Create a handoff tool from this handoff configuration."""

        def _handoff_tool() -> str:
            return self.message

        return FunctionToolWithType(
            _handoff_tool, 
            name=self.name,
            description=self.description, 
            strict=True,
            type=HandoffType.HANDOFF_TOOL,
        )