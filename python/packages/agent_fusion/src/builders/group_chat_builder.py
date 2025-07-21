from schemas.component import ComponentInfo
from schemas.group_chat import GroupChatType, SelectorGroupChatConfig
from autogen_agentchat.teams import BaseGroupChat,SelectorGroupChat
from builders.model_builder import ModelClientBuilder
from base.utils import get_prompt
from builders.agent_builder import AgentBuilder
import json
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncGenerator, Callable, Awaitable, abstractmethod, TypeVar, Generic, Type
import asyncio
from builders.utils import GroupChatInfo
from autogen_core.models import ChatCompletionClient
from autogen_agentchat.base import ChatAgent
from schemas.model_info import model_client as model_client_label
from builders.prompt_builder import PromptBuilder
from schemas.types import ComponentType

class GroupChatBuilder:
    def __init__(
        self,
        input_func: Callable[[str], Awaitable[str]] | None = None
    ):
        self._input_func: Callable[[str], Awaitable[str]] | None = input_func

    def agent_builder(self) -> AgentBuilder:
        return AgentBuilder()

    def model_client_builder(self) -> ModelClientBuilder:
        return ModelClientBuilder()

    def prompt_builder(self) -> PromptBuilder:
        return PromptBuilder()

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
    async def build(self, group_chat_info: SelectorGroupChatConfig) -> AsyncGenerator[BaseGroupChat, None]:
        
        agent_builder = self.agent_builder()
        async with AsyncExitStack() as stack:
            # 使用泛型类型创建 model_client_builder 实例
            model_client_builder: ModelClientBuilder = self.model_client_builder()
            model_client_config = model_client_builder.get_component_by_name(group_chat_info.model_client)
            model_client = await stack.enter_async_context(model_client_builder.build(model_client_config))
            
            # Use get_component_by_name to get agent configs by name
            agent_configs = [agent_builder.get_component_by_name(participant_name) 
                           for participant_name in group_chat_info.participants]
            participants = await asyncio.gather(
                *[stack.enter_async_context(agent_builder.build(agent_config)) 
                for agent_config in agent_configs]
            )
            prompt_builder: PromptBuilder = self.prompt_builder()
            selector_prompt = prompt_builder.get_prompt_by_catagory_and_name(ComponentType.GROUP_CHAT, group_chat_info.selector_prompt)

            if group_chat_info.type == GroupChatType.SELECTOR_GROUP_CHAT:
                group_chat = self._create_selector_group_chat(
                    participants=participants,
                    selector_prompt=selector_prompt,
                    model_client=model_client
                )()
                yield group_chat
                await stack.aclose()
            else:
                raise ValueError(f"Invalid group chat type: {group_chat_info.type}")