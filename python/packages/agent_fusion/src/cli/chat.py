
import argparse
import asyncio
from autogen_core import CancellationToken
from builders.group_chat_builder import GroupChatBuilder
import os
from builders.agent_builder import AgentBuilder
from builders.graph_flow_builder import GraphFlowBuilder
from builders.utils import load_info, GroupChatInfo, AgentInfo, GraphFlowInfo
from autogen_agentchat.ui import Console, UserInputManager
from typing import Optional

# Get the project root directory (where config.json is located)
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", ".."))

def wrap_input(prompt: str, cancellation_token: Optional[CancellationToken]) -> str:
    user_input = input(prompt)
    while user_input != "EOF":
        user_input = user_input + input("\n")
    return user_input

async def agent(agent_name: str, message: str):
    load_info()
    if agent_name in AgentInfo:
        agent_info = AgentInfo[agent_name]
    else:
        raise ValueError(f"{agent_name} not found in AgentInfo")
    agent_builder = AgentBuilder()
    async with agent_builder.build(agent_info) as agent:
        await Console(agent.run_stream(task=message))

async def group_chat(group_chat_name: str, message: str):
    load_info()
    if group_chat_name in GroupChatInfo:
        group_chat_info = GroupChatInfo[group_chat_name]
    else:
        raise ValueError(f"{group_chat_name} not found in GroupChatInfo")
    group_chat_builder = GroupChatBuilder()
    input_manager=UserInputManager(wrap_input)
    async with group_chat_builder.build(group_chat_info) as group_chat:
        await Console(stream=group_chat.run_stream(task=message), user_input_manager=input_manager)

async def graphflow(graphflow_name: str, message: str):
    load_info()
    if graphflow_name not in GraphFlowInfo:
        raise ValueError(f"{graphflow_name} not found in GraphFlowInfo")
    input_manager = UserInputManager(wrap_input)
    async with GraphFlowBuilder(graphflow_name) as flow:
        await Console(stream=flow.run_stream(task=message), user_input_manager=input_manager)

async def main():
    parser = argparse.ArgumentParser(description="Start a chat with an agent.")
    parser.add_argument("type", choices=["agent", "group_chat", "graphflow"], default="agent", help="The type of the component to run.")
    parser.add_argument("component", help="The name of the component to run.")
    parser.add_argument("message", help="The message to send to the agent.")

    args = parser.parse_args()

    # Change to project root directory so config paths work correctly
    original_dir = os.getcwd()
    os.chdir(PROJECT_ROOT)

    try:
        if args.type == "agent":
            await agent(agent_name=args.component, message=args.message)
        elif args.type == "group_chat":
            await group_chat(group_chat_name=args.component, message=args.message)
        elif args.type == "graphflow":
            await graphflow(graphflow_name=args.component, message=args.message)
        else:
            raise ValueError(f"Invalid type: {args.type}")
    finally:
        os.chdir(original_dir)

if __name__ == "__main__":
    asyncio.run(main())
    #python -m cli.chat agent assistant_agent "list all files of current directory"
