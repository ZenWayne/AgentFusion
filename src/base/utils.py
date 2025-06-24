import os
import re
from os.path import dirname, abspath, join
from autogen_core._component_config import ComponentToConfig
import asyncio
from autogen_core import CancellationToken
from autogen_agentchat.agents import UserProxyAgent
from aglogger import agentgenerator_logger as logger
import json
from dataclass import AssistantAgentConfig, UserProxyAgentConfig

prompt_path = ""

def dump_component(component_config:ComponentToConfig, agent_path:str):
    paths = agent_path.split('/')
    dir = join(dirname(dirname(abspath(__file__))), "agent_dump_config")
    for path in paths[:-1]:
        dir = join(dir, path)
    comp_name = paths[-1]
    outputpath = join(dir, f"{comp_name}.json")
    logger.info(f"outputpath: {outputpath}")
    dump_config(component_config, outputpath)
    logger.info(f"dump success")

def dump_config(component_name:ComponentToConfig, path:str):
    config = component_name.dump_component().model_dump_json(indent=4)
    with open(path, "w", encoding="utf-8") as f:
        f.write(config)

def get_prompt(agent_path:str, spliter = '/') -> str:
    paths = agent_path.split(spliter)

    dir = prompt_path
    for path in paths[:-1]:
        dir = join(dir, path)
    agent_name = paths[-1]
    prompt_file_path = join(
        dir, f"{agent_name}"
    )

    try:
        with open(prompt_file_path, "r", encoding="utf-8") as f:
            prompt_template = f.read()
    except:
        raise FileNotFoundError(f"prompt not found {agent_path}")
    
    return prompt_template

async def warp_input(prompt:str, token: CancellationToken) -> str:
    logger.info(f"warp_input: {prompt} token: {token}")
    input_list = []

    input_str=input(prompt)
    while True:
        if input_str == "EOF":
            #token.cancel()
            break
        input_list.append(input_str)
        input_str = input()        
    ret="\n".join(input_list)
    return ret

def pre_hook_decorator():
    """
    装饰器：在函数调用前向input_list开头插入内容
    
    Args:
        input_list: 要操作的列表
        insert_value: 要插入的值，如果为None则插入函数名
    """
    def decorator(func):        
        async def async_wrapper(*args, **kwargs):
            pre_prompt=await func()
            prompt=await warp_input(*args, **kwargs)
            final_prompt=f"{pre_prompt}\n{prompt}"
            logger.debug(f"pre_hook: 在函数 {func.__name__} 调用前插入到列表开头: {final_prompt}")
            return final_prompt
        
        return async_wrapper
    return decorator

def post_hook_decorator():
    """
    装饰器：在函数调用后向input_list末尾插入内容
    
    Args:
        input_list: 要操作的列表
        insert_value: 要插入的值，如果为None则插入函数名
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            post_prompt=await func()
            prompt=await warp_input(*args, **kwargs)
            final_prompt=f"{prompt}\n{post_prompt}"
            logger.debug(f"post_hook: 在函数 {func.__name__} 调用后插入到列表末尾: {final_prompt}")
            return final_prompt
        return async_wrapper
    return decorator

def dual_hook_decorator():
    """
    装饰器：在函数调用前后向input_list插入内容
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            pre_prompt, post_prompt = await func()
            prompt=await warp_input(*args, **kwargs)
            final_prompt=f"{pre_prompt}\n{prompt}\n{post_prompt}"
            logger.debug(f"dual_hook: 在函数 {func.__name__} 调用前后插入到列表: {final_prompt}")
            return final_prompt
        return async_wrapper
    return decorator

def cancellable_user_agent():
    agent = UserProxyAgent("user", input_func=warp_input, description="一个人类用户")

    return agent
