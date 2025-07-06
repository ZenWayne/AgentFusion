from schemas.group_chat import ComponentInfo, GroupChatType, SelectorGroupChatConfig
from autogen import GroupChat, GroupChatManager
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

    async def build(self, name: str) -> GroupChatManager:
        group_chat_info: ComponentInfo = GroupChatInfo[name]
        
        agent_builder = AgentBuilder(self._input_func)
        participants = await asyncio.gather(
            *[agent_builder.build(participant) 
            for participant in group_chat_info.participants]
        )
        selector_prompt = get_prompt(group_chat_info.selector_prompt, prompt_path=self._prompt_root)
        groupchat = GroupChat(
            agents=participants, 
            messages=[], 
            max_round=99, 
            select_speaker_prompt_template=selector_prompt
        )
        model_client :dict = ModelClient[group_chat_info.model_client.value]
        group_chat_manager = GroupChatManager(
            groupchat=groupchat,
            llm_config=model_client
        )
        return group_chat_manager


async def test():
    from builders.utils import load_info
    from autogen.agentchat.user_proxy_agent import UserProxyAgent
    load_info()
    builder = GroupChatBuilder("config/prompt")
    group_chat_manager = await builder.build("prompt_flow")
    user_proxy: UserProxyAgent = next(agent for agent in group_chat_manager.groupchat.agents if agent.name.startswith("user"))
    if user_proxy:
        user_proxy.initiate_chat(group_chat_manager)
    else:
        raise ValueError("User proxy not found")

if __name__ == "__main__":
    asyncio.run(test())
    #python -m builders.group_chat_builder