"""
Agent type module.

This module contains typed wrapper classes for agent components and
the AgentType union type for runtime type checking and discrimination.
"""

from typing import Annotated
from typing_extensions import Literal
from pydantic import Field, computed_field
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent

from .agent import AgentType as AgentTypeEnum


class TypedAssistantAgent(AssistantAgent):
    """带有类型标识的 AssistantAgent
    
    Wrapper around AssistantAgent that adds a computed type field
    for Pydantic discrimination and type safety.
    """
    
    @computed_field
    @property
    def type(self) -> Literal[AgentTypeEnum.ASSISTANT_AGENT]:
        return AgentTypeEnum.ASSISTANT_AGENT


class TypedUserProxyAgent(UserProxyAgent):
    """带有类型标识的 UserProxyAgent
    
    Wrapper around UserProxyAgent that adds a computed type field
    for Pydantic discrimination and type safety.
    """
    
    @computed_field
    @property
    def type(self) -> Literal[AgentTypeEnum.USER_PROXY_AGENT]:
        return AgentTypeEnum.USER_PROXY_AGENT


# Union type for all agent types with discrimination
AgentType = Annotated[
    TypedAssistantAgent
    | TypedUserProxyAgent, 
    Field(discriminator="type")
]