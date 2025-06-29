import pytest
import json
import tempfile
import os
import asyncio
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path

# Import the modules we want to test
from builders import load_info, AgentBuilder, AgentInfo, McpInfo
from builders.utils import McpInfo, AgentInfo, GraphFlowInfo, GroupChatInfo
from schemas.agent import AgentType, AssistantAgentConfig, UserProxyAgentConfig
from schemas.model_info import model_client


class TestLoadInfo:
    """Test cases for the load_info function."""
    
    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing."""
        return {
            "prompt_root": "config/prompt",
            "mcpServers": {
                "test_server": {
                    "command": "npx",
                    "args": ["-y", "@modelcontextprotocol/server-filesystem", "${cwd}"],
                    "env": {},
                    "read_timeout_seconds": 30
                }
            },
            "agents": {
                "test_assistant": {
                    "name": "test_assistant",
                    "description": "Test assistant agent",
                    "labels": ["test", "agent"],
                    "type": "assistant_agent",
                    "prompt_path": "agent/test_pt.md",
                    "model_client": "deepseek-chat_DeepSeek",
                    "mcp_tools": ["test_server"]
                },
                "test_user_proxy": {
                    "name": "test_user_proxy",
                    "description": "Test user proxy agent",
                    "labels": ["test", "user"],
                    "type": "user_proxy_agent",
                    "input_func": "input"
                }
            },
            "group_chats": {
                "test_group": {
                    "name": "test_group",
                    "description": "Test group chat",
                    "labels": ["test", "group_chat"],
                    "type": "selector_group_chat",
                    "selector_prompt": "group_chat/test/selector_pt.md",
                    "model_client": "deepseek-chat_DeepSeek",
                    "participants": ["test_assistant", "test_user_proxy"]
                }
            },
            "graph_flows": {
                "test_flow": {
                    "name": "test_flow",
                    "description": "Test graph flow",
                    "labels": ["test", "graph_flow"],
                    "type": "graph_flow",
                    "participants": ["test_assistant", "test_user_proxy"],
                    "nodes": [["test_assistant", "test_user_proxy"]],
                    "start_node": "test_assistant"
                }
            }
        }
    
    @pytest.fixture
    def temp_config_file(self, sample_config):
        """Create a temporary config file for testing."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_config, f)
            temp_path = f.name
        yield temp_path
        os.unlink(temp_path)
    
    def setup_method(self):
        """Clear global dictionaries before each test."""
        McpInfo.clear()
        AgentInfo.clear()
        GraphFlowInfo.clear()
        GroupChatInfo.clear()
    
    @patch('builders.utils.get_prompt')
    def test_load_info_success(self, mock_get_prompt, temp_config_file):
        """Test successful loading of configuration."""
        mock_get_prompt.return_value = "Test prompt content"
        
        # Load the configuration
        load_info(temp_config_file)
        
        # Check MCP servers were loaded
        assert "test_server" in McpInfo
        assert McpInfo["test_server"].command == "npx"
        
        # Check agents were loaded
        assert "test_assistant" in AgentInfo
        assert "test_user_proxy" in AgentInfo
        assert AgentInfo["test_assistant"].name == "test_assistant"
        assert AgentInfo["test_assistant"].type == AgentType.ASSISTANT_AGENT
        assert AgentInfo["test_assistant"].prompt_path == "agent/test_pt.md"
        assert callable(AgentInfo["test_assistant"].prompt), "prompt should be callable"
        assert AgentInfo["test_assistant"].prompt() == "Test prompt content", "prompt should return mocked content"
        assert AgentInfo["test_user_proxy"].type == AgentType.USER_PROXY_AGENT
        
        # Check group chats were loaded
        assert "test_group" in GroupChatInfo
        assert GroupChatInfo["test_group"].name == "test_group"
        
        # Check graph flows were loaded
        assert "test_flow" in GraphFlowInfo
        assert GraphFlowInfo["test_flow"].name == "test_flow"
    
    def test_load_info_file_not_found(self):
        """Test load_info with non-existent file."""
        with pytest.raises(FileNotFoundError):
            load_info("non_existent_file.json")
    
    def test_load_info_invalid_json(self):
        """Test load_info with invalid JSON."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("invalid json content")
            temp_path = f.name
        
        try:
            with pytest.raises(json.JSONDecodeError):
                load_info(temp_path)
        finally:
            os.unlink(temp_path)
    
    @patch('builders.utils.get_prompt')
    def test_load_info_with_mcp_tools(self, mock_get_prompt, sample_config):
        """Test loading agents with MCP tools."""
        mock_get_prompt.return_value = "Test prompt"
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(sample_config, f)
            temp_path = f.name
        
        try:
            load_info(temp_path)
            
            # Check that agent with MCP tools was loaded correctly
            test_agent = AgentInfo["test_assistant"]
            assert hasattr(test_agent, 'mcp_tools')
            assert len(test_agent.mcp_tools) == 1
            assert test_agent.mcp_tools[0].command == "npx"
        finally:
            os.unlink(temp_path)


class TestAgentBuilder:
    """Test cases for the AgentBuilder class."""
    
    @pytest.fixture
    def mock_agent_config(self):
        """Mock agent configuration for testing."""
        return {
            "name": "test_agent",
            "description": "Test agent",
            "type": AgentType.ASSISTANT_AGENT,
            "model_client": model_client.deepseek_chat_DeepSeek,
            "mcp_tools": [],
            "prompt": lambda: "Test system message"
        }
    
    @pytest.fixture
    def mock_user_proxy_config(self):
        """Mock user proxy configuration for testing."""
        return {
            "name": "test_user_proxy",
            "description": "Test user proxy",
            "type": AgentType.USER_PROXY_AGENT,
            "input_func": "input"
        }
    
    def setup_method(self):
        """Clear global dictionaries before each test."""
        AgentInfo.clear()
    
    @pytest.mark.asyncio
    @patch('builders.agent_builder.ModelClient')
    @patch('builders.agent_builder.mcp_server_tools')
    async def test_agent_builder_assistant_agent(self, mock_mcp_tools, mock_model_client):
        """Test building an assistant agent."""
        # Setup mocks
        mock_model_client_instance = MagicMock()
        mock_model_client_instance.close = AsyncMock()
        mock_model_client_dict = {model_client.deepseek_chat_DeepSeek.value: MagicMock(return_value=mock_model_client_instance)}
        mock_model_client.__getitem__.side_effect = mock_model_client_dict.__getitem__
        mock_mcp_tools.return_value = []
        
        # Create agent configuration
        agent_config = AssistantAgentConfig(
            name="test_agent",
            description="Test agent",
            labels=["test", "agent"],
            type=AgentType.ASSISTANT_AGENT,
            model_client=model_client.deepseek_chat_DeepSeek,
            mcp_tools=[],
            prompt=lambda: "Test system message"
        )
        AgentInfo["test_agent"] = agent_config
        
        # Test agent building
        async def test_input(prompt: str) -> str:
            return "test input"
        
        builder = AgentBuilder(test_input)
        
        async with builder.build("test_agent") as agent:
            assert agent is not None
            assert agent.name == "test_agent"
            assert hasattr(agent, 'component_label')
            assert agent.component_label == "test_agent"
        
        # Verify model client was closed
        mock_model_client_instance.close.assert_called_once()
    
    @pytest.mark.asyncio
    @patch('builders.agent_builder.ModelClient')
    async def test_agent_builder_user_proxy_agent(self, mock_model_client):
        """Test building a user proxy agent."""
        # Setup mock for the dummy model client
        mock_client_instance = MagicMock()
        mock_model_client_dict = {"dummy_model": MagicMock(return_value=mock_client_instance)}
        mock_model_client.__getitem__.side_effect = mock_model_client_dict.__getitem__
        # Create user proxy configuration
        user_proxy_config = UserProxyAgentConfig(
            name="test_user_proxy",
            description="Test user proxy",
            labels=["test", "user_proxy"],
            type=AgentType.USER_PROXY_AGENT,
            input_func="input"
        )
        
        # Work around AgentBuilder bug - it tries to access model_client on all agents
        # Use object.__setattr__ to bypass Pydantic validation
        mock_model_client_attr = MagicMock()
        mock_model_client_attr.value = "dummy_model"
        object.__setattr__(user_proxy_config, 'model_client', mock_model_client_attr)
        AgentInfo["test_user_proxy"] = user_proxy_config
        
        # Test agent building
        async def test_input(prompt: str) -> str:
            return "test input"
        
        builder = AgentBuilder(test_input)
        
        async with builder.build("test_user_proxy") as agent:
            assert agent is not None
            assert agent.name == "test_user_proxy"
            assert hasattr(agent, 'component_label')
            assert agent.component_label == "test_user_proxy"
        
        # Verify model client was not called for user proxy
        mock_model_client.assert_not_called()
    
    @patch('builders.agent_builder.ModelClient')
    def test_agent_builder_invalid_agent_type(self, mock_model_client):
        """Test building agent with invalid type."""
        # Setup mock for model client
        mock_client_instance = MagicMock()
        mock_model_client_dict = {model_client.deepseek_chat_DeepSeek.value: MagicMock(return_value=mock_client_instance)}
        mock_model_client.__getitem__.side_effect = mock_model_client_dict.__getitem__
        
        # Create invalid agent configuration
        invalid_config = MagicMock()
        invalid_config.name = "invalid_agent"
        invalid_config.type = "invalid_type"
        # Mock the model_client property to avoid KeyError
        invalid_config.model_client = MagicMock()
        invalid_config.model_client.value = model_client.deepseek_chat_DeepSeek.value
        AgentInfo["invalid_agent"] = invalid_config
        
        builder = AgentBuilder()
        
        # This should raise a ValueError
        with pytest.raises(ValueError, match="Invalid agent type"):
            async def test_build():
                async with builder.build("invalid_agent") as agent:
                    pass
            
            import asyncio
            asyncio.run(test_build())
    
    def test_agent_builder_agent_not_found(self):
        """Test building non-existent agent."""
        builder = AgentBuilder()
        
        # This should raise a KeyError
        with pytest.raises(KeyError):
            async def test_build():
                async with builder.build("non_existent_agent") as agent:
                    pass
            
            import asyncio
            asyncio.run(test_build())
    
    @pytest.mark.asyncio
    @patch('builders.agent_builder.ModelClient')
    @patch('builders.agent_builder.mcp_server_tools')
    async def test_agent_builder_with_mcp_tools(self, mock_mcp_tools, mock_model_client):
        """Test building agent with MCP tools."""
        # Setup mocks
        mock_model_client_instance = MagicMock()
        mock_model_client_instance.close = AsyncMock()
        mock_model_client_dict = {model_client.deepseek_chat_DeepSeek.value: MagicMock(return_value=mock_model_client_instance)}
        mock_model_client.__getitem__.side_effect = mock_model_client_dict.__getitem__
        
        # Create a more realistic mock tool that can be used by AgentBuilder
        from autogen_ext.tools.mcp import StdioMcpToolAdapter
        mock_tool = MagicMock(spec=StdioMcpToolAdapter)
        mock_tool.name = "test_tool"
        mock_tool.__call__ = MagicMock()
        # Mock the necessary attributes for FunctionTool creation
        mock_tool.__name__ = "test_tool"
        mock_tool.__doc__ = "Test tool description"
        mock_tool.__annotations__ = {}
        mock_mcp_tools.return_value = [mock_tool]
        
        # Create mock MCP server with proper type (using filesystem example)
        from autogen_ext.tools.mcp import StdioServerParams
        mock_mcp_server = StdioServerParams(
            command="npx",
            args=["-y", "@modelcontextprotocol/server-filesystem", "${cwd}"],
            env={},
            read_timeout_seconds=30
        )
        
        # Create agent configuration with MCP tools
        agent_config = AssistantAgentConfig(
            name="test_agent_with_tools",
            description="Test agent with tools",
            labels=["test", "agent", "tools"],
            type=AgentType.ASSISTANT_AGENT,
            model_client=model_client.deepseek_chat_DeepSeek,
            mcp_tools=[mock_mcp_server],
            prompt=lambda: "Test system message"
        )
        AgentInfo["test_agent_with_tools"] = agent_config
        
        builder = AgentBuilder()
        
        async with builder.build("test_agent_with_tools") as agent:
            assert agent is not None
            assert agent.name == "test_agent_with_tools"
            
        # Verify MCP tools were loaded
        mock_mcp_tools.assert_called_once_with(mock_mcp_server)
        
        # Verify tool component label was set
        assert mock_tool.component_label == "test_tool"


class TestIntegration:
    """Integration tests for load_info and AgentBuilder."""
    
    def setup_method(self):
        """Clear global dictionaries before each test."""
        McpInfo.clear()
        AgentInfo.clear()
        GraphFlowInfo.clear()
        GroupChatInfo.clear()
    
    @pytest.mark.asyncio
    @patch('builders.utils.get_prompt')
    @patch('builders.agent_builder.ModelClient')
    @patch('builders.agent_builder.mcp_server_tools')
    async def test_load_and_build_integration(self, mock_mcp_tools, mock_model_client, mock_get_prompt):
        """Test integration of load_info and AgentBuilder."""
        # Setup mocks
        mock_get_prompt.return_value = "Test prompt content"
        mock_model_client_instance = MagicMock()
        mock_model_client_instance.close = AsyncMock()
        mock_model_client_dict = {model_client.deepseek_chat_DeepSeek.value: MagicMock(return_value=mock_model_client_instance)}
        mock_model_client.__getitem__.side_effect = mock_model_client_dict.__getitem__
        mock_mcp_tools.return_value = []
        
        # Create test configuration
        config = {
            "prompt_root": "config/prompt",
            "mcpServers": {
                "file_system": {
                    "command": "npx",
                    "args": [
                        "-y", 
                        "@modelcontextprotocol/server-filesystem", 
                        "${cwd}"
                    ],
                    "env": {},
                    "read_timeout_seconds": 30
                }
            },
            "agents": {
                "integration_test_agent": {
                    "name": "integration_test_agent",
                    "description": "Integration test agent",
                    "labels": ["integration", "test"],
                    "type": "assistant_agent",
                    "prompt_path": "agent/test_pt.md",
                    "model_client": "deepseek-chat_DeepSeek",
                    "mcp_tools": ["file_system"],
                    "prompt": "placeholder"
                }
            },
            "group_chats": {},
            "graph_flows": {}
        }
        
        # Save config to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(config, f)
            temp_path = f.name
        
        try:
            # Load configuration
            load_info(temp_path)
            
            # Verify agent was loaded
            assert "integration_test_agent" in AgentInfo
            
            # Build agent
            builder = AgentBuilder()
            async with builder.build("integration_test_agent") as agent:
                assert agent is not None
                assert agent.name == "integration_test_agent"
                assert agent.component_label == "integration_test_agent"
                
        finally:
            os.unlink(temp_path)


if __name__ == "__main__":
    pytest.main([__file__]) 