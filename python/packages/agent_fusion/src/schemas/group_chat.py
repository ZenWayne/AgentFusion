from pydantic import BaseModel, Field
from typing import Annotated
from typing_extensions import Literal
from enum import Enum
from .model_info import model_client as model_client_label
from autogen_agentchat.base import Handoff

class GroupChatType(str, Enum):
    SELECTOR_GROUP_CHAT = "selector_group_chat"
    ROUND_ROBIN_GROUP_CHAT = "round_robin_group_chat"

class BaseGroupChatConfig(BaseModel):
    name: str
    description: str
    labels: list[str]

class SelectorGroupChatConfig(BaseGroupChatConfig):
    type: Literal[GroupChatType.SELECTOR_GROUP_CHAT]
    selector_prompt: str
    participants: list[str]
    model_client: model_client_label


class RoundRobinGroupChatConfig(BaseGroupChatConfig):
    type: Literal[GroupChatType.ROUND_ROBIN_GROUP_CHAT]
    participants: list[str]
    handoff_target: str = "user"


GroupChatConfig = Annotated[
    SelectorGroupChatConfig 
    | RoundRobinGroupChatConfig, Field(discriminator="type")]

# ComponentInfo moved to schemas.component for unified component interface
