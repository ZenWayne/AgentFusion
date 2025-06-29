from dump.dump import dump_component
from builders.file_system import file_system
agent_map = {
    "file_system": file_system
}

async def dump_agent(agent_name:str):
    async with agent_map[agent_name]() as agent:
        dump_component(agent, f"agent/{agent_name}")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(dump_agent("file_system"))