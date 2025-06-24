#package you need to install:
#pip install autogen-ext[mcp]
from autogen_agentchat.agents import AssistantAgent, UserProxyAgent
from autogen_ext.models.openai import OpenAIChatCompletionClient
import os
from autogen_agentchat.ui import Console

import asyncio
from asyncio import coroutines
from autogen_core import CancellationToken
from autogen_agentchat.agents import UserProxyAgent
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ModelFamily
from autogen_ext.tools.mcp import StdioMcpToolAdapter, StdioServerParams, mcp_server_tools
from autogen_agentchat import EVENT_LOGGER_NAME
from autogen_agentchat.conditions import MaxMessageTermination, TextMentionTermination
from model_client.utils import ModelClient, label
import logging

from autogen_agentchat.teams import RoundRobinGroupChat
# import nest_asyncio
# nest_asyncio.apply()

# logging.basicConfig(level=logging.DEBUG)
# logging.Logger("asyncio").setLevel(logging.DEBUG)
logging.Logger(EVENT_LOGGER_NAME).setLevel(logging.DEBUG)


async def main() -> None:
    src_project_root = "/c/fs_test"
    project_root = "/app/project/"
    
    server_params = StdioServerParams(
            command = "uvx",
            args = [
                "blender-mcp"
                ],
            env = None
    )

    tools_list : list[StdioMcpToolAdapter] =  await mcp_server_tools(server_params)
    for tool in tools_list:
        tool.component_label = tool.name
    # Get the tools from the server
    # write_file = await StdioMcpToolAdapter.from_server_params(server_params, "write_file")
    # list_directory = await StdioMcpToolAdapter.from_server_params(server_params, "list_directory")
    # create_directory = await StdioMcpToolAdapter.from_server_params(server_params, "create_directory")

    model_client = ModelClient[label.deepseek_r1_DeepSeek]
    print(f"model_config: {model_client.dump_component().model_dump_json()}")
    tailing_message = "when finished, respond with 'TERMINATE'"
    system_message = f"You are a helpful blender assistant.{tailing_message}"
    agent = AssistantAgent(
        name="blender_mcp_group_chat",
        model_client=model_client,
        tools=tools_list,
        system_message=system_message
    )

    max_msg_termination = MaxMessageTermination(max_messages=10)
    text_termination = TextMentionTermination("TERMINATE")
    combined_termination = max_msg_termination | text_termination

    round_robin_team = RoundRobinGroupChat(
        participants=[agent],
        termination_condition=combined_termination
        )
    round_robin_team.component_label = "blender_mcp_group_chat"
    
    with open("round_robin_team.json", "w") as f:
        f.write(round_robin_team.dump_component().model_dump_json(indent=4))
    print(f"dump success")
    #print(f"AssistantAgent config: {round_robin_team.dump_component().model_dump_json()}")

    # await Console(
    #     round_robin_team.run_stream(task="list all files under the /app/project directory", cancellation_token=CancellationToken())
    # )

if __name__ == "__main__":
    ## should not use asyncio.run() cos it will close loop which will be close after main function
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(main())

#python -m blender-mcp.blender-mcp

