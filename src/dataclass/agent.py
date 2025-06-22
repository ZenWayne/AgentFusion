from pydantic import BaseModel, Field
from autogen_ext.tools.mcp import McpServerParams
from .model_info import model_client as model_client_label
from enum import Enum
from typing import Annotated, Union
from typing_extensions import Literal

class InputFuncType(str, Enum):
    INPUT = "input"
    WRAPPED_INPUT = "wrapped_input"

class AgentType(str, Enum):
    ASSISTANT_AGENT = "assistant_agent"
    USER_PROXY_AGENT = "user_proxy_agent"

class BaseAgentConfig(BaseModel):
    name: str
    description: str
    labels: list[str]

class UserProxyAgentConfig(BaseAgentConfig):
    type : Literal[AgentType.USER_PROXY_AGENT]
    input_func: str

class AssistantAgentConfig(BaseAgentConfig):
    type: Literal[AgentType.ASSISTANT_AGENT]
    prompt: str
    model_client: model_client_label
    mcp_tools: list[McpServerParams] | None = None

ComponentInfo = Annotated[AssistantAgentConfig|UserProxyAgentConfig, Field(discriminator="type")]


