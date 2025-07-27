"""
GroupChat模型类

处理GroupChat相关的所有数据库操作，从group_chats表加载组件信息
"""

import json
import uuid
import asyncio
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from data_layer.models.base_model import ComponentModel, BaseComponentTable
from data_layer.models.tables.group_chat_table import GroupChatTable
from data_layer.models.tables.relationship_table import GroupChatParticipantsTable
from data_layer.models.tables.agent_table import AgentTable
from schemas.component import ComponentInfo
from schemas.group_chat import SelectorGroupChatConfig, RoundRobinGroupChatConfig

from sqlalchemy import select, insert, update, delete, and_, UUID, Column, Integer, String, Text, Boolean, DateTime, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import selectinload


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
        
        # Get participants from relationship table
        participants = await self._get_group_chat_participants(group_chat.id)
        
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
        elif group_chat.type == "round_robin_group_chat":
            return RoundRobinGroupChatConfig(
                type="round_robin_group_chat",
                name=group_chat.name,
                description=group_chat.description or "",
                labels=labels,
                participants=participants,
                handoff_target=group_chat.handoff_target or "user",
                termination_condition=group_chat.termination_condition or "handoff"
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
    
    async def get_all_components(self, filter_active: bool = True) -> List[ComponentInfo]:
        """
        获取所有组件信息，重写父类方法来处理group_chat_participants关联查询
        filter_active为True时，只获取active为True的组件，否则不考虑is_active是否为True都选
        """
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            name_column = getattr(self.table_class, self.name_column_name)
            
            # 先查询所有group chats
            stmt = select(self.table_class).order_by(name_column)
            if filter_active:
                stmt = stmt.where(self.table_class.is_active == True)
            
            result = await session.execute(stmt)
            group_chats = result.scalars().all()
            
            # 为每个group chat单独查询participants
            components = []
            for group_chat in group_chats:
                participants = await self._get_group_chat_participants(group_chat.id, session)
                component_info = await self._to_component_info_with_participants(group_chat, participants)
                components.append(component_info)
            
            return components

    async def _to_component_info_with_participants(self, group_chat: GroupChatTable, participant_names: List[str]) -> ComponentInfo:
        """Convert SQLAlchemy model to ComponentInfo with provided participant names"""
        
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
        
        # Use provided participant names directly
        participants = participant_names or []
        
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
        elif group_chat.type == "round_robin_group_chat":
            return RoundRobinGroupChatConfig(
                type="round_robin_group_chat",
                name=group_chat.name,
                description=group_chat.description or "",
                labels=labels,
                participants=participants,
                handoff_target=group_chat.handoff_target or "user",
                termination_condition=group_chat.termination_condition or "handoff"
            )
        else:
            # Fallback for unknown types - treat as selector group chat with empty fields
            return SelectorGroupChatConfig(
                type="selector_group_chat",
                name=group_chat.name,
                description=group_chat.description or "",
                labels=labels,
                selector_prompt="",
                participants=participants,
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
                              handoff_target: Optional[str] = None,
                              termination_condition: Optional[str] = None,
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
                
                # participants will be handled separately through relationship table
                
                # Generate UUID for SQLite if needed
                group_chat_uuid = str(uuid.uuid4()) if "sqlite" in str(self.db.database_url).lower() else None
                
                new_group_chat = GroupChatTable(
                    name=name,
                    type=type,
                    description=description,
                    labels=labels_value,
                    selector_prompt=selector_prompt,
                    handoff_target=handoff_target,
                    termination_condition=termination_condition,
                    model_client=model_client,
                    created_by=created_by,
                    group_chat_uuid=group_chat_uuid
                )
                
                session.add(new_group_chat)
                await session.commit()
                await session.refresh(new_group_chat)
                
                # Add participants to relationship table
                if participants:
                    await self._add_group_chat_participants(session, new_group_chat.id, participants, created_by)
                    await session.commit()
                
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
                # Handle participants separately before filtering update_data
                participants_to_update = None
                if 'participants' in kwargs:
                    participants_to_update = kwargs.pop('participants')
                
                update_data = {k: v for k, v in kwargs.items() if hasattr(self.table_class, k)}

                if not update_data and participants_to_update is None:
                    return True

                # Handle special fields for SQLite compatibility
                if 'labels' in update_data and isinstance(update_data['labels'], list):
                    if "sqlite" in str(self.db.database_url).lower():
                        update_data['labels'] = ",".join(update_data['labels']) if update_data['labels'] else None

                # Execute table update only if there are fields to update
                update_result = None
                if update_data:
                    update_data['updated_at'] = func.current_timestamp()

                    stmt = (
                        update(self.table_class)
                        .where(self.table_class.id == group_chat_id)
                        .values(**update_data)
                    )
                    
                    update_result = await session.execute(stmt)
                
                # Update participants if provided
                if participants_to_update is not None:
                    await self._update_group_chat_participants(session, group_chat_id, participants_to_update, 1)
                
                await session.commit()
                
                # Return True if either table update succeeded or participants were updated
                return (update_result is None or update_result.rowcount > 0) if update_data else True
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
            "labels": component_info.labels
        }
        
        # 只有SelectorGroupChatConfig有model_client字段
        if hasattr(component_info, 'model_client'):
            update_data["model_client"] = component_info.model_client
        
        # 根据类型添加特定字段
        if component_info.type == "selector_group_chat":
            update_data.update({
                "selector_prompt": component_info.selector_prompt,
                "participants": component_info.participants
            })
        elif component_info.type == "round_robin_group_chat":
            update_data.update({
                "handoff_target": component_info.handoff_target,
                "termination_condition": component_info.termination_condition,
                "participants": component_info.participants
            })
        
        update_success = await self.update_group_chat(component_id, **update_data)
        
        if not update_success:
            return None
        
        return await self.get_component_by_id(component_id)
    
    async def _get_group_chat_participants(self, group_chat_id: int, session=None) -> List[str]:
        """Get participant names for a group chat"""
        use_existing_session = session is not None
        if not use_existing_session:
            session = await self.db.get_session()
        
        try:
            stmt = (
                select(AgentTable.name)
                .join(GroupChatParticipantsTable, AgentTable.id == GroupChatParticipantsTable.agent_id)
                .where(
                    and_(
                        GroupChatParticipantsTable.group_chat_id == group_chat_id,
                        GroupChatParticipantsTable.is_active == True,
                        AgentTable.is_active == True
                    )
                )
                .order_by(GroupChatParticipantsTable.join_order)
            )
            result = await session.execute(stmt)
            return [row[0] for row in result.fetchall()]
        except Exception as e:
            print(f"Error getting group chat participants: {e}")
            return []
        finally:
            if not use_existing_session:
                await session.close()
    
    async def _add_group_chat_participants(self, session, group_chat_id: int, participant_names: List[str], created_by: Optional[int] = None):
        """Add participants to group chat"""
        try:
            # Get agent IDs from names
            stmt = select(AgentTable.id, AgentTable.name).where(
                and_(
                    AgentTable.name.in_(participant_names),
                    AgentTable.is_active == True
                )
            )
            result = await session.execute(stmt)
            agent_map = {name: agent_id for agent_id, name in result.fetchall()}
            
            # Add participants
            for order, participant_name in enumerate(participant_names):
                if participant_name in agent_map:
                    participant = GroupChatParticipantsTable(
                        group_chat_id=group_chat_id,
                        agent_id=agent_map[participant_name],
                        join_order=order,
                        created_by=created_by
                    )
                    session.add(participant)
        except Exception as e:
            print(f"Error adding group chat participants: {e}")
    
    async def _update_group_chat_participants(self, session, group_chat_id: int, participant_names: List[str], created_by: Optional[int] = None):
        """Update group chat participants by replacing existing ones"""
        try:
            # Remove existing participants
            stmt = delete(GroupChatParticipantsTable).where(
                GroupChatParticipantsTable.group_chat_id == group_chat_id
            )
            await session.execute(stmt)
            
            # Add new participants
            await self._add_group_chat_participants(session, group_chat_id, participant_names, created_by)
        except Exception as e:
            print(f"Error updating group chat participants: {e}")
    
