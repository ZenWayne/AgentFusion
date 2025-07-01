from autogen_core.models import ModelFamily
from pydantic import BaseModel
from enum import Enum

class ModelClientConfig(BaseModel):
    api_type: str
    model: str
    base_url: str
    api_key_type: str

class model_client(str, Enum):
    deepseek_chat_DeepSeek= "deepseek-chat_DeepSeek"
    deepseek_reasoner_DeepSeek= "deepseek-reasoner_DeepSeek"
    qwq_plus_Aliyun = "qwq-plus_Aliyun"
    deepseek_r1_Aliyun= "deepseek-r1_Aliyun"
    deepseek_v3_Aliyun= "deepseek-v3_Aliyun"
    qwq_32b_Aliyun= "qwq-32b_Aliyun"
    gemini_2_5_flash_preview_04_17_Google= "gemini-2.5-flash-preview-04-17_Google"


model_list = [
        {
            "label": "deepseek-chat_DeepSeek",
            "api_type": "openai",
            "model": "deepseek-chat",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_type": "DEEPSEEK_API_KEY",
        },
        {
            "label": "deepseek-reasoner_DeepSeek",
            "api_type": "openai",
            "model": "deepseek-reasoner",
            "base_url": "https://api.deepseek.com/v1",
            "api_key_type": "DEEPSEEK_API_KEY",
        },
        {
            "label": "qwq-plus_Aliyun",
            "api_type": "openai",
            "model": "qwq-plus-latest",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_type": "DASHSCOPE_API_KEY",
        },
        {
            "label": "deepseek-r1_Aliyun",
            "api_type": "openai",
            "model": "deepseek-r1",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_type": "DASHSCOPE_API_KEY",
        },
        {
            "label": "deepseek-v3_Aliyun",
            "api_type": "openai",
            "model": "deepseek-v3",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_type": "DASHSCOPE_API_KEY",
        },
        {
            "label": "qwq-32b_Aliyun",
            "api_type": "openai",
            "model": "qwq-32b",
            "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "api_key_type": "DASHSCOPE_API_KEY",
        },
        {
            "label": "gemini-2.5-flash-preview-04-17_Google",
            "api_type": "openai",
            "model": "gemini-2.5-flash-preview-04-17",
            "base_url": "https://generativelanguage.googleapis.com/v1beta/",
            "api_key_type": "GEMINI_API_KEY",
        }
]