import asyncio
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncGenerator, List, Any, TypeVar, Generic, Union

from autogen_agentchat.teams import BaseGroupChat
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, StopMessage, TextMessage, ModelClientStreamingChunkEvent
from autogen_agentchat.base import TaskResult
from autogen_core import AgentRuntime, CancellationToken, SingleThreadedAgentRuntime, AgentId
from autogen_core.models import LLMMessage
from autogen_agentchat.teams._group_chat._events import (
    GroupChatTermination, 
    GroupChatStart, 
    SerializableException
)
from schemas.group_chat_type import GroupChatType
from base.goupchat_queue import BaseChatQueue

T = TypeVar('T', bound=BaseGroupChat)
# Type alias for supported agent types
AgentTypes = Union[AssistantAgent, UserProxyAgent]

class AutoGenGroupChatQueue(BaseChatQueue, Generic[T]):
    """AutoGen GroupChat Queue using inheritance instead of composition"""
    
    def __init__(self, group_chat_instance: T):
        BaseChatQueue.__init__(self)
        # Store the group chat instance and delegate attribute access to it
        self._group_chat_instance = group_chat_instance
        self._cancellation_token: CancellationToken | None = None
        self._output_task_messages: bool = True
    
    def __getattr__(self, name):
        """Delegate attribute access to the group chat instance"""
        return getattr(self._group_chat_instance, name)
    
    @asynccontextmanager
    async def start(self, cancellation_token: CancellationToken | None = None, output_task_messages: bool = True):
        """Start the group chat with proper runtime management"""
        if self._is_running:
            raise ValueError("The group chat is already running.")
        
        if cancellation_token is not None:
            self._cancellation_token = cancellation_token
        if output_task_messages is not None:
            self._output_task_messages = output_task_messages

        self._is_running = True
        embedded_runtime = self._group_chat_instance._embedded_runtime
        output_message_queue = self._group_chat_instance._output_message_queue
        shutdown_task: asyncio.Task[None] | None = None
        
        if embedded_runtime:
            async def stop_runtime() -> None:
                assert isinstance(self._group_chat_instance._runtime, SingleThreadedAgentRuntime)
                try:
                    await self._group_chat_instance._runtime.stop_when_idle()
                    await output_message_queue.put(
                        GroupChatTermination(
                            message=StopMessage(
                                content="The group chat is stopped.", 
                                source=self._group_chat_instance._group_chat_manager_name
                            )
                        )
                    )
                except Exception as e:
                    await output_message_queue.put(
                        GroupChatTermination(
                            message=StopMessage(
                                content="An exception occurred in the runtime.", 
                                source=self._group_chat_instance._group_chat_manager_name
                            ),
                            error=SerializableException.from_exception(e),
                        )
                    )

            shutdown_task = asyncio.create_task(stop_runtime())
        
        try:
            yield shutdown_task
        finally:
            try:
                if shutdown_task is not None:
                    await shutdown_task
            finally:
                # Clear the output message queue
                while not output_message_queue.empty():
                    output_message_queue.get_nowait()
                self._is_running = False

    async def push(self, messages: Union[str, List[LLMMessage]]) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None]:
        """Process messages from queue and dispatch to handlers"""
        output_messages: List[BaseAgentEvent | BaseChatMessage] = []
        stop_reason: str | None = None
        
        output_message_queue = self._group_chat_instance._output_message_queue
        
        try:
            # Handle both string and List[LLMMessage] input
            if isinstance(messages, str):
                text_message = TextMessage(content=messages, source="user")
                message_list = [text_message]
            else:
                # Convert LLMMessage list to TextMessage list
                message_list = []
                for msg in messages:
                    if hasattr(msg, 'content'):
                        text_message = TextMessage(content=str(msg.content), source=getattr(msg, 'source', 'user'))
                        message_list.append(text_message)
            
            # Send start message to group chat manager
            await self._group_chat_instance._runtime.send_message(
                GroupChatStart(messages=message_list, output_task_messages=self._output_task_messages),
                recipient=AgentId(
                    type=self._group_chat_instance._group_chat_manager_topic_type, 
                    key=self._group_chat_instance._team_id
                ),
                cancellation_token=self._cancellation_token,
            )
            
            # Yield messages until termination
            while True:
                message_future = asyncio.ensure_future(output_message_queue.get())
                if self._cancellation_token is not None:
                    self._cancellation_token.link_future(message_future)
                
                queue_message = await message_future
                
                # Handle termination
                if isinstance(queue_message, GroupChatTermination):
                    if queue_message.error is not None:
                        raise RuntimeError(str(queue_message.error))
                    stop_reason = queue_message.message.content
                    break
                
                # Dispatch and yield message
                await self._dispatch_message(queue_message)
                yield queue_message
                
                # Add to output messages (skip streaming chunks)
                if not isinstance(queue_message, ModelClientStreamingChunkEvent):
                    output_messages.append(queue_message)
            
            # Yield final result
            task_result = TaskResult(messages=output_messages, stop_reason=stop_reason)
            await self.task_finished(task_result)
            yield task_result
            
        except Exception as e:
            # Handle any errors during message processing
            raise RuntimeError(f"Error processing message: {str(e)}") from e
    
    async def _dispatch_message(self, message: BaseAgentEvent | BaseChatMessage | GroupChatTermination) -> None:
        """Dispatch message to appropriate handler based on type"""
        if isinstance(message, GroupChatTermination):
            await self.handle_group_chat_termination(message)
        elif isinstance(message, BaseAgentEvent):
            await self.handle_agent_event(message)
        elif isinstance(message, BaseChatMessage):
            await self.handle_chat_message(message)
        else:
            await self.handle_unknown_message(message)
    
    async def handle_group_chat_termination(self, message: GroupChatTermination) -> None:
        """Handle GroupChatTermination messages"""
        pass
    
    async def handle_agent_event(self, message: BaseAgentEvent) -> None:
        """Handle BaseAgentEvent messages"""
        pass
    
    async def handle_chat_message(self, message: BaseChatMessage) -> None:
        """Handle BaseChatMessage messages"""
        pass
    
    async def handle_unknown_message(self, message: Any) -> None:
        """Handle unknown message types"""
        pass
    
    async def task_finished(self, task_result: TaskResult) -> None:
        """Handle task completion - can be overridden by derived classes"""
        pass


class AutoGenAgentChatQueue(BaseChatQueue):
    """Single agent chat queue implementation with run_stream support"""
    
    def __init__(self, agent_instance: AgentTypes):
        super().__init__()
        self._agent = agent_instance
        self._cancellation_token: CancellationToken | None = None
        
    @asynccontextmanager
    async def start(self, cancellation_token: CancellationToken | None = None, output_task_messages: bool = True):
        """Start the agent chat session"""
        if self._is_running:
            raise ValueError("The agent chat is already running.")
        
        if cancellation_token is not None:
            self._cancellation_token = cancellation_token
            
        self._is_running = True
        
        try:
            yield None
        finally:
            self._is_running = False

    async def push(self, messages: Union[str, List[LLMMessage]]) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None]:
        """Process message using agent's run_stream and yield results"""
        if not self._is_running:
            raise ValueError("Agent chat queue is not running. Call start() first.")
            
        try:
            # Handle both string and List[LLMMessage] input
            if isinstance(messages, str):
                task_content = messages
            else:
                # Convert LLMMessage list to string
                task_content = ""
                for msg in messages:
                    if hasattr(msg, 'content'):
                        task_content += str(msg.content) + "\n"
                task_content = task_content.strip()
            
            # Use the agent's run_stream method to process the message
            async for event in self._agent.run_stream(task=task_content, cancellation_token=self._cancellation_token):
                # Dispatch the event to appropriate handler
                await self._dispatch_message(event)
                yield event
                
                # Check if this is a TaskResult (final result)
                if isinstance(event, TaskResult):
                    await self.task_finished(event)
                    break
                    
        except Exception as e:
            # Handle any errors during message processing
            raise RuntimeError(f"Error processing message in agent: {str(e)}") from e
    
    async def _dispatch_message(self, message: BaseAgentEvent | BaseChatMessage | TaskResult) -> None:
        """Dispatch message to appropriate handler based on type"""
        if isinstance(message, TaskResult):
            await self.handle_task_result(message)
        elif isinstance(message, BaseAgentEvent):
            await self.handle_agent_event(message)
        elif isinstance(message, BaseChatMessage):
            await self.handle_chat_message(message)
        else:
            await self.handle_unknown_message(message)
    
    async def handle_task_result(self, message: TaskResult) -> None:
        """Handle TaskResult messages"""
        pass
    
    async def handle_agent_event(self, message: BaseAgentEvent) -> None:
        """Handle BaseAgentEvent messages"""
        pass
    
    async def handle_chat_message(self, message: BaseChatMessage) -> None:
        """Handle BaseChatMessage messages"""
        pass
    
    async def handle_unknown_message(self, message: Any) -> None:
        """Handle unknown message types"""
        pass
    
    async def task_finished(self, task_result: TaskResult) -> None:
        """Handle task completion - can be overridden by derived classes"""
        pass