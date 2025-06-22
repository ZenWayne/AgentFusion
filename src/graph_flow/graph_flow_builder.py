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
                
                if edge.condition is not None:
                    # Handle conditional edges
                    condition_to_target = {edge.condition: target}
                    builder.add_conditional_edges(
                        source, 
                        condition_to_target,
                        activation_group=edge.activation_group,
                        activation_condition=edge.activation_condition
                    )
                else:
                    # Handle simple edges
                    builder.add_edge(source, target)
        # Build and validate the graph
        graph = builder.build()

        # Create the flow
        flow = GraphFlow(builder.get_participants(), graph=graph)
        yield flow

