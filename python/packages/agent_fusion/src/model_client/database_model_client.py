"""
数据库模型客户端构建器

从数据库加载模型配置并创建模型客户端
"""

import os
from typing import Dict, Optional, Any
from autogen_ext.models.openai import OpenAIChatCompletionClient
from dotenv import load_dotenv


def create_model_client_from_db_config(config: Dict[str, Any], dotenv_path: Optional[str] = None) -> OpenAIChatCompletionClient:
    """
    从数据库配置创建模型客户端
    
    Args:
        config: 数据库中的模型配置
        dotenv_path: .env文件路径
        
    Returns:
        OpenAIChatCompletionClient实例
    """
    if dotenv_path:
        load_dotenv(dotenv_path)
    
    # 从配置中提取信息
    label = config.get("label", "")
    model_name = config.get("model_name", "")
    base_url = config.get("base_url", "")
    model_info = config.get("model_info", {})
    full_config = config.get("config", {})
    
    # 获取API密钥
    api_key_type = full_config.get("api_key_type", "")
    api_key = os.getenv(api_key_type) if api_key_type else None
    
    if not api_key:
        raise ValueError(f"API key not found for {api_key_type}")
    
    # 创建模型客户端
    model_client = OpenAIChatCompletionClient(
        model=model_name,
        base_url=base_url,
        api_key=api_key,
        model_info={
            "vision": model_info.get("vision", False),
            "function_calling": model_info.get("function_calling", True),
            "json_output": model_info.get("json_output", True),
            "family": model_info.get("family", "unknown"),
            "structured_output": True,
        }
    )
    
    model_client.component_label = label
    return model_client


class DatabaseModelClientBuilder:
    """数据库模型客户端构建器"""
    
    def __init__(self, data_layer_instance, dotenv_path: Optional[str] = None):
        """
        初始化构建器
        
        Args:
            data_layer_instance: 数据层实例
            dotenv_path: .env文件路径
        """
        self.data_layer = data_layer_instance
        self.dotenv_path = dotenv_path
        self._model_cache = {}
    
    async def get_model_client(self, label: str) -> Optional[OpenAIChatCompletionClient]:
        """
        根据标签获取模型客户端
        
        Args:
            label: 模型标签
            
        Returns:
            模型客户端实例，如果不存在则返回None
        """
        # 检查缓存
        if label in self._model_cache:
            return self._model_cache[label]
        
        # 从数据库获取配置
        config = await self.data_layer.get_model_config_for_agent_builder(label)
        if not config:
            return None
        
        # 创建模型客户端
        try:
            model_client = create_model_client_from_db_config(config, self.dotenv_path)
            self._model_cache[label] = model_client
            return model_client
        except Exception as e:
            print(f"Error creating model client for {label}: {e}")
            return None
    
    async def get_all_model_clients(self) -> Dict[str, OpenAIChatCompletionClient]:
        """
        获取所有模型客户端
        
        Returns:
            模型客户端字典
        """
        models = await self.data_layer.get_all_active_models()
        model_clients = {}
        
        for model in models:
            try:
                config = {
                    "label": model.label,
                    "model_name": model.model_name,
                    "base_url": model.base_url,
                    "model_info": model.model_info,
                    "config": model.config
                }
                model_client = create_model_client_from_db_config(config, self.dotenv_path)
                model_clients[model.label] = model_client
            except Exception as e:
                print(f"Error creating model client for {model.label}: {e}")
                continue
        
        return model_clients
    
    def clear_cache(self):
        """清除缓存"""
        self._model_cache.clear() 