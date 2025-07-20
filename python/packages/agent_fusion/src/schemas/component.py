from pydantic import BaseModel, Field
from typing import Annotated, Union
from typing_extensions import Literal

# Import ComponentType from types to avoid circular imports
from .types import ComponentType

# Import specific component configs
from .agent import AssistantAgentConfig, UserProxyAgentConfig
from .group_chat import SelectorGroupChatConfig
from .model_info import ModelClientConfig

class Component(BaseModel):
    type: ComponentType
    name: str

# Unified ComponentInfo that can handle both Agent and GroupChat components
ComponentInfo = Annotated[
    AssistantAgentConfig 
    | UserProxyAgentConfig 
    | SelectorGroupChatConfig
    | ModelClientConfig, 
    Field(discriminator="type")
]