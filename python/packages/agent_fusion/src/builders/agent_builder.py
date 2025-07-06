from autogen import AssistantAgent, UserProxyAgent, config_list_from_json, filter_config
from schemas.agent import AssistantAgentConfig, UserProxyAgentConfig, AgentType
from model_client import ModelClient
from builders.utils import AgentInfo
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Awaitable
from autogen.agentchat.realtime_agent import RealtimeAgent

from autogen.mcp import create_toolkit
from mcp import StdioServerParameters, ClientSession, stdio_client

class AgentBuilder:
    def __init__(self, input_func: Callable[[str], Awaitable[str]] | None = input):
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func

    async def build(self, name: str) -> AssistantAgent | UserProxyAgent:
        agent_info: AssistantAgentConfig| UserProxyAgentConfig = AgentInfo[name]

        if agent_info.type == AgentType.ASSISTANT_AGENT:
            model_client = ModelClient[agent_info.model_client.value]
            prompt = agent_info.prompt()
            config_list = filter_config(
                config_list=[model_client],
                filter_dict={
                    "model": [model_client["model"]],
                }
            )
            agent = AssistantAgent(
                name=agent_info.name,
                llm_config={
                    "config_list": config_list,
                },
                system_message=prompt,
                description=agent_info.description
            )
            for mcp_server in agent_info.mcp_tools:
                async with stdio_client(mcp_server) as (read, write), ClientSession(read, write) as session:
                    # Initialize the connection
                    await session.initialize()
                    toolkit = await create_toolkit(session=session, use_mcp_resources=False)
                    toolkit.register_for_llm(agent)
            return agent

        elif agent_info.type == AgentType.USER_PROXY_AGENT:
            agent = UserProxyAgent(
                name=agent_info.name,
                is_termination_msg=lambda msg: "TERMINATE" in msg["content"],
                human_input_mode="ALWAYS",
                max_consecutive_auto_reply=1,
                description=agent_info.description
            )
            return agent
        else:
            raise ValueError(f"Invalid agent type: {agent_info.type}")

async def test():
    from builders.utils import load_info
    load_info()
    agent = AgentBuilder()
    async with agent.build("file_system") as (agent, toolkit):
        agent : AssistantAgent = agent
        result = await agent.a_run(
            message="""list the content of the current directory""",
            tools=toolkit.tools,
            max_turns=4,
            user_input=False,
        )
        agent.initiate_chat()
        await result.process()

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test())
    #python -m builders.agent_builder