from schemas.component import ComponentInfo, GroupChatType, TypedSelectorGroupChat, TypedRoundRobinGroupChat
from schemas.group_chat import GroupChatType as GroupChatTypeEnum, GroupChatConfig
from autogen_agentchat.teams import BaseGroupChat,SelectorGroupChat, RoundRobinGroupChat
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
from autogen_agentchat.conditions import HandoffTermination, TextMentionTermination
from autogen_agentchat.base import Handoff

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

    def _group_chat_map(self, GroupChatTypeEnum: GroupChatTypeEnum) -> Type[GroupChatType]:
        return {
            GroupChatTypeEnum.SELECTOR_GROUP_CHAT: TypedSelectorGroupChat,
            GroupChatTypeEnum.ROUND_ROBIN_GROUP_CHAT: TypedRoundRobinGroupChat
        }[GroupChatTypeEnum]

    def _create_group_chat_factory(
        self, 
        stack: AsyncExitStack,
        participants: list[ChatAgent],
        group_chat_info:GroupChatConfig
        ) -> Callable[[], GroupChatType]:
        async def _factory() -> GroupChatType:
            if group_chat_info.type not in GroupChatTypeEnum:
                raise ValueError(f"Invalid group chat type: {group_chat_info.type}")
            group_chat_class = self._group_chat_map(group_chat_info.type)
            if group_chat_info.type == GroupChatTypeEnum.SELECTOR_GROUP_CHAT:
                model_client_builder: ModelClientBuilder = self.model_client_builder()
                model_client_config = model_client_builder.get_component_by_name(group_chat_info.model_client)
                model_client = await stack.enter_async_context(model_client_builder.build(model_client_config))

                prompt_builder: PromptBuilder = self.prompt_builder()
                selector_prompt = prompt_builder.get_prompt_by_catagory_and_name(ComponentType.GROUP_CHAT, group_chat_info.selector_prompt)

                return group_chat_class(
                    participants=participants,
                    selector_prompt=selector_prompt,
                    model_client=model_client,
                )
            elif group_chat_info.type == GroupChatTypeEnum.ROUND_ROBIN_GROUP_CHAT:
                handoff_termination = HandoffTermination(target=group_chat_info.handoff_target)
                return group_chat_class(
                        participants=participants,
                        #TODO add this feild in round_robin_group_chat_config and add example in config.json
                        termination_condition=handoff_termination
                    )
            else:
                raise ValueError(f"Invalid group chat type: {group_chat_info.type}")
        return _factory

    @asynccontextmanager
    async def build(self, group_chat_info: GroupChatConfig) -> AsyncGenerator[BaseGroupChat, None]:
        
        agent_builder = self.agent_builder()
        async with AsyncExitStack() as stack:
            # 使用泛型类型创建 model_client_builder 实例
            
            # Use get_component_by_name to get agent configs by name
            agent_configs = [agent_builder.get_component_by_name(participant_name) 
                           for participant_name in group_chat_info.participants]
            participants = await asyncio.gather(
                *[stack.enter_async_context(agent_builder.build(agent_config)) 
                for agent_config in agent_configs]
            )
            
            factory = self._create_group_chat_factory(
                stack=stack,
                participants=participants,
                group_chat_info=group_chat_info
            )

            group_chat = await factory()
            yield group_chat
            await stack.aclose()