from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.teams import DiGraphBuilder, GraphFlow
from autogen_ext.models.openai import OpenAIChatCompletionClient
from typing import AsyncGenerator
from autogen_agentchat.teams import SelectorGroupChat
from contextlib import asynccontextmanager
from agent import AgentBuilder
from contextlib import asynccontextmanager, AsyncExitStack
import asyncio
import json
from dataclass.graph_flow import ComponentInfo, GraphFlowConfig
from model_client import ModelClient, create_model_clients
from dataclass.model_info import model_client as model_client_label

GraphFlowInfo : dict[str, GraphFlowConfig] = {}

def load_info(config_path: str) -> ComponentInfo:
    with open(config_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    for name, graph_flow_config in metadata["graph_flows"].items():
        GraphFlowInfo[name] = GraphFlowConfig(**graph_flow_config)
    return GraphFlowInfo

@asynccontextmanager
async def prompt_specialization(name: str) -> AsyncGenerator[SelectorGroupChat, None]:
    graph_flow_config: GraphFlowConfig = GraphFlowInfo[name]

    ModelClient=create_model_clients()

    starter = AssistantAgent(
        name="starter",
        model_client=ModelClient[model_client_label.deepseek_chat_DeepSeek],
        system_message="you can only repeate 'i am starter' every time you are called",
        description="starter"
    )
    #starter -> a -> b -> c -> end
    #conditional b -> a
    agent_a = AssistantAgent(
        name="repeater",
        model_client=ModelClient[model_client_label.deepseek_chat_DeepSeek],
        system_message="you can only repeate 'i am Agent a' every time you are called",
        description="repeater a"
    )
    agent_b = AssistantAgent(
        name="repeater",
        model_client=ModelClient[model_client_label.deepseek_chat_DeepSeek],
        system_message="you can only repeate 'i am Agent b' every time you are called",
        description="repeater b"
    )



    async with AsyncExitStack() as stack:
        participants = await asyncio.gather(
            *[stack.enter_async_context(AgentBuilder(participant)) for participant in graph_flow_config.participants]
        )
        participants_map = {participant.name: participant for participant in participants}

        # Build the graph
        builder = DiGraphBuilder()
        for participant in participants_map.values():
            builder.add_node(participant)
        builder.add_edge(participants_map["template_extractor"], participants_map["prompt_specialization"])
        builder.add_edge(
            participants_map["prompt_specialization"], 
            participants_map["prompt_specialization"], 
            condition=lambda msg: "<EOF>" not in msg.content
        )
        builder.add_edge(
            participants_map["prompt_specialization"], 
            participants_map["file_system"], 
            condition=lambda msg: "<EOF>" in msg.content
            )
        # Build and validate the graph
        graph = builder.build()

        # Create the flow
        flow = GraphFlow(builder.get_participants(), graph=graph)
        yield flow

async def test_prompt_specialization():
    from graph_flow.graph_flow_builder import load_info as load_graph_flow_info
    async with prompt_specialization("prompt_specialization") as flow:
        await flow.run_stream(task="")

