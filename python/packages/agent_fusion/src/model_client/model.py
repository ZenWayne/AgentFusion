
from autogen_ext.models.openai import OpenAIChatCompletionClient
from typing import Dict
from schemas.model_info import model_list, ModelClientConfig
import os
from dotenv import load_dotenv

def model_client_builder(label, model_name, base_url, family, api_key)->OpenAIChatCompletionClient:
    model_client = OpenAIChatCompletionClient(
            model=model_name,
            base_url=base_url,
            api_key=api_key,
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": family,
                "structured_output": True,
            }
    )
    model_client.component_label = label
    return model_client

def create_model_clients(dotenv_path:str=None)->Dict[str, OpenAIChatCompletionClient]:
    configs : Dict[str, ModelClientConfig] = {
        obj["label"] :ModelClientConfig(**obj) for obj in model_list
    }
    ModelClient = {}
    if dotenv_path:
        load_dotenv(dotenv_path)
    for k, config in configs.items():
        model_client = lambda config=config: model_client_builder(
            label=config.label,
            model_name=config.model_name,
            base_url=config.base_url,
            family=config.family,
            api_key=os.getenv(config.api_key_type)
        )
        ModelClient[k] = model_client
    
    return ModelClient


ModelClient : dict[str, OpenAIChatCompletionClient] = create_model_clients()