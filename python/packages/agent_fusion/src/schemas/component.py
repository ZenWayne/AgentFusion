from pydantic import BaseModel, Field, computed_field
from typing import Annotated, Union
from typing_extensions import Literal
from autogen_agentchat.teams import SelectorGroupChat, RoundRobinGroupChat

# Import ComponentType from types to avoid circular imports
from .types import ComponentType

# Import specific component configs
from .agent import AssistantAgentConfig, UserProxyAgentConfig
from .group_chat import SelectorGroupChatConfig, RoundRobinGroupChatConfig, GroupChatType as GroupChatTypeEnum
from .model_info import ModelClientConfig

class Component(BaseModel):
    type: ComponentType
    name: str


# 轻量级包装器类，为原始 GroupChat 类添加 type 字段
class TypedSelectorGroupChat(SelectorGroupChat):
    """带有类型标识的 SelectorGroupChat"""
    
    @computed_field
    @property
    def type(self) -> Literal[GroupChatTypeEnum.SELECTOR_GROUP_CHAT]:
        return GroupChatTypeEnum.SELECTOR_GROUP_CHAT


class TypedRoundRobinGroupChat(RoundRobinGroupChat):
    """带有类型标识的 RoundRobinGroupChat"""
    
    @computed_field
    @property
    def type(self) -> Literal[GroupChatTypeEnum.ROUND_ROBIN_GROUP_CHAT]:
        return GroupChatTypeEnum.ROUND_ROBIN_GROUP_CHAT


# 使用带类型的包装器类
GroupChatType = Annotated[
    TypedSelectorGroupChat 
    | TypedRoundRobinGroupChat, 
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