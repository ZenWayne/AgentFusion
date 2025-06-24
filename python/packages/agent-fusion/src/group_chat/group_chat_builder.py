from dataclass.group_chat import ComponentInfo, GroupChatType, SelectorGroupChatConfig
from autogen_agentchat.teams import BaseGroupChat,SelectorGroupChat
from model_client import ModelClient
from base.utils import get_prompt
from agent.agent_builder import AgentBuilder
import json
from contextlib import asynccontextmanager, AsyncExitStack
from typing import AsyncGenerator
import asyncio


GroupChatInfo : dict[str, SelectorGroupChatConfig] = {}


def load_info(config_path: str) -> ComponentInfo:
    global GroupChatInfo
    with open(config_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    factory_func = {
        GroupChatType.SELECTOR_GROUP_CHAT: SelectorGroupChatConfig
    }
    for name, group_chat_config in metadata["group_chats"].items():
        GroupChatInfo[name] = factory_func[group_chat_config["type"]](**group_chat_config)
    return GroupChatInfo

@asynccontextmanager
async def GroupChatBuilder(name: str) -> AsyncGenerator[BaseGroupChat, None]:
    group_chat_info: ComponentInfo = GroupChatInfo[name]

    async with AsyncExitStack() as stack:
        participants = await asyncio.gather(
            *[stack.enter_async_context(AgentBuilder(participant)) for participant in group_chat_info.participants]
        )

        selector_prompt = get_prompt(f"{group_chat_info.selector_prompt}")

        if group_chat_info.type == GroupChatType.SELECTOR_GROUP_CHAT:
            group_chat = SelectorGroupChat(
                participants=participants,
                selector_prompt=selector_prompt,
                model_client=ModelClient[group_chat_info.model_client],
            )
        yield group_chat