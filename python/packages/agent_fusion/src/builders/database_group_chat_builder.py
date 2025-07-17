"""
数据库感知的群聊构建器

支持从数据库加载模型配置的群聊构建器
"""

from schemas.group_chat import ComponentInfo, GroupChatType, SelectorGroupChatConfig
from autogen_agentchat.teams import BaseGroupChat,SelectorGroupChat
from model_client import ModelClient
from model_client.database_model_client import DatabaseModelClientBuilder
from base.utils import get_prompt
from builders.database_agent_builder import DatabaseAgentBuilder
import json
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncGenerator, Callable, Awaitable, Optional
import asyncio
from builders.utils import GroupChatInfo
from autogen_core.models import ChatCompletionClient
from autogen_agentchat.base import ChatAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient


class DatabaseGroupChatBuilder:
    """支持数据库模型的群聊构建器"""
    
    def __init__(self, 
                 prompt_root: str, 
                 input_func: Callable[[str], Awaitable[str]] | None = input,
                 data_layer_instance = None,
                 dotenv_path: Optional[str] = None):
        """
        初始化群聊构建器
        
        Args:
            prompt_root: 提示词根目录
            input_func: 输入函数
            data_layer_instance: 数据层实例
            dotenv_path: .env文件路径
        """
        self._prompt_root: str = prompt_root
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func
        self.data_layer = data_layer_instance
        self.dotenv_path = dotenv_path
        
        # 初始化数据库模型客户端构建器
        if self.data_layer:
            self.db_model_builder = DatabaseModelClientBuilder(self.data_layer, dotenv_path)
        else:
            self.db_model_builder = None

    def _create_selector_group_chat(
        self, 
        participants: list[ChatAgent],
        selector_prompt: str,
        model_client: ChatCompletionClient,
        ) -> Callable[[], SelectorGroupChat]:
        def _factory() -> SelectorGroupChat:
            return SelectorGroupChat(
                participants=participants,
                selector_prompt=selector_prompt,
                model_client=model_client,
            )
        return _factory

    @asynccontextmanager
    async def build(self, name: str) -> AsyncGenerator[BaseGroupChat, None]:
        group_chat_info: ComponentInfo = GroupChatInfo[name]
        
        # 使用数据库感知的Agent构建器
        agent_builder = DatabaseAgentBuilder(
            self._input_func, 
            self.data_layer, 
            self.dotenv_path
        )
        
        async with AsyncExitStack() as stack:
            participants = await asyncio.gather(
                *[stack.enter_async_context(agent_builder.build(participant)) 
                for participant in group_chat_info.participants]
            )

            selector_prompt = get_prompt(group_chat_info.selector_prompt, prompt_path=self._prompt_root)
            
            # 尝试从数据库获取模型客户端
            model_client = None
            if self.db_model_builder:
                try:
                    model_client = await self.db_model_builder.get_model_client(group_chat_info.model_client.value)
                except Exception as e:
                    print(f"Failed to get model client from database for {group_chat_info.model_client.value}: {e}")
            
            # 如果数据库中没有找到，使用原有的ModelClient
            if not model_client:
                try:
                    model_client = ModelClient[group_chat_info.model_client.value]()
                except Exception as e:
                    print(f"Failed to get model client from ModelClient for {group_chat_info.model_client.value}: {e}")
                    raise ValueError(f"Model client not found: {group_chat_info.model_client.value}")
            
            if group_chat_info.type == GroupChatType.SELECTOR_GROUP_CHAT:
                group_chat = self._create_selector_group_chat(
                    participants=participants,
                    selector_prompt=selector_prompt,
                    model_client=model_client
                )()
                yield group_chat
                await model_client.close()
                await stack.aclose()
            else:
                raise ValueError(f"Invalid group chat type: {group_chat_info.type}")


class GroupChatBuilder:
    """保持向后兼容的群聊构建器"""
    
    def __init__(self, prompt_root: str, input_func: Callable[[str], Awaitable[str]] | None = input):
        self._prompt_root: str = prompt_root
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func

    def _create_selector_group_chat(
        self, 
        participants: list[ChatAgent],
        selector_prompt: str,
        model_client: ChatCompletionClient,
        ) -> Callable[[], SelectorGroupChat]:
        def _factory() -> SelectorGroupChat:
            return SelectorGroupChat(
                participants=participants,
                selector_prompt=selector_prompt,
                model_client=model_client,
            )
        return _factory

    @asynccontextmanager
    async def build(self, name: str) -> AsyncGenerator[BaseGroupChat, None]:
        group_chat_info: ComponentInfo = GroupChatInfo[name]
        
        agent_builder = AgentBuilder(self._input_func)
        async with AsyncExitStack() as stack:
            participants = await asyncio.gather(
                *[stack.enter_async_context(agent_builder.build(participant)) 
                for participant in group_chat_info.participants]
            )

            selector_prompt = get_prompt(group_chat_info.selector_prompt, prompt_path=self._prompt_root)
            model_client :OpenAIChatCompletionClient = ModelClient[group_chat_info.model_client.value]()
            if group_chat_info.type == GroupChatType.SELECTOR_GROUP_CHAT:
                group_chat = self._create_selector_group_chat(
                    participants=participants,
                    selector_prompt=selector_prompt,
                    model_client=model_client
                )()
                yield group_chat
                await model_client.close()
                await stack.aclose()
            else:
                raise ValueError(f"Invalid group chat type: {group_chat_info.type}") 