from typing import AsyncGenerator, List, Sequence, Optional, Union
import subprocess
import tempfile
import os
import re
import asyncio
import uuid

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, TextMessage, UserMessage
from autogen_agentchat.messages import ModelClientStreamingChunkEvent
from autogen_core import CancellationToken
from autogen_core.models import CreateResult, ChatCompletionClient, LLMMessage, SystemMessage
from autogen_core.model_context import ChatCompletionContext, UnboundedChatCompletionContext

from ..base.goupchat_queue import BaseChatQueue

HANDOFF_TOKEN = "<|handoff|>"

class CodeAgent(BaseChatQueue, BaseChatAgent):
    def __init__(
        self, 
        name: str, 
        model_client: ChatCompletionClient,
        model_context: ChatCompletionContext | None = None,
        system_message: str = "You are a helpful code execution assistant. You can execute Python code wrapped in <code> tags and provide results."
    ):
        BaseChatAgent.__init__(self, name, "A code execution agent that executes Python code and uses LLM for responses.")
        BaseChatQueue.__init__(self)
        self._model_client = model_client
        self._system_message = system_message
        
        if not model_context:
            model_context = UnboundedChatCompletionContext([SystemMessage(content=self._system_message, source="system")])
        self._model_context: ChatCompletionContext = model_context
        
        self._is_running = False

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def update_context(self, new_messages: List[LLMMessage] = None) -> None:
        """Update context with history messages, ensuring system message is at the front"""        
        # Add history messages if provided
        if new_messages:
            for msg in new_messages:
                await self._model_context.add_message(msg)

    async def push(self, messages: Union[str, List[LLMMessage]]) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None]:
        """Push interface to accept new messages with context caching"""
        output_messages: List[BaseAgentEvent | BaseChatMessage] = []
        stop_reason: str | None = None
        
        try:
            # Handle both string and List[LLMMessage] input
            if isinstance(messages, str):
                # Convert string to LLMMessage
                user_message = TextMessage(content=messages, source="user")
                messages_to_process = [user_message]
            else:
                messages_to_process = messages
            
            # Update context with new messages
            await self.update_context(messages_to_process)
            
            # Process through on_messages_stream
            async for result in self.on_messages_stream(messages_to_process, CancellationToken()):
                # Dispatch the event to appropriate handler
                await self._dispatch_message(result)
                yield result
                
                # Add to output messages (skip streaming chunks)
                if not isinstance(result, ModelClientStreamingChunkEvent):
                    output_messages.append(result)
                
                # Check if this is a TaskResult (final result)
                if isinstance(result, TaskResult):
                    await self.task_finished(result)
                    break
                    
        except Exception as e:
            # Handle any errors during message processing
            raise RuntimeError(f"Error processing message in CodeAgent: {str(e)}") from e

    async def _dispatch_message(self, message: BaseAgentEvent | BaseChatMessage | TaskResult | Response) -> None:
        """Dispatch message to appropriate handler based on type"""
        if isinstance(message, TaskResult):
            await self.handle_task_result(message)
        elif isinstance(message, Response):
            await self.handle_response(message)
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
    
    async def handle_unknown_message(self, message) -> None:
        """Handle unknown message types"""
        pass

    async def task_finished(self, task_result: TaskResult) -> None:
        """Handle task completion"""
        self._is_running = False

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """Stream-based message processing with LLM integration"""
        message_id = str(uuid.uuid4())
        
        # Add new messages to context
        for message in messages:
            await self._model_context.add_message(message)
        
        # Call LLM and monitor for code blocks in streaming output
        async for chunk in self._call_llm_with_code_monitoring(cancellation_token, message_id):
            yield chunk

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
        llm_messages = self._get_compatible_context(self._model_client, all_messages)
        
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

    @staticmethod
    def _get_compatible_context(model_client: ChatCompletionClient, messages: List[BaseChatMessage]) -> Sequence[BaseChatMessage]:
        """Get compatible context - simplified without vision handling"""
        return messages

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
    
    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        self._code_buffer = ""
        self._in_code_block = False


