from autogen_ext.tools.mcp import McpServerParams, StdioServerParams, SseServerParams
import json
from base.utils import parse_cwd_placeholders

McpInfo: dict[str, McpServerParams] = {}

def load_info(config_path: str) -> dict[str, McpServerParams]:
    with open(config_path, "r", encoding="utf-8") as f:
        mcp_config_str = f.read()
        mcp_config_str=parse_cwd_placeholders(mcp_config_str)

        metadata = json.loads(mcp_config_str)
    
    factory_func = {
        "stdio": StdioServerParams,
        "sse": SseServerParams
    }
    for name, mcp_config in metadata["mcpServers"].items():
        mcp_type = mcp_config.get("type", "stdio")
        McpInfo[name] = factory_func[mcp_type](**mcp_config)
    return McpInfo
