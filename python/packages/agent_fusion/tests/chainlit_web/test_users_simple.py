"""
Focused tests for the User class interface in chainlit_web.users module.

This test suite covers the core functionality that can be tested without 
full chainlit context initialization.
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


@pytest.fixture
def mock_data_layer():
    """Mock AgentFusionDataLayer for testing"""
    data_layer = Mock(spec=AgentFusionDataLayer)
    
    # Mock agent methods
    data_layer.agent = Mock()
    data_layer.agent.get_all_components = AsyncMock(return_value=[
        AssistantAgentConfig(
            name="test_agent",
            type=AgentType.ASSISTANT_AGENT,
            description="Test assistant agent",
            labels=["test"],
            prompt_path="test.md",
            model_client=model_client.deepseek_chat_DeepSeek
        )
    ])
    
    # Mock group chat methods
    data_layer.group_chat = Mock()
    data_layer.group_chat.get_all_components = AsyncMock(return_value=[
        SelectorGroupChatConfig(
            name="test_groupchat",
            type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT,
            description="Test group chat",
            labels=["test"],
            selector_prompt="test prompt",
            model_client=model_client.deepseek_chat_DeepSeek,
            participants=[]
        )
    ])
    
    # Mock LLM methods
    data_layer.llm = Mock()
    data_layer.llm.get_component_by_name = AsyncMock(return_value=ModelClientConfig(
        type=ComponentType.LLM,
        label="test_model",
        model_name="test-model-1",
        base_url="https://api.test.com",
        family=ModelFamily.UNKNOWN,
        api_key_type="TEST_API_KEY",
        stream=True
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


class TestUserStaticMethods:
    """Tests for User class static methods that don't require context"""
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_success(self, mock_data_layer):
        """Test get_chat_profiles successful execution"""
        # Import here to avoid context issues during module import
        from chainlit_web.users import User
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 2
        assert profiles[0].name == "test_agent"
        assert "Agent" in profiles[0].markdown_description
        assert profiles[1].name == "test_groupchat"
        assert "Group Chat" in profiles[1].markdown_description
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_empty_components(self, mock_data_layer):
        """Test get_chat_profiles with empty component lists"""
        from chainlit_web.users import User
        
        mock_data_layer.agent.get_all_components.return_value = []
        mock_data_layer.group_chat.get_all_components.return_value = []
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 1
        assert profiles[0].name == "executor"
        assert "Default Group Chat" in profiles[0].markdown_description
    
    @pytest.mark.asyncio
    async def test_get_chat_profiles_error_handling(self, mock_data_layer):
        """Test get_chat_profiles error handling"""
        from chainlit_web.users import User
        
        mock_data_layer.agent.get_all_components.side_effect = Exception("Database error")
        
        profiles = await User.get_chat_profiles(mock_data_layer)
        
        assert len(profiles) == 1
        assert profiles[0].name == "hil"
        assert "Default Group Chat" in profiles[0].markdown_description


class TestUserMethodsWithMockedContext:
    """Tests for User class methods with properly mocked context"""
    
    def test_user_session_manager_get_without_context(self):
        """Test UserSessionManager get method without context"""
        from chainlit_web.users import UserSessionManager
        
        manager = UserSessionManager()
        result = manager.get("test_key", "default_value")
        assert result == "default_value"
    
    @patch('chainlit_web.users.context')
    def test_component_info_access(self, mock_context):
        """Test accessing component info map"""
        from chainlit_web.users import UserSessionManager
        
        # Set up mock context
        mock_session = Mock()
        mock_session.id = "test_session"
        mock_context.session = mock_session
        
        manager = UserSessionManager()
        manager.component_info_map = {
            "test_component": AssistantAgentConfig(
                name="test_component",
                type=AgentType.ASSISTANT_AGENT,
                description="Test component",
                labels=["test"],
                prompt_path="test.md",
                model_client=model_client.deepseek_chat_DeepSeek
            )
        }
        
        assert "test_component" in manager.component_info_map
        assert manager.component_info_map["test_component"].name == "test_component"
    
    def test_model_list_operations(self):
        """Test model list operations"""
        from chainlit_web.users import UserSessionManager
        
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


class TestComponentManagement:
    """Tests for component management functionality"""
    
    @pytest.mark.asyncio
    async def test_component_info_map_building(self, mock_data_layer):
        """Test building component info map from data layer"""
        from chainlit_web.users import UserSessionManager
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_data_layer)
        
        # Verify both agents and group chats are included
        component_names = list(manager.component_info_map.keys())
        assert "test_agent" in component_names
        assert "test_groupchat" in component_names
        
        # Verify component types
        agent_component = manager.component_info_map["test_agent"]
        groupchat_component = manager.component_info_map["test_groupchat"]
        
        assert agent_component.type == AgentType.ASSISTANT_AGENT
        assert groupchat_component.type == GroupChatTypeEnum.SELECTOR_GROUP_CHAT
    
    @pytest.mark.asyncio
    async def test_component_info_map_with_multiple_agents(self, mock_data_layer):
        """Test component info map with multiple agents"""
        from chainlit_web.users import UserSessionManager
        
        # Mock multiple agents
        mock_data_layer.agent.get_all_components.return_value = [
            AssistantAgentConfig(name="agent1", type=AgentType.ASSISTANT_AGENT, description="Agent 1", labels=["test"], prompt_path="test.md", model_client="test"),
            AssistantAgentConfig(name="agent2", type=AgentType.CODE_AGENT, description="Agent 2", labels=["test"], prompt_path="test.md", model_client="test")
        ]
        
        # Mock multiple group chats  
        mock_data_layer.group_chat.get_all_components.return_value = [
            SelectorGroupChatConfig(name="gc1", type=GroupChatTypeEnum.SELECTOR_GROUP_CHAT, description="GC 1", labels=["test"], selector_prompt="test", model_client="test", participants=[])
        ]
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_data_layer)
        
        # Verify all components are included
        assert len(manager.component_info_map) == 3
        assert "agent1" in manager.component_info_map
        assert "agent2" in manager.component_info_map
        assert "gc1" in manager.component_info_map


class TestErrorHandling:
    """Tests for error handling scenarios"""
    
    @pytest.mark.asyncio
    async def test_data_layer_agent_error(self, mock_data_layer):
        """Test handling of agent data layer errors"""
        from chainlit_web.users import UserSessionManager
        
        mock_data_layer.agent.get_all_components.side_effect = Exception("Agent DB error")
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_data_layer)
        
        # Should handle error gracefully and set empty map
        assert manager.component_info_map == {}
    
    @pytest.mark.asyncio
    async def test_data_layer_groupchat_error(self, mock_data_layer):
        """Test handling of group chat data layer errors"""
        from chainlit_web.users import UserSessionManager
        
        mock_data_layer.group_chat.get_all_components.side_effect = Exception("GroupChat DB error")
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_data_layer)
        
        # Should handle error gracefully and set empty map
        assert manager.component_info_map == {}
    
    @pytest.mark.asyncio
    async def test_partial_data_layer_success(self, mock_data_layer):
        """Test handling when only one data source succeeds"""
        from chainlit_web.users import UserSessionManager
        
        # Agent succeeds, group chat fails
        mock_data_layer.group_chat.get_all_components.side_effect = Exception("GroupChat error")
        
        manager = UserSessionManager()
        await manager.initialize_component_info_map(mock_data_layer)
        
        # Should handle error gracefully and set empty map (current implementation)
        assert manager.component_info_map == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])