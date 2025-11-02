import logging
from typing import Literal

from autogen_agentchat.base import Handoff
from autogen_core.tools import BaseTool
from pydantic import BaseModel, Field

from base.handoff import ToolType, HandoffFunctionToolWithType

from contextlib import redirect_stdout, redirect_stderr
from io import StringIO

class HandoffCodeFunctionToolWithType(HandoffFunctionToolWithType):
    def __init__(self, tool_result, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._tool_results = tool_result

class HandoffCodeWithType(Handoff):
    """Handoff tool that executes Python code before transferring control."""

    handoff_type: Literal[ToolType.HANDOFF_TOOL_CODE] = Field(default=ToolType.HANDOFF_TOOL_CODE)

    def __init__(
        self,
        *args, 
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self._tool_results = []

    async def _execute_python_code(self, tool_results :list, code: str) -> dict:
        """
        Execute Python code in a subprocess and capture stdout, stderr, and return code.

        Args:
            code: The Python code to execute

        Returns:
            Dictionary containing stdout, stderr, and return code
        """
        try:
            # Create StringIO objects to capture output
            captured_stdout = StringIO()
            captured_stderr = StringIO()

            namespace = {'TOOL_RESULT': tool_results}
            # Redirect stdout and stderr using context managers
            with redirect_stdout(captured_stdout), redirect_stderr(captured_stderr):
                exec(code)

            # Retrieve the captured output
            stdout_output = captured_stdout.getvalue()
            stderr_output = captured_stderr.getvalue()            

            return {
                'stdout': stdout_output,
                'stderr': stderr_output,
            }

        except Exception as e:
            return {
                'stdout': stdout_output,
                'stderr': f'Execution error: {str(e)}',
            }
    @property
    def handoff_tool(self) -> BaseTool[BaseModel, BaseModel]:
        """Create a handoff tool from this handoff configuration."""

        async def handoff_to_python(code: str) -> str:
            """
            Execute Python code and return formatted output.

            Args:
                tool_result_dir: Directory for tool results
                session_id: Session identifier
                code: Python code to execute

            Returns:
                Formatted string with execution results and handoff message
            """
            if code:
                result = await self._execute_python_code(self._tool_results, code)
                if not result.get('stderr', ''):
                    output = result.get('stdout', '')
                else:
                    output = f"""
##STDOUT##
{result.get('stdout', '')}

##STDERR##
{result.get('stderr', '')}

##RETURN_CODE##
{result.get('returncode', 0)}
"""
                return output
            else:
                return f"## No code provided. {self.message} ##"

        return HandoffCodeFunctionToolWithType(
            self._tool_results,
            handoff_to_python,
            name=self.name,
            description=self.description,
            strict=True,
            type=ToolType.HANDOFF_TOOL_CODE,
            target=self.target
        )