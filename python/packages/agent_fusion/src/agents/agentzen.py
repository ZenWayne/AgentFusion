from typing import AsyncGenerator, List, Sequence
import subprocess
import tempfile
import os
import re
import asyncio

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage, TextMessage
from autogen_core import CancellationToken


class CodeExecutionAgent(BaseChatAgent):
    def __init__(self, name: str):
        super().__init__(name, "A code execution agent that executes Python code wrapped in <code> tags.")
        self._code_buffer = ""
        self._in_code_block = False

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def on_messages(self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken) -> Response:
        # Process messages for code execution
        inner_messages: List[BaseAgentEvent | BaseChatMessage] = []
        
        # Extract and combine all message content
        full_content = ""
        for message in messages:
            if hasattr(message, 'content'):
                full_content += str(message.content)
        
        #CR 和下面的方法有重复逻辑，整理下
        # Extract and execute code blocks
        code_blocks = self._extract_code_blocks(full_content)
        
        if code_blocks:
            for i, code_block in enumerate(code_blocks):
                # Execute each code block
                result = await self._execute_python_code(code_block)
                
                # Create response message with execution results
                result_content = f"Code Block {i+1} Execution:\n"
                result_content += f"Code:\n```python\n{code_block}\n```\n\n"
                result_content += f"Stdout:\n{result['stdout']}\n\n"
                result_content += f"Stderr:\n{result['stderr']}\n\n"
                result_content += f"Return Code: {result['returncode']}\n"
                
                msg = TextMessage(content=result_content, source=self.name)
                inner_messages.append(msg)
        
        # Create final response
        if code_blocks:
            final_content = f"Successfully executed {len(code_blocks)} code block(s)."
        else:
            final_content = "No code blocks found in the message."
            no_code_msg = TextMessage(content="No code blocks found in the message.", source=self.name)
            inner_messages.append(no_code_msg)
        
        return Response(
            chat_message=TextMessage(content=final_content, source=self.name), 
            inner_messages=inner_messages
        )

    async def on_messages_stream(
        self, messages: Sequence[BaseChatMessage], cancellation_token: CancellationToken
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        inner_messages: List[BaseAgentEvent | BaseChatMessage] = []
        
        # Process all messages to extract and execute code
        full_content = ""
        for message in messages:
            if hasattr(message, 'content'):
                full_content += str(message.content)
        
             async for chunk in model_client.create_stream(
                llm_messages,
                tools=tools,
                json_output=output_content_type,
                cancellation_token=cancellation_token,
            ):
                if isinstance(chunk, CreateResult):
                    model_result = chunk
                elif isinstance(chunk, str):
                    yield ModelClientStreamingChunkEvent(content=chunk, source=agent_name, full_message_id=message_id)
                else:
                    raise RuntimeError(f"Invalid chunk type: {type(chunk)}")
        # Extract code blocks from the full content
        code_blocks = self._extract_code_blocks(full_content)
        
        if code_blocks:
            for i, code_block in enumerate(code_blocks):
                # Execute each code block
                result = await self._execute_python_code(code_block)
                
                # Create response message with execution results
                result_content = f"Code Block {i+1} Execution:\n"
                #result_content += f"Code:\n```python\n{code_block}\n```\n\n"
                result_content += f"Stdout:\n{result['stdout']}\n\n"
                result_content += f"Stderr:\n{result['stderr']}\n\n"
                result_content += f"Return Code: {result['returncode']}\n"
                
                msg = TextMessage(content=result_content, source=self.name)
                inner_messages.append(msg)
                yield msg
        else:
            # No code blocks found
            msg = TextMessage(content="No code blocks found in the message.", source=self.name)
            inner_messages.append(msg)
            yield msg
        
        # Return final response
        final_message = "Code execution completed." if code_blocks else "No code to execute."
        yield Response(chat_message=TextMessage(content=final_message, source=self.name), inner_messages=inner_messages)

    def _extract_code_blocks(self, content: str) -> List[str]:
        """
        Extract Python code blocks wrapped in <code> ... </code> tags
        """
        code_blocks = []
        pattern = r'<code>(.*?)</code>'
        matches = re.findall(pattern, content, re.DOTALL)
        
        for match in matches:
            # Clean up the code block
            code = match.strip()
            if code:
                code_blocks.append(code)
        
        return code_blocks
    
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


async def run_code_agent() -> None:
    # Create a code execution agent.
    code_agent = CodeExecutionAgent("code_executor")
    
    # Example message with code to execute
    test_message = TextMessage(
        content="Please execute this code: <code>print('Hello, World!')\nresult = 2 + 2\nprint(f'2 + 2 = {result}')</code>",
        source="user"
    )

    # Run the agent with the test message and stream the response.
    async for message in code_agent.on_messages_stream([test_message], CancellationToken()):
        if isinstance(message, Response):
            print(f"Final Response: {message.chat_message.content}")
        else:
            print(f"Stream Message: {message.content}")

if __name__ == "__main__":
    asyncio.run(run_code_agent())