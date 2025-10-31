import asyncio
from base.utils import get_prompt, parse_cwd_placeholders
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from agents.codeagent import CodeAgent
from schemas.component import ComponentInfo
from schemas.agent import AssistantAgentConfig, UserProxyAgentConfig, AgentType as AgentTypeEnum, InputFuncType
from schemas.agent_type import AgentType, TypedAssistantAgent, TypedUserProxyAgent, TypedCodeAgent
from builders.model_builder import ModelClientBuilder
from autogen_ext.tools.mcp import mcp_server_tools, McpServerParams
from autogen_ext.tools.mcp import StdioMcpToolAdapter, SseMcpToolAdapter
from .utils import AgentInfo
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Awaitable, Type
from autogen_core.memory import ListMemory
from autogen_agentchat.base import Handoff
from autogen_ext.tools.mcp import McpWorkbench
from autogen_core.model_context import ChatCompletionContext
from contextlib import AsyncExitStack
from tools.handoff import HandoffWithTypeRaw, HandoffCodeWithType, HandoffType
from tools.workbench import VectorStreamWorkbench
from tools.retrieve import retrieve_filesystem_tool
from tools.handoff import ToolType

class AgentBuilder:
    def __init__(self, input_func: Callable[[str], Awaitable[str]] | None = input, context: ChatCompletionContext | None = None):
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func
        self._context: ChatCompletionContext | None = context
    
    def model_client_builder(self) -> ModelClientBuilder:
        return ModelClientBuilder()

    def get_component_by_name(self, name: str) -> AssistantAgentConfig | UserProxyAgentConfig:
        """Get agent config by name"""
        if name not in AgentInfo:
            raise ValueError(f"Agent config not found for name: {name}")
        return AgentInfo[name]

    def _agent_chat_map(self, agent_type_enum: AgentTypeEnum) -> Type[AgentType]:
        """Map agent type enum to typed agent class"""
        return {
            AgentTypeEnum.ASSISTANT_AGENT: TypedAssistantAgent,
            AgentTypeEnum.USER_PROXY_AGENT: TypedUserProxyAgent,
            AgentTypeEnum.CODE_AGENT: TypedCodeAgent,
        }[agent_type_enum]

    def _handoff_map(self, handoff_type: ToolType, target: str, message: str) -> Type[HandoffType]:
        """Map handoff type to handoff class"""
        cls_dict= {
            ToolType.HANDOFF_TOOL: HandoffWithTypeRaw,
            ToolType.HANDOFF_TOOL_CODE: HandoffCodeWithType,
        }

        return cls_dict[handoff_type](handoff_type=handoff_type, target=target, message=message)
    @asynccontextmanager
    async def build(self, agent_info: AssistantAgentConfig| UserProxyAgentConfig) -> AsyncGenerator[AssistantAgent | UserProxyAgent, None]:
        # Use dynamic class mapping for type-safe agent creation
        agent_class = self._agent_chat_map(agent_info.type)
        user_memory = ListMemory()
        model_client_builder: ModelClientBuilder = self.model_client_builder()
        if agent_info.type == AgentTypeEnum.CODE_AGENT:
            tools = []
            # Handle MCP tools if they exist
            if agent_info.mcp_tools:
                for mcp_server in agent_info.mcp_tools:
                    if mcp_server.type != "StdioServerParams":
                        continue
                    for idx, arg in enumerate(mcp_server.args):
                        mcp_server.args[idx] = parse_cwd_placeholders(arg)
                mcp_tools = await asyncio.gather(
                    *[mcp_server_tools(mcp_server) 
                    for mcp_server in agent_info.mcp_tools]
                )
                # Flatten the list of lists
                tools = [tool for sublist in mcp_tools for tool in sublist]

            # Add handoff tools if defined
            if agent_info.handoff_tools:
                tools.extend([
                    self._handoff_map(handoff_tool.handoff_type, target=handoff_tool.target, message=handoff_tool.message).handoff_tool
                    for handoff_tool in agent_info.handoff_tools
                ])
            #tools.append(retrieve_filesystem_tool())
            model_client_config = await model_client_builder.get_component_by_name(agent_info.model_client)
            async with model_client_builder.build(model_client_config) as model_client:
                workbench = [VectorStreamWorkbench(tools=tools)] if tools else None
                agent = agent_class(
                    name=agent_info.name,
                    workbench=workbench,
                    model_client=model_client,
                    model_context=self._context,
                    system_message=agent_info.prompt(),
                    output_content_type=None,
                    output_content_type_format=None,
                    max_tool_iterations=10,
                )
                agent.component_label = agent_info.name
                yield agent
        elif agent_info.type == AgentTypeEnum.ASSISTANT_AGENT:
            model_client_config = await model_client_builder.get_component_by_name(agent_info.model_client)
            async with model_client_builder.build(model_client_config) as model_client:
                agent_tools = []
                # Handle MCP tools if they exist
                if agent_info.mcp_tools:
                    try:
                        for mcp_server in agent_info.mcp_tools:
                            for idx, arg in enumerate(mcp_server.args):
                                mcp_server.args[idx] = parse_cwd_placeholders(arg)
                            tools : list[StdioMcpToolAdapter | SseMcpToolAdapter] = await mcp_server_tools(mcp_server)
                            for tool in tools:
                                tool.component_label = tool.name
                            agent_tools.extend(tools)
                    except Exception as e:
                        print(f"Error fetching agent tools: {e}")
                prompt = agent_info.prompt()
                # Build handoffs from handoff_tools
                handoffs = []
                if agent_info.handoff_tools:
                    for handoff_tool in agent_info.handoff_tools:
                        handoffs.append(HandoffWithType(target=handoff_tool.target, message=handoff_tool.message))
                else:
                    # Default handoff to user if none specified
                    handoffs = [HandoffWithType(target="user", message="Transfer to user.")]
                
                agent = agent_class(
                    name=agent_info.name,
                    model_client=model_client,
                    model_client_stream=True,
                    system_message=prompt,
                    tools=agent_tools,
                    description=agent_info.description,
                    memory=[user_memory],
                    handoffs=handoffs,
                    max_tool_iterations=10
                )
                agent.component_label = agent_info.name
                yield agent

        elif agent_info.type == AgentTypeEnum.USER_PROXY_AGENT:
            agent = agent_class(
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