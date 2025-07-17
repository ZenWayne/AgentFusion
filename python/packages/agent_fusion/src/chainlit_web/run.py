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
from builders.database_agent_builder import DatabaseAgentBuilder
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
from chainlit.config import config


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
        agents = await data_layer_instance.get_agents_for_chat_profile()
        group_chats = await data_layer_instance.get_group_chats_for_chat_profile()
        
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
    print("on_app_startup")

async def chat_settings():
     
     model_list = await data_layer_instance.get_model_list()
     
     # 构建模型选项列表
     model_values = []
     model_labels = []
     initial_index = 0
     
     for i, model in enumerate(model_list):
         model_values.append(model["label"])
         model_labels.append(f"{model['label']} - {model['description']}")
         if i == 0:  # 第一个模型作为默认选择
             initial_index = 0
     
     # 如果没有数据库模型，使用默认选项
     if not model_values:
         raise ValueError("No models found in the database")
     
     # 初始化ComponentInfoMap
     agents = await data_layer_instance.get_agents_for_chat_profile()
     group_chats = await data_layer_instance.get_group_chats_for_chat_profile()
     
     # 创建ComponentInfoMap并存储到session中
     component_info_map = {**agents, **group_chats}
     cl.user_session.set("component_info_map", component_info_map)
     
     await cl.ChatSettings(
        [
            Select(
                id="Model",
                label="LLM Model",
                values=model_values,
                initial_index=initial_index,
            ),
            Switch(id="Streaming", label="Stream Tokens", initial=True),
            Slider(
                id="Temperature",
                label="Temperature",
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

@cl.on_settings_update
async def setup_agent(settings):
    """当设置更新时，根据选择的聊天配置更新Agent"""
    try:
        # 获取当前选择的聊天配置
        chat_profile = cl.user_session.get("chat_profile")
        if not chat_profile:
            return
            
        # 获取ComponentInfoMap
        component_info_map = cl.user_session.get("component_info_map", {})
        
        # 检查是否需要切换Agent/GroupChat
        current_component_name = cl.user_session.get("current_component_name")
        
        if current_component_name != chat_profile:
            # 需要切换，先清理当前的聊天
            await cleanup_current_chat()
            
            # 设置新的组件
            await setup_new_component(chat_profile, component_info_map)
            
            # 更新当前组件名称
            cl.user_session.set("current_component_name", chat_profile)
            
            # 通知用户切换完成
            await cl.Message(
                content=f"已切换到 {chat_profile}",
                author="System"
            ).send()
        
        # 更新其他设置
        cl.user_session.set("settings", settings)
        
    except Exception as e:
        print(f"Error in setup_agent: {e}")
        await cl.Message(
            content=f"切换失败: {str(e)}",
            author="System"
        ).send()

async def cleanup_current_chat():
    """清理当前聊天资源"""
    try:
        # 清理GroupChat
        await cleanup_groupchat()
        
        # 清理Agent
        await cleanup_agent()
        
        # 清理session中的相关数据
        cl.user_session.set("current_agent", None)
        cl.user_session.set("groupchat", None)
        cl.user_session.set("groupchat_context", None)
        cl.user_session.set("current_agent_context", None)
        cl.user_session.set("message_queue", None)
        cl.user_session.set("ready", False)
        
    except Exception as e:
        print(f"Error in cleanup_current_chat: {e}")

async def setup_new_component(component_name: str, component_info_map: Dict[str, ComponentInfo]):
    """设置新的组件（Agent或GroupChat）"""
    try:
        component_info = component_info_map.get(component_name)
        
        if component_info:
            # 这是一个Agent
            if component_info.type == AgentType.ASSISTANT_AGENT or component_info.type == AgentType.USER_PROXY_AGENT:
                await setup_agent_component(component_name, component_info)
            else:
                # 可能是GroupChat或其他类型
                await setup_groupchat_component(component_name)
        else:
            # 默认设置为GroupChat
            await setup_groupchat_component(component_name)
            
    except Exception as e:
        print(f"Error in setup_new_component: {e}")
        raise

async def setup_agent_component(agent_name: str, agent_info: ComponentInfo):
    """设置Agent组件"""
    try:
        # 创建Agent构建器
        agent_builder = DatabaseAgentBuilder(
            input_func=wrap_input,
            data_layer_instance=data_layer_instance
        )
        
        # 临时更新AgentInfo以便构建器使用
        builders_utils.AgentInfo[agent_name] = agent_info
        
        # 创建Agent
        async_context_manager = agent_builder.build(agent_name)
        agent = await async_context_manager.__aenter__()
        
        # 存储到session
        cl.user_session.set("current_agent", agent)
        cl.user_session.set("current_agent_context", async_context_manager)
        
        # 创建消息队列
        message_queue = asyncio.Queue()
        cl.user_session.set("message_queue", message_queue)
        
        # 对于单个Agent，我们需要创建一个简单的对话流
        # 这里暂时设置为ready状态，让用户可以开始对话
        cl.user_session.set("ready", True)
        
    except Exception as e:
        print(f"Error in setup_agent_component: {e}")
        raise

async def setup_groupchat_component(component_name: str):
    """设置GroupChat组件"""
    try:
        # 使用现有的GroupChat设置逻辑
        groupchat_builder = UISelectorGroupChatBuilder(
            prompt_root=builders_utils.prompt_root, 
            input_func=wrap_input,
            model_client_streaming=True
        )
        
        # 创建GroupChat
        async_context_manager = groupchat_builder.build(component_name)
        groupchat = await async_context_manager.__aenter__()
        
        # 存储到session
        message_queue = asyncio.Queue()
        cl.user_session.set("message_queue", message_queue)
        cl.user_session.set("groupchat", groupchat)
        cl.user_session.set("groupchat_context", async_context_manager)
        
        # 启动GroupChat
        asyncio.create_task(Console(groupchat.run_stream()))
        cl.user_session.set("ready", False)
        
        # 等待ready
        while not cl.user_session.get("ready"):
            await asyncio.sleep(0.1)
            
    except Exception as e:
        print(f"Error in setup_groupchat_component: {e}")
        raise

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

    # 获取ComponentInfoMap
    component_info_map = cl.user_session.get("component_info_map", {})
    
    # 设置初始组件
    await setup_new_component(chat_profile, component_info_map)
    
    # 设置当前组件名称
    cl.user_session.set("current_component_name", chat_profile)

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

async def cleanup_agent() -> None:
    """Manually call exit context for the agent"""
    async_context_manager = cl.user_session.get("current_agent_context")  # type: ignore
    if async_context_manager:
        await async_context_manager.__aexit__(None, None, None)
        cl.user_session.set("current_agent_context", None)  # type: ignore

@cl.on_chat_end  # type: ignore
async def end_chat() -> None:
    """Called when chat session ends - cleanup resources"""
    await cleanup_current_chat()

async def dry_run():
    await start_chat()
    await chat(cl.Message(content="Hello, how are you?"))
    await end_chat()

if __name__ == "__main__":
    from chainlit.cli import run_chainlit
    run_chainlit(__file__)
