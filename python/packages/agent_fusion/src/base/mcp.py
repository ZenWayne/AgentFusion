from autogen_ext.tools.mcp import StdioServerParams, McpServerParams, SseServerParams
from autogen_ext.tools.mcp import StdioMcpToolAdapter, SseMcpToolAdapter
from autogen_ext.tools.mcp import mcp_server_tools
import os

def parse_mcp_server(mcp_server: dict) -> McpServerParams:
    if mcp_server["type"] == "StdioServerParams":
        return StdioServerParams(
            command=mcp_server["command"],
            args=mcp_server["args"],
            env=mcp_server["env"],
            read_timeout_seconds=mcp_server.get("read_timeout_seconds", 5)
        )
    elif mcp_server["type"] == "SseServerParams":
        return SseServerParams(
            url=mcp_server["url"],
            headers=mcp_server["headers"],
            timeout=mcp_server["timeout"],
            sse_read_timeout=mcp_server["sse_read_timeout"]
        )
    else:
        raise ValueError(f"Unsupported MCP server type: {mcp_server['type']}")

async def fetch_mcp_tools(mcp_server: dict) -> list[StdioMcpToolAdapter]:
    mcp_server_params = parse_mcp_server(mcp_server)
    tools :list[StdioMcpToolAdapter | SseMcpToolAdapter] = await mcp_server_tools(mcp_server_params)
    for tool in tools:
        tool.component_label = tool.name
    
    return tools

