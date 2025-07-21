from asyncio import Queue
from typing import Any, Awaitable, Callable, List, Tuple, cast, Optional, Type
from autogen_core.model_context import ChatCompletionContext
from autogen_agentchat.teams._group_chat._selector_group_chat import SelectorGroupChatManager
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.teams._group_chat._events import ( 
    GroupChatAgentResponse, 
    GroupChatMessage,
    GroupChatTermination
)
from dataclasses import dataclass
from autogen_core import MessageContext,  event
from chainlit import Message  # type: ignore [reportAttributeAccessIssue]
from autogen_agentchat.base import Response
import asyncio
from autogen_agentchat.base import ChatAgent, TerminationCondition
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.messages import BaseAgentEvent, BaseTextChatMessage, BaseChatMessage
from autogen_agentchat.teams._group_chat._chat_agent_container import ChatAgentContainer
from autogen_agentchat.teams._group_chat._selector_group_chat import SelectorFuncType, CandidateFuncType
from autogen_agentchat.messages import (
    MessageFactory, 
    TextMessage, 
    ModelClientStreamingChunkEvent, 
)
import chainlit as cl
from builders.group_chat_builder import GroupChatBuilder as GroupChatBuilderBase
from autogen_core.models import ChatCompletionClient
from autogen_core import SingleThreadedAgentRuntime
from builders.model_builder import ModelClientBuilder
from data_layer.data_layer import AgentFusionDataLayer
from data_layer.models.llm_model import LLMModel
from data_layer.models.prompt_model import PromptModel
from data_layer.models.agent_model import AgentModel

## ref from python\packages\autogen-core\src\autogen_core\_message_context.py

@dataclass
class MessageChunk:
    message_id: str
    text: str
    author: str
    finished: bool

    def __str__(self) -> str:
        return f"{self.author}({self.message_id}): {self.text}"

message_chunks: dict[str, Message] = {}  # type: ignore [reportUnknownVariableType]


class UISelectorGroupChatManager(SelectorGroupChatManager):

    def __init__(
        self,
        name: str,
        group_topic_type: str,
        output_topic_type: str,
        participant_topic_types: List[str],
        participant_names: List[str],
        participant_descriptions: List[str],
        output_message_queue: asyncio.Queue[BaseAgentEvent | BaseChatMessage | GroupChatTermination],
        termination_condition: TerminationCondition | None,
        max_turns: int | None,
        message_factory: MessageFactory,
        model_client: ChatCompletionClient,
        selector_prompt: str,
        allow_repeated_speaker: bool,
        selector_func: Optional[SelectorFuncType],
        max_selector_attempts: int,
        candidate_func: Optional[CandidateFuncType],
        emit_team_events: bool,
        model_context: ChatCompletionContext | None,
        model_client_streaming: bool = False,
    ) -> None:
        super().__init__(
            name,
            group_topic_type,
            output_topic_type,
            participant_topic_types,
            participant_names,
            participant_descriptions,
            output_message_queue,
            termination_condition,
            max_turns,
            message_factory,
            model_client,
            selector_prompt,
            allow_repeated_speaker,
            selector_func,
            max_selector_attempts,
            candidate_func,
            emit_team_events,
            model_context,
            model_client_streaming,
        )
        self.streaming_event = False
        self._participant_name_to_topic_type
        self._response : cl.Message | None = None

    #RECORD first parameter name must be message
    @event
    async def handle_group_chat_message(self, message: GroupChatMessage, ctx: MessageContext) -> None:
        """Handle a start event by sending the response to the user."""
        await super().handle_group_chat_message(message, ctx)
        inner_message : BaseAgentEvent | BaseTextChatMessage = message.message
        runtime : SingleThreadedAgentRuntime = self._runtime
        sender_agent: UISelectorGroupChatAgentChatContainer = await runtime._get_agent(ctx.sender)
        agent_name = sender_agent._agent.name
        if agent_name == "user":
            return
        if isinstance(inner_message, TextMessage):
            # Check if the message is from a user - if so, skip streaming
            # Only stream messages from AI agents, not from human users
            if self._model_client_streaming == False:
                self._response = cl.Message(content="")
                await self._response.stream_token(inner_message.content)
                await self._response.update()
            else:
                self.streaming_event = False
            await self._response.send()
        elif isinstance(inner_message, ModelClientStreamingChunkEvent):
            if self.streaming_event == False:
                self.streaming_event = True
                self._response = cl.Message(author=agent_name, content="")                
            await self._response.stream_token(inner_message.to_text())
        elif isinstance(inner_message, BaseAgentEvent):
            pass
    
    @event
    async def handle_agent_response(self, message: GroupChatAgentResponse, ctx: MessageContext) -> None:
        """Handle an agent response event by passing the messages in the buffer
        to the delegate agent and publish the response."""
        await super().handle_agent_response(message, ctx)
        #await self._response.send()


class UISelectorGroupChatAgentChatContainer(ChatAgentContainer):
    """A container for a graph flow agent chat."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    # @event
    # async def handle_request(self, message: GroupChatRequestPublish, ctx: MessageContext) -> None:
    #     """Handle a request event by passing the messages in the buffer
    #     to the delegate agent and publish the response."""
    #     await super().handle_request(message, ctx)

    @event
    async def handle_agent_response(self, message: GroupChatAgentResponse, ctx: MessageContext) -> None:
        """Handle a request event by passing the messages in the buffer
        to the delegate agent and publish the response."""
        await super().handle_agent_response(message, ctx)

class UISelectorGroupChat(SelectorGroupChat):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def _create_group_chat_manager_factory(
            self,
            name: str,
            group_topic_type: str,
            output_topic_type: str,
            participant_topic_types: List[str],
            participant_names: List[str],
            participant_descriptions: List[str],
            output_message_queue: asyncio.Queue[BaseAgentEvent | BaseChatMessage | GroupChatTermination],
            termination_condition: TerminationCondition | None,
            max_turns: int | None,
            message_factory: MessageFactory,
        ) -> Callable[[], SelectorGroupChatManager]:
        return lambda: UISelectorGroupChatManager(
            name,
            group_topic_type,
            output_topic_type,
            participant_topic_types,
            participant_names,
            participant_descriptions,
            output_message_queue,
            termination_condition,
            max_turns,
            message_factory,
            self._model_client,
            self._selector_prompt,
            self._allow_repeated_speaker,
            self._selector_func,
            self._max_selector_attempts,
            self._candidate_func,
            self._emit_team_events,
            self._model_context,
            self._model_client_streaming,
        )

    def _create_participant_factory(        
            self,
            parent_topic_type: str,
            output_topic_type: str,
            agent: ChatAgent,
            message_factory: MessageFactory
        ) -> Callable[[], ChatAgent]:
        return lambda: \
            UISelectorGroupChatAgentChatContainer(parent_topic_type, output_topic_type, agent, message_factory)

class UISelectorGroupChatBuilder(GroupChatBuilderBase):
    def __init__(self, 
                 data_layer: AgentFusionDataLayer,
                 input_func: Callable[[str], Awaitable[str]] | None = input, 
                 model_client_streaming: bool = True
        ):
        super().__init__(input_func)
        self._model_client_streaming = model_client_streaming
        self._data_layer = data_layer

    def prompt_builder(self) -> PromptModel:
        return PromptModel(self._data_layer) #type: ignore

    def model_client_builder(self) -> AgentModel:
        return AgentModel(self._data_layer)

    def _create_selector_group_chat(
        self, 
        participants: list[ChatAgent],
        selector_prompt: str,
        model_client: ChatCompletionClient,
        model_client_streaming: bool = False,
    ) -> Callable[[], SelectorGroupChat]:
        return lambda: UISelectorGroupChat(
            participants=participants,
            selector_prompt=selector_prompt,
            model_client=model_client,
            model_client_streaming=self._model_client_streaming
        )






