from dump.dump import dump_component
from model_client import ModelClient
from aglogger.logger import logger

async def dump_model_client(model_model_client:str|None=None):
    if model_model_client is None:
        for k, model_client in ModelClient.items():
            dump_component(model_client, f"model_client/{k}")
    logger.info("dump model clients success")

if __name__ == "__main__":
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(dump_model_client())
    #python -m dump.dump_model_client
