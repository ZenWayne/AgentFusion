"""
Comprehensive tests for the User class interface in chainlit_web.users module.

This test suite covers all public methods and core functionality of the User class,
including session management, chat lifecycle, component management, and settings.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

# Import the classes under test
from chainlit_web.users import User, UserSessionManager, UserSessionData
from chainlit_web.ui_hook.ui_agent_builder import UIAgentBuilder
from schemas.config_type import ComponentInfo
from schemas.agent import AgentType
from schemas.group_chat import GroupChatType as GroupChatTypeEnum
from schemas.model_info import ModelClientConfig
from data_layer.data_layer import AgentFusionDataLayer
from chainlit.types import ChatProfile
from autogen_core import CancellationToken
import chainlit as cl


@pytest.fixture
def mock_context():
    """Mock chainlit context for testing"""
    with patch('chainlit_web.users.context') as mock_ctx:
        mock_session = Mock()
        mock_session.id = "test_session_id"
        mock_session.user_env = {}
        mock_session.chat_settings = {}
        mock_session.user = Mock()
        mock_session.user.identifier = "test_user"
        mock_session.chat_profile = "test_profile"
        mock_session.client_type = "web"
        mock_ctx.session = mock_session
        yield mock_ctx


@pytest.fixture
def mock_user_session_manager():
    """Mock UserSessionManager for testing"""
    manager = UserSessionManager()
    manager.user_sessions = {}
    manager.component_info_map = {
        "test_agent": ComponentInfo(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent"
        ),
        "test_groupchat": ComponentInfo(
            name="test_groupchat", 
            type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT,
            description="Test group chat"
        )
    }
    manager.model_list = [
        ModelClientConfig(
            label="test_model",
            provider="test_provider",
            model_name="test-model-1"
        )
    ]
    return manager


@pytest.fixture
def mock_data_layer():
    """Mock AgentFusionDataLayer for testing"""
    data_layer = Mock(spec=AgentFusionDataLayer)
    
    # Mock agent methods
    data_layer.agent = Mock()
    data_layer.agent.get_all_components = AsyncMock(return_value=[
        ComponentInfo(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent"
        )
    ])
    
    # Mock group chat methods
    data_layer.group_chat = Mock()
    data_layer.group_chat.get_all_components = AsyncMock(return_value=[
        ComponentInfo(
            name="test_groupchat",
            type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT,
            description="Test group chat"
        )
    ])
    
    # Mock LLM methods
    data_layer.llm = Mock()
    data_layer.llm.get_component_by_name = AsyncMock(return_value=ModelClientConfig(
        label="test_model",
        provider="test_provider",
        model_name="test-model-1"
    ))
    
    return data_layer


class TestUserSessionManager:
    """Tests for UserSessionManager class"""
    
    def test_init(self):
        """Test UserSessionManager initialization"""
        manager = UserSessionManager()
        assert manager.user_sessions == {}
        assert manager.component_info_map == {}
        assert manager.model_list == []
    
    @pytest.mark.asyncio
    async def test_initialize_component_info_map(self, mock_data_layer):
        """Test component info map initialization"""
        manager = UserSessionManager()
        
        await manager.initialize_component_info_map(mock_data_layer)
        
        assert "test_agent" in manager.component_info_map
        assert "test_groupchat" in manager.component_info_map
        assert manager.component_info_map["test_agent"].type == AgentType.ASSISTANT_AGENT
        assert manager.component_info_map["test_groupchat"].type == GroupChatTypeEnum.SELECTOR_GROUP_CHAT
    
    @pytest.mark.asyncio
    async def test_initialize_component_info_map_error_handling(self, mock_data_layer):
        """Test error handling in component info map initialization"""
        manager = UserSessionManager()
        mock_data_layer.agent.get_all_components.side_effect = Exception("Database error")
        
        await manager.initialize_component_info_map(mock_data_layer)
        
        assert manager.component_info_map == {}
    
    def test_cache_and_get_model_list(self):
        """Test model list caching and retrieval"""
        manager = UserSessionManager()
        test_models = [
            ModelClientConfig(label="model1", provider="provider1", model_name="model-1"),
            ModelClientConfig(label="model2", provider="provider2", model_name="model-2")
        ]
        
        manager.cache_model_list(test_models)
        
        assert manager.get_model_list() == test_models
        assert len(manager.model_list) == 2


class TestUserSessionData:
    """Tests for UserSessionData dataclass"""
    
    def test_default_initialization(self):
        """Test default UserSessionData initialization"""
        data = UserSessionData()
        
        assert data.chat_profile is None
        assert data.component_info_map == {}
        assert data.cancellation_token is None
        assert data.current_component_name is None
        assert data.current_component_queue is None
        assert data.current_component_context is None
        assert data.current_model_client is None
        assert data.settings == {}
        assert data.ready is False
        assert data.messages == []


class TestUIAgentBuilder:
    """Tests for UIAgentBuilder class"""
    
    def test_init(self, mock_data_layer):
        """Test UIAgentBuilder initialization"""
        builder = UIAgentBuilder(mock_data_layer)
        
        assert builder.data_layer == mock_data_layer
        assert builder.input_func is None
    
    def test_init_with_input_func(self, mock_data_layer):
        """Test UIAgentBuilder initialization with input function"""
        input_func = AsyncMock()
        builder = UIAgentBuilder(mock_data_layer, input_func)
        
        assert builder.data_layer == mock_data_layer
        assert builder.input_func == input_func


class TestUser:
    """Tests for User class"""
    
    def test_init_with_context(self, mock_context):
        """Test User initialization with valid context"""
        with patch('chainlit_web.users.context', mock_context):
            User.user_session_manager = UserSessionManager()
            user = User()
            
            assert user.identifier == "test_user"
    
    def test_init_without_context(self):
        """Test User initialization without context"""
        with patch('chainlit_web.users.context') as mock_ctx:
            mock_ctx.session = None
            User.user_session_manager = UserSessionManager()
            user = User()
            
            assert user.identifier == "anonymous"
    
    def test_get_without_context(self):
        """Test get method without context"""
        with patch('chainlit_web.users.context') as mock_ctx:
            mock_ctx.session = None
            user = User()
            
            result = user.get("test_key", "default_value")
            assert result == "default_value"
    
    def test_get_without_session_manager(self, mock_context):
        """Test get method without session manager"""
        User.user_session_manager = None
        user = User()
        
        result = user.get("test_key", "default_value")
        assert result == "default_value"
    
    def test_get_with_new_session(self, mock_context, mock_user_session_manager):
        """Test get method with new session"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        result = user.get("test_key", "default_value")
        
        assert "test_session_id" in mock_user_session_manager.user_sessions
        assert result == "default_value"
    
    def test_get_with_existing_session(self, mock_context, mock_user_session_manager):
        """Test get method with existing session"""
        User.user_session_manager = mock_user_session_manager
        mock_user_session_manager.user_sessions["test_session_id"] = {"existing_key": "existing_value"}
        user = User()
        
        result = user.get("existing_key", "default_value")
        assert result == "existing_value"
    
    def test_set_without_context(self):
        """Test set method without context"""
        with patch('chainlit_web.users.context') as mock_ctx:
            mock_ctx.session = None
            user = User()
            
            result = user.set("test_key", "test_value")
            assert result == "test_value"
    
    def test_set_without_session_manager(self, mock_context):
        """Test set method without session manager"""
        User.user_session_manager = None
        user = User()
        
        result = user.set("test_key", "test_value")
        assert result == "test_value"
    
    def test_set_with_new_session(self, mock_context, mock_user_session_manager):
        """Test set method with new session"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        result = user.set("test_key", "test_value")
        
        assert "test_session_id" in mock_user_session_manager.user_sessions
        assert mock_user_session_manager.user_sessions["test_session_id"]["test_key"] == "test_value"
        assert result == "test_value"
    
    def test_set_with_existing_session(self, mock_context, mock_user_session_manager):
        """Test set method with existing session"""
        User.user_session_manager = mock_user_session_manager
        mock_user_session_manager.user_sessions["test_session_id"] = {}
        user = User()
        
        result = user.set("test_key", "test_value")
        
        assert mock_user_session_manager.user_sessions["test_session_id"]["test_key"] == "test_value"
        assert result == "test_value"
    
    def test_init_session_data_without_manager(self, mock_context):
        """Test init_session_data without session manager"""
        User.user_session_manager = None
        user = User()
        
        # Should not raise an exception
        user.init_session_data()
    
    def test_init_session_data_with_manager(self, mock_context, mock_user_session_manager):
        """Test init_session_data with session manager"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        # Verify default values are set
        session_data = mock_user_session_manager.user_sessions["test_session_id"]
        assert session_data["current_component_name"] == "default"
        assert session_data["current_component"] is None
        assert session_data["settings"] == {}
        assert session_data["ready"] is False
    
    def test_on_stop_with_token(self, mock_context, mock_user_session_manager):
        """Test on_stop method with cancellation token"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_token = Mock(spec=CancellationToken)
        user.cancellation_token = mock_token
        
        user.on_stop()
        
        mock_token.cancel.assert_called_once()
    
    def test_on_stop_without_token(self, mock_context, mock_user_session_manager):
        """Test on_stop method without cancellation token"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        # Should not raise an exception
        user.on_stop()
    
    def test_clear_chat_resources(self, mock_context, mock_user_session_manager):
        """Test clear_chat_resources method"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        user.current_component_queue = Mock()
        user.current_component_context = Mock()
        user.ready = True
        
        user.clear_chat_resources()
        
        assert user.current_component_queue is None
        assert user.current_component_context is None
        assert user.ready is False
    
    @pytest.mark.asyncio
    async def test_start_chat_with_existing_profile(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test start_chat with existing chat profile"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        with patch.object(user, 'get', return_value="test_agent"):
            with patch.object(user, 'setup_new_component', new_callable=AsyncMock) as mock_setup:
                with patch('chainlit_web.users.cl.Message') as mock_message:
                    mock_msg = AsyncMock()
                    mock_message.return_value = mock_msg
                    
                    await user.start_chat(mock_data_layer)
                    
                    mock_setup.assert_called_once()
                    mock_msg.send.assert_called_once()
                    assert user.current_component_name == "test_agent"
    
    @pytest.mark.asyncio
    async def test_start_chat_without_profile(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test start_chat without existing chat profile"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        with patch.object(user, 'get', return_value=None):
            with patch.object(User, 'get_chat_profiles', new_callable=AsyncMock) as mock_profiles:
                mock_profiles.return_value = [ChatProfile(name="default_profile")]
                with patch.object(user, 'set', return_value="default_profile"):
                    with patch.object(user, 'setup_new_component', new_callable=AsyncMock) as mock_setup:
                        with patch('chainlit_web.users.cl.Message') as mock_message:
                            mock_msg = AsyncMock()
                            mock_message.return_value = mock_msg
                            
                            await user.start_chat(mock_data_layer)
                            
                            mock_profiles.assert_called_once_with(mock_data_layer)
                            mock_setup.assert_called_once()
                            mock_msg.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_start_chat_error_handling(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test start_chat error handling"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        with patch.object(user, 'get', side_effect=Exception("Test error")):
            with pytest.raises(Exception, match="Test error"):
                await user.start_chat(mock_data_layer)
    
    @pytest.mark.asyncio
    async def test_component_create_assistant_agent(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test component_create for assistant agent"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        component_info = ComponentInfo(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test agent"
        )
        
        with patch.object(user, 'input_func', return_value=AsyncMock()):
            with patch('chainlit_web.users.UIAgentBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_context_manager = AsyncMock()
                mock_builder.build_with_queue.return_value = mock_context_manager
                mock_builder_class.return_value = mock_builder
                
                result = await user.component_create(component_info, mock_data_layer)
                
                assert result == mock_context_manager
                mock_builder_class.assert_called_once()
                mock_builder.build_with_queue.assert_called_once_with(component_info)
    
    @pytest.mark.asyncio
    async def test_component_create_group_chat(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test component_create for group chat"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        component_info = ComponentInfo(
            name="test_groupchat",
            type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT,
            description="Test group chat"
        )
        
        with patch.object(user, 'input_func', return_value=AsyncMock()):
            with patch('chainlit_web.users.UIGroupChatBuilder') as mock_builder_class:
                mock_builder = Mock()
                mock_context_manager = AsyncMock()
                mock_builder.build_with_queue.return_value = mock_context_manager
                mock_builder_class.return_value = mock_builder
                
                result = await user.component_create(component_info, mock_data_layer)
                
                assert result == mock_context_manager
                mock_builder_class.assert_called_once()
                mock_builder.build_with_queue.assert_called_once_with(component_info)
    
    @pytest.mark.asyncio
    async def test_component_cleanup(self, mock_context, mock_user_session_manager):
        """Test component_cleanup method"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_component = AsyncMock()
        await user.component_cleanup(mock_component)
        
        mock_component.__aexit__.assert_called_once_with(None, None, None)
    
    @pytest.mark.asyncio
    async def test_setup_new_component_success(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test setup_new_component successful execution"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        component_info_map = {
            "test_agent": ComponentInfo(
                name="test_agent",
                type=AgentType.ASSISTANT_AGENT,
                description="Test agent"
            )
        }
        
        mock_queue = AsyncMock()
        mock_context = AsyncMock()
        mock_context.__aenter__.return_value = mock_queue
        
        with patch.object(user, 'component_create', return_value=mock_context) as mock_create:
            with patch.object(user, 'set', return_value=Mock(spec=CancellationToken)) as mock_set:
                
                await user.setup_new_component("test_agent", component_info_map, mock_data_layer)
                
                mock_create.assert_called_once()
                mock_context.__aenter__.assert_called_once()
                mock_queue.start.assert_called_once()
                assert user.current_component_context == mock_context
                assert user.current_component_queue == mock_queue
    
    @pytest.mark.asyncio
    async def test_setup_new_component_error(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test setup_new_component error handling"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        component_info_map = {"test_agent": Mock()}
        
        with patch.object(user, 'component_create', side_effect=Exception("Setup error")):
            with pytest.raises(Exception, match="Setup error"):
                await user.setup_new_component("test_agent", component_info_map, mock_data_layer)
    
    @pytest.mark.asyncio
    async def test_chat_success(self, mock_context, mock_user_session_manager):
        """Test chat method successful execution"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_queue = AsyncMock()
        mock_event = Mock()
        mock_event.content = "Test response"
        mock_queue.push.return_value = [mock_event].__aiter__()
        user.current_component_queue = mock_queue
        
        mock_message = Mock()
        mock_message.content = "Test message"
        
        with patch('chainlit_web.users.cl.Message') as mock_cl_message:
            mock_cl_msg = AsyncMock()
            mock_cl_message.return_value = mock_cl_msg
            
            await user.chat(mock_message)
            
            mock_queue.push.assert_called_once_with("Test message")
            mock_cl_message.assert_called_once_with(content="Test response")
            mock_cl_msg.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_chat_no_queue(self, mock_context, mock_user_session_manager):
        """Test chat method without component queue"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        user.current_component_queue = None
        
        mock_message = Mock()
        mock_message.content = "Test message"
        
        # Should not raise an exception but log an error
        await user.chat(mock_message)
    
    @pytest.mark.asyncio
    async def test_chat_error_handling(self, mock_context, mock_user_session_manager):
        """Test chat method error handling"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_queue = AsyncMock()
        mock_queue.push.side_effect = Exception("Chat error")
        user.current_component_queue = mock_queue
        
        mock_message = Mock()
        mock_message.content = "Test message"
        
        # Should not raise an exception but log an error
        await user.chat(mock_message)
    
    @pytest.mark.asyncio
    async def test_cleanup_current_chat_success(self, mock_context, mock_user_session_manager):
        """Test cleanup_current_chat successful execution"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_context = AsyncMock()
        user.current_component_context = mock_context
        
        with patch.object(user, 'clear_chat_resources') as mock_clear:
            await user.cleanup_current_chat()
            
            mock_context.__aexit__.assert_called_once_with(None, None, None)
            mock_clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_current_chat_no_context(self, mock_context, mock_user_session_manager):
        """Test cleanup_current_chat without component context"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        user.current_component_context = None
        
        with patch.object(user, 'clear_chat_resources') as mock_clear:
            await user.cleanup_current_chat()
            
            mock_clear.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_cleanup_current_chat_error(self, mock_context, mock_user_session_manager):
        """Test cleanup_current_chat error handling"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_context = AsyncMock()
        mock_context.__aexit__.side_effect = Exception("Cleanup error")
        user.current_component_context = mock_context
        
        # Should not raise an exception but log an error
        await user.cleanup_current_chat()
    
    @pytest.mark.asyncio
    async def test_settings_update_model_selection(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test settings_update with model selection"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        user.settings = {}
        
        mock_widget = Mock()
        mock_widget.id = "Model"
        mock_widget.initial = "test_model"
        
        mock_settings = Mock()
        mock_settings.inputs = [mock_widget]
        
        await user.settings_update(mock_settings, mock_data_layer)
        
        mock_data_layer.llm.get_component_by_name.assert_called_once_with("test_model")
        assert user.current_model_client is not None
    
    @pytest.mark.asyncio
    async def test_settings_update_no_model_widget(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test settings_update without model widget"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        user.settings = {}
        
        mock_settings = Mock()
        mock_settings.inputs = []
        
        await user.settings_update(mock_settings, mock_data_layer)
        
        mock_data_layer.llm.get_component_by_name.assert_not_called()
    
    @pytest.mark.asyncio
    async def test_settings_update_error(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test settings_update error handling"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        mock_settings = Mock()
        mock_settings.inputs = []
        user.settings.update.side_effect = Exception("Settings error")
        
        with patch('chainlit_web.users.cl.Message') as mock_message:
            mock_msg = AsyncMock()
            mock_message.return_value = mock_msg
            
            await user.settings_update(mock_settings, mock_data_layer)
            
            mock_message.assert_called_once()
            mock_msg.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_success(self, mock_data_layer):
        """Test get_chat_profiles successful execution"""
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 2
        assert profiles[0].name == "test_agent"
        assert "Agent" in profiles[0].markdown_description
        assert profiles[1].name == "test_groupchat"
        assert "Group Chat" in profiles[1].markdown_description
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_empty_components(self, mock_data_layer):
        """Test get_chat_profiles with empty component lists"""
        mock_data_layer.agent.get_all_components.return_value = []
        mock_data_layer.group_chat.get_all_components.return_value = []
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 1
        assert profiles[0].name == "executor"
        assert "Default Group Chat" in profiles[0].markdown_description
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_error_handling(self, mock_data_layer):
        """Test get_chat_profiles error handling"""
        mock_data_layer.agent.get_all_components.side_effect = Exception("Database error")
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 1
        assert profiles[0].name == "hil"
        assert "Default Group Chat" in profiles[0].markdown_description


class TestIntegration:
    """Integration tests for User class workflow"""
    
    @pytest.mark.asyncio
    async def test_full_chat_workflow(self, mock_context, mock_user_session_manager, mock_data_layer):
        """Test complete chat workflow from initialization to cleanup"""
        User.user_session_manager = mock_user_session_manager
        user = User()
        
        # Mock component queue
        mock_queue = AsyncMock()
        mock_event = Mock()
        mock_event.content = "Response"
        mock_queue.push.return_value = [mock_event].__aiter__()
        
        # Mock context manager
        mock_context_mgr = AsyncMock()
        mock_context_mgr.__aenter__.return_value = mock_queue
        
        with patch.object(user, 'component_create', return_value=mock_context_mgr):
            with patch('chainlit_web.users.cl.Message') as mock_message:
                mock_msg = AsyncMock()
                mock_message.return_value = mock_msg
                
                # Start chat
                await user.start_chat(mock_data_layer)
                
                # Send message
                test_message = Mock()
                test_message.content = "Hello"
                await user.chat(test_message)
                
                # Cleanup
                await user.cleanup_current_chat()
                
                # Verify workflow
                mock_context_mgr.__aenter__.assert_called_once()
                mock_queue.start.assert_called_once()
                mock_queue.push.assert_called_once_with("Hello")
                mock_context_mgr.__aexit__.assert_called_once()
                assert user.current_component_queue is None