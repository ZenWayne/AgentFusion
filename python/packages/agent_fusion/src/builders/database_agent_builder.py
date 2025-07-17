"""
数据库感知的Agent构建器

支持从数据库加载模型配置的Agent构建器
"""

from base.utils import get_prompt  
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from schemas.agent import AssistantAgentConfig, UserProxyAgentConfig, AgentType, InputFuncType, ComponentInfo
from model_client import ModelClient
from model_client.database_model_client import DatabaseModelClientBuilder
from autogen_ext.tools.mcp import mcp_server_tools, McpServerParams
from autogen_ext.tools.mcp import StdioMcpToolAdapter, SseMcpToolAdapter
from .utils import AgentInfo
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Awaitable, Optional
from autogen_core.memory import ListMemory


class DatabaseAgentBuilder:
    """支持数据库模型的Agent构建器"""
    
    def __init__(self, 
                 input_func: Callable[[str], Awaitable[str]] | None = input,
                 data_layer_instance = None,
                 dotenv_path: Optional[str] = None):
        """
        初始化Agent构建器
        
        Args:
            input_func: 输入函数
            data_layer_instance: 数据层实例
            dotenv_path: .env文件路径
        """
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func
        self.data_layer = data_layer_instance
        self.dotenv_path = dotenv_path
        
        # 初始化数据库模型客户端构建器
        if self.data_layer:
            self.db_model_builder = DatabaseModelClientBuilder(self.data_layer, dotenv_path)
        else:
            self.db_model_builder = None

    @asynccontextmanager
    async def build(self, name: str) -> AsyncGenerator[AssistantAgent | UserProxyAgent, None]:
        agent_info: AssistantAgentConfig| UserProxyAgentConfig = AgentInfo[name]

        user_memory = ListMemory()
        if agent_info.type == AgentType.ASSISTANT_AGENT:
            # 尝试从数据库获取模型客户端
            model_client = None
            if self.db_model_builder:
                try:
                    model_client = await self.db_model_builder.get_model_client(agent_info.model_client.value)
                except Exception as e:
                    print(f"Failed to get model client from database for {agent_info.model_client.value}: {e}")
            
            # 如果数据库中没有找到，使用原有的ModelClient
            if not model_client:
                try:
                    model_client = ModelClient[agent_info.model_client.value]()
                except Exception as e:
                    print(f"Failed to get model client from ModelClient for {agent_info.model_client.value}: {e}")
                    raise ValueError(f"Model client not found: {agent_info.model_client.value}")
            
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


class AgentBuilder:
    """保持向后兼容的Agent构建器"""
    
    def __init__(self, input_func: Callable[[str], Awaitable[str]] | None = input):
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func

    @asynccontextmanager
    async def build(self, name: str) -> AsyncGenerator[AssistantAgent | UserProxyAgent, None]:
        agent_info: AssistantAgentConfig| UserProxyAgentConfig = AgentInfo[name]

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