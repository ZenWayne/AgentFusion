"""
Group chat type module.

This module contains typed wrapper classes for group chat components and
the GroupChatType union type for runtime type checking and discrimination.
"""

from typing import Annotated
from typing_extensions import Literal
from pydantic import Field, computed_field
from autogen_agentchat.teams import SelectorGroupChat, RoundRobinGroupChat

from .group_chat import GroupChatType as GroupChatTypeEnum


class TypedSelectorGroupChat(SelectorGroupChat):
    """带有类型标识的 SelectorGroupChat
    
    Wrapper around SelectorGroupChat that adds a computed type field
    for Pydantic discrimination and type safety.
    """
    
    @computed_field
    @property
    def type(self) -> Literal[GroupChatTypeEnum.SELECTOR_GROUP_CHAT]:
        return GroupChatTypeEnum.SELECTOR_GROUP_CHAT


class TypedRoundRobinGroupChat(RoundRobinGroupChat):
    """带有类型标识的 RoundRobinGroupChat
    
    Wrapper around RoundRobinGroupChat that adds a computed type field
    for Pydantic discrimination and type safety.
    """
    
    @computed_field
    @property
    def type(self) -> Literal[GroupChatTypeEnum.ROUND_ROBIN_GROUP_CHAT]:
        return GroupChatTypeEnum.ROUND_ROBIN_GROUP_CHAT


# Union type for all group chat types with discrimination
GroupChatType = Annotated[
    TypedSelectorGroupChat 
    | TypedRoundRobinGroupChat, 
    Field(discriminator="type")
]