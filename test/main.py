from .utils import run_test_case
from model_client.utils import create_model_clients
from os.path import join
from . import utils as test_utils
from agent.agent_builder import load_info as load_agent_info
from group_chat.group_chat_builder import load_info as load_group_chat_info
from graph_flow.graph_flow_builder import load_info as load_graph_flow_info
from agent.mcp_builder import load_info as load_mcp_info
from aglogger import enable_logger, FilterType
from base import utils
from opentelemetry import trace
import os

def init():
    test_utils.load_config(join(os.getcwd(), "test_case.json"))
    utils.prompt_path = utils.parse_cwd_placeholders(test_utils.test_config.prompt_config)
    create_model_clients(dotenv_path=test_utils.test_config.model_client_config)
    load_mcp_info(join(os.getcwd(), "config", "mcp.json"))
    load_agent_info(join(os.getcwd(), "config", "metadata.json"))
    load_group_chat_info(join(os.getcwd(), "config", "metadata.json"))
    load_graph_flow_info(join(os.getcwd(), "config", "metadata.json"))
 #??? wtf !??

async def main():
    init()
    #enable_logger(["autogen_core.events"], filter_types=[FilterType.ToolCall, FilterType.LLMCall])
    #tracer = trace.get_tracer("autogen_demo")
    #with tracer.start_as_current_span("runtime"):
    for case in test_utils.test_config.cases_for_test:
        await run_test_case(test_utils.test_config.cases[case])

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())
    #python -m test.main