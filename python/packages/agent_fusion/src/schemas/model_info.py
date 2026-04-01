from autogen_core.models import ModelFamily
from pydantic import BaseModel
from enum import Enum
from schemas.types import ComponentType
from typing import Literal

class ModelClientConfig(BaseModel):
    type: Literal[ComponentType.LLM]
    label: str
    model_name: str
    base_url: str | None
    family: str
    api_key_type: str
    stream: bool

class model_client(str, Enum):
    deepseek_chat_DeepSeek= "deepseek-chat_DeepSeek"
    deepseek_reasoner_DeepSeek= "deepseek-reasoner_DeepSeek"
    qwq_plus_Aliyun = "qwq-plus_Aliyun"
    deepseek_r1_Aliyun= "deepseek-r1_Aliyun"
    deepseek_v3_Aliyun= "deepseek-v3_Aliyun"
    qwq_32b_Aliyun= "qwq-32b_Aliyun"
    gemini_2_5_flash_preview_04_17_Google= "gemini-2.5-flash-preview-04-17_Google"
    qwen3_max_DashScope= "qwen3-max_DashScope"
    text_embedding_v4_DashScope= "text-embedding-v4_DashScope"
    qwen3_vl_embedding_DashScope= "qwen3-vl-embedding_DashScope"


model_list = [
        {
            "type": ComponentType.LLM,
            "label": model_client.deepseek_chat_DeepSeek,
            "model_name": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "family": ModelFamily.UNKNOWN,
            "api_key_type": "DEEPSEEK_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.deepseek_reasoner_DeepSeek,
            "model_name": "deepseek-reasoner",
            "base_url": "https://api.deepseek.com/v1",
            "family": ModelFamily.R1,
            "api_key_type": "DEEPSEEK_API_KEY",
            "stream": False
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.qwq_plus_Aliyun,
            "model_name": "qwq-plus-latest",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "family": ModelFamily.R1,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.deepseek_r1_Aliyun,
            "model_name": "deepseek-r1",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "family": ModelFamily.R1,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.deepseek_v3_Aliyun,
            "model_name": "deepseek-v3",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "family": ModelFamily.UNKNOWN,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.qwq_32b_Aliyun,
            "model_name": "qwq-32b",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "family": ModelFamily.UNKNOWN,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.qwen3_max_DashScope,
            "model_name": "qwen3-max",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "family": ModelFamily.UNKNOWN,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.gemini_2_5_flash_preview_04_17_Google,
            "model_name": "gemini-2.5-flash-preview-04-17",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/models/",
            "family": ModelFamily.GEMINI_2_5_FLASH,
            "api_key_type": "GEMINI_API_KEY",
            "stream": True
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.text_embedding_v4_DashScope,
            "model_name": "text-embedding-v4",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "family": ModelFamily.UNKNOWN,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": False
        },
        {
            "type": ComponentType.LLM,
            "label": model_client.qwen3_vl_embedding_DashScope,
            "model_name": "qwen3-vl-embedding",
            "base_url": None,
            "litellm_provider": "dashscope",
            "family": ModelFamily.UNKNOWN,
            "api_key_type": "DASHSCOPE_API_KEY",
            "stream": False
        }
]