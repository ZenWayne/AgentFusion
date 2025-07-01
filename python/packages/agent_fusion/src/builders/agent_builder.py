from autogen import AssistantAgent, UserProxyAgent
from schemas.agent import AssistantAgentConfig, UserProxyAgentConfig, AgentType
from model_client import ModelClient
from builders.utils import AgentInfo
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Awaitable

from autogen.mcp import create_toolkit
from mcp import StdioServerParameters, ClientSession, stdio_client

class AgentBuilder:
    def __init__(self, input_func: Callable[[str], Awaitable[str]] | None = input):
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func

    @asynccontextmanager
    async def build(self, name: str) -> AsyncGenerator[AssistantAgent | UserProxyAgent, None]:
        agent_info: AssistantAgentConfig| UserProxyAgentConfig = AgentInfo[name]

        if agent_info.type == AgentType.ASSISTANT_AGENT:
            model_client = ModelClient[agent_info.model_client.value]
            prompt = agent_info.prompt()
            agent = AssistantAgent(
                name=agent_info.name,
                llm_config=model_client,
                system_message=prompt,
                description=agent_info.description
            )
            for mcp_server in agent_info.mcp_tools:
                async with stdio_client(mcp_server) as (read, write), ClientSession(read, write) as session:
                    # Initialize the connection
                    await session.initialize()
                    toolkit = await create_toolkit(session)
                    toolkit.register_for_llm(agent)
                    yield agent, toolkit

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
    from builders.utils import load_info
    load_info()
    agent = AgentBuilder()
    async with agent.build("file_system") as (agent, toolkit):
        result = await agent.a_run(
            message="""list the content of the current directory""",
            tools=toolkit.tools,
            max_turns=2,
            user_input=False,
        )
        await result.process()

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(test())
    #python -m agent.agent_builder