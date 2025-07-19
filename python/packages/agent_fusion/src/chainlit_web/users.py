"""
User session management module using OOP principles.

This module provides a User class to manage dynamic objects like agent settings,
component info maps, and messages for each user session.
"""

import asyncio
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
import chainlit as cl
from schemas.model_info import ModelClientConfig
from schemas.agent import ComponentInfo
from schemas.agent import AgentType
from autogen_agentchat.teams import BaseGroupChat
from autogen_core import CancellationToken
from chainlit.user_session import UserSession
from chainlit.context import context
from autogen_agentchat.ui import Console


@dataclass
class UserSessionData:
    """Data container for user session information"""
    chat_profile : Optional[str]
    component_info_map: Dict[str, ComponentInfo] = field(default_factory=dict)
    current_component_name: Optional[str] = None
    current_agent: Optional[Any] = None
    current_agent_context: Optional[Any] = None
    current_model_client: Optional[ModelClientConfig] = None
    groupchat: Optional[BaseGroupChat] = None
    groupchat_context: Optional[Any] = None
    message_queue: Optional[asyncio.Queue] = None
    settings: Dict[str, Any] = field(default_factory=dict)
    ready: bool = False
    messages: List[Dict[str, Any]] = field(default_factory=list)

class UserSessionManager:
    def __init__(self):
        self.user_sessions = {}
        self.component_info_map = {}
    
    def get(self, key, default=None):
        if not context.session:
            return default
    
    async def initialize_component_info_map(self, data_layer_instance):
        """Initialize component_info_map during startup"""
        try:
            agents = await data_layer_instance.agent.get_all_components()
            group_chats = await data_layer_instance.group_chat.get_all_components()
            self.component_info_map = {**agents, **group_chats}
        except Exception as e:
            print(f"Error initializing component_info_map: {e}")
            self.component_info_map = {}

class User(UserSessionData, UserSession):
    """
    Manages user session data and provides methods for handling dynamic objects
    like agent settings, component info maps, and messages.
    """
    user_session_manager: Optional[UserSessionManager] = None  # 延迟初始化，在startup时设置
    
    def __init__(self, user_id: str, session_data: Optional[UserSessionData] = None):
        """
        Initialize User instance
        
        Args:
            user_id: Unique identifier for the user
            session_data: Optional initial session data
        """
        self.user_id = user_id
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

    def init_session_data(self):
        if self.user_session_manager is None:
            # UserSessionManager not initialized yet, skip initialization
            return

        if context.session.id not in self.user_session_manager.user_sessions:
            # Create a new user session
            self.user_session_manager.user_sessions[context.session.id] = {}

        user_session = self.user_session_manager.user_sessions[context.session.id]
        #CR这个component_info_map移到SessionManager中

        self.chat_profile = self.set("chat_profile", "default")
        self.component_info_map = self.set("component_info_map", {})
        self.current_component_name = self.set("current_component_name", "default")
        self.current_agent = self.set("current_agent", None)
        self.current_agent_context = self.set("current_agent_context", None)
        self.groupchat = self.set("groupchat", None)
        self.groupchat_context = self.set("groupchat_context", None)
        self.message_queue = self.set("message_queue", None)
        self.settings = self.set("settings", {})
        self.ready = self.set("ready", False)
        self.messages = self.set("messages", [])
    
    def create_message_queue(self) -> asyncio.Queue:
        """Create and set a new message queue"""
        self.message_queue = asyncio.Queue()
        return self.message_queue
    
    def clear_chat_resources(self) -> None:
        """Clear chat-related resources (agent, groupchat, message queue)"""
        self.current_agent = None
        self.current_agent_context = None
        self.groupchat = None
        self.groupchat_context = None
        self.message_queue = None
        self.ready = False
    
    async def start_chat(self, chat_profile: str, data_layer_instance):
        """Initialize and start chat session"""
        try:
            chat_profile = self.chat_profile
            # Get component_info_map from session manager
            if hasattr(self.user_session_manager, 'component_info_map'):
                self.component_info_map = self.user_session_manager.component_info_map
            else:
                # Fallback if not initialized
                agents = await data_layer_instance.get_agents_for_chat_profile()
                group_chats = await data_layer_instance.get_group_chats_for_chat_profile()
                self.component_info_map = {**agents, **group_chats}
            
            await self.setup_new_component(chat_profile, data_layer_instance)
            self.current_component_name = chat_profile
            
        except Exception as e:
            print(f"Error in start_chat: {e}")
            raise
    
    async def setup_new_component(self, component_name: str, data_layer_instance):
        """Set up new component (Agent or GroupChat)"""
        try:
            component_info = self.component_info_map.get(component_name)
            
            if component_info:
                if component_info.type == AgentType.ASSISTANT_AGENT or component_info.type == AgentType.USER_PROXY_AGENT:
                    await self._setup_agent_component(component_name, component_info, data_layer_instance)
                else:
                    await self._setup_groupchat_component(component_name)
            else:
                await self._setup_groupchat_component(component_name)
                
        except Exception as e:
            print(f"Error in setup_new_component: {e}")
            raise
    
    async def _setup_agent_component(self, agent_name: str, agent_info: ComponentInfo, data_layer_instance):
        """Set up Agent component"""
        try:
            from builders.database_agent_builder import DatabaseAgentBuilder
            from builders import utils as builders_utils
            
            # Create Agent builder
            async def wrap_input(prompt: str, token: CancellationToken) -> str:
                if not self.ready:
                    self.ready = True
                message = await self.message_queue.get()
                return message
            
            agent_builder = DatabaseAgentBuilder(
                input_func=wrap_input,
                data_layer_instance=data_layer_instance
            )
            
            # Update AgentInfo for builder
            builders_utils.AgentInfo[agent_name] = agent_info
            
            # Create Agent
            async_context_manager = agent_builder.build(agent_name)
            agent = await async_context_manager.__aenter__()
            
            # Set up state
            self.current_agent = agent
            self.current_agent_context = async_context_manager
            self.create_message_queue()
            
            # Use unified Console approach
            asyncio.create_task(Console(agent.run_stream()))
            self.ready = False
            
        except Exception as e:
            print(f"Error in _setup_agent_component: {e}")
            raise
    
    async def _setup_groupchat_component(self, component_name: str):
        """Set up GroupChat component"""
        try:
            from chainlit_web.ui_hook.ui_select_group_chat import UISelectorGroupChatBuilder
            from builders import utils as builders_utils
            
            # Create GroupChat builder
            async def wrap_input(prompt: str, token: CancellationToken) -> str:
                if not self.ready:
                    self.ready = True
                message = await self.message_queue.get()
                return message
            
            groupchat_builder = UISelectorGroupChatBuilder(
                prompt_root=builders_utils.prompt_root,
                input_func=wrap_input,
                model_client_streaming=True
            )
            
            # Create GroupChat
            async_context_manager = groupchat_builder.build(component_name)
            groupchat = await async_context_manager.__aenter__()
            
            # Set up state
            self.create_message_queue()
            self.groupchat = groupchat
            self.groupchat_context = async_context_manager
            
            # Use unified Console approach
            asyncio.create_task(Console(groupchat.run_stream()))
            self.ready = False
            
            # Wait for ready
            while not self.ready:
                await asyncio.sleep(0.1)
                
        except Exception as e:
            print(f"Error in _setup_groupchat_component: {e}")
            raise
    
    async def chat(self, message: cl.Message):
        """Handle incoming chat message"""
        try:
            if self.message_queue:
                self.message_queue.put_nowait(message.content)
                
                # Add to message history
                self.messages.append({
                    "content": message.content,
                    "author": "user", 
                    "timestamp": message.created_at
                })
        except Exception as e:
            print(f"Error in chat: {e}")
    
    async def cleanup_current_chat(self):
        """Clean up current chat resources"""
        try:
            # Clean up GroupChat
            if self.groupchat_context:
                await self.groupchat_context.__aexit__(None, None, None)
                
            # Clean up Agent
            if self.current_agent_context:
                await self.current_agent_context.__aexit__(None, None, None)
                
            # Clear resources
            self.clear_chat_resources()
            
        except Exception as e:
            print(f"Error in cleanup_current_chat: {e}")