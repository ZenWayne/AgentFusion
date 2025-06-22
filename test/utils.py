from .dataclass import TestConfiguration
import json
from autogen_agentchat.ui import Console
from agent import AgentBuilder
from autogen_core import CancellationToken
from .dataclass import AnyTestCase, ComponentType
from group_chat.group_chat_builder import GroupChatBuilder
from graph_flow.graph_flow_builder import GraphFlowBuilder
from base.utils import get_prompt
import re

test_config: TestConfiguration| None = None

def extract_brace_contents(text: str) -> list[str]:
    return re.findall(r"(?<!\\)\${([^}]*)}", text)

async def run_test_case(test_case :AnyTestCase):
    agent_name = test_case.component.name
    task = test_case.task
    contents = extract_brace_contents(task)
    for content in contents:
        prompt = get_prompt(content)
        task = task.replace(f"${{{content}}}", prompt)

    if test_case.component.type == ComponentType.AGENT:
        async with AgentBuilder(agent_name) as component:
            await Console(
                component.run_stream(
                    task=task,
                    cancellation_token=CancellationToken()
                )
            )
    elif test_case.component.type == ComponentType.GROUP_CHAT:
        async with GroupChatBuilder(agent_name) as component:
            await Console(
                component.run_stream(
                    task=task,
                    cancellation_token=CancellationToken()
                )
            )
    elif test_case.component.type == ComponentType.GRAPH_FLOW:
        async with GraphFlowBuilder(agent_name) as component:
            await Console(
                component.run_stream(
                    task=task,
                    cancellation_token=CancellationToken()
                )
            )


def load_config(path)->TestConfiguration:
    global test_config
    with open(path, 'r') as f:        
        test_config = TestConfiguration(**json.load(f))
    return test_config

