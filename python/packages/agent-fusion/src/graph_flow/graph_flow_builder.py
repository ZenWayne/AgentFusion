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

GraphFlowInfo : dict[str, GraphFlowConfig] = {}

def load_info(config_path: str) -> ComponentInfo:
    with open(config_path, "r", encoding="utf-8") as f:
        metadata = json.load(f)
    for name, graph_flow_config in metadata["graph_flows"].items():
        GraphFlowInfo[name] = GraphFlowConfig(**graph_flow_config)
    return GraphFlowInfo

@asynccontextmanager
async def GraphFlowBuilder(name: str) -> AsyncGenerator[SelectorGroupChat, None]:
    graph_flow_config: GraphFlowConfig = GraphFlowInfo[name]

    async with AsyncExitStack() as stack:
        participants = await asyncio.gather(
            *[stack.enter_async_context(AgentBuilder(participant)) for participant in graph_flow_config.participants]
        )
        participants_map = {participant.name: participant for participant in participants}

        # Build the graph
        builder = DiGraphBuilder()
        for participant in participants_map.values():
            builder.add_node(participant)
        for node in graph_flow_config.nodes:
            source = participants_map[node.name]
            
            # Handle multiple edges from the same source node
            for edge in node.edges:
                target = participants_map[edge.target]

                builder.add_edge(
                    source=source, 
                    target=target,
                    condition=edge.condition,
                    activation_group=edge.activation_group,
                    activation_condition=edge.activation_condition
                )
        builder.set_entry_point(graph_flow_config.start_node)
        # Build and validate the graph
        graph = builder.build()

        # Create the flow
        flow = GraphFlow(builder.get_participants(), graph=graph)
        yield flow

