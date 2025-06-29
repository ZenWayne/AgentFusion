from schemas.group_chat import ComponentInfo, GroupChatType, SelectorGroupChatConfig
from autogen_agentchat.teams import BaseGroupChat,SelectorGroupChat
from model_client import ModelClient
from base.utils import get_prompt
from builders.agent_builder import AgentBuilder
import json
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncGenerator, Callable, Awaitable, abstractmethod
import asyncio
from builders.utils import GroupChatInfo
from autogen_core.models import ChatCompletionClient
from autogen_agentchat.base import ChatAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient

class GroupChatBuilder:
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