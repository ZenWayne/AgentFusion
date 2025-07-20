from pydantic import BaseModel, Field
from typing import Annotated
from typing_extensions import Literal
from enum import Enum
from .model_info import model_client as model_client_label

class GroupChatType(str, Enum):
    SELECTOR_GROUP_CHAT = "selector_group_chat"

class BaseGroupChatConfig(BaseModel):
    name: str
    description: str
    labels: list[str]

class SelectorGroupChatConfig(BaseGroupChatConfig):
    type: Literal[GroupChatType.SELECTOR_GROUP_CHAT]
    selector_prompt: str
    participants: list[str]
    model_client: model_client_label

# ComponentInfo moved to schemas.component for unified component interface
