"""
User session management module using OOP principles.

This module provides a User class to manage dynamic objects like agent settings,
component info maps, and messages for each user session.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import chainlit as cl
from schemas.model_info import ModelClientConfig
from schemas.component import ComponentInfo
from schemas.types import ComponentType
from schemas.agent import AgentType
from schemas.group_chat import GroupChatType
from autogen_agentchat.teams import BaseGroupChat
from chainlit_web.ui_hook.ui_select_group_chat import UIGroupChatBuilder
from autogen_core import CancellationToken
from chainlit.user_session import UserSession
from chainlit.context import context
from autogen_agentchat.ui import Console
from data_layer.data_layer import AgentFusionDataLayer
from data_layer.models.llm_model import LLMModel
from builders.agent_builder import AgentBuilder
from chainlit.types import ChatProfile

MODEL_WIDGET_ID = "Model"  # 常量定义

# @dataclass
# class ChatProfile(cl.ChatProfile):
#     #id: Optional[int] = None
#     component_type: Optional[ComponentType] = None
@dataclass
class UserSessionData:
    """Data container for user session information"""
    chat_profile : Optional[List[ChatProfile]] = None
    component_info_map: Dict[str, ComponentInfo] = field(default_factory=dict)
    current_component_name: Optional[str] = None
    current_component: Optional[Any] = None
    current_component_context: Optional[Any] = None
    current_model_client: Optional[ModelClientConfig] = None
    message_queue: Optional[asyncio.Queue] = None
    close_event: Optional[asyncio.Event] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    ready: bool = False
    messages: List[Dict[str, Any]] = field(default_factory=list)

class UserSessionManager:
    def __init__(self):
        self.user_sessions = {}
        self.component_info_map = {}
        self.model_list = []
    
    def get(self, key, default=None):
        if not context.session:
            return default
    
    async def initialize_component_info_map(self, data_layer_instance: AgentFusionDataLayer):
        """Initialize component_info_map during startup"""
        try:
            agents = await data_layer_instance.agent.get_all_components()  # List[ComponentInfo]
            group_chats = await data_layer_instance.group_chat.get_all_components()  # List[ComponentInfo]
            
            agents_dict = {agent.name: agent for agent in agents}
            # 将group_chats列表转换为字典
            group_chats_dict = {gc.name: gc for gc in group_chats}
            
            self.component_info_map = {**agents_dict, **group_chats_dict}
        except Exception as e:
            print(f"Error initializing component_info_map: {e}")
            self.component_info_map = {}
    
    def cache_model_list(self, model_list: List[ModelClientConfig]):
        """缓存模型列表到session manager"""
        self.model_list = model_list

    def get_model_list(self):
        return self.model_list



class User(UserSessionData, UserSession):
    """
    Manages user session data and provides methods for handling dynamic objects
    like agent settings, component info maps, and messages.
    """
    user_session_manager: Optional[UserSessionManager] = None  # 延迟初始化，在startup时设置
    
    def __init__(self):
        """
        Initialize User instance
        
        Args:
            session_data: Optional initial session data
        """
        if context.session and context.session.user:
            self.identifier = context.session.user.identifier
        else:
            self.identifier = "anonymous"
        self.init_session_data()

    def get(self, key, default=None):
        if not context.session:
            return default

        if self.user_session_manager is None:
            # UserSessionManager not initialized yet, return default
            return default

        if context.session.id not in self.user_session_manager.user_sessions:
            # Create a new user session
            self.user_session_manager.user_sessions[context.session.id] = {}

        user_session = self.user_session_manager.user_sessions[context.session.id]

        # Copy important fields from the session
        user_session["id"] = context.session.id
        user_session["env"] = context.session.user_env
        user_session["chat_settings"] = context.session.chat_settings
        user_session["user"] = context.session.user
        user_session["chat_profile"] = context.session.chat_profile
        user_session["client_type"] = context.session.client_type

        return user_session.get(key, default)

    def set(self, key: str, value: Any) -> Any:
        """Set a value in user session and return it"""
        if not context.session or self.user_session_manager is None:
            return value
            
        if context.session.id not in self.user_session_manager.user_sessions:
            self.user_session_manager.user_sessions[context.session.id] = {}
            
        self.user_session_manager.user_sessions[context.session.id][key] = value
        return value

    def init_session_data(self):
        if self.user_session_manager is None:
            # UserSessionManager not initialized yet, skip initialization
            return

        if context.session.id not in self.user_session_manager.user_sessions:
            # Create a new user session
            self.user_session_manager.user_sessions[context.session.id] = {}

        user_session = self.user_session_manager.user_sessions[context.session.id]

        self.chat_profile = self.set("chat_profile", None)
        # component_info_map现在从SessionManager中获取
        self.current_component_name = self.set("current_component_name", "default")
        self.current_component = self.set("current_component", None)
        self.current_component_context = self.set("current_component_context", None)
        self.current_model_client = self.set("current_model_client", None)
        self.message_queue = self.set("message_queue", None)
        self.close_event = self.set("close_event", None)
        self.settings = self.set("settings", {})
        self.ready = self.set("ready", False)
    
    def create_message_queue(self) -> asyncio.Queue:
        """Create and set a new message queue"""
        self.message_queue = asyncio.Queue()
        self.close_event = asyncio.Event()
        return self.message_queue
    
    def signal_close(self) -> None:
        """Signal close event to unblock waiting operations"""
        if self.close_event:
            self.close_event.set()
    
    def clear_chat_resources(self) -> None:
        """Clear chat-related resources (component, message queue)"""
        if self.close_event:
            self.close_event.set()  # Signal close before clearing
        self.current_component = None
        self.current_component_context = None
        self.message_queue = None
        self.close_event = None
        self.ready = False
    
    async def start_chat(self, data_layer: AgentFusionDataLayer):
        """Initialize and start chat session"""
        try:
            if self.chat_profile is None:
                self.chat_profile = self.set("chat_profile", await User.get_chat_profiles(data_layer))

            component_name = self.chat_profile[0].name
            await cl.Message(
                content=f"starting chat with {self.identifier} using the {component_name} chat profile"
            ).send()

            # Get component_info_map from session manager
            component_info_map = self.user_session_manager.component_info_map
            await self.setup_new_component(component_name, component_info_map, data_layer)
            self.current_component_name = component_name
            
        except Exception as e:
            print(f"Error in start_chat: {e}")
            raise
    
    async def input_func(self):
        async def wrap_input(prompt: str, token: CancellationToken) -> str:
            if not self.ready:
                self.ready = True
            
            # Check if message queue and close event exist
            if not self.message_queue or not self.close_event:
                raise RuntimeError("Message queue or close event not initialized")
            
            # Create tasks for both message queue and close event
            message_task = asyncio.create_task(self.message_queue.get())
            close_task = asyncio.create_task(self.close_event.wait())
            
            try:
                # Wait for either message or close signal (like Unix select)
                done, _ = await asyncio.wait(
                    {message_task, close_task}, 
                    return_when=asyncio.FIRST_COMPLETED
                )
                
                # Cancel pending tasks
                # for task in pending:
                #     task.cancel()
                #     try:
                #         await task
                #     except asyncio.CancelledError:
                #         pass
                
                # Check which task completed
                for task in done:
                    if task == close_task:
                        # Close signal received
                        token.cancel()
                        raise asyncio.CancelledError("Chat session closed")
                    elif task == message_task:
                        # Message received
                        return task.result()
                        
            except asyncio.CancelledError:
                # Clean up tasks if cancelled
                message_task.cancel()
                close_task.cancel()
                raise
                
        return wrap_input

    async def component_create(self, component_info: ComponentInfo, data_layer: AgentFusionDataLayer):
        wrap_input = self.input_func()
        factory_map = {
            AgentType.ASSISTANT_AGENT: AgentBuilder(input_func=wrap_input).build,
            AgentType.USER_PROXY_AGENT: AgentBuilder(input_func=wrap_input).build,
            GroupChatType.SELECTOR_GROUP_CHAT:UIGroupChatBuilder(data_layer=data_layer,input_func=wrap_input).build,
            GroupChatType.ROUND_ROBIN_GROUP_CHAT:UIGroupChatBuilder(data_layer=data_layer,input_func=wrap_input).build,
        }
        async_context = factory_map[component_info.type](component_info)
        return async_context

    async def component_cleanup(self, component: Any):
        await component.__aexit__(None, None, None)
    
    async def setup_new_component(self, component_name: str, component_info_map: Dict[str, ComponentInfo], data_layer: AgentFusionDataLayer):
        """Set up new component (Agent or GroupChat)"""
        try:
            component_info = component_info_map.get(component_name)

            async_context = await self.component_create(
                component_info, 
                data_layer
            )

            self.current_component_context = async_context
            component = await async_context.__aenter__()
            self.current_component = component
            asyncio.create_task(Console(component.run_stream()))
            self.create_message_queue()

            #only for selector group chat
            if component_info.type == GroupChatType.SELECTOR_GROUP_CHAT:
                self.ready = False            
                # Wait for ready
                while not self.ready:
                    await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"Error in setup_new_component: {e}")
            raise
    
    async def chat(self, message: cl.Message):
        """Handle incoming chat message"""
        try:
            if self.message_queue and not self.close_event.is_set():
                self.message_queue.put_nowait(message.content)
            else:
                print("Message queue not available or session closed")
                
        except Exception as e:
            print(f"Error in chat: {e}")
    
    async def cleanup_current_chat(self):
        """Clean up current chat resources"""
        try:
            # Clean up current component
            if self.current_component_context:
                await self.current_component_context.__aexit__(None, None, None)
                
            # Clear resources
            self.clear_chat_resources()
            
        except Exception as e:
            print(f"Error in cleanup_current_chat: {e}")

    async def settings_update(self, settings: cl.ChatSettings, data_layer_instance: AgentFusionDataLayer):
        """处理设置更新，主要处理模型选择"""
        try:            
            # 处理模型选择
            model_widget = next((widget for widget in settings.inputs if widget.id == MODEL_WIDGET_ID), None)
            if model_widget:
                model_name = model_widget.initial
                print(f"Selected model: {model_name}")
                self.current_model_client = await data_layer_instance.llm.get_component_by_name(model_name)
            
            # 更新其他设置
            self.settings.update(settings)
            
        except Exception as e:
            print(f"Error in settings_update: {e}")
            await cl.Message(
                content=f"设置更新失败: {str(e)}",
                author="System"
            ).send()
    @staticmethod
    async def get_chat_profiles(data_layer_instance: AgentFusionDataLayer):
        """设置聊天配置文件，包含profile切换时的agent切换逻辑"""
        try:
            # 从数据库获取可用的agents和group_chats
            agents = await data_layer_instance.agent.get_all_components()
            group_chats = await data_layer_instance.group_chat.get_all_components()
            
            profiles = []
            
            # 添加Agent选项
            for agent_info in agents:
                profiles.append(ChatProfile(
                    name=agent_info.name,
                    markdown_description=f"**Agent**: {agent_info.description}",
                    icon="https://picsum.photos/200",
                    #component_type=agent_info.type
                ))
            
            # 添加GroupChat选项
            for group_chat in group_chats:
                profiles.append(ChatProfile(
                    name=group_chat.name,
                    markdown_description=f"**Group Chat**: {group_chat.description}",
                    icon="https://picsum.photos/250",
                    #component_type=group_chat.type
                ))
            
            # 如果没有从数据库获取到任何配置，使用默认配置
            if not profiles:
                profiles = [
                    ChatProfile(
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
                ChatProfile(
                    name="hil",
                    markdown_description="**Default Group Chat**: Human-in-the-loop conversation",
                    icon="https://picsum.photos/200",
                ),
            ]