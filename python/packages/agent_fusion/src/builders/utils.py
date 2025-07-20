import json
from autogen_ext.tools.mcp import McpServerParams, StdioServerParams, SseServerParams
from schemas.component import ComponentInfo
from schemas.agent import AgentType, AssistantAgentConfig, UserProxyAgentConfig
from schemas.graph_flow import GraphFlowConfig
from schemas.group_chat import SelectorGroupChatConfig
from base.utils import get_prompt, parse_cwd_placeholders

prompt_root: str = ""
McpInfo: dict[str, McpServerParams] = {}
AgentInfo: dict[str, ComponentInfo] = {}
GraphFlowInfo: dict[str, GraphFlowConfig] = {}
GroupChatInfo: dict[str, SelectorGroupChatConfig] = {}

def extract_mcp_tools(mcp_tools: list[str]) -> list[McpServerParams]:
    tools = []
    for mcp_tool in mcp_tools:
        tools.append(McpInfo[mcp_tool])
    return tools

def load_info(config_path: str="config.json"):
    with open(config_path, "r", encoding="utf-8") as f:
        metadata = parse_cwd_placeholders(f.read())
        metadata = json.loads(metadata)
    mcp_factory_func = {
        "stdio": StdioServerParams,
        "sse": SseServerParams
    }
    global prompt_root
    prompt_root = metadata["prompt_root"]
    for name, mcp_config in metadata["mcpServers"].items():
        mcp_type = mcp_config.get("type", "stdio")
        McpInfo[name] = mcp_factory_func[mcp_type](**mcp_config)
    
    agent_factory_func = {
        AgentType.ASSISTANT_AGENT: AssistantAgentConfig,
        AgentType.USER_PROXY_AGENT: UserProxyAgentConfig
    }
    for name, agent_config in metadata["agents"].items():
        if agent_config.get("mcp_tools", None):
            agent_config["mcp_tools"] = extract_mcp_tools(agent_config["mcp_tools"])
        if agent_config.get("prompt_path", None):
            agent_config["prompt"] = lambda agent_path=agent_config["prompt_path"]: get_prompt(
                agent_path=agent_path, 
                prompt_path=prompt_root
            )
        AgentInfo[name] = agent_factory_func[agent_config["type"]](**agent_config)

    
    for name, graph_flow_config in metadata["graph_flows"].items():
        GraphFlowInfo[name] = GraphFlowConfig(**graph_flow_config)
    
    for name, group_chat_config in metadata["group_chats"].items():
        GroupChatInfo[name] = SelectorGroupChatConfig(**group_chat_config)