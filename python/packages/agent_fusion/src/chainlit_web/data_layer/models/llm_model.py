"""
LLM模型类

处理LLM模型相关的所有数据库操作，从model_clients表加载模型信息
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from chainlit_web.data_layer.models.base_model import BaseModel
from schemas.model_info import ModelClientConfig

from sqlalchemy import select, insert, update, and_, UUID, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class ModelClientTable(Base):
    """SQLAlchemy ORM model for model_clients table"""
    __tablename__ = 'model_clients'
    
    id = Column(Integer, primary_key=True)
    client_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    label = Column(String(255), nullable=False, unique=True)
    provider = Column(String(500), nullable=False)
    component_type_id = Column(Integer)
    version = Column(Integer, default=1)
    component_version = Column(Integer, default=1)
    description = Column(Text)
    model_name = Column(String(255))
    base_url = Column(String(500))
    api_key_hash = Column(String(255))
    model_info = Column(JSONB, default={})
    config = Column(JSONB, default={})
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    updated_by = Column(Integer)
    is_active = Column(Boolean, default=True)


@dataclass
class LLMModelInfo:
    """LLM模型信息数据类"""
    id: int
    client_uuid: str
    label: str
    provider: str
    description: Optional[str]
    model_name: Optional[str]
    base_url: Optional[str]
    model_info: Dict[str, Any]
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LLMModel(BaseModel):
    """LLM模型数据模型"""
    
    def _model_to_info(self, model: ModelClientTable) -> LLMModelInfo:
        """Convert SQLAlchemy model to LLMModelInfo"""
        return LLMModelInfo(
            id=model.id,
            client_uuid=str(model.client_uuid),
            label=model.label,
            provider=model.provider,
            description=model.description,
            model_name=model.model_name,
            base_url=model.base_url,
            model_info=model.model_info if model.model_info else {},
            config=model.config if model.config else {},
            is_active=model.is_active,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    async def get_all_active_models(self) -> List[LLMModelInfo]:
        """获取所有活跃的模型客户端"""
        async with await self.db.get_session() as session:
            stmt = select(ModelClientTable).where(
                ModelClientTable.is_active == True
            ).order_by(ModelClientTable.label)
            
            result = await session.execute(stmt)
            models = result.scalars().all()
            
            return [self._model_to_info(model) for model in models]
    
    async def get_model_by_label(self, label: str) -> Optional[LLMModelInfo]:
        """根据标签获取模型信息"""
        async with await self.db.get_session() as session:
            stmt = select(ModelClientTable).where(
                and_(
                    ModelClientTable.label == label,
                    ModelClientTable.is_active == True
                )
            )
            
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            
            if not model:
                return None
            
            return self._model_to_info(model)
    
    async def get_model_by_id(self, model_id: int) -> Optional[LLMModelInfo]:
        """根据ID获取模型信息"""
        async with await self.db.get_session() as session:
            stmt = select(ModelClientTable).where(
                and_(
                    ModelClientTable.id == model_id,
                    ModelClientTable.is_active == True
                )
            )
            
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            
            if not model:
                return None
            
            return self._model_to_info(model)
    
    async def get_model_labels_for_chat_settings(self) -> List[Dict[str, Any]]:
        """获取用于聊天设置的模型标签列表"""
        async with await self.db.get_session() as session:
            stmt = select(
                ModelClientTable.label,
                ModelClientTable.description,
                ModelClientTable.model_name,
                ModelClientTable.model_info
            ).where(
                ModelClientTable.is_active == True
            ).order_by(ModelClientTable.label)
            
            result = await session.execute(stmt)
            rows = result.all()
            
            model_options = []
            for row in rows:
                model_info = row.model_info if row.model_info else {}
                model_options.append({
                    "label": row.label,
                    "description": row.description or "",
                    "model_name": row.model_name or "",
                    "capabilities": {
                        "vision": model_info.get("vision", False),
                        "function_calling": model_info.get("function_calling", False),
                        "json_output": model_info.get("json_output", False),
                        "family": model_info.get("family", "unknown")
                    }
                })
            
            return model_options
    
    async def get_model_config_for_agent_builder(self, label: str) -> Optional[Dict[str, Any]]:
        """获取用于Agent Builder的模型配置"""
        model_info = await self.get_model_by_label(label)
        if not model_info:
            return None
        
        # 构建与现有ModelClient兼容的配置
        config = {
            "label": model_info.label,
            "model_name": model_info.model_name or "",
            "base_url": model_info.base_url or "",
            "provider": model_info.provider,
            "model_info": model_info.model_info,
            "config": model_info.config,
            "description": model_info.description or ""
        }
        
        return config
    
    
    async def get_model_config_by_label(self, label: str) -> Optional[ModelClientConfig]:
        """根据标签获取模型的ModelClientConfig配置"""
        model_info = await self.get_model_by_label(label)
        if not model_info:
            return None
        
        return ModelClientConfig(
            label=model_info.label,
            model_name=model_info.model_name or "",
            base_url=model_info.base_url or "",
            family=model_info.model_info.get("family", "unknown") if model_info.model_info else "unknown",
            api_key_type=model_info.config.get("api_key_type", "") if model_info.config else "",
            stream=model_info.config.get("stream", True) if model_info.config else True
        )
    
    async def create_model_client(self, 
                                label: str,
                                provider: str,
                                description: Optional[str] = None,
                                model_name: Optional[str] = None,
                                base_url: Optional[str] = None,
                                model_info: Optional[Dict[str, Any]] = None,
                                config: Optional[Dict[str, Any]] = None,
                                created_by: Optional[int] = None) -> Optional[int]:
        """创建新的模型客户端"""
        async with await self.db.get_session() as session:
            try:
                new_model = ModelClientTable(
                    label=label,
                    provider=provider,
                    description=description,
                    model_name=model_name,
                    base_url=base_url,
                    model_info=model_info or {},
                    config=config or {},
                    created_by=created_by
                )
                
                session.add(new_model)
                await session.commit()
                await session.refresh(new_model)
                
                return new_model.id
            except Exception as e:
                await session.rollback()
                print(f"Error creating model client: {e}")
                return None
    
    async def update_model_client(self, 
                                model_id: int,
                                **kwargs) -> bool:
        """更新模型客户端"""
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
    
    async def deactivate_model_client(self, model_id: int) -> bool:
        """停用模型客户端"""
        async with await self.db.get_session() as session:
            try:
                stmt = select(ModelClientTable).where(ModelClientTable.id == model_id)
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()
                
                if not model:
                    return False
                
                model.is_active = False
                model.updated_at = func.current_timestamp()
                
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                print(f"Error deactivating model client: {e}")
                return False
    
    
    async def get_all_components(self, filter_active: bool = True) -> List[ModelClientConfig]:
        """获取所有模型组件配置"""
        if filter_active:
            models = await self.get_all_active_models()
        else:
            async with await self.db.get_session() as session:
                stmt = select(ModelClientTable).order_by(ModelClientTable.label)
                result = await session.execute(stmt)
                model_rows = result.scalars().all()
                models = [self._model_to_info(model) for model in model_rows]
        
        components = []
        for model in models:
            model_client_config = ModelClientConfig(
                label=model.label,
                model_name=model.model_name or "",
                base_url=model.base_url or "",
                family=model.model_info.get("family", "unknown") if model.model_info else "unknown",
                api_key_type=model.config.get("api_key_type", "") if model.config else "",
                stream=model.config.get("stream", True) if model.config else True
            )
            components.append(model_client_config)
        
        return components
    
    async def get_component_by_name(self, component_name: str) -> Optional[ModelClientConfig]:
        """根据组件名称获取组件信息"""
        return await self.get_model_config_by_label(component_name)
    
    async def get_component_id_by_uuid(self, component_uuid: str) -> int:
        """根据组件UUID获取组件主键ID"""
        async with await self.db.get_session() as session:
            stmt = select(ModelClientTable.id).where(ModelClientTable.client_uuid == component_uuid)
            result = await session.execute(stmt)
            model_id = result.scalar_one_or_none()
            
            if not model_id:
                raise ValueError(f"Component with UUID '{component_uuid}' not found")
            return model_id
    
    async def get_component_by_uuid(self, component_uuid: str) -> Optional[ModelClientConfig]:
        """根据组件UUID获取组件信息"""
        async with await self.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.client_uuid == component_uuid)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            
            if not model:
                return None
            
            model_info = self._model_to_info(model)
            
            return ModelClientConfig(
                label=model_info.label,
                model_name=model_info.model_name or "",
                base_url=model_info.base_url or "",
                family=model_info.model_info.get("family", "unknown") if model_info.model_info else "unknown",
                api_key_type=model_info.config.get("api_key_type", "") if model_info.config else "",
                stream=model_info.config.get("stream", True) if model_info.config else True
            )
    
    async def update_component(self, component_uuid: str, model_config: ModelClientConfig) -> Optional[ModelClientConfig]:
        """根据组件UUID更新组件信息"""
        model_id = await self.get_component_id_by_uuid(component_uuid)
        return await self.update_component_by_id(model_id, model_config)
    
    async def update_component_by_id(self, component_id: int, model_config: ModelClientConfig) -> Optional[ModelClientConfig]:
        """根据组件主键ID更新组件信息"""
        # 准备更新数据
        update_data = {
            "label": model_config.label,
            "model_name": model_config.model_name,
            "base_url": model_config.base_url,
            "model_info": {"family": model_config.family},
            "config": {
                "api_key_type": model_config.api_key_type,
                "stream": model_config.stream
            }
        }
        
        update_success = await self.update_model_client(component_id, **update_data)
        
        if not update_success:
            return None
        
        updated_model = await self.get_model_by_id(component_id)
        if not updated_model:
            return None
        
        return ModelClientConfig(
            label=updated_model.label,
            model_name=updated_model.model_name or "",
            base_url=updated_model.base_url or "",
            family=updated_model.model_info.get("family", "unknown") if updated_model.model_info else "unknown",
            api_key_type=updated_model.config.get("api_key_type", "") if updated_model.config else "",
            stream=updated_model.config.get("stream", True) if updated_model.config else True
        )
    
    async def get_component_by_id(self, component_id: int) -> Optional[ModelClientConfig]:
        """根据组件主键ID获取组件信息"""
        async with await self.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.id == component_id)
            result = await session.execute(stmt)
            model = result.scalar_one_or_none()
            
            if not model:
                return None
            
            model_info = self._model_to_info(model)
            
            return ModelClientConfig(
                label=model_info.label,
                model_name=model_info.model_name or "",
                base_url=model_info.base_url or "",
                family=model_info.model_info.get("family", "unknown") if model_info.model_info else "unknown",
                api_key_type=model_info.config.get("api_key_type", "") if model_info.config else "",
                stream=model_info.config.get("stream", True) if model_info.config else True
            )