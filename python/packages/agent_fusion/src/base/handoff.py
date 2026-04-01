import asyncio
import os
from typing import Annotated

from autogen_agentchat.base import Handoff
from autogen_core.tools import BaseTool, FunctionTool
from pydantic import BaseModel
from enum import StrEnum
from autogen_core.tools._base import ToolSchema


class ToolType(StrEnum):
    HANDOFF_TOOL = "handoff_tool"
    HANDOFF_TOOL_CODE = "handoff_tool_code"
    NORMAL_TOOL = "normal_tool"


class TypedToolSchema(ToolSchema):
    type: ToolType

class HandoffTypedToolSchema(TypedToolSchema):
    target_agent: str

class FunctionToolWithType(FunctionTool):
    type: ToolType
    def __init__(self, *args, **kwargs):
        _type = kwargs.get("type")
        _type=kwargs.pop("type")
        super().__init__(*args, **kwargs)
        self.type = ToolType.HANDOFF_TOOL if _type is None else _type       
    
    @property
    def schema(self) -> TypedToolSchema:
        base_ret = super().schema

        return TypedToolSchema(
            name=base_ret["name"],
            description=base_ret["description"],
            parameters=base_ret["parameters"],
            strict=base_ret["strict"],
            type=self.type
        )

async def _bash_exec(
    command: Annotated[str, "The bash command to execute"],
    timeout: Annotated[int, "Timeout in seconds (0 means no timeout)"] = 30,
    cwd: Annotated[str, "Working directory for the command (empty string means current directory)"] = "",
    env_vars: Annotated[str, "Extra environment variables as KEY=VALUE pairs separated by newlines"] = "",
) -> str:
    """Execute a bash command and return combined stdout/stderr with exit code."""
    env = os.environ.copy()
    if env_vars:
        for line in env_vars.splitlines():
            line = line.strip()
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd if cwd else None,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(),
            timeout=timeout if timeout > 0 else None,
        )
    except asyncio.TimeoutError:
        proc.kill()
        await proc.communicate()
        return f"[error] Command timed out after {timeout}s"

    output_parts: list[str] = []
    if stdout:
        output_parts.append(stdout.decode(errors="replace"))
    if stderr:
        output_parts.append(f"[stderr]\n{stderr.decode(errors='replace')}")
    output_parts.append(f"[exit code: {proc.returncode}]")
    return "\n".join(output_parts)


class BashFunctionTool(FunctionToolWithType):
    """A FunctionToolWithType that executes arbitrary bash commands."""

    def __init__(self, **kwargs: object) -> None:
        kwargs.setdefault("type", ToolType.NORMAL_TOOL)
        kwargs.setdefault("name", "bash")
        kwargs.setdefault("description", "Execute a bash command and return its output (stdout + stderr + exit code).")
        kwargs.setdefault("strict", False)
        super().__init__(_bash_exec, **kwargs)


class HandoffFunctionToolWithType(FunctionToolWithType):
    def __init__(self, *args, **kwargs):
        self.target = kwargs.pop("target", "next_agent")
        super().__init__(*args, **kwargs)

    @property
    def schema(self) -> TypedToolSchema:
        base_ret = super().schema

        return HandoffTypedToolSchema(
            name=base_ret["name"],
            description=base_ret["description"],
            parameters=base_ret["parameters"],
            strict=base_ret["strict"],
            type=self.type,
            target=self.target
        )