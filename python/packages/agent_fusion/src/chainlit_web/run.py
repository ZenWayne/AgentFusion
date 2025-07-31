import chainlit as cl
from chainlit import Message
import dataclasses
from typing import Dict
from dotenv import load_dotenv
from builders import load_info
from aglogger import enable_autogen_logger, FilterType, enable_chainlit_logger
from chainlit.input_widget import Select
from chainlit_web.user.auth import get_data_layer
from data_layer.data_layer import database_layer
from chainlit_web.users import User, UserSessionManager
from logging import getLogger
from aglogger.agentgerator_logger import gobal_log_filterer

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
    return await User.get_chat_profiles(database_layer)

@cl.on_app_startup
async def on_app_startup() -> None:
    load_dotenv()
    # config.run.port = 443
    # config.run.host = "e73cd5b88ea8.ngrok-free.app"
    #enable_chainlit_logger()
    #enable_autogen_logger(["autogen_core.events"], filter_types=[FilterType.ToolCall, FilterType.LLMCall])
    enable_autogen_logger(["chainlit_web","chainlit"])
    global database_layer
    database_layer=get_data_layer()
    
    # Initialize component_info_map in UserSessionManager (only once)
    user_session_manager = UserSessionManager()
    await user_session_manager.initialize_component_info_map(database_layer)
    User.user_session_manager = user_session_manager    
    print("on_app_startup")

@cl.on_settings_update
async def settings_update(settings: cl.ChatSettings):
    """当设置更新时，根据选择的聊天配置更新Agent"""
    current_user = User()
    await current_user.settings_update(settings, database_layer)

async def chat_settings():
     model_list= User.user_session_manager.get_model_list()
         
     if not model_list:
        model_list : list[ModelClientConfig] = await database_layer.llm.get_all_components()
        User.user_session_manager.cache_model_list(model_list)
     
     return await cl.ChatSettings(
        [Select(
                id=MODEL_WIDGET_ID,
                label=model_list[0].label if len(model_list) > 0 else "No model found",
                values=[model.label for model in model_list],
                initial_index=0,
            )]
        ).send()

@cl.on_chat_start  # type: ignore
async def start_chat() -> None:
    """this function will called every time user start a session to chat"""
    # Load model configuration and create the model client.
    print("start_chat")
    await chat_settings() 
    current_user = User()   
    await current_user.start_chat(database_layer)

@cl.on_stop
async def on_stop() -> None:
    current_user = User()
    await current_user.on_stop()

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
