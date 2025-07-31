"""
Final comprehensive tests for the User class interface in chainlit_web.users module.

This test suite focuses on the core functionality that can be reliably tested
without complex schema validation issues.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch, MagicMock
from dataclasses import dataclass
from typing import Dict, Any, Optional, List

# Import the classes under test
from chainlit_web.users import UserSessionManager, UserSessionData, UIAgentBuilder
from schemas.agent import AgentType, AssistantAgentConfig
from schemas.group_chat import GroupChatType as GroupChatTypeEnum, SelectorGroupChatConfig
from schemas.model_info import ModelClientConfig, model_client
from schemas.types import ComponentType
from data_layer.data_layer import AgentFusionDataLayer
from chainlit.types import ChatProfile
from autogen_core.models import ModelFamily


class TestUserSessionManager:
    """Tests for UserSessionManager class"""
    
    def test_init(self):
        """Test UserSessionManager initialization"""
        manager = UserSessionManager()
        assert manager.user_sessions == {}
        assert manager.component_info_map == {}
        assert manager.model_list == []
    
    def test_cache_and_get_model_list(self):
        """Test model list caching and retrieval"""
        manager = UserSessionManager()
        test_models = [
            ModelClientConfig(
                type=ComponentType.LLM,
                label="model1",
                model_name="model-1",
                base_url="https://api.test1.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="TEST_API_KEY",
                stream=True
            ),
            ModelClientConfig(
                type=ComponentType.LLM,
                label="model2",
                model_name="model-2",
                base_url="https://api.test2.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="TEST_API_KEY",
                stream=False
            )
        ]
        
        manager.cache_model_list(test_models)
        
        assert manager.get_model_list() == test_models
        assert len(manager.model_list) == 2
    
    @pytest.mark.asyncio
    async def test_initialize_component_info_map_error_handling(self):
        """Test error handling in component info map initialization"""
        manager = UserSessionManager()
        
        # Mock data layer that raises exceptions
        mock_data_layer = Mock(spec=AgentFusionDataLayer)
        mock_data_layer.agent = Mock()
        mock_data_layer.agent.get_all_components = AsyncMock(side_effect=Exception("Database error"))
        mock_data_layer.group_chat = Mock()
        mock_data_layer.group_chat.get_all_components = AsyncMock(return_value=[])
        
        await manager.initialize_component_info_map(mock_data_layer)
        
        assert manager.component_info_map == {}
    
    def test_user_session_manager_basic_operations(self):
        """Test UserSessionManager basic operations"""
        manager = UserSessionManager()
        
        # Test that manager starts with empty state
        assert manager.user_sessions == {}
        assert manager.component_info_map == {}
        assert manager.model_list == []
        
        # Test that we can modify these attributes directly
        manager.user_sessions["test"] = {"data": "value"}
        assert manager.user_sessions["test"]["data"] == "value"


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
    
    def test_custom_initialization(self):
        """Test UserSessionData with custom values"""
        custom_settings = {"theme": "dark", "language": "en"}
        custom_messages = [{"role": "user", "content": "Hello"}]
        
        data = UserSessionData(
            settings=custom_settings,
            messages=custom_messages,
            ready=True
        )
        
        assert data.settings == custom_settings
        assert data.messages == custom_messages
        assert data.ready is True


class TestUIAgentBuilder:
    """Tests for UIAgentBuilder class"""
    
    def test_init(self):
        """Test UIAgentBuilder initialization"""
        mock_data_layer = Mock(spec=AgentFusionDataLayer)
        builder = UIAgentBuilder(mock_data_layer)
        
        assert builder.data_layer == mock_data_layer
        assert builder.input_func is None
    
    def test_init_with_input_func(self):
        """Test UIAgentBuilder initialization with input function"""
        mock_data_layer = Mock(spec=AgentFusionDataLayer)
        input_func = AsyncMock()
        builder = UIAgentBuilder(mock_data_layer, input_func)
        
        assert builder.data_layer == mock_data_layer
        assert builder.input_func == input_func


class TestUserStaticMethods:
    """Tests for User class static methods that don't require complex context"""
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_empty_components(self):
        """Test get_chat_profiles with empty component lists"""
        from chainlit_web.users import User
        
        # Mock data layer with empty responses
        mock_data_layer = Mock(spec=AgentFusionDataLayer)
        mock_data_layer.agent = Mock()
        mock_data_layer.agent.get_all_components = AsyncMock(return_value=[])
        mock_data_layer.group_chat = Mock()
        mock_data_layer.group_chat.get_all_components = AsyncMock(return_value=[])
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 1
        assert profiles[0].name == "executor"
        assert "Default Group Chat" in profiles[0].markdown_description
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_error_handling(self):
        """Test get_chat_profiles error handling"""
        from chainlit_web.users import User
        
        # Mock data layer that raises exceptions
        mock_data_layer = Mock(spec=AgentFusionDataLayer)
        mock_data_layer.agent = Mock()
        mock_data_layer.agent.get_all_components = AsyncMock(side_effect=Exception("Database error"))
        mock_data_layer.group_chat = Mock()
        mock_data_layer.group_chat.get_all_components = AsyncMock(return_value=[])
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 1
        assert profiles[0].name == "hil"
        assert "Default Group Chat" in profiles[0].markdown_description


class TestModelManagement:
    """Tests for model management functionality"""
    
    def test_model_list_operations(self):
        """Test model list operations"""
        manager = UserSessionManager()
        
        # Test empty list initially
        assert manager.get_model_list() == []
        
        # Test caching models
        test_models = [
            ModelClientConfig(
                type=ComponentType.LLM,
                label="gpt-4",
                model_name="gpt-4",
                base_url="https://api.openai.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="OPENAI_API_KEY",
                stream=True
            ),
            ModelClientConfig(
                type=ComponentType.LLM,
                label="claude-3",
                model_name="claude-3-opus",
                base_url="https://api.anthropic.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="ANTHROPIC_API_KEY",
                stream=True
            )
        ]
        
        manager.cache_model_list(test_models)
        cached_models = manager.get_model_list()
        
        assert len(cached_models) == 2
        assert cached_models[0].label == "gpt-4"
        assert cached_models[1].label == "claude-3"
    
    def test_model_list_persistence(self):
        """Test that model list persists correctly"""
        manager = UserSessionManager()
        
        # Create test model
        test_model = ModelClientConfig(
            type=ComponentType.LLM,
            label="test-model",
            model_name="test-model-name",
            base_url="https://api.test.com",
            family=ModelFamily.UNKNOWN,
            api_key_type="TEST_API_KEY",
            stream=True
        )
        
        # Cache single model
        manager.cache_model_list([test_model])
        
        # Verify persistence
        retrieved_models = manager.get_model_list()
        assert len(retrieved_models) == 1
        assert retrieved_models[0].label == "test-model"
        assert retrieved_models[0].model_name == "test-model-name"
    
    def test_model_list_overwrite(self):
        """Test that caching overwrites previous model list"""
        manager = UserSessionManager()
        
        # Cache initial models
        initial_models = [
            ModelClientConfig(
                type=ComponentType.LLM,
                label="initial",
                model_name="initial-model",
                base_url="https://api.initial.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="INITIAL_API_KEY",
                stream=True
            )
        ]
        manager.cache_model_list(initial_models)
        assert len(manager.get_model_list()) == 1
        
        # Cache new models (should overwrite)
        new_models = [
            ModelClientConfig(
                type=ComponentType.LLM,
                label="new1",
                model_name="new-model-1",
                base_url="https://api.new1.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="NEW_API_KEY",
                stream=True
            ),
            ModelClientConfig(
                type=ComponentType.LLM,
                label="new2",
                model_name="new-model-2",
                base_url="https://api.new2.com",
                family=ModelFamily.UNKNOWN,
                api_key_type="NEW_API_KEY",
                stream=False
            )
        ]
        manager.cache_model_list(new_models)
        
        # Verify overwrite
        final_models = manager.get_model_list()
        assert len(final_models) == 2
        assert final_models[0].label == "new1"
        assert final_models[1].label == "new2"


class TestSessionManagement:
    """Tests for session management functionality"""
    
    def test_user_session_initialization(self):
        """Test user session initialization"""
        manager = UserSessionManager()
        
        # Initially empty
        assert manager.user_sessions == {}
        
        # Add session manually for testing
        manager.user_sessions["test_session"] = {"key": "value"}
        assert "test_session" in manager.user_sessions
        assert manager.user_sessions["test_session"]["key"] == "value"
    
    def test_component_info_map_access(self):
        """Test component info map access"""
        manager = UserSessionManager()
        
        # Initially empty
        assert manager.component_info_map == {}
        
        # Add component info manually for testing
        manager.component_info_map["test_component"] = {
            "name": "test_component",
            "type": "assistant_agent",
            "description": "Test component"
        }
        
        assert "test_component" in manager.component_info_map
        assert manager.component_info_map["test_component"]["name"] == "test_component"


class TestErrorHandling:
    """Tests for error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_data_layer_initialization_with_partial_failure(self):
        """Test component info map initialization with partial failures"""
        manager = UserSessionManager()
        
        # Mock data layer where agents succeed but group chats fail
        mock_data_layer = Mock(spec=AgentFusionDataLayer)
        mock_data_layer.agent = Mock()
        mock_data_layer.agent.get_all_components = AsyncMock(return_value=[])  # Empty but successful
        mock_data_layer.group_chat = Mock()
        mock_data_layer.group_chat.get_all_components = AsyncMock(side_effect=Exception("GroupChat error"))
        
        # Should handle error gracefully
        await manager.initialize_component_info_map(mock_data_layer)
        assert manager.component_info_map == {}
    
    def test_session_manager_robustness(self):
        """Test that UserSessionManager handles edge cases robustly"""
        manager = UserSessionManager()
        
        # Test with None values
        manager.cache_model_list([])
        assert manager.get_model_list() == []
        
        # Test multiple calls
        manager.cache_model_list([])
        manager.cache_model_list([])
        assert manager.get_model_list() == []


if __name__ == "__main__":
    pytest.main([__file__, "-v"])