from autogen import LLMConfig, OpenAIWrapper, AssistantAgent, LLMConfig
from typing import Dict
from schemas.model_info import model_list, ModelClientConfig
import os
from dotenv import load_dotenv

def create_model_config(dotenv_path:str=None)->Dict[str, str]:
    if dotenv_path:
        load_dotenv(dotenv_path)
    configs = {}
    for obj in model_list:
        obj["api_key"] = os.getenv(obj["api_key_type"])
        label = obj["label"]
        obj.pop("label")
        obj.pop("api_key_type")
        configs[label] = obj
    
    return configs


ModelClient : Dict[str, Dict[str,str]] = create_model_config()