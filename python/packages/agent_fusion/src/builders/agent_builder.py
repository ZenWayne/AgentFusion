from base.utils import get_prompt  
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from schemas.component import ComponentInfo
from schemas.agent import AssistantAgentConfig, UserProxyAgentConfig, AgentType, InputFuncType
from model_client import ModelClient
from autogen_ext.tools.mcp import mcp_server_tools, McpServerParams
from autogen_ext.tools.mcp import StdioMcpToolAdapter, SseMcpToolAdapter
from .utils import AgentInfo
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Awaitable
from autogen_core.memory import ListMemory

class AgentBuilder:
    def __init__(self, input_func: Callable[[str], Awaitable[str]] | None = input):
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func

    @asynccontextmanager
    async def build(self, agent_info: AssistantAgentConfig| UserProxyAgentConfig) -> AsyncGenerator[AssistantAgent | UserProxyAgent, None]:
        user_memory = ListMemory()
        if agent_info.type == AgentType.ASSISTANT_AGENT:
            model_client = ModelClient[agent_info.model_client.value]()
            agent_tools = []
            for mcp_server in agent_info.mcp_tools:
                tools : list[StdioMcpToolAdapter | SseMcpToolAdapter] = await mcp_server_tools(mcp_server)
                for tool in tools:
                    tool.component_label = tool.name
                agent_tools.extend(tools)
            prompt = agent_info.prompt()
            agent = AssistantAgent(
                name=agent_info.name,
                model_client=model_client,
                model_client_stream=True,
                system_message=prompt,
                tools=agent_tools,
                description=agent_info.description,
                memory=[user_memory]
            )
            agent.component_label = agent_info.name
            yield agent

            await model_client.close()
        elif agent_info.type == AgentType.USER_PROXY_AGENT:
            agent = UserProxyAgent(
                name=agent_info.name,
                input_func=self._input_func
            )
            agent.component_label = agent_info.name
            yield agent
        else:
            raise ValueError(f"Invalid agent type: {agent_info.type}")

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