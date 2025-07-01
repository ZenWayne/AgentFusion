from pydantic import BaseModel, Field, field_validator, model_validator
from mcp import StdioServerParameters
from .model_info import model_client as model_client_label
from enum import Enum
from typing import Annotated, Any, Callable
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
    prompt_path: str | None = None
    prompt: Callable[[], str] | None = None
    model_client: model_client_label
    mcp_tools: list[StdioServerParameters] | None = None

    @model_validator(mode='before')
    @classmethod
    def validate_prompt_config(cls, values: dict[str, Any]) -> dict[str, Any]:
        prompt = values.get('prompt')
        prompt_path = values.get('prompt_path')
        
        if prompt is None and prompt_path is None:
            raise ValueError("Agent must have either 'prompt' or 'prompt_path' specified")
        
        return values

ComponentInfo = Annotated[AssistantAgentConfig|UserProxyAgentConfig, Field(discriminator="type")]


