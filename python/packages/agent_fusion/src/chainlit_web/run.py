import asyncio
import chainlit as cl
from chainlit import Message
from schemas import ComponentType, Component
from schemas.agent import AgentType, ComponentInfo
import dataclasses
from typing import Dict, cast
from dotenv import load_dotenv
from builders import GraphFlowBuilder
from builders import load_info
from builders import utils as builders_utils
from builders.database_group_chat_builder import DatabaseGroupChatBuilder
from autogen_agentchat.teams import BaseGroupChat
from autogen_core import CancellationToken
from autogen_agentchat.ui import Console
from aglogger import enable_autogen_logger, FilterType, enable_chainlit_logger
from chainlit.input_widget import Select, Switch, Slider
from chainlit_web import user
from chainlit_web.user.auth import get_data_layer, data_layer_instance
from chainlit_web.users import User, UserSessionManager
from chainlit.config import config
from contextlib import asynccontextmanager
from chainlit_web.data_layer.models.agent_model import AgentModel
from chainlit_web.data_layer.models.llm_model import LLMModel
from schemas.model_info import ModelClientConfig

MODEL_WIDGET_ID = "Model"

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
    try:
        # 从数据库获取可用的agents和group_chats
        agents = await data_layer_instance.agent.get_all_components()
        group_chats = await data_layer_instance.group_chat.get_all_components()
        
        profiles = []
        
        # 添加Agent选项
        for agent_name, agent_info in agents.items():
            profiles.append(cl.ChatProfile(
                name=agent_name,
                markdown_description=f"**Agent**: {agent_info.description}",
                icon="https://picsum.photos/200",
            ))
        
        # 添加GroupChat选项
        for group_name, group_info in group_chats.items():
            profiles.append(cl.ChatProfile(
                name=group_name,
                markdown_description=f"**Group Chat**: {group_info.get('description', 'Group conversation')}",
                icon="https://picsum.photos/250",
            ))
        
        # 如果没有从数据库获取到任何配置，使用默认配置
        if not profiles:
            profiles = [
                cl.ChatProfile(
                    name="hil",
                    markdown_description="**Default Group Chat**: Human-in-the-loop conversation",
                    icon="https://picsum.photos/200",
                ),
            ]
        
        return profiles
        
    except Exception as e:
        print(f"Error loading chat profiles: {e}")
        # 发生错误时返回默认配置
        return [
            cl.ChatProfile(
                name="hil",
                markdown_description="**Default Group Chat**: Human-in-the-loop conversation",
                icon="https://picsum.photos/200",
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
    # config.run.port = 443
    # config.run.host = "e73cd5b88ea8.ngrok-free.app"
    enable_chainlit_logger()
    enable_autogen_logger(["autogen_core.events"], filter_types=[FilterType.ToolCall, FilterType.LLMCall])
    global data_layer_instance
    data_layer_instance=get_data_layer()
    
    # Initialize component_info_map in UserSessionManager (only once)
    user_session_manager = UserSessionManager()
    await user_session_manager.initialize_component_info_map(data_layer_instance)
    User.user_session_manager = user_session_manager    
    print("on_app_startup")

@cl.on_settings_update
async def setup_agent(settings: cl.ChatSettings):
    """当设置更新时，根据选择的聊天配置更新Agent"""
    try:
        current_user = User()
        
        # 处理模型选择
        model_widget = next((widget for widget in settings.inputs if widget.id == MODEL_WIDGET_ID), None)
        if model_widget:
            model_name = model_widget.initial
            print(f"Selected model: {model_name}")
            current_user.current_model_client = await data_layer_instance.llm.get_component_by_name(model_name)
        
        # 获取当前聊天配置
        chat_profile = cl.user_session.get("chat_profile")
        if not chat_profile:
            return
        
        # 检查是否需要切换Agent/GroupChat
        current_component_name = current_user.current_component_name
        
        if current_component_name != chat_profile:
            # 需要切换，先清理当前的聊天
            await current_user.cleanup_current_chat()
            
            # 使用已设置的model_client设置新组件
            await current_user.setup_new_component(chat_profile, data_layer_instance)
            
            # 通知用户切换完成
            await cl.Message(
                content=f"已切换到 {chat_profile}",
                author="System"
            ).send()
        
        # 更新其他设置
        current_user.settings.update(settings)
        
    except Exception as e:
        print(f"Error in setup_agent: {e}")
        await cl.Message(
            content=f"切换失败: {str(e)}",
            author="System"
        ).send()

async def chat_settings():
     model_list : list[ModelClientConfig] = await data_layer_instance.llm.get_all_components()
     
     # 缓存model_list到UserSessionManager
     if User.user_session_manager:
         User.user_session_manager.cache_model_list(model_list)
     
     return await cl.ChatSettings(
        [Select(
                id=MODEL_WIDGET_ID,
                label=model_list[0].label if len(model_list) > 0 else "No model found",
                values=[model.label for model in model_list],
                initial_index=0,
            )]
        )

@cl.on_chat_start  # type: ignore
async def start_chat() -> None:
    """this function will called every time user start a session to chat"""
    # Load model configuration and create the model client.
    print("start_chat")
    load_info()
    
    user = cl.user_session.get("user")
    chat_profile: str = cl.user_session.get("chat_profile")
    await cl.Message(
        content=f"starting chat with {user.identifier} using the {chat_profile} chat profile"
    ).send()
    await chat_settings()

    current_user = User()
    await current_user.start_chat(chat_profile, data_layer_instance)

@cl.on_message  # type: ignore
async def chat(message: cl.Message) -> None:
    # 使用User对象管理消息
    current_user = User()
    await current_user.chat(message)

@cl.on_chat_end  # type: ignore
async def end_chat() -> None:
    """Called when chat session ends - cleanup resources"""
    current_user = User()
    await current_user.cleanup_current_chat()

async def dry_run():
    await start_chat()
    await chat(cl.Message(content="Hello, how are you?"))
    await end_chat()

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
