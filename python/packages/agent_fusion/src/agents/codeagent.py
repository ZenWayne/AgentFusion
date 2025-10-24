from typing import AsyncGenerator, List, Sequence, Optional, Union, Tuple
import subprocess
import tempfile
import os
import re
import asyncio
import uuid

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.messages import (
    BaseAgentEvent, 
    BaseChatMessage, 
    TextMessage, 
    ToolCallRequestEvent, 
    ToolCallExecutionEvent, 
    HandoffMessage, 
    StructuredMessage,
    ToolCallSummaryMessage
)
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    CreateResult,
    FunctionExecutionResult,
    FunctionExecutionResultMessage
)
from autogen_agentchat.messages import ModelClientStreamingChunkEvent, ThoughtEvent
from autogen_core import CancellationToken
from autogen_core.tools import Workbench, Tool, ToolSchema
from autogen_core.models import CreateResult, ChatCompletionClient, LLMMessage, SystemMessage, UserMessage
from autogen_core import FunctionCall
from autogen_core.model_context import ChatCompletionContext, UnboundedChatCompletionContext
from autogen_agentchat.utils import remove_images
from pydantic import BaseModel
from tools.workbench import VectorStreamWorkbench

from base.groupchat_queue import BaseChatQueue
from autogen_agentchat import EVENT_LOGGER_NAME, TRACE_LOGGER_NAME
import logging
import json
from typing import Any
import warnings
from autogen_core.tools import ToolResult, StaticStreamWorkbench
from base.handoff import ToolType
from contextlib import asynccontextmanager


event_logger = logging.getLogger(EVENT_LOGGER_NAME)
logger = logging.getLogger(TRACE_LOGGER_NAME)

HANDOFF_TOKEN = "<|handoff|>"

class CodeAgent(BaseChatQueue, BaseChatAgent):
    def __init__(
        self, 
        name: str, 
        model_client: ChatCompletionClient,
        model_context: ChatCompletionContext | None = None,
        workbench: Sequence[Workbench] | None = None,
        system_message: str = "You are a helpful code execution assistant. You can execute Python code wrapped in <code> tags and provide results.",
        output_content_type: Optional[bool | type[BaseModel]] = None,
        output_content_type_format: Optional[str] = None,
        max_tool_iterations: int = 1,
    ):
        BaseChatAgent.__init__(self, name, "A code execution agent that executes Python code and uses LLM for responses.")
        BaseChatQueue.__init__(self)
        self._model_client = model_client
        self._system_message = system_message
        if workbench:
            assert isinstance(workbench, list), "workbench must be a list of Workbench"
        self._workbench = workbench
        if not model_context:
            model_context = UnboundedChatCompletionContext([SystemMessage(content=self._system_message, source="system")])
        self._model_context: ChatCompletionContext = model_context
        self._output_content_type = output_content_type
        self._output_content_type_format = output_content_type_format
        self._max_tool_iterations = max_tool_iterations
        self._is_running = False
        self._cancellation_token: CancellationToken |None = None
        self._reflect_on_tool_use = False
        self._handoff_tool_name : dict[str,str] | None = None

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        """Get the types of messages this agent can produce.

        Returns:
            Sequence of message types this agent can generate
        """
        types: List[type[BaseChatMessage]] = [TextMessage, ToolCallSummaryMessage, HandoffMessage]
        # if self._structured_message_factory is not None:
        #     types.append(StructuredMessage)
        return types

    async def start(self, cancellation_token: CancellationToken | None = None, output_task_messages: bool = True):
        """Start the agent chat session"""
        if self._is_running:
            raise ValueError("The agent chat is already running.")
        
        if cancellation_token is not None:
            self._cancellation_token = cancellation_token
            
        self._is_running = True

    async def update_context(self, new_messages: List[LLMMessage] = None) -> None:
        """Update context with history messages, ensuring system message is at the front"""        
        # Add history messages if provided
        if new_messages:
            for msg in new_messages:
                await self._model_context.add_message(msg)

    async def push(self, messages: Union[str, List[LLMMessage]]) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None]:
        """Push interface to accept new messages with context caching"""        
        try:
            # Handle both string and List[LLMMessage] input
            if isinstance(messages, str):
                # Convert string to LLMMessage
                user_message = TextMessage(content=messages, source="user")
                messages_to_process = [user_message]
            else:
                messages_to_process = messages
            
            # Process through on_messages_stream
            async for result in self.on_messages_stream(messages_to_process, self._cancellation_token):
                # Dispatch the event to appropriate handler
                await self._dispatch_message(result)
                    
        except Exception as e:
            # Handle any errors during message processing
            raise RuntimeError(f"Error processing message in CodeAgent: {str(e)}") from e

    async def _dispatch_message(self, message: BaseAgentEvent | BaseChatMessage | TaskResult | Response) -> None:
        """Dispatch message to appropriate handler based on type"""
        if isinstance(message, TaskResult):
            await self.handle_task_result(message)
        elif isinstance(message, Response):
            await self.handle_response(message)
        elif isinstance(message, ModelClientStreamingChunkEvent):
            await self.handle_streaming_chunk(message)
        elif isinstance(message, BaseAgentEvent):
            await self.handle_agent_event(message)
        elif isinstance(message, BaseChatMessage):
            await self.handle_chat_message(message)
        else:
            await self.handle_unknown_message(message)
    
    async def handle_task_result(self, message: TaskResult) -> None:
        """Handle TaskResult messages"""
        pass
    
    async def handle_response(self, message: Response) -> None:
        """Handle Response messages"""
        pass
    
    async def handle_agent_event(self, message: BaseAgentEvent) -> None:
        """Handle BaseAgentEvent messages"""
        pass
    
    async def handle_chat_message(self, message: BaseChatMessage) -> None:
        """Handle BaseChatMessage messages"""
        pass
    
    async def handle_streaming_chunk(self, message: ModelClientStreamingChunkEvent) -> None:
        """Handle ModelClientStreamingChunkEvent messages"""
        pass
    
    async def handle_unknown_message(self, message) -> None:
        """Handle unknown message types"""
        pass

    async def task_finished(self, task_result: TaskResult) -> None:
        """Handle task completion"""
        self._is_running = False

    async def _get_tools_from_workbench(self, messages: list[LLMMessage]):
        """Get tools from workbench"""
        tools = []
        text_messages = [msg for msg in messages if (isinstance(msg, SystemMessage) or isinstance(msg, UserMessage))]
        for wb in self._workbench:
            if isinstance(wb, VectorStreamWorkbench):
                tools.extend(wb.get_tools_for_context(text_messages))
            else:
                tools.extend(await wb.list_tools())
        return tools

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """Stream-based message processing with LLM integration"""
        message_id = str(uuid.uuid4())
        
        # Add new messages to context
        for message in messages:
            await self._model_context.add_message(message.to_model_message())
        
        # Call LLM
        llm_messages = await self._get_compatible_context(self._model_client, self._model_context)

        #TODO get tools based on context
        tools =await self._get_tools_from_workbench(llm_messages)

        if not self._handoff_tool_name:
            self._handoff_tool_name = { 
                tool["name"]: tool["target"] for wb in self._workbench 
                for tool in await wb.list_tools() 
                if tool.get("type", None) == ToolType.HANDOFF_TOOL }

        async for create_result_or_stream_event in self._call_llm(message_id, llm_messages, tools, cancellation_token):
            if isinstance(create_result_or_stream_event, CreateResult):
                model_result = create_result_or_stream_event
            elif isinstance(create_result_or_stream_event, ModelClientStreamingChunkEvent):
                yield create_result_or_stream_event
            else:
                pass

        assert model_result is not None, "No model result was produced."

        # --- NEW: If the model produced a hidden "thought," yield it as an event ---
        if model_result.thought:
            thought_event = ThoughtEvent(content=model_result.thought, source=self.name)
            yield thought_event

        # Add the assistant message to the model context (including thought if present)
        await self._model_context.add_message(
            AssistantMessage(
                content=model_result.content,
                source=self.name,
                thought=getattr(model_result, "thought", None),
            )
        )

        for loop_iteration in range(1,self._max_tool_iterations):            
            assert create_result_or_stream_event is not None, "No model result was produced."
            
            #when it finally output str it means this is the final response
            if isinstance(model_result.content, str):
                yield self._output_llm_response(model_result, message_id)
            else:
            
                #otherwise it means it's a tool call
                # assert isinstance(model_result.content, list) and all(
                #     isinstance(item, FunctionCall) for item in model_result.content
                # )
                tool_call_msg = ToolCallRequestEvent(
                    content=model_result.content,
                    source=self.name,
                    models_usage=model_result.usage,
                )
                event_logger.debug(tool_call_msg)
                yield tool_call_msg

                stream = asyncio.Queue[BaseAgentEvent | BaseChatMessage | None]()

                task = asyncio.create_task(self._execute_tool_calls(model_result.content, stream))
                while True:
                    event = await stream.get()
                    if event is None:
                        # End of streaming, break the loop.
                        break
                    if isinstance(event, BaseAgentEvent) or isinstance(event, BaseChatMessage):
                        yield event
                
                executed_calls_and_results = await task
                exec_results = [result for _, result in executed_calls_and_results]
                tool_call_result_msg = ToolCallExecutionEvent(
                    content=exec_results,
                    source=self.name,
                )
                event_logger.debug(tool_call_result_msg)
                await self._model_context.add_message(FunctionExecutionResultMessage(content=exec_results))
                yield tool_call_result_msg

                handoff_output = self._check_and_handle_handoff(
                    model_result=model_result,
                    executed_calls_and_results=executed_calls_and_results,
                    agent_name=self.name,
                )
                if handoff_output:
                    yield handoff_output
                    return
            
            llm_messages = await self._get_compatible_context(self._model_client, self._model_context)
            tools =await self._get_tools_from_workbench(llm_messages)
            async for create_result_or_stream_event in self._call_llm(message_id, llm_messages, tools, cancellation_token):
                if isinstance(create_result_or_stream_event, CreateResult):
                    model_result = create_result_or_stream_event
                elif isinstance(create_result_or_stream_event, ModelClientStreamingChunkEvent):
                    yield create_result_or_stream_event
                else:
                    pass
            
            # --- NEW: If the model produced a hidden "thought," yield it as an event ---
            if model_result.thought:
                thought_event = ThoughtEvent(content=model_result.thought, source=self.name)
                yield thought_event

            #TODO yield thought event
            await self._model_context.add_message(
                AssistantMessage(
                    content=model_result.content,
                    source=self.name,
                    thought=getattr(model_result, "thought", None),
                )
            )
        # If we exit the loop without returning, provide final response
        yield self._output_llm_response(model_result, message_id)

    def _check_and_handle_handoff(
        self,
        model_result: CreateResult,
        executed_calls_and_results: List[Tuple[FunctionCall, FunctionExecutionResult]],
        agent_name: str,
    ) -> Optional[Response]:
        """Check for and handle any handoff requests in the model result."""
        if len(self._workbench) == 0 or not isinstance(model_result.content, list):
            return None

        # Simplified handoff detection - just check if there are any handoff tool calls
        handoff_reqs = [
            call for call in model_result.content if (
            isinstance(call, FunctionCall) 
            and call.name in self._handoff_tool_name.keys()
            )
        ]
        if len(handoff_reqs) > 0:
            # We have at least one handoff function call
            selected_handoff = handoff_reqs[0]
            
            if len(handoff_reqs) > 1:
                logger.warning(f"Multiple handoffs detected. Only the first is executed.", stacklevel=2)
            
            # Find the corresponding execution result
            selected_handoff_message = "Handoff requested"
            target = "next_agent"
            for exec_call, exec_result in executed_calls_and_results:
                if exec_call.name == selected_handoff.name:
                    selected_handoff_message = exec_result.content
                    target = self._handoff_tool_name[exec_call.name]
                    break
            
            # Create handoff context
            handoff_context: List[LLMMessage] = []
            if hasattr(model_result, 'thought') and model_result.thought:
                handoff_context.append(
                    AssistantMessage(
                        content=model_result.thought,
                        source=agent_name,
                    )
                )

            # Return handoff response
            return Response(
                chat_message=HandoffMessage(
                    content=selected_handoff_message,
                    target=target,  # Default target
                    source=agent_name,
                    context=handoff_context,
                ),
            )
        
        return None
    async def _execute_tool_calls(
        self,
        function_calls: List[FunctionCall],
        stream: asyncio.Queue[BaseAgentEvent | BaseChatMessage | None],
    ) -> List[Tuple[FunctionCall, FunctionExecutionResult]]:
        """Execute tool calls and return results"""
        results = []
        for call in function_calls:
            result = await self._execute_tool_call(
                tool_call=call,
                workbench=self._workbench,
                cancellation_token=self._cancellation_token,
                stream=stream,
            )
            results.append(result)
        
        # Signal the end of streaming by putting None in the queue.
        await stream.put(None)
        return results

    async def _execute_tool_call(
        self,
        tool_call: FunctionCall,
        workbench: Sequence[Workbench],
        cancellation_token: CancellationToken,
        stream: asyncio.Queue[BaseAgentEvent | BaseChatMessage | None],
    ) -> Tuple[FunctionCall, FunctionExecutionResult]:
        """Execute tool calls and return results"""
        try:
            arguments = json.loads(tool_call.arguments)
        except json.JSONDecodeError as e:
            return (
                tool_call,
                FunctionExecutionResult(
                    content=f"Error: {e}",
                    call_id=tool_call.id,
                    is_error=True,
                    name=tool_call.name,
                ),
            )
        
        for wb in workbench:
            tools = await wb.list_tools()
            if any(t["name"] == tool_call.name for t in tools):
                if isinstance(wb, StaticStreamWorkbench):
                    tool_result: ToolResult | None = None
                    async for event in wb.call_tool_stream(
                        name=tool_call.name,
                        arguments=arguments,
                        cancellation_token=cancellation_token,
                        call_id=tool_call.id,
                    ):
                        if isinstance(event, ToolResult):
                            tool_result = event
                        elif isinstance(event, BaseAgentEvent) or isinstance(event, BaseChatMessage):
                            await stream.put(event)
                        else:
                            logger.warning(
                                f"Unexpected event type: {type(event)} in tool call streaming.",
                                stacklevel=2,
                            )
                    assert isinstance(tool_result, ToolResult), "Tool result should not be None in streaming mode."
                else:
                    tool_result = await wb.call_tool(
                        name=tool_call.name,
                        arguments=arguments,
                        cancellation_token=cancellation_token,
                        call_id=tool_call.id,
                    )
                return (
                    tool_call,
                    FunctionExecutionResult(
                        content=tool_result.to_text(),
                        call_id=tool_call.id,
                        is_error=tool_result.is_error,
                        name=tool_call.name,
                    ),
                )

        return (
            tool_call,
            FunctionExecutionResult(
                content=f"Error: tool '{tool_call.name}' not found in any workbench",
                call_id=tool_call.id,
                is_error=True,
                name=tool_call.name,
            ),
        )

    def _output_llm_response(self, model_result: CreateResult, message_id: str) -> Response:
        if self._output_content_type:
            content = self._output_content_type.model_validate_json(model_result.content)
            return Response(
                chat_message=StructuredMessage[self._output_content_type](  # type: ignore[valid-type]
                    content=content,
                    source=self.name,
                    models_usage=model_result.usage,
                    full_message_id=message_id
                )
            )
        else:
            return Response(
                chat_message=TextMessage(content=model_result.content, source=self.name, full_message_id=message_id)
            )

    async def _call_llm(
        self,
        message_id: str,
        llm_messages: Sequence[LLMMessage],
        tools: Sequence[Tool | ToolSchema] = [],
        cancellation_token: CancellationToken = CancellationToken(),
    ) -> AsyncGenerator[Union[ModelClientStreamingChunkEvent, CreateResult], None]:
        """Call LLM and monitor streaming output for code blocks"""

        # Check if model client supports streaming
        if hasattr(self._model_client, 'create_stream'):
            async for chunk in self._model_client.create_stream(
                llm_messages,
                tools=tools,
                json_output=self._output_content_type,
                cancellation_token=cancellation_token,
            ):
                if isinstance(chunk, CreateResult):
                    model_result = chunk
                elif isinstance(chunk, str):
                    yield ModelClientStreamingChunkEvent(content=chunk, source=self.name, full_message_id=message_id)
                else:
                    raise RuntimeError(f"Invalid chunk type: {type(chunk)}")
        else:
            model_result = await self._model_client.create(
                llm_messages,
                tools=tools,
                json_output=self._output_content_type,
                cancellation_token=cancellation_token,
            )

        yield model_result


    async def _call_llm_with_code_monitoring(
        self, 
        cancellation_token: CancellationToken, 
        message_id: str
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """Call LLM and monitor streaming output for code blocks"""
        if not self._model_context:
            return
        
        # Get all messages from context
        all_messages = await self._model_context.get_messages()
        
        # Get compatible context (simplified, no vision handling needed)
        if self._model_client.model_info["vision"]:
            llm_messages = all_messages
        else:
            llm_messages = remove_images(all_messages)
        
        # Code monitoring state
        code_buffer = ""
        in_code_block = False
        full_response = ""
        
        try:
            # Stream LLM response
            async for chunk in self._model_client.create_stream(
                llm_messages, 
                tools=[],  # No tools needed as per CR
                cancellation_token=cancellation_token
            ):
                if isinstance(chunk, CreateResult):
                    # Final response - process any remaining code
                    if in_code_block and code_buffer.strip():
                        # Execute the final code block
                        execution_result = await self._execute_python_code(code_buffer)
                        tool_use_msg = TextMessage(
                            content=f"Code execution result:\n{self._format_single_execution_result(code_buffer, execution_result)}", 
                            source=self.name
                        )
                        yield tool_use_msg
                    
                    # Final response
                    response_content = chunk.content
                    response_msg = TextMessage(content=response_content, source=self.name)
                    await self._model_context.add_message(response_msg)
                    yield Response(chat_message=response_msg)
                    
                elif isinstance(chunk, str):
                    # Monitor streaming chunk for code blocks
                    full_response += chunk
                    
                    # Check for code block start/end
                    if not in_code_block and "<code>" in chunk:
                        in_code_block = True
                        # Find the start of code content after <code> tag
                        code_start_idx = chunk.find("<code>") + len("<code>")
                        code_buffer = chunk[code_start_idx:]
                    elif in_code_block:
                        if "</code>" in chunk:
                            # End of code block found
                            code_end_idx = chunk.find("</code>")
                            code_buffer += chunk[:code_end_idx]
                            
                            # Execute the complete code block
                            if code_buffer.strip():
                                execution_result = await self._execute_python_code(code_buffer)
                                tool_use_msg = TextMessage(
                                    content=f"Code execution result:\n{self._format_single_execution_result(code_buffer, execution_result)}", 
                                    source=self.name
                                )
                                yield tool_use_msg
                            
                            # Reset code monitoring state
                            in_code_block = False
                            code_buffer = ""
                        else:
                            # Continue buffering code content
                            code_buffer += chunk
                    
                    # Always yield the streaming chunk for real-time display
                    yield ModelClientStreamingChunkEvent(
                        content=chunk, 
                        source=self.name, 
                        full_message_id=message_id
                    )
                    
        except Exception as e:
            error_msg = TextMessage(content=f"LLM call failed: {str(e)}", source=self.name)
            yield Response(chat_message=error_msg)

    async def _get_compatible_context(self, model_client: ChatCompletionClient, model_context: ChatCompletionContext) -> Sequence[LLMMessage]:
        """Get compatible context - simplified without vision handling"""
        messages = await model_context.get_messages()
        if model_client.model_info["vision"]:
            return messages
        else:
            return remove_images(messages)

    def _format_single_execution_result(self, code: str, result: dict) -> str:
        """Format single code execution result"""
        formatted = f"Code:\n```python\n{code}\n```\n"
        formatted += f"Output: {result['stdout']}\n"
        if result['stderr']:
            formatted += f"Errors: {result['stderr']}\n"
        formatted += f"Return Code: {result['returncode']}\n"
        return formatted

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        """Non-streaming message processing"""
        result_messages = []
        async for chunk in self.on_messages_stream(messages, cancellation_token):
            if isinstance(chunk, Response):
                return chunk
            else:
                result_messages.append(chunk)
        
        # Fallback response if no Response was yielded
        final_content = "Processing completed."
        return Response(chat_message=TextMessage(content=final_content, source=self.name))

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """Reset agent state"""
        if self._model_context:
            await self._model_context.clear()
        self._is_running = False
    
    async def _execute_python_code(self, code: str) -> dict:
        """
        Execute Python code in a subprocess and capture stdout, stderr, and return code
        """
        try:
            # Create a temporary file with the Python code
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name
            
            # Execute the Python code using subprocess
            process = subprocess.Popen(
                ['python', temp_file_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=os.getcwd()
            )
            
            stdout, stderr = process.communicate()
            
            return {
                'stdout': stdout or '(no output)',
                'stderr': stderr or '(no errors)',
                'returncode': process.returncode
            }
        
        except Exception as e:
            return {
                'stdout': '',
                'stderr': f'Execution error: {str(e)}',
                'returncode': -1
            }
        finally:
            # Clean up the temporary file
            try:
                if 'temp_file_path' in locals():
                    os.unlink(temp_file_path)
            except OSError:
                pass
    


