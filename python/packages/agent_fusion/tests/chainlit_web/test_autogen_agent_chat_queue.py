"""
Test cases for AutoGenAgentChatQueue implementation.

These tests verify the single agent mode functionality with queue-based message handling,
including run_stream integration and proper event dispatching.
"""

import pytest
import pytest_asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from autogen_core import CancellationToken
from autogen_agentchat.messages import TextMessage, BaseAgentEvent, BaseChatMessage
from autogen_agentchat.base import TaskResult

from chainlit_web.ui_hook.autogen_chat_queue import AutoGenAgentChatQueue


class TestAutoGenAgentChatQueue:
    """Test cases for AutoGenAgentChatQueue"""

    @pytest.fixture
    def mock_agent(self):
        """Create a mock agent with run_stream method"""
        agent = MagicMock()
        # Don't use AsyncMock for run_stream since it needs to return an async generator
        agent.run_stream = MagicMock()
        return agent

    @pytest.fixture
    def agent_queue(self, mock_agent):
        """Create an AutoGenAgentChatQueue instance"""
        return AutoGenAgentChatQueue(mock_agent)

    @pytest.fixture
    def cancellation_token(self):
        """Create a cancellation token for testing"""
        return CancellationToken()

    def test_initialization(self, mock_agent):
        """Test AutoGenAgentChatQueue initialization"""
        queue = AutoGenAgentChatQueue(mock_agent)
        
        assert queue._agent == mock_agent
        assert queue._cancellation_token is None
        assert not queue._is_running

    @pytest.mark.asyncio
    async def test_start_context_manager(self, agent_queue, cancellation_token):
        """Test start context manager behavior"""
        assert not agent_queue._is_running
        
        async with agent_queue.start(cancellation_token=cancellation_token):
            assert agent_queue._is_running
            assert agent_queue._cancellation_token == cancellation_token
        
        assert not agent_queue._is_running

    @pytest.mark.asyncio
    async def test_start_already_running_error(self, agent_queue):
        """Test that starting an already running queue raises error"""
        async with agent_queue.start():
            with pytest.raises(ValueError, match="already running"):
                async with agent_queue.start():
                    pass

    @pytest.mark.asyncio
    async def test_push_not_running_error(self, agent_queue):
        """Test that pushing to non-running queue raises error"""
        with pytest.raises(ValueError, match="not running"):
            async for _ in agent_queue.push("test message"):
                pass

    @pytest.mark.asyncio
    async def test_push_successful_message_processing(self, agent_queue, mock_agent):
        """Test successful message processing through push method"""
        # Setup mock run_stream to return test events
        test_message = TextMessage(content="Hello", source="user")
        test_result = TaskResult(messages=[test_message], stop_reason="completed")
        
        async def mock_run_stream(task, cancellation_token=None):
            yield test_message
            yield test_result
        
        mock_agent.run_stream = MagicMock(side_effect=mock_run_stream)
        
        # Test the push method
        events = []
        async with agent_queue.start():
            async for event in agent_queue.push("test message"):
                events.append(event)
        
        # Verify events
        assert len(events) == 2
        assert events[0] == test_message
        assert events[1] == test_result
        
        # Verify agent was called correctly
        mock_agent.run_stream.assert_called_once()
        call_args = mock_agent.run_stream.call_args
        assert call_args[1]['task'] == "test message"

    @pytest.mark.asyncio
    async def test_push_with_cancellation_token(self, agent_queue, mock_agent, cancellation_token):
        """Test push method with cancellation token"""
        test_result = TaskResult(messages=[], stop_reason="completed")
        
        async def mock_run_stream(task, cancellation_token=None):
            yield test_result
        
        mock_agent.run_stream = MagicMock(side_effect=mock_run_stream)
        
        async with agent_queue.start(cancellation_token=cancellation_token):
            async for event in agent_queue.push("test message"):
                pass
        
        # Verify cancellation token was passed
        call_args = mock_agent.run_stream.call_args
        assert call_args[1]['cancellation_token'] == cancellation_token

    @pytest.mark.asyncio
    async def test_push_error_handling(self, agent_queue, mock_agent):
        """Test error handling in push method"""
        # Setup mock to raise an exception
        mock_agent.run_stream.side_effect = Exception("Test error")
        
        async with agent_queue.start():
            with pytest.raises(RuntimeError, match="Error processing message"):
                async for event in agent_queue.push("test message"):
                    pass

    @pytest.mark.asyncio
    async def test_message_dispatch_handlers(self, agent_queue):
        """Test message dispatch to appropriate handlers"""
        # Mock the handler methods
        agent_queue.handle_task_result = AsyncMock()
        agent_queue.handle_agent_event = AsyncMock()
        agent_queue.handle_chat_message = AsyncMock()
        agent_queue.handle_unknown_message = AsyncMock()
        
        # Test TaskResult dispatch
        task_result = TaskResult(messages=[], stop_reason="test")
        await agent_queue._dispatch_message(task_result)
        agent_queue.handle_task_result.assert_called_once_with(task_result)
        
        # Test BaseAgentEvent dispatch
        agent_event = MagicMock(spec=BaseAgentEvent)
        await agent_queue._dispatch_message(agent_event)
        agent_queue.handle_agent_event.assert_called_once_with(agent_event)
        
        # Test BaseChatMessage dispatch
        chat_message = MagicMock(spec=BaseChatMessage)
        await agent_queue._dispatch_message(chat_message)
        agent_queue.handle_chat_message.assert_called_once_with(chat_message)
        
        # Test unknown message dispatch
        unknown_message = "unknown"
        await agent_queue._dispatch_message(unknown_message)
        agent_queue.handle_unknown_message.assert_called_once_with(unknown_message)

    @pytest.mark.asyncio
    async def test_task_finished_called(self, agent_queue, mock_agent):
        """Test that task_finished is called when TaskResult is received"""
        # Mock task_finished method
        agent_queue.task_finished = AsyncMock()
        
        test_result = TaskResult(messages=[], stop_reason="completed")
        
        async def mock_run_stream(task, cancellation_token=None):
            yield test_result
        
        mock_agent.run_stream = mock_run_stream
        
        async with agent_queue.start():
            async for event in agent_queue.push("test message"):
                pass
        
        # Verify task_finished was called
        agent_queue.task_finished.assert_called_once_with(test_result)

    @pytest.mark.asyncio
    async def test_multiple_events_processing(self, agent_queue, mock_agent):
        """Test processing multiple events from run_stream"""
        # Setup multiple events
        message1 = TextMessage(content="Message 1", source="agent")
        message2 = TextMessage(content="Message 2", source="agent")
        task_result = TaskResult(messages=[message1, message2], stop_reason="completed")
        
        async def mock_run_stream(task, cancellation_token=None):
            yield message1
            yield message2
            yield task_result
        
        mock_agent.run_stream = mock_run_stream
        
        events = []
        async with agent_queue.start():
            async for event in agent_queue.push("test message"):
                events.append(event)
        
        # Verify all events were processed
        assert len(events) == 3
        assert events[0] == message1
        assert events[1] == message2
        assert events[2] == task_result

    def test_handler_methods_exist(self, agent_queue):
        """Test that all required handler methods exist and are callable"""
        # Verify all handler methods exist
        assert hasattr(agent_queue, 'handle_task_result')
        assert hasattr(agent_queue, 'handle_agent_event')
        assert hasattr(agent_queue, 'handle_chat_message')
        assert hasattr(agent_queue, 'handle_unknown_message')
        assert hasattr(agent_queue, 'task_finished')
        
        # Verify they are callable
        assert callable(agent_queue.handle_task_result)
        assert callable(agent_queue.handle_agent_event)
        assert callable(agent_queue.handle_chat_message)
        assert callable(agent_queue.handle_unknown_message)
        assert callable(agent_queue.task_finished)


class TestAutoGenAgentChatQueueIntegration:
    """Integration tests for AutoGenAgentChatQueue with real agent scenarios"""

    @pytest.mark.asyncio
    async def test_queue_with_mock_assistant_agent(self):
        """Test queue integration with a mock assistant agent"""
        # Create a more realistic mock agent
        mock_agent = MagicMock()
        
        # Simulate realistic run_stream behavior
        async def realistic_run_stream(task, cancellation_token=None):
            # Agent processes the task and responds
            yield TextMessage(content=f"Processing: {task}", source="agent")
            yield TextMessage(content=f"Result for: {task}", source="agent")
            yield TaskResult(
                messages=[
                    TextMessage(content=f"Processing: {task}", source="agent"),
                    TextMessage(content=f"Result for: {task}", source="agent")
                ],
                stop_reason="task_completed"
            )
        
        mock_agent.run_stream = realistic_run_stream
        
        # Test the queue
        queue = AutoGenAgentChatQueue(mock_agent)
        collected_events = []
        
        async with queue.start():
            async for event in queue.push("Hello, how are you?"):
                collected_events.append(event)
        
        # Verify the interaction
        assert len(collected_events) == 3
        assert isinstance(collected_events[0], TextMessage)
        assert isinstance(collected_events[1], TextMessage)
        assert isinstance(collected_events[2], TaskResult)
        
        # Verify the content
        assert "Processing: Hello, how are you?" in collected_events[0].content
        assert "Result for: Hello, how are you?" in collected_events[1].content

    @pytest.mark.asyncio
    async def test_queue_error_recovery(self):
        """Test queue behavior when agent encounters errors"""
        mock_agent = MagicMock()
        
        # First call fails, second succeeds
        call_count = 0
        async def failing_then_succeeding_run_stream(task, cancellation_token=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("Simulated agent error")
            else:
                yield TaskResult(messages=[], stop_reason="recovered")
        
        mock_agent.run_stream = failing_then_succeeding_run_stream
        
        queue = AutoGenAgentChatQueue(mock_agent)
        
        # First call should fail
        async with queue.start():
            with pytest.raises(RuntimeError):
                async for event in queue.push("First message"):
                    pass
        
        # Queue should still be usable after error
        async with queue.start():
            events = []
            async for event in queue.push("Second message"):
                events.append(event)
            
            assert len(events) == 1
            assert isinstance(events[0], TaskResult)
            assert events[0].stop_reason == "recovered"