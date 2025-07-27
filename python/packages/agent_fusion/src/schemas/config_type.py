"""
Configuration type module.

This module contains union types for configuration objects with
runtime type checking and discrimination.
"""

from typing import Annotated
from pydantic import BaseModel, Field

from .types import ComponentType
from .agent import AssistantAgentConfig, UserProxyAgentConfig
from .group_chat import SelectorGroupChatConfig, RoundRobinGroupChatConfig
from .model_info import ModelClientConfig


class Component(BaseModel):
    """Base component class with type and name."""
    type: ComponentType
    name: str


# Union type for all agent configuration types with discrimination
AgentConfigType = Annotated[
    AssistantAgentConfig 
    | UserProxyAgentConfig, 
    Field(discriminator="type")
]

# Unified ComponentInfo that can handle both Agent and GroupChat components
ComponentInfo = Annotated[
    AssistantAgentConfig 
    | UserProxyAgentConfig 
    | SelectorGroupChatConfig
    | RoundRobinGroupChatConfig
    | ModelClientConfig, 
    Field(discriminator="type")
]