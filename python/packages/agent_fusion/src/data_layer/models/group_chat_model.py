"""
GroupChat模型类

处理GroupChat相关的所有数据库操作，从group_chats表加载组件信息
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from data_layer.models.base_model import ComponentModel, BaseComponentTable
from schemas.component import ComponentInfo
from schemas.group_chat import SelectorGroupChatConfig

from sqlalchemy import select, insert, update, and_, UUID, Column, Integer, String, Text, Boolean, DateTime, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class GroupChatTable(BaseComponentTable):
    """SQLAlchemy ORM model for group_chats table"""
    __tablename__ = 'group_chats'
    
    group_chat_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(100), nullable=False)
    labels = Column(ARRAY(Text), default=[])
    selector_prompt = Column(Text)
    participants = Column(JSONB, default=[])
    model_client = Column(String(255))
    component_type_id = Column(Integer)
    version = Column(Integer, default=1)
    component_version = Column(Integer, default=1)


# Note: ComponentInfo is now imported from schemas.component and provides 
# unified interface for both Agent and GroupChat components


class GroupChatModel(ComponentModel):
    """GroupChat数据模型"""
    table_class = GroupChatTable
    uuid_column_name = "group_chat_uuid"
    name_column_name = "name"
    
    async def to_component_info(self, group_chat: GroupChatTable) -> ComponentInfo:
        """Convert SQLAlchemy model to ComponentInfo"""
        if group_chat.type == "selector_group_chat":
            return SelectorGroupChatConfig(
                type="selector_group_chat",
                name=group_chat.name,
                description=group_chat.description or "",
                labels=group_chat.labels if group_chat.labels else [],
                selector_prompt=group_chat.selector_prompt or "",
                participants=group_chat.participants if group_chat.participants else [],
                model_client=group_chat.model_client or ""
            )
        else:
            # Fallback for unknown types - return basic ComponentInfo
            return ComponentInfo(
                type=group_chat.type,
                name=group_chat.name,
                description=group_chat.description or "",
                labels=group_chat.labels if group_chat.labels else [],
                model_client=group_chat.model_client
            )
    
    async def create_group_chat(self, 
                              name: str,
                              type: str,
                              description: Optional[str] = None,
                              labels: Optional[List[str]] = None,
                              selector_prompt: Optional[str] = None,
                              participants: Optional[List[str]] = None,
                              model_client: Optional[str] = None,
                              created_by: Optional[int] = None) -> Optional[int]:
        """创建新的GroupChat"""
        async with await self.db.get_session() as session:
            try:
                new_group_chat = GroupChatTable(
                    name=name,
                    type=type,
                    description=description,
                    labels=labels or [],
                    selector_prompt=selector_prompt,
                    participants=participants or [],
                    model_client=model_client,
                    created_by=created_by
                )
                
                session.add(new_group_chat)
                await session.commit()
                await session.refresh(new_group_chat)
                
                return new_group_chat.id
            except Exception as e:
                await session.rollback()
                print(f"Error creating group chat: {e}")
                return None
    
    async def update_group_chat(self, 
                              group_chat_id: int,
                              **kwargs) -> bool:
        """更新GroupChat"""
        async with await self.db.get_session() as session:
            try:
                update_data = {k: v for k, v in kwargs.items() if hasattr(self.table_class, k)}

                if not update_data:
                    return True

                update_data['updated_at'] = func.current_timestamp()

                stmt = (
                    update(self.table_class)
                    .where(self.table_class.id == group_chat_id)
                    .values(**update_data)
                )
                
                result = await session.execute(stmt)
                await session.commit()
                
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                print(f"Error updating group chat: {e}")
                return False
    
    async def deactivate_group_chat(self, group_chat_id: int) -> bool:
        """停用GroupChat"""
        async with await self.db.get_session() as session:
            try:
                stmt = (
                    update(self.table_class)
                    .where(self.table_class.id == group_chat_id)
                    .values(is_active=False, updated_at=func.current_timestamp())
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                print(f"Error deactivating group chat: {e}")
                return False
    
    
    async def update_component_by_id(self, component_id: int, component_info: ComponentInfo) -> Optional[ComponentInfo]:
        """根据组件主键ID更新组件信息"""
        # 准备更新数据
        update_data = {
            "name": component_info.name,
            "description": component_info.description,
            "labels": component_info.labels,
            "model_client": component_info.model_client
        }
        
        # 根据类型添加特定字段
        if component_info.type == "selector_group_chat":
            update_data.update({
                "selector_prompt": component_info.selector_prompt,
                "participants": component_info.participants
            })
        
        update_success = await self.update_group_chat(component_id, **update_data)
        
        if not update_success:
            return None
        
        return await self.get_component_by_id(component_id)
    
