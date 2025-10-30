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