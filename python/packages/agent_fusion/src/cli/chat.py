
import argparse
import asyncio
from autogen_core import CancellationToken
from data_layer.models.agent_model import AgentModel
from data_layer.data_layer import DBDataLayer
from builders.group_chat_builder import GroupChatBuilder
import os
from builders.utils import load_info, GroupChatInfo
from autogen_agentchat.ui import Console

#CR inherit User and then  override the input_func to get the message from the command line
#    extractor = SqlCommentExtractor()
#    comments = extractor.extract_comments_from_sql(sql_string)

async def group_chat(group_chat_name: str, message: str):
    load_info()
    database_url = os.getenv("DATABASE_URL")
    db_layer = DBDataLayer(database_url)
    agent_model = AgentModel(db_layer)
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
    parser.add_argument("component", help="The name of the component to run.")
    parser.add_argument("message", help="The message to send to the agent.")

    args = parser.parse_args()

    await group_chat(group_chat_name=args.component, message=args.message)

if __name__ == "__main__":
    asyncio.run(main())
    #
