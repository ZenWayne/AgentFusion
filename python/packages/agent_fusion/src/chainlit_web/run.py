import asyncio
import chainlit as cl
from chainlit import Message
from schemas import ComponentType, Component
import dataclasses
from typing import Dict

from builders import GraphFlowBuilder
from builders import load_info
from builders import utils as builders_utils
from chainlit_web.ui_hook.ui_select_group_chat import (
    UISelectorGroupChatBuilder
)
from autogen_agentchat.teams import BaseGroupChat
from autogen_core import CancellationToken
from autogen_agentchat.ui import Console


# TODO: Import get_weather function from appropriate module
# from your_weather_module import get_weather

@dataclasses.dataclass
class MessageChunk:
    message_id: str
    text: str
    author: str
    finished: bool

    def __str__(self) -> str:
        return f"{self.author}({self.message_id}): {self.text}"

message_chunks: Dict[str, Message] = {}

async def wrap_input(prompt: str, token: CancellationToken) -> str:
    message_queue = cast(asyncio.Queue[str], cl.user_session.get("message_queue"))  # type: ignore
    message = await message_queue.get()
    return message

@cl.on_chat_start  # type: ignore
async def start_chat() -> None:
    # Load model configuration and create the model client.
    print("start_chat")
    load_info()

    component_config = Component(type=ComponentType.GROUP_CHAT, name="hil")

    if component_config.type == ComponentType.AGENT:
        #TODO
        pass
    elif component_config.type == ComponentType.GROUP_CHAT:
        groupchat_builder = UISelectorGroupChatBuilder(prompt_root=builders_utils.prompt_root, input_func=wrap_input)
        groupchat_factory_func = {
            ComponentType.GROUP_CHAT: groupchat_builder.build,
            ComponentType.GRAPH_FLOW: GraphFlowBuilder
        }
        builder = groupchat_factory_func[component_config.type]
        
        # Better type safety: use a different variable name for the built component
        # The built_component type depends on the builder type used
        
        # Manual enter context - get the async context manager
        async_context_manager = builder(component_config.name)
        
        # Call __aenter__ manually to enter the context
        groupchat:BaseGroupChat = await async_context_manager.__aenter__()
        
        try:
            asyncio.create_task(Console(groupchat.run_stream()))
            cl.user_session.set("groupchat", groupchat)  # type: ignore
            # Store the context manager for later exit
            cl.user_session.set("groupchat_context", async_context_manager)  # type: ignore
            message_queue = asyncio.Queue()
            cl.user_session.set("message_queue", message_queue)
        except Exception as e:
            # If something goes wrong, make sure to exit the context
            await async_context_manager.__aexit__(type(e), e, e.__traceback__)
            raise
    else:
        raise ValueError(f"Invalid component type: {component_config.type}")

@cl.on_message  # type: ignore
async def chat(message: cl.Message) -> None:
    # Get the assistant agent from the user session.
    message_queue = cast(asyncio.Queue[str], cl.user_session.get("message_queue"))  # type: ignore
    message_queue.put_nowait(message.content)
    #group_chat = cast(BaseGroupChat, cl.user_session.get("groupchat"))  # type: ignore
    # topic_type = group_chat._output_topic_type
    # group_chat._runtime.publish_message(
    #     message=GroupChatMessage(message=TextMessage(content=message.content)),
    #     topic_id=DefaultTopicId(type=topic_type),
    # )

# Function to manually call exit context
async def cleanup_groupchat() -> None:
    """Manually call exit context for the groupchat"""
    async_context_manager = cl.user_session.get("groupchat_context")  # type: ignore
    if async_context_manager:
        await async_context_manager.__aexit__(None, None, None)
        cl.user_session.set("groupchat_context", None)  # type: ignore

@cl.on_chat_end  # type: ignore
async def end_chat() -> None:
    """Called when chat session ends - cleanup resources"""
    await cleanup_groupchat()

async def dry_run():
    await start_chat()
    await chat(cl.Message(content="Hello, how are you?"))
    await end_chat()

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
