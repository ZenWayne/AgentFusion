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
from enum import Enum
from typing import Callable, Any

class HandoffType(Enum):
    HANDOFF_TOOL = "handoff_tool"
    NORMAL_TOOL = "normal_tool"


class FunctionToolWithType(FunctionTool):
    type: HandoffType

class StdioMcpToolAdapterWithType(StdioMcpToolAdapter):
    type: HandoffType

class SseMcpToolAdapterWithType(SseMcpToolAdapter):
    type: HandoffType

class StreamableHttpMcpToolAdapterWithType(StreamableHttpMcpToolAdapter):
    type: HandoffType

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
        return [StdioMcpToolAdapterWithType(server_params=server_params, tool=tool, session=session) for tool in tools.tools]
    elif isinstance(server_params, SseServerParams):
        return [SseMcpToolAdapterWithType(server_params=server_params, tool=tool, session=session) for tool in tools.tools]
    elif isinstance(server_params, StreamableHttpServerParams):
        return [
            StreamableHttpMcpToolAdapterWithType(server_params=server_params, tool=tool, session=session)
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