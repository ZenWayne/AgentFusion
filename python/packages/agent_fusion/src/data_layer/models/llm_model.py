"""
LLM模型类

处理LLM模型相关的所有数据库操作，从model_clients表加载模型信息
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from data_layer.models.base_model import BaseModel, ComponentModel, BaseComponentTable
from data_layer.models.tables.llm_table import ModelClientTable
from schemas.model_info import ModelClientConfig
from builders.model_builder import ModelClientBuilder
from schemas.types import ComponentType
from data_layer.base_data_layer import DBDataLayer
from sqlalchemy import select, insert, update, and_, UUID, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from dotenv import load_dotenv

class LLMModel(ComponentModel, ModelClientBuilder):
    """LLM模型数据模型"""
    table_class = ModelClientTable
    uuid_column_name = "client_uuid"
    name_column_name = "label"

    def __init__(self, db_layer: DBDataLayer):
        super().__init__(db_layer)
    
    async def init_component_map(self, dotenv_path: str = None):
        """consider move to base one day? currently it's unnecessary because there is no common between agent and modelclient"""
        load_dotenv(dotenv_path)
        self._component_map = self.get_all_active_components()
        return self._component_map

    async def to_component_info(self, model: ModelClientTable) -> ModelClientConfig:
        """Convert SQLAlchemy model to ModelClientConfig"""
        return ModelClientConfig(
            type=ComponentType.LLM,
            label=model.label,
            model_name=model.model_name or "",
            base_url=model.base_url or "",
            family=model.model_info.get("family", "unknown") if model.model_info else "unknown",
            api_key_type=model.api_key_type or "",
            stream=model.config.get("stream", True) if model.config else True
        )
    
    async def _update_model_client(self, model_id: int, **kwargs) -> bool:
        """更新模型客户端（内部方法）"""
        async with await self.db.get_session() as session:
            try:
                stmt = select(ModelClientTable).where(ModelClientTable.id == model_id)
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()
                
                if not model:
                    return False
                
                # Update fields
                for field, value in kwargs.items():
                    if hasattr(model, field):
                        setattr(model, field, value)
                
                # Update timestamp
                model.updated_at = func.current_timestamp()
                
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                print(f"Error updating model client: {e}")
                return False
    
    async def update_component_by_id(self, component_id: int, model_config: ModelClientConfig) -> Optional[ModelClientConfig]:
        """根据组件主键ID更新组件信息"""
        # 准备更新数据
        update_data = {
            "label": model_config.label,
            "model_name": model_config.model_name,
            "base_url": model_config.base_url,
            "api_key_type": model_config.api_key_type,
            "model_info": {"family": model_config.family},
            "config": {
                "stream": model_config.stream
            }
        }

        update_success = await self._update_model_client(component_id, **update_data)

        if not update_success:
            return None

        updated_model = await self.get_component_by_id(component_id)
        if not updated_model:
            return None

        return updated_model