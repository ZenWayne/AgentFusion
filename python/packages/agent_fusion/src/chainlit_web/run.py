import asyncio
import chainlit as cl
from chainlit import Message
from schemas import ComponentType, Component
import dataclasses
from typing import Dict, cast
from dotenv import load_dotenv
from builders import GraphFlowBuilder
from builders import load_info
from builders import utils as builders_utils
from chainlit_web.ui_hook.ui_select_group_chat import (
    UISelectorGroupChatBuilder
)
from autogen_agentchat.teams import BaseGroupChat
from autogen_core import CancellationToken
from autogen_agentchat.ui import Console
from aglogger import enable_autogen_logger, FilterType, enable_chainlit_logger
from chainlit.input_widget import Select, Switch, Slider
from chainlit_web import user
from chainlit_web.user.auth import get_data_layer, data_layer_instance


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

@cl.set_chat_profiles
async def chat_profile():
    return [
        cl.ChatProfile(
            name="GPT-3.5",
            markdown_description="The underlying LLM model is **GPT-3.5**.",
            icon="https://picsum.photos/200",
        ),
        cl.ChatProfile(
            name="GPT-4",
            markdown_description="The underlying LLM model is **GPT-4**.",
            icon="https://picsum.photos/250",
        ),
    ]

async def wrap_input(prompt: str, token: CancellationToken) -> str:
    message_queue = cast(asyncio.Queue[str], cl.user_session.get("message_queue"))  # type: ignore
    print(f"message_queue: {message_queue}")
    ready = cast(bool, cl.user_session.get("ready"))
    print(f"ready: {ready}")
    if not ready:
        cl.user_session.set("ready", True)
    message = await message_queue.get()
    return message

@cl.on_app_startup
async def on_app_startup() -> None:
    load_dotenv()
    enable_chainlit_logger()
    enable_autogen_logger(["autogen_core.events"], filter_types=[FilterType.ToolCall, FilterType.LLMCall])
    global data_layer_instance
    data_layer_instance=get_data_layer()
    print("on_app_startup")

@cl.on_chat_start  # type: ignore
async def start_chat() -> None:
    # Load model configuration and create the model client.
    print("start_chat")
    load_info()
    settings = await cl.ChatSettings(
        [
            Select(
                id="Model",
                label="OpenAI - Model",
                values=["gpt-3.5-turbo", "gpt-3.5-turbo-16k", "gpt-4", "gpt-4-32k"],
                initial_index=0,
            ),
            Switch(id="Streaming", label="OpenAI - Stream Tokens", initial=True),
            Slider(
                id="Temperature",
                label="OpenAI - Temperature",
                initial=1,
                min=0,
                max=2,
                step=0.1,
            ),
            Slider(
                id="SAI_Steps",
                label="Stability AI - Steps",
                initial=30,
                min=10,
                max=150,
                step=1,
                description="Amount of inference steps performed on image generation.",
            ),
            Slider(
                id="SAI_Cfg_Scale",
                label="Stability AI - Cfg_Scale",
                initial=7,
                min=1,
                max=35,
                step=0.1,
                description="Influences how strongly your generation is guided to match your prompt.",
            ),
            Slider(
                id="SAI_Width",
                label="Stability AI - Image Width",
                initial=512,
                min=256,
                max=2048,
                step=64,
                tooltip="Measured in pixels",
            ),
            Slider(
                id="SAI_Height",
                label="Stability AI - Image Height",
                initial=512,
                min=256,
                max=2048,
                step=64,
                tooltip="Measured in pixels",
            ),
        ]
    ).send()

    component_config = Component(type=ComponentType.GROUP_CHAT, name="hil")

    if component_config.type == ComponentType.AGENT:
        #TODO
        pass
    elif component_config.type == ComponentType.GROUP_CHAT:
        groupchat_builder = UISelectorGroupChatBuilder(
            prompt_root=builders_utils.prompt_root, 
            input_func=wrap_input,
            model_client_streaming=True
            )
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
            message_queue = asyncio.Queue()
            cl.user_session.set("message_queue", message_queue)
            cl.user_session.set("groupchat", groupchat)  # type: ignore
            # Store the context manager for later exit
            cl.user_session.set("groupchat_context", async_context_manager)  # type: ignore
            asyncio.create_task(Console(groupchat.run_stream()))
            cl.user_session.set("ready",False)
            #sync the ready flag
            while not cl.user_session.get("ready"):
                await asyncio.sleep(0.5)
            
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
