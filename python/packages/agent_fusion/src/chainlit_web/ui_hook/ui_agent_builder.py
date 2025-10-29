"""
UI Agent Builder module.

This module provides UI-specific agent building functionality following
the same patterns as UIGroupChatBuilder for single agent mode support.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Callable, Awaitable, Optional, Union, TypeVar, Generic

from data_layer.data_layer import AgentFusionDataLayer
from data_layer.models.agent_model import AgentModel as AgentBuilderBase
from schemas.config_type import AgentConfigType
from schemas.agent import AgentType as AgentTypeEnum
from schemas.agent_type import AgentType, TypedAssistantAgent, TypedUserProxyAgent, TypedCodeAgent
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from agents.codeagent import CodeAgent
from typing import Type
from chainlit_web.ui_hook.autogen_chat_queue import AgentTypes
import chainlit as cl
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, TextMessage, ModelClientStreamingChunkEvent
from autogen_agentchat.base import TaskResult
from autogen_agentchat.base import Response

# Type aliases following project guidelines
InputFuncType = Optional[Callable[[str], Awaitable[str]]]

class UIAutoGenAgentChatQueue(CodeAgent):
    """UI-specific agent chat queue with Chainlit streaming support, inherits from CodeAgent"""
    

    def __init__(self,
        name: str, 
        model_client,
        model_context = None,
        workbench = None,
        system_message: str = "You are a helpful code execution assistant. You can execute Python code wrapped in <code> tags and provide results.",
        output_content_type = None,
        output_content_type_format = None,
        max_tool_iterations: int = 1,
        model_client_streaming: bool = False):
        
        # Initialize CodeAgent with all required parameters
        super().__init__(
            name=name,
            model_client=model_client,
            model_context=model_context,
            workbench=workbench,
            system_message=system_message,
            output_content_type=output_content_type,
            output_content_type_format=output_content_type_format,
            max_tool_iterations=max_tool_iterations,
        )

        self._model_client_streaming = model_client_streaming
        self.streaming_event = False
        self._response: cl.Message | None = None

    async def start(self, cancellation_token = None, output_task_messages = True):
        await super().start(cancellation_token, output_task_messages)

    async def handle_chat_message(self, message: BaseChatMessage) -> None:
        """Handle BaseChatMessage messages with Chainlit streaming"""
        if isinstance(message, TextMessage):                
            if not self._model_client_streaming:
                self._response = cl.Message(content="", author=message.source)
                await self._response.stream_token(message.content)
                await self._response.update()
            else:
                self.streaming_event = False
            await self._response.send()
    
    async def _dispatch_message(self, message):
        if not isinstance(message, ModelClientStreamingChunkEvent):
            self.streaming_event = False
            if self._response:
                await self._response.send()
        return await super()._dispatch_message(message)

    async def handle_agent_event(self, message: BaseAgentEvent) -> None:
        """Handle BaseAgentEvent messages"""
        pass
    
    async def handle_streaming_chunk(self, message: ModelClientStreamingChunkEvent) -> None:
        """Handle ModelClientStreamingChunkEvent messages with Chainlit streaming"""
        if not self.streaming_event:
            self.streaming_event = True
            self._response = cl.Message(author=message.source, content="")
        await self._response.stream_token(message.to_text())
    
    async def handle_response(self, message:Response):
        if not self._response:
            self._response=cl.Message(author=message.chat_message.source, content="")
        await self._response.send()

    async def handle_task_result(self, message: TaskResult) -> None:
        """Handle TaskResult messages"""
        await super().handle_task_result(message)
    
    async def handle_unknown_message(self, message) -> None:
        """Handle unknown message types"""
        await super().handle_unknown_message(message)
    
    async def task_finished(self, task_result: TaskResult) -> None:
        """Handle task completion - finalize streaming"""
        self.streaming_event = False
        if self._response:
            await self._response.send()
        # Call parent class task_finished
        await super().task_finished(task_result)


class UIAgentBuilder(AgentBuilderBase):
    """Builder for single agent mode with UI support following UIGroupChatBuilder pattern"""
    
    def __init__(self, 
                 data_layer: AgentFusionDataLayer, 
                 input_func: InputFuncType = None, 
                 model_client_streaming: bool = True):
        super().__init__(data_layer.db_layer)
        #self._data_layer = data_layer
        self._model_client_streaming = model_client_streaming
    
    def _agent_chat_map(self, agent_type_enum: AgentTypeEnum) -> Type[AgentType]:
        """Override agent chat map for UI-specific typed agents"""
        return {
            AgentTypeEnum.ASSISTANT_AGENT: UIAutoGenAgentChatQueue,
            AgentTypeEnum.USER_PROXY_AGENT: UIAutoGenAgentChatQueue,
            AgentTypeEnum.CODE_AGENT: UIAutoGenAgentChatQueue,
        }[agent_type_enum]
    
    @asynccontextmanager
    async def build_with_queue(self, agent_info: AgentConfigType):
        """Build an agent and wrap it in UIAutoGenAgentChatQueue"""
        async with self.build(agent_info) as agent:
            yield agent