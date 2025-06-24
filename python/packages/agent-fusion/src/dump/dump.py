from os.path import dirname, abspath, join
from aglogger.logger import logger
from autogen_core._component_config import ComponentToConfig

def dump_component(component_config:ComponentToConfig, agent_path:str):
    paths = agent_path.split('/')
    dir = join(dirname(dirname(abspath(__file__))), "dump_config")
    for path in paths[:-1]:
        dir = join(dir, path)
    comp_name = paths[-1]
    outputpath = join(dir, f"{comp_name}.json")
    logger.debug(f"outputpath: {outputpath}")
    dump_config(component_config, outputpath)
    logger.debug(f"model_client {comp_name} dump success")
    return outputpath

def dump_config(component_name:ComponentToConfig, path:str):
    config = component_name.dump_component().model_dump_json(indent=4)
    with open(path, "w", encoding="utf-8") as f:
        f.write(config)

# if __name__ == "__main__":
#     import asyncio
#     loop = asyncio.new_event_loop()
#     asyncio.set_event_loop(loop)
#     loop.run_until_complete(dump_all())
