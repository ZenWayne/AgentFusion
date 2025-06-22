from dump.dump import dump_component
from aglogger.logger import logger
from dump.component import GroupChat

async def dump_group_chat(group_chat_name:str|None=None):
    if group_chat_name is None:
        for agent_name, group_chat_func in GroupChat.items():
            async with group_chat_func() as agent:
                outputpath = dump_component(agent, f"group_chat/{agent_name}")
                logger.info(f"dump GroupChat {agent_name} success outputpath: {outputpath}")
    else:
        async with GroupChat[group_chat_name]() as agent:
            outputpath = dump_component(agent, f"group_chat/{group_chat_name}")
            logger.info(f"dump GroupChat {group_chat_name} success outputpath: {outputpath}")
        return outputpath

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(dump_group_chat("prompt_flow"))
    #python -m dump.dump_group_chat
