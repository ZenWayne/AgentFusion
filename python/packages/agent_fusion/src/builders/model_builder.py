
from autogen_ext.models.openai import OpenAIChatCompletionClient
from typing import Dict, Callable, AsyncGenerator
from schemas.model_info import model_list, ModelClientConfig
import os
from dotenv import load_dotenv
from contextlib import asynccontextmanager

class ModelClientBuilder:
    """Model client builder following AgentBuilder pattern"""
    
    def init_component_map(self,  dotenv_path: str = None):
        load_dotenv(dotenv_path)
        self._component_map: Dict[str, ModelClientConfig] = {
            obj["label"]: ModelClientConfig(**obj) for obj in model_list
        }
    
    async def get_component_by_name(self, label: str) -> ModelClientConfig:
        """Get model client config by label"""
        if label not in self._component_map:
            raise ValueError(f"Model client config not found for label: {label}")
        return self._component_map[label]
    
    @asynccontextmanager
    async def build(self, component_info: ModelClientConfig) -> AsyncGenerator[OpenAIChatCompletionClient, None]:
        """Build a model client by label"""        

        api_key = os.getenv(component_info.api_key_type)
        
        if not api_key:
            raise ValueError(f"API key not found for {component_info.api_key_type}")
        
        model_client = OpenAIChatCompletionClient(
            model=component_info.model_name,
            base_url=component_info.base_url,
            api_key=api_key,
            model_info={
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": component_info.family,
                "structured_output": True,
            }
        )
        model_client.component_label = component_info.label
        yield model_client
        await model_client.close()
    
    def get_available_labels(self) -> list[str]:
        """Get all available model client labels"""
        return list(self._component_map.keys())

def create_model_clients(dotenv_path: str = None) -> Dict[str, Callable[[], OpenAIChatCompletionClient]]:
    """Create model client factory functions"""
    builder = ModelClientBuilder()
    builder.init_component_map(dotenv_path)
    
    model_clients = {}
    for label in builder.get_available_labels():
        # Create a closure to capture the label
        model_clients[label] = lambda l=label: builder.build(l)
    
    return model_clients

# Global model client factory
ModelClient: Dict[str, Callable[[], OpenAIChatCompletionClient]] = create_model_clients()