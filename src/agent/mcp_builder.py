from autogen_ext.tools.mcp import McpServerParams, StdioServerParams, SseServerParams
import json
import re
import os

McpInfo: dict[str, McpServerParams] = {}

def load_info(config_path: str) -> dict[str, McpServerParams]:
    with open(config_path, "r", encoding="utf-8") as f:
        mcp_config_str = f.read()
        safe_pwd = os.getcwd()
        # double escape, for windows
        if os.name == "nt":
            safe_pwd = safe_pwd.replace('\\', '\\\\')
            safe_pwd = safe_pwd.replace('\\', '\\\\')
        # 在字符串上执行替换
        mcp_config_str=re.sub(r"\${cwd}", safe_pwd, mcp_config_str, flags=re.ASCII)

        metadata = json.loads(mcp_config_str)
    
    factory_func = {
        "stdio": StdioServerParams,
        "sse": SseServerParams
    }
    for name, mcp_config in metadata["mcpServers"].items():
        mcp_type = mcp_config.get("type", "stdio")
        McpInfo[name] = factory_func[mcp_type](**mcp_config)
    return McpInfo
