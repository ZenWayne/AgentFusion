from base.utils import get_prompt  
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from base.utils import warp_input
from dataclass.agent import AssistantAgentConfig, UserProxyAgentConfig, AgentType, InputFuncType, ComponentInfo
from model_client import ModelClient
from autogen_ext.tools.mcp import mcp_server_tools, McpServerParams
from autogen_ext.tools.mcp import StdioMcpToolAdapter, SseMcpToolAdapter
from agent.mcp_builder import McpInfo
from contextlib import asynccontextmanager
from typing import AsyncGenerator
from autogen_core.memory import ListMemory
import json

AgentInfo : dict[str, ComponentInfo] = {}

def extract_mcp_tools(mcp_tools: list[str]) -> list[McpServerParams]:
    tools = []
    for mcp_tool in mcp_tools:
        tools.append(McpInfo[mcp_tool])
    return tools

def load_info(config_path: str) -> ComponentInfo:
    global AgentInfo
    with open(config_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    factory_func = {
        AgentType.ASSISTANT_AGENT: AssistantAgentConfig,
        AgentType.USER_PROXY_AGENT: UserProxyAgentConfig
    }
    for name, agent_config in metadata["agents"].items():
        if agent_config.get("mcp_tools", None):
            agent_config["mcp_tools"] = extract_mcp_tools(agent_config["mcp_tools"])
        AgentInfo[name] = factory_func[agent_config["type"]](**agent_config)
    return AgentInfo

@asynccontextmanager
async def AgentBuilder(name: str) -> AsyncGenerator[AssistantAgent | UserProxyAgent, None]:
    agent_info: AssistantAgentConfig| UserProxyAgentConfig = AgentInfo[name]

    user_memory = ListMemory()
    if agent_info.type == AgentType.ASSISTANT_AGENT:
        agent_tools = []
        for mcp_server in agent_info.mcp_tools:
            tools : list[StdioMcpToolAdapter | SseMcpToolAdapter] = await mcp_server_tools(mcp_server)
            for tool in tools:
                tool.component_label = tool.name
            agent_tools.extend(tools)
        prompt = get_prompt(f"{agent_info.prompt}")
        agent = AssistantAgent(
            name=agent_info.name,
            model_client=ModelClient[agent_info.model_client.value],
            model_client_stream=True,
            system_message=prompt,
            tools=agent_tools,
            description=agent_info.description,
            memory=[user_memory]
        )
    elif agent_info.type == AgentType.USER_PROXY_AGENT:
        input_func = InputFuncType.INPUT
        if agent_info.input_func == InputFuncType.WRAPPED_INPUT:
            input_func = warp_input
        agent = UserProxyAgent(
            name=agent_info.name,
            input_func=input_func
        )
    else:
        raise ValueError(f"Invalid agent type: {agent_info.type}")

    agent.component_label = agent_info.name

    if agent_info.type == AgentType.ASSISTANT_AGENT:
        yield agent
        await ModelClient[agent_info.model_client.value].close()
    elif agent_info.type == AgentType.USER_PROXY_AGENT:
        yield agent

async def test():
    from autogen_agentchat.ui import Console
    from autogen_agentchat.messages import TextMessage
    from autogen_core import CancellationToken

    agent = await AgentBuilder("file_system")
    await Console(
            agent.on_messages_stream(
                [TextMessage(content=f"列出当前文件夹下所有文件和文件夹", source="user")], CancellationToken()
            )
    )

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test())
    #python -m agent.agent_builder