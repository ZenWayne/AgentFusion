from pydantic import BaseModel
from enum import Enum

class ComponentType(str, Enum):
    AGENT = "agent"
    GROUP_CHAT = "group_chat"
    GRAPH_FLOW = "graph_flow"

class Component(BaseModel):
    type: ComponentType
    name: str