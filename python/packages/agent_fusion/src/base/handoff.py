from autogen_agentchat.base import Handoff
from autogen_core.tools import BaseTool, FunctionTool
from pydantic import BaseModel
from enum import StrEnum
from autogen_core.tools._base import ToolSchema


class ToolType(StrEnum):
    HANDOFF_TOOL = "handoff_tool"
    NORMAL_TOOL = "normal_tool"


class ToolSchemaWithType(ToolSchema):
    type: ToolType


class FunctionToolWithType(FunctionTool):
    type: ToolType
    def __init__(self, *args, **kwargs):
        _type = kwargs.get("type")
        _type=kwargs.pop("type")
        super().__init__(*args, **kwargs)
        self.type = ToolType.HANDOFF_TOOL if _type is None else _type
    
    @property
    def schema(self) -> ToolSchemaWithType:
        base_ret = super().schema

        return ToolSchemaWithType(
            name=base_ret["name"],
            description=base_ret["description"],
            parameters=base_ret["parameters"],
            strict=base_ret["strict"],
            type=self.type
        )