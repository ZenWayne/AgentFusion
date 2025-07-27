import asyncio
import pytest
from unittest.mock import Mock, AsyncMock

from autogen_core.models import ChatCompletionClient
from autogen_core.model_context import UnboundedChatCompletionContext
from autogen_agentchat.messages import TextMessage

from agents.codeagent import CodeAgent


async def test_code_agent_example():
    """Example usage - requires a proper model client to work"""
    print("CodeAgent has been rewritten with LLM integration and context management.")
    print("To use this agent, initialize it with:")
    print("1. A name")
    print("2. A ChatCompletionClient instance")
    print("3. Optional system message")
    print("")
    print("Key features:")
    print("- Inherits from both BaseChatQueue and BaseChatAgent")
    print("- Context management with update_context method")
    print("- LLM integration following AssistantAgent._call_llm pattern")
    print("- Push interface for new messages with context caching")
    print("- Code execution with <code> tags")


@pytest.mark.asyncio
async def test_code_agent_initialization():
    """Test CodeAgent initialization"""
    # Mock model client
    mock_client = Mock(spec=ChatCompletionClient)
    
    # Initialize CodeAgent
    agent = CodeAgent(
        name="test_agent",
        model_client=mock_client,
        system_message="Test system message"
    )
    
    assert agent.name == "test_agent"
    assert agent._model_client == mock_client
    assert agent._system_message == "Test system message"
    assert agent._model_context is not None
    assert not agent._is_running


@pytest.mark.asyncio
async def test_code_agent_update_context():
    """Test update_context method"""
    # Mock model client
    mock_client = Mock(spec=ChatCompletionClient)
    
    # Initialize CodeAgent
    agent = CodeAgent(
        name="test_agent",
        model_client=mock_client
    )
    
    # Mock model context
    agent._model_context = AsyncMock()
    
    # Test update_context with messages
    messages = [
        TextMessage(content="Hello", source="user"),
        TextMessage(content="World", source="user")
    ]
    
    await agent.update_context(messages)
    
    # Verify add_message was called for each message
    assert agent._model_context.add_message.call_count == 2


if __name__ == "__main__":
    asyncio.run(test_code_agent_example())