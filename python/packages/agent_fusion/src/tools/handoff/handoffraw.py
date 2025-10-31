from typing import Literal

from autogen_agentchat.base import Handoff
from autogen_core.tools import BaseTool
from pydantic import BaseModel, Field

from base.handoff import ToolType, HandoffFunctionToolWithType

class HandoffWithTypeRaw(Handoff):
    handoff_type : Literal[ToolType.HANDOFF_TOOL]
    @property
    def handoff_tool(self) -> BaseTool[BaseModel, BaseModel]:
        """Create a handoff tool from this handoff configuration."""
        def _handoff_tool() -> str:
            return self.message

        return HandoffFunctionToolWithType(
            _handoff_tool, 
            name=self.name,
            description=self.description, 
            strict=True,
            type=ToolType.HANDOFF_TOOL,
            target=self.target
        )
  