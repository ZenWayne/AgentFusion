"""
GroupChat模型类

处理GroupChat相关的所有数据库操作，从group_chats表加载组件信息
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from chainlit_web.data_layer.models.base_model import BaseModel
from schemas.group_chat import ComponentInfo as GroupChatComponentInfo

from sqlalchemy import select, insert, update, and_, UUID, Column, Integer, String, Text, Boolean, DateTime, JSONB, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()

class GroupChatTable(Base):
    """SQLAlchemy ORM model for group_chats table"""
    __tablename__ = 'group_chats'
    
    id = Column(Integer, primary_key=True)
    group_chat_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(100), nullable=False)
    description = Column(Text)
    labels = Column(ARRAY(Text), default=[])
    selector_prompt = Column(Text)
    participants = Column(JSONB, default=[])
    model_client = Column(String(255))
    config = Column(JSONB, default={})
    component_type_id = Column(Integer)
    version = Column(Integer, default=1)
    component_version = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    updated_by = Column(Integer)
    is_active = Column(Boolean, default=True)


@dataclass
class GroupChatInfo:
    """GroupChat信息数据类"""
    id: int
    group_chat_uuid: str
    name: str
    type: str
    description: Optional[str]
    labels: List[str]
    selector_prompt: Optional[str]
    participants: List[str]
    model_client: Optional[str]
    config: Dict[str, Any]
    component_type_id: Optional[int]
    version: int
    component_version: int
    is_active: bool
    created_at: datetime
    updated_at: datetime


class GroupChatModel(BaseModel):
    """GroupChat数据模型"""
    
    def _group_chat_to_info(self, group_chat: GroupChatTable) -> GroupChatInfo:
        """Convert SQLAlchemy model to GroupChatInfo"""
        return GroupChatInfo(
            id=group_chat.id,
            group_chat_uuid=str(group_chat.group_chat_uuid),
            name=group_chat.name,
            type=group_chat.type,
            description=group_chat.description,
            labels=group_chat.labels if group_chat.labels else [],
            selector_prompt=group_chat.selector_prompt,
            participants=group_chat.participants if group_chat.participants else [],
            model_client=group_chat.model_client,
            config=group_chat.config if group_chat.config else {},
            component_type_id=group_chat.component_type_id,
            version=group_chat.version,
            component_version=group_chat.component_version,
            is_active=group_chat.is_active,
            created_at=group_chat.created_at,
            updated_at=group_chat.updated_at
        )
    
    async def get_all_active_group_chats(self) -> List[GroupChatInfo]:
        """获取所有活跃的GroupChat"""
        async with await self.db.get_session() as session:
            stmt = select(GroupChatTable).where(
                GroupChatTable.is_active == True
            ).order_by(GroupChatTable.name)
            
            result = await session.execute(stmt)
            group_chats = result.scalars().all()
            
            return [self._group_chat_to_info(gc) for gc in group_chats]
    
    async def get_group_chat_by_name(self, name: str) -> Optional[GroupChatInfo]:
        """根据名称获取GroupChat信息"""
        async with await self.db.get_session() as session:
            stmt = select(GroupChatTable).where(
                and_(
                    GroupChatTable.name == name,
                    GroupChatTable.is_active == True
                )
            )
            
            result = await session.execute(stmt)
            group_chat = result.scalar_one_or_none()
            
            if not group_chat:
                return None
            
            return self._group_chat_to_info(group_chat)
    
    async def get_group_chat_by_id(self, group_chat_id: int) -> Optional[GroupChatInfo]:
        """根据ID获取GroupChat信息"""
        async with await self.db.get_session() as session:
            stmt = select(GroupChatTable).where(
                and_(
                    GroupChatTable.id == group_chat_id,
                    GroupChatTable.is_active == True
                )
            )
            
            result = await session.execute(stmt)
            group_chat = result.scalar_one_or_none()
            
            if not group_chat:
                return None
            
            return self._group_chat_to_info(group_chat)
    
    async def get_all_components(self, filter_active: bool = True) -> List[GroupChatComponentInfo]:
        """获取所有GroupChat组件配置"""
        if filter_active:
            group_chats = await self.get_all_active_group_chats()
        else:
            async with await self.db.get_session() as session:
                stmt = select(GroupChatTable).order_by(GroupChatTable.name)
                result = await session.execute(stmt)
                group_chat_rows = result.scalars().all()
                group_chats = [self._group_chat_to_info(gc) for gc in group_chat_rows]
        
        components = []
        for gc in group_chats:
            # 根据type创建对应的ComponentInfo
            if gc.type == "selector_group_chat":
                component_info = GroupChatComponentInfo(
                    type="selector_group_chat",
                    name=gc.name,
                    description=gc.description or "",
                    labels=gc.labels,
                    selector_prompt=gc.selector_prompt or "",
                    participants=gc.participants,
                    model_client=gc.model_client or ""
                )
                components.append(component_info)
        
        return components
    
    async def get_component_by_name(self, component_name: str) -> Optional[GroupChatComponentInfo]:
        """根据组件名称获取组件信息"""
        gc_info = await self.get_group_chat_by_name(component_name)
        if not gc_info:
            return None
        
        if gc_info.type == "selector_group_chat":
            return GroupChatComponentInfo(
                type="selector_group_chat",
                name=gc_info.name,
                description=gc_info.description or "",
                labels=gc_info.labels,
                selector_prompt=gc_info.selector_prompt or "",
                participants=gc_info.participants,
                model_client=gc_info.model_client or ""
            )
        
        return None
    
    async def get_component_id_by_uuid(self, component_uuid: str) -> int:
        """根据组件UUID获取组件主键ID"""
        async with await self.db.get_session() as session:
            stmt = select(GroupChatTable.id).where(GroupChatTable.group_chat_uuid == component_uuid)
            result = await session.execute(stmt)
            group_chat_id = result.scalar_one_or_none()
            
            if not group_chat_id:
                raise ValueError(f"Component with UUID '{component_uuid}' not found")
            return group_chat_id
    
    async def get_component_by_uuid(self, component_uuid: str) -> Optional[GroupChatComponentInfo]:
        """根据组件UUID获取组件信息"""
        async with await self.db.get_session() as session:
            stmt = select(GroupChatTable).where(GroupChatTable.group_chat_uuid == component_uuid)
            result = await session.execute(stmt)
            group_chat = result.scalar_one_or_none()
            
            if not group_chat:
                return None
            
            gc_info = self._group_chat_to_info(group_chat)
            
            if gc_info.type == "selector_group_chat":
                return GroupChatComponentInfo(
                    type="selector_group_chat",
                    name=gc_info.name,
                    description=gc_info.description or "",
                    labels=gc_info.labels,
                    selector_prompt=gc_info.selector_prompt or "",
                    participants=gc_info.participants,
                    model_client=gc_info.model_client or ""
                )
            
            return None
    
    async def create_group_chat(self, 
                              name: str,
                              type: str,
                              description: Optional[str] = None,
                              labels: Optional[List[str]] = None,
                              selector_prompt: Optional[str] = None,
                              participants: Optional[List[str]] = None,
                              model_client: Optional[str] = None,
                              config: Optional[Dict[str, Any]] = None,
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
                    config=config or {},
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
                stmt = select(GroupChatTable).where(GroupChatTable.id == group_chat_id)
                result = await session.execute(stmt)
                group_chat = result.scalar_one_or_none()
                
                if not group_chat:
                    return False
                
                # Update fields
                for field, value in kwargs.items():
                    if hasattr(group_chat, field):
                        setattr(group_chat, field, value)
                
                # Update timestamp
                group_chat.updated_at = func.current_timestamp()
                
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                print(f"Error updating group chat: {e}")
                return False
    
    async def deactivate_group_chat(self, group_chat_id: int) -> bool:
        """停用GroupChat"""
        async with await self.db.get_session() as session:
            try:
                stmt = select(GroupChatTable).where(GroupChatTable.id == group_chat_id)
                result = await session.execute(stmt)
                group_chat = result.scalar_one_or_none()
                
                if not group_chat:
                    return False
                
                group_chat.is_active = False
                group_chat.updated_at = func.current_timestamp()
                
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                print(f"Error deactivating group chat: {e}")
                return False
    
    async def update_component(self, component_uuid: str, component_info: GroupChatComponentInfo) -> Optional[GroupChatComponentInfo]:
        """根据组件UUID更新组件信息"""
        group_chat_id = await self.get_component_id_by_uuid(component_uuid)
        return await self.update_component_by_id(group_chat_id, component_info)
    
    async def update_component_by_id(self, component_id: int, component_info: GroupChatComponentInfo) -> Optional[GroupChatComponentInfo]:
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
        
        updated_group_chat = await self.get_group_chat_by_id(component_id)
        if not updated_group_chat:
            return None
        
        if updated_group_chat.type == "selector_group_chat":
            return GroupChatComponentInfo(
                type="selector_group_chat",
                name=updated_group_chat.name,
                description=updated_group_chat.description or "",
                labels=updated_group_chat.labels,
                selector_prompt=updated_group_chat.selector_prompt or "",
                participants=updated_group_chat.participants,
                model_client=updated_group_chat.model_client or ""
            )
        
        return None
    
    async def get_component_by_id(self, component_id: int) -> Optional[GroupChatComponentInfo]:
        """根据组件主键ID获取组件信息"""
        async with await self.db.get_session() as session:
            stmt = select(GroupChatTable).where(GroupChatTable.id == component_id)
            result = await session.execute(stmt)
            group_chat = result.scalar_one_or_none()
            
            if not group_chat:
                return None
            
            gc_info = self._group_chat_to_info(group_chat)
            
            if gc_info.type == "selector_group_chat":
                return GroupChatComponentInfo(
                    type="selector_group_chat",
                    name=gc_info.name,
                    description=gc_info.description or "",
                    labels=gc_info.labels,
                    selector_prompt=gc_info.selector_prompt or "",
                    participants=gc_info.participants,
                    model_client=gc_info.model_client or ""
                )
            
            return None