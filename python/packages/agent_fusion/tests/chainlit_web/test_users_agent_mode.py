"""
Test cases for single agent mode integration in users.py.

These tests verify the integration between UIAgentBuilder, AutoGenAgentChatQueue,
and the User class for single agent chat functionality.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from typing import Dict, Any

from schemas.config_type import ComponentInfo
from schemas.agent import AgentType, AssistantAgentConfig
from schemas.group_chat import GroupChatType as GroupChatTypeEnum
from data_layer.data_layer import AgentFusionDataLayer
from chainlit_web.users import UIAgentBuilder, User, UserSessionManager
from chainlit_web.ui_hook.autogen_chat_queue import AutoGenAgentChatQueue
from autogen_agentchat.messages import TextMessage
from autogen_agentchat.base import TaskResult
from autogen_core import CancellationToken


class TestUIAgentBuilder:
    """Test cases for UIAgentBuilder"""

    @pytest.fixture
    def mock_data_layer(self):
        """Create a mock data layer"""
        return MagicMock(spec=AgentFusionDataLayer)

    @pytest.fixture
    def mock_input_func(self):
        """Create a mock input function"""
        return AsyncMock()

    @pytest.fixture
    def ui_agent_builder(self, mock_data_layer, mock_input_func):
        """Create a UIAgentBuilder instance"""
        return UIAgentBuilder(mock_data_layer, mock_input_func)

    @pytest.fixture
    def sample_agent_info(self):
        """Create sample agent configuration"""
        return AssistantAgentConfig(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent",
            model_client="test_model",
            prompt="You are a helpful assistant",
            mcp_tools=[]
        )

    def test_ui_agent_builder_initialization(self, mock_data_layer, mock_input_func):
        """Test UIAgentBuilder initialization"""
        builder = UIAgentBuilder(mock_data_layer, mock_input_func)
        
        assert builder.data_layer == mock_data_layer
        assert builder.input_func == mock_input_func

    @pytest.mark.asyncio
    async def test_build_with_queue(self, ui_agent_builder, sample_agent_info):
        """Test build_with_queue method"""
        # Mock the AgentBuilder and its build method
        mock_agent = MagicMock()
        mock_agent.run_stream = AsyncMock()
        
        with patch('chainlit_web.users.AgentBuilder') as mock_agent_builder_class:
            mock_agent_builder = MagicMock()
            mock_agent_builder_class.return_value = mock_agent_builder
            
            # Setup the async context manager
            @asynccontextmanager
            async def mock_build(agent_info):
                yield mock_agent
            
            mock_agent_builder.build = mock_build
            
            # Test the build_with_queue method
            async with ui_agent_builder.build_with_queue(sample_agent_info) as queue:
                assert isinstance(queue, AutoGenAgentChatQueue)
                assert queue._agent == mock_agent

    @pytest.mark.asyncio
    async def test_build_with_queue_agent_builder_called_correctly(self, ui_agent_builder, sample_agent_info, mock_input_func):
        """Test that AgentBuilder is called with correct parameters"""
        with patch('chainlit_web.users.AgentBuilder') as mock_agent_builder_class:
            mock_agent_builder = MagicMock()
            mock_agent_builder_class.return_value = mock_agent_builder
            
            @asynccontextmanager
            async def mock_build(agent_info):
                yield MagicMock()
            
            mock_agent_builder.build = mock_build
            
            async with ui_agent_builder.build_with_queue(sample_agent_info):
                pass
            
            # Verify AgentBuilder was created with correct input_func
            mock_agent_builder_class.assert_called_once_with(input_func=mock_input_func)
            mock_agent_builder.build.assert_called_once_with(sample_agent_info)


class TestUserSingleAgentMode:
    """Test cases for User class single agent mode functionality"""

    @pytest.fixture
    def mock_data_layer(self):
        """Create a mock data layer"""
        mock_dl = MagicMock(spec=AgentFusionDataLayer)
        mock_dl.agent = MagicMock()
        mock_dl.group_chat = MagicMock()
        return mock_dl

    @pytest.fixture
    def mock_user_session_manager(self):
        """Create a mock user session manager"""
        manager = MagicMock(spec=UserSessionManager)
        manager.component_info_map = {}
        return manager

    @pytest.fixture
    def sample_component_info_map(self):
        """Create sample component info map with agents and group chats"""
        agent_info = AssistantAgentConfig(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent",
            model_client="test_model",
            prompt="You are a helpful assistant",
            mcp_tools=[]
        )
        
        group_chat_info = ComponentInfo(
            name="test_group_chat",
            type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT,
            description="Test group chat"
        )
        
        return {
            "test_agent": agent_info,
            "test_group_chat": group_chat_info
        }

    @pytest.mark.asyncio
    async def test_component_create_assistant_agent(self, mock_data_layer, sample_component_info_map):
        """Test component creation for assistant agent"""
        with patch('chainlit_web.users.context') as mock_context:
            mock_context.session = MagicMock()
            mock_context.session.user = MagicMock()
            mock_context.session.user.identifier = "test_user"
            mock_context.session.id = "test_session"
            
            user = User()
            user.user_session_manager = MagicMock()
            user.user_session_manager.user_sessions = {}
            
            agent_info = sample_component_info_map["test_agent"]
            
            with patch.object(user, 'input_func', return_value=AsyncMock()):
                with patch('chainlit_web.users.UIAgentBuilder') as mock_ui_agent_builder_class:
                    mock_ui_agent_builder = MagicMock()
                    mock_ui_agent_builder_class.return_value = mock_ui_agent_builder
                    mock_ui_agent_builder.build_with_queue.return_value = MagicMock()
                    
                    result = await user.component_create(agent_info, mock_data_layer)
                    
                    # Verify UIAgentBuilder was created and called correctly
                    mock_ui_agent_builder_class.assert_called_once()
                    mock_ui_agent_builder.build_with_queue.assert_called_once_with(agent_info)

    @pytest.mark.asyncio 
    async def test_component_create_group_chat(self, mock_data_layer, sample_component_info_map):
        """Test component creation for group chat"""
        with patch('chainlit_web.users.context') as mock_context:
            mock_context.session = MagicMock()
            mock_context.session.user = MagicMock()
            mock_context.session.user.identifier = "test_user"
            mock_context.session.id = "test_session"
            
            user = User()
            user.user_session_manager = MagicMock()
            user.user_session_manager.user_sessions = {}
            
            group_chat_info = sample_component_info_map["test_group_chat"]
            
            with patch.object(user, 'input_func', return_value=AsyncMock()):
                with patch('chainlit_web.users.UIGroupChatBuilder') as mock_ui_group_chat_builder_class:
                    mock_ui_group_chat_builder = MagicMock()
                    mock_ui_group_chat_builder_class.return_value = mock_ui_group_chat_builder
                    mock_ui_group_chat_builder.build_with_queue.return_value = MagicMock()
                    
                    result = await user.component_create(group_chat_info, mock_data_layer)
                    
                    # Verify UIGroupChatBuilder was created and called correctly
                    mock_ui_group_chat_builder_class.assert_called_once()
                    mock_ui_group_chat_builder.build_with_queue.assert_called_once_with(group_chat_info)

    @pytest.mark.asyncio
    async def test_chat_method_with_agent_queue(self, mock_data_layer):
        """Test chat method with agent queue"""
        with patch('chainlit_web.users.context') as mock_context:
            mock_context.session = MagicMock()
            mock_context.session.user = MagicMock()
            mock_context.session.user.identifier = "test_user"
            mock_context.session.id = "test_session"
            
            with patch('chainlit_web.users.cl') as mock_cl:
                mock_message = MagicMock()
                mock_message.content = "Hello, agent!"
                
                # Mock the queue's push method
                mock_queue = MagicMock()
                
                async def mock_push(content):
                    yield TextMessage(content=f"Response to: {content}", source="agent")
                    yield TaskResult(messages=[], stop_reason="completed")
                
                mock_queue.push = mock_push
                
                user = User()
                user.user_session_manager = MagicMock()
                user.user_session_manager.user_sessions = {}
                user.current_component_queue = mock_queue
                
                await user.chat(mock_message)
                
                # Verify that cl.Message was called to send responses
                assert mock_cl.Message.called

    @pytest.mark.asyncio
    async def test_setup_new_component_agent(self, mock_data_layer, sample_component_info_map):
        """Test setup_new_component for agent"""
        with patch('chainlit_web.users.context') as mock_context:
            mock_context.session = MagicMock()
            mock_context.session.user = MagicMock()
            mock_context.session.user.identifier = "test_user"
            mock_context.session.id = "test_session"
            
            user = User()
            user.user_session_manager = MagicMock()
            user.user_session_manager.user_sessions = {}
            
            # Mock the component creation and context
            mock_queue = MagicMock()
            mock_context_manager = MagicMock()
            mock_context_manager.__aenter__ = AsyncMock(return_value=mock_queue)
            mock_queue.start = AsyncMock()
            
            with patch.object(user, 'component_create', return_value=mock_context_manager):
                with patch.object(user, 'set', return_value=CancellationToken()):
                    await user.setup_new_component("test_agent", sample_component_info_map, mock_data_layer)
                    
                    # Verify component was set up correctly
                    assert user.current_component_context == mock_context_manager
                    assert user.current_component_queue == mock_queue
                    mock_queue.start.assert_called_once()


class TestUserSessionManagerAgentIntegration:
    """Test cases for UserSessionManager with agent integration"""

    @pytest.fixture
    def mock_data_layer(self):
        """Create a mock data layer with agent and group chat data"""
        mock_dl = MagicMock(spec=AgentFusionDataLayer)
        
        # Create mock agent and group_chat attributes
        mock_dl.agent = MagicMock()
        mock_dl.group_chat = MagicMock()
        
        # Mock agent data
        mock_agent_info = AssistantAgentConfig(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent",
            model_client="test_model",
            prompt="You are a helpful assistant",
            mcp_tools=[]
        )
        
        mock_dl.agent.get_all_components = AsyncMock(return_value=[mock_agent_info])
        mock_dl.group_chat.get_all_components = AsyncMock(return_value=[])
        
        return mock_dl

    @pytest.mark.asyncio
    async def test_initialize_component_info_map_includes_agents(self, mock_data_layer):
        """Test that component info map includes agents"""
        manager = UserSessionManager()
        
        await manager.initialize_component_info_map(mock_data_layer)
        
        # Verify agents are included in component map
        assert "test_agent" in manager.component_info_map
        assert manager.component_info_map["test_agent"].type == AgentType.ASSISTANT_AGENT

    @pytest.mark.asyncio
    async def test_initialize_component_info_map_with_both_agents_and_group_chats(self):
        """Test component info map with both agents and group chats"""
        mock_dl = MagicMock(spec=AgentFusionDataLayer)
        mock_dl.agent = MagicMock()
        mock_dl.group_chat = MagicMock()
        
        mock_agent_info = AssistantAgentConfig(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent",
            model_client="test_model",
            prompt="You are a helpful assistant",
            mcp_tools=[]
        )
        
        mock_group_chat_info = ComponentInfo(
            name="test_group_chat",
            type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT,
            description="Test group chat"
        )
        
        mock_dl.agent.get_all_components = AsyncMock(return_value=[mock_agent_info])
        mock_dl.group_chat.get_all_components = AsyncMock(return_value=[mock_group_chat_info])
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_dl)
        
        # Verify both agents and group chats are included
        assert "test_agent" in manager.component_info_map
        assert "test_group_chat" in manager.component_info_map
        assert manager.component_info_map["test_agent"].type == AgentType.ASSISTANT_AGENT
        assert manager.component_info_map["test_group_chat"].type == GroupChatTypeEnum.SELECTOR_GROUP_CHAT

    @pytest.mark.asyncio
    async def test_initialize_component_info_map_error_handling(self):
        """Test error handling in component info map initialization"""
        mock_dl = MagicMock(spec=AgentFusionDataLayer)
        mock_dl.agent = MagicMock()
        mock_dl.group_chat = MagicMock()
        mock_dl.agent.get_all_components = AsyncMock(side_effect=Exception("Database error"))
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_dl)
        
        # Verify error is handled gracefully
        assert manager.component_info_map == {}