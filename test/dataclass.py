from pydantic import BaseModel
from enum import Enum
from typing import List, Union, Literal

class TestType(str, Enum):
    DUMP = "dump"
    RUN = "run"

class ComponentType(str, Enum):
    AGENT = "agent"
    GROUP_CHAT = "group_chat"
    GRAPH_FLOW = "graph_flow"

class Component(BaseModel):
    type: ComponentType
    name: str

class BaseTestCase(BaseModel):
    name: str


class RunTestCase(BaseTestCase):
    type: Literal[TestType.RUN]
    component: Component
    task: str

class DumpTestCase(BaseTestCase):
    type: Literal[TestType.DUMP]
    model_client: list[str]
    agents: list[str]
    group_chats: list[str]
    output_path: str

AnyTestCase = Union[RunTestCase, DumpTestCase]

class TestConfiguration(BaseModel):
    model_client_config: str
    cases_for_test: list[str]
    cases: dict[str, AnyTestCase]
