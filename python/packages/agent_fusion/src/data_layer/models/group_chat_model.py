"""
GroupChat模型类

处理GroupChat相关的所有数据库操作，从group_chats表加载组件信息
"""

import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from data_layer.models.base_model import ComponentModel, BaseComponentTable
from data_layer.models.tables.group_chat_table import GroupChatTable
from schemas.component import ComponentInfo
from schemas.group_chat import SelectorGroupChatConfig

from sqlalchemy import select, insert, update, and_, UUID, Column, Integer, String, Text, Boolean, DateTime, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB


class GroupChatModel(ComponentModel):
    """GroupChat数据模型"""
    table_class = GroupChatTable
    uuid_column_name = "group_chat_uuid"
    name_column_name = "name"
    
    async def to_component_info(self, group_chat: GroupChatTable) -> ComponentInfo:
        """Convert SQLAlchemy model to ComponentInfo"""
        
        # Handle labels - can be string (SQLite) or list (PostgreSQL)
        labels = []
        if group_chat.labels:
            if isinstance(group_chat.labels, str):
                # Handle comma-separated string format for SQLite
                if group_chat.labels.startswith('[') and group_chat.labels.endswith(']'):
                    try:
                        labels = json.loads(group_chat.labels)
                    except (json.JSONDecodeError, ValueError):
                        labels = []
                else:
                    # Handle comma-separated format
                    labels = [label.strip() for label in group_chat.labels.split(',') if label.strip()]
            elif isinstance(group_chat.labels, list):
                labels = group_chat.labels
        
        # Handle participants - can be JSON string (SQLite) or list (PostgreSQL)
        participants = []
        if group_chat.participants:
            if isinstance(group_chat.participants, str):
                try:
                    participants = json.loads(group_chat.participants)
                except (json.JSONDecodeError, ValueError):
                    participants = []
            elif isinstance(group_chat.participants, list):
                participants = group_chat.participants
        
        if group_chat.type == "selector_group_chat":
            return SelectorGroupChatConfig(
                type="selector_group_chat",
                name=group_chat.name,
                description=group_chat.description or "",
                labels=labels,
                selector_prompt=group_chat.selector_prompt or "",
                participants=participants,
                model_client=group_chat.model_client or ""
            )
        else:
            # Fallback for unknown types - treat as selector group chat with empty fields
            return SelectorGroupChatConfig(
                type="selector_group_chat",
                name=group_chat.name,
                description=group_chat.description or "",
                labels=labels,
                selector_prompt="",
                participants=[],
                model_client=group_chat.model_client or ""
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
                # Handle labels - convert to appropriate format based on database
                labels_data = labels or []
                if isinstance(labels_data, list) and labels_data:
                    # For SQLite compatibility, store as comma-separated string or JSON
                    if "sqlite" in str(self.db.database_url).lower():
                        labels_value = ",".join(labels_data) if labels_data else None
                    else:
                        labels_value = labels_data
                else:
                    labels_value = None
                
                # Handle participants - convert to appropriate format based on database  
                participants_data = participants or []
                if isinstance(participants_data, list):
                    if "sqlite" in str(self.db.database_url).lower():
                        participants_value = json.dumps(participants_data)
                    else:
                        participants_value = participants_data
                else:
                    participants_value = json.dumps([])
                
                # Generate UUID for SQLite if needed
                group_chat_uuid = str(uuid.uuid4()) if "sqlite" in str(self.db.database_url).lower() else None
                
                new_group_chat = GroupChatTable(
                    name=name,
                    type=type,
                    description=description,
                    labels=labels_value,
                    selector_prompt=selector_prompt,
                    participants=participants_value,
                    model_client=model_client,
                    created_by=created_by,
                    group_chat_uuid=group_chat_uuid
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

                # Handle special fields for SQLite compatibility
                if 'labels' in update_data and isinstance(update_data['labels'], list):
                    if "sqlite" in str(self.db.database_url).lower():
                        update_data['labels'] = ",".join(update_data['labels']) if update_data['labels'] else None
                
                if 'participants' in update_data and isinstance(update_data['participants'], list):
                    if "sqlite" in str(self.db.database_url).lower():
                        update_data['participants'] = json.dumps(update_data['participants'])

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
    
