
import argparse
import asyncio
from autogen_core import CancellationToken
from builders.group_chat_builder import GroupChatBuilder
import os
from builders.agent_builder import AgentBuilder
from builders.utils import load_info, GroupChatInfo, AgentInfo
from autogen_agentchat.ui import Console

#CR inherit User and then  override the input_func to get the message from the command line
#    extractor = SqlCommentExtractor()
#    comments = extractor.extract_comments_from_sql(sql_string)

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
    async with group_chat_builder.build(group_chat_info) as group_chat:
        await Console(group_chat.run_stream(task=message))


async def main():
    #CR achive the same effect as python -m cli.chat run component_name you can reference 
    #src/chainlit_web/users.py, src/chainlit_web/run.py and the reference code in src/chainlit_web/
    #you should create user first, and then use the user to start a chat
    parser = argparse.ArgumentParser(description="Start a chat with an agent.")
    parser.add_argument("type", default="agent", help="The type of the component to run.")
    parser.add_argument("component", help="The name of the component to run.")
    parser.add_argument("message", help="The message to send to the agent.")


    args = parser.parse_args()
    if args.type == "agent":
        await agent(agent_name=args.component, message=args.message)
    elif args.type == "group_chat":
        await group_chat(group_chat_name=args.component, message=args.message)
    else:
        raise ValueError(f"Invalid type: {args.type}")

if __name__ == "__main__":
    asyncio.run(main())
    #python -m cli.chat agent assistant_agent "list all files of current directory"
