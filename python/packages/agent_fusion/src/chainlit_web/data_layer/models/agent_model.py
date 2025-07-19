"""
Agent model for handling agent-related database operations.

This module provides functionality to manage agents in the database.
"""

import json
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass

from .base_model import ComponentModel
from schemas.agent import ComponentInfo, AgentType, AssistantAgentConfig, UserProxyAgentConfig

from sqlalchemy import select, insert, update, and_, Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

if TYPE_CHECKING:
    from chainlit_web.data_layer.base_data_layer import DBDataLayer

Base = declarative_base()

class AgentTable(Base):
    """SQLAlchemy ORM model for agents table"""
    __tablename__ = 'agents'
    
    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    label = Column(String(255))
    description = Column(Text)
    config = Column(JSONB, default={})
    model_client_id = Column(Integer, ForeignKey('model_clients.id'))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    updated_by = Column(Integer)
    
    # Relationships
    prompts = relationship("PromptTable", back_populates="agent")

class PromptTable(Base):
    """SQLAlchemy ORM model for prompts table"""
    __tablename__ = 'prompts'
    
    id = Column(Integer, primary_key=True)
    prompt_id = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    subcategory = Column(String(100))
    description = Column(Text)
    agent_id = Column(Integer, ForeignKey('agents.id'))
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    updated_by = Column(Integer)
    
    # Relationships
    agent = relationship("AgentTable", back_populates="prompts")
    versions = relationship("PromptVersionTable", back_populates="prompt")

class PromptVersionTable(Base):
    """SQLAlchemy ORM model for prompt_versions table"""
    __tablename__ = 'prompt_versions'
    
    id = Column(Integer, primary_key=True)
    prompt_id = Column(Integer, ForeignKey('prompts.id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    version_label = Column(String(255))
    content = Column(Text, nullable=False)
    status = Column(String(50), default='active')
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    change_description = Column(Text)
    
    # Relationships
    prompt = relationship("PromptTable", back_populates="versions")

class ModelClientTable(Base):
    """SQLAlchemy ORM model for model_clients table (reference)"""
    __tablename__ = 'model_clients'
    
    id = Column(Integer, primary_key=True)
    label = Column(String(255), nullable=False, unique=True)
    config = Column(JSONB, default={})

@dataclass
class AgentInfo:
    """Agent信息数据类"""
    id: int
    name: str
    label: Optional[str]
    description: Optional[str]
    config: Dict[str, Any]
    model_client_label: Optional[str]
    current_prompt: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class AgentModel(ComponentModel):
    """Agent model class"""
    
    def __init__(self, db_layer: "DBDataLayer"):
        super().__init__(db_layer)
    
    def _build_agent_info(self, agent: AgentTable, model_client: Optional[ModelClientTable] = None, current_prompt: Optional[str] = None) -> AgentInfo:
        """Convert SQLAlchemy agent model to AgentInfo"""
        return AgentInfo(
            id=agent.id,
            name=agent.name,
            label=agent.label,
            description=agent.description,
            config=agent.config if agent.config else {},
            model_client_label=model_client.label if model_client else None,
            current_prompt=current_prompt,
            is_active=agent.is_active,
            created_at=agent.created_at,
            updated_at=agent.updated_at
        )
    
    async def get_all_components(self, filter_active: bool = True) -> Dict[str, ComponentInfo]:
        """
        Get agents for chat profile and return as ComponentInfo objects
        
        Returns:
            Dict[str, ComponentInfo]: Agent name to ComponentInfo mapping
        """
        async with await self.db.get_session() as session:
            # Build query with joins
            stmt = select(
                AgentTable,
                ModelClientTable.label.label('model_client_label'),
                PromptVersionTable.content.label('current_prompt')
            ).select_from(
                AgentTable.__table__.outerjoin(ModelClientTable.__table__, AgentTable.model_client_id == ModelClientTable.id)
                .outerjoin(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                .outerjoin(PromptVersionTable.__table__, and_(
                    PromptTable.id == PromptVersionTable.prompt_id,
                    PromptVersionTable.is_current == True
                ))
            )
            
            if filter_active:
                stmt = stmt.where(AgentTable.is_active == True)
                
            stmt = stmt.order_by(AgentTable.name)
            
            result = await session.execute(stmt)
            rows = result.all()
            
            agent_info = {}
            
            for row in rows:
                agent = row[0]  # AgentTable object
                model_client_label = row[1]  # model_client_label
                current_prompt = row[2]  # current_prompt
                
                agent_config = agent.config if agent.config else {}
                
                # Base configuration
                base_config = {
                    "name": agent.name,
                    "description": agent.description or "",
                    "labels": agent_config.get("labels", [])
                }
                
                # Determine agent type
                agent_type = agent_config.get("type", "assistant_agent")
                
                if agent_type == AgentType.ASSISTANT_AGENT:
                    # AssistantAgent configuration
                    component_info = AssistantAgentConfig(
                        type=AgentType.ASSISTANT_AGENT,
                        model_client=model_client_label or "default",
                        prompt=lambda content=current_prompt: content or "",
                        mcp_tools=agent_config.get("mcp_tools"),
                        **base_config
                    )
                else:
                    # UserProxyAgent configuration
                    component_info = UserProxyAgentConfig(
                        type=AgentType.USER_PROXY_AGENT,
                        input_func=agent_config.get("input_func", "input"),
                        **base_config
                    )
                
                agent_info[agent.name] = component_info
            
            return agent_info
    
    async def to_component_info(self, component_name: str) -> ComponentInfo:
        """将组件信息转换为ComponentInfo对象"""
        async with await self.db.get_session() as session:
            # Build query with joins
            stmt = select(
                AgentTable,
                ModelClientTable.label.label('model_client_label'),
                PromptVersionTable.content.label('current_prompt')
            ).select_from(
                AgentTable.__table__.outerjoin(ModelClientTable.__table__, AgentTable.model_client_id == ModelClientTable.id)
                .outerjoin(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                .outerjoin(PromptVersionTable.__table__, and_(
                    PromptTable.id == PromptVersionTable.prompt_id,
                    PromptVersionTable.is_current == True
                ))
            ).where(and_(
                AgentTable.name == component_name,
                AgentTable.is_active == True
            ))
            
            result = await session.execute(stmt)
            row = result.first()
            
            if not row:
                raise ValueError(f"Agent '{component_name}' not found")
            
            agent = row[0]  # AgentTable object
            model_client_label = row[1]  # model_client_label
            current_prompt = row[2]  # current_prompt
            
            agent_config = agent.config if agent.config else {}
            
            # Base configuration
            base_config = {
                "name": agent.name,
                "description": agent.description or "",
                "labels": agent_config.get("labels", [])
            }
            
            # Determine agent type
            agent_type = agent_config.get("type", "assistant_agent")
            
            if agent_type == AgentType.ASSISTANT_AGENT:
                return AssistantAgentConfig(
                    type=AgentType.ASSISTANT_AGENT,
                    model_client=model_client_label or "default",
                    prompt=lambda content=current_prompt: content or "",
                    mcp_tools=agent_config.get("mcp_tools"),
                    **base_config
                )
            else:
                return UserProxyAgentConfig(
                    type=AgentType.USER_PROXY_AGENT,
                    input_func=agent_config.get("input_func", "input"),
                    **base_config
                )
    
    async def get_component_by_name(self, component_name: str) -> ComponentInfo:
        """根据组件名称获取组件信息"""
        return await self.to_component_info(component_name)
    
    async def get_component_id_by_uuid(self, component_uuid: str) -> int:
        """根据组件UUID获取组件主键ID"""
        async with await self.db.get_session() as session:
            stmt = select(AgentTable.id).where(and_(
                AgentTable.name == component_uuid,
                AgentTable.is_active == True
            ))
            
            result = await session.execute(stmt)
            agent_id = result.scalar_one_or_none()
            
            if not agent_id:
                raise ValueError(f"Agent with UUID '{component_uuid}' not found")
            return agent_id
    
    async def get_component_by_uuid(self, component_uuid: str) -> ComponentInfo:
        """根据组件UUID获取组件信息"""
        return await self.to_component_info(component_uuid)
    
    async def get_component_by_id(self, component_id: int) -> ComponentInfo:
        """根据组件主键ID获取组件信息"""
        async with await self.db.get_session() as session:
            stmt = select(AgentTable.name).where(and_(
                AgentTable.id == component_id,
                AgentTable.is_active == True
            ))
            
            result = await session.execute(stmt)
            agent_name = result.scalar_one_or_none()
            
            if not agent_name:
                raise ValueError(f"Agent with ID '{component_id}' not found")
            return await self.to_component_info(agent_name)
    
    async def update_component_by_id(self, component_id: int, component_info: ComponentInfo) -> ComponentInfo:
        """根据组件主键ID更新组件信息"""
        async with await self.db.get_session() as session:
            try:
                # Find the agent
                stmt = select(AgentTable).where(and_(
                    AgentTable.id == component_id,
                    AgentTable.is_active == True
                ))
                
                result = await session.execute(stmt)
                agent = result.scalar_one_or_none()
                
                if not agent:
                    raise ValueError(f"Agent with ID '{component_id}' not found")
                
                # Build config from ComponentInfo
                config = {
                    "type": component_info.type,
                    "labels": component_info.labels
                }
                
                if hasattr(component_info, 'mcp_tools'):
                    config["mcp_tools"] = component_info.mcp_tools
                if hasattr(component_info, 'input_func'):
                    config["input_func"] = component_info.input_func
                
                # Update agent fields
                agent.label = component_info.name
                agent.description = component_info.description
                agent.config = config
                agent.updated_at = func.current_timestamp()
                
                await session.commit()
                
                return await self.to_component_info(agent.name)
                
            except Exception as e:
                await session.rollback()
                raise ValueError(f"Agent with ID '{component_id}' update failed: {e}")
    
    async def update_component(self, component_uuid: str, component_info: ComponentInfo) -> ComponentInfo:
        """根据组件UUID更新组件信息"""
        component_id = await self.get_component_id_by_uuid(component_uuid)
        return await self.update_component_by_id(component_id, component_info)
    
    async def update_agent_prompt(self, agent_name: str, new_prompt: str, version_label: Optional[str] = None, changed_by: int = 1) -> bool:
        """
        Update agent prompt
        
        Args:
            agent_name: Agent name
            new_prompt: New prompt content
            version_label: Version label
            changed_by: User ID who made the change
            
        Returns:
            bool: Whether update was successful
        """
        try:
            async with await self.db.get_session() as session:
                # Find agent info with existing prompt
                stmt = select(
                    AgentTable.id,
                    PromptTable.id.label('prompt_id'),
                    PromptTable.prompt_id.label('prompt_business_id')
                ).select_from(
                    AgentTable.__table__.outerjoin(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                ).where(and_(
                    AgentTable.name == agent_name,
                    AgentTable.is_active == True
                ))
                
                result = await session.execute(stmt)
                row = result.first()
                
                if not row:
                    return False
                
                agent_id = row[0]
                prompt_id = row[1]
                prompt_business_id = row[2]
                
                # Create prompt if it doesn't exist
                if not prompt_id:
                    prompt_business_id = f"{agent_name}_system"
                    new_prompt_obj = PromptTable(
                        prompt_id=prompt_business_id,
                        name=f"{agent_name} System Message",
                        category='agent',
                        subcategory='system_message',
                        description=f"System message for {agent_name} agent",
                        agent_id=agent_id,
                        created_by=changed_by
                    )
                    
                    session.add(new_prompt_obj)
                    await session.commit()
                    await session.refresh(new_prompt_obj)
                    prompt_id = new_prompt_obj.id
                
                # Create new prompt version using stored procedure
                # Note: This still uses the stored procedure as it likely handles version numbering logic
                await session.execute(
                    select(func.create_prompt_version(
                        prompt_business_id, 
                        new_prompt, 
                        version_label, 
                        changed_by, 
                        "Updated via API"
                    ))
                )
                
                await session.commit()
                return True
                
        except Exception as e:
            print(f"Error updating agent prompt: {e}")
            return False
    
    async def get_agent_prompt_history(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get agent prompt version history
        
        Args:
            agent_name: Agent name
            
        Returns:
            List[Dict[str, Any]]: Prompt version history
        """
        async with await self.db.get_session() as session:
            # Build query with joins for prompt history
            # Note: Assuming there's a User table, but we'll handle it gracefully if not
            stmt = select(
                PromptVersionTable.version_number,
                PromptVersionTable.version_label,
                PromptVersionTable.content,
                PromptVersionTable.status,
                PromptVersionTable.created_at,
                PromptVersionTable.is_current,
                # Handle User table join gracefully - may not exist in all schemas
                # For now, just use created_by ID
                PromptVersionTable.created_by.label('created_by_username')
            ).select_from(
                AgentTable.__table__
                .join(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                .join(PromptVersionTable.__table__, PromptTable.id == PromptVersionTable.prompt_id)
            ).where(and_(
                AgentTable.name == agent_name,
                AgentTable.is_active == True
            )).order_by(PromptVersionTable.version_number.desc())
            
            result = await session.execute(stmt)
            rows = result.all()
            
            # Convert to list
            history = []
            for row in rows:
                history.append({
                    "version_number": row[0],
                    "version_label": row[1],
                    "content": row[2],
                    "status": row[3],
                    "created_at": row[4].isoformat() if row[4] else None,
                    "is_current": row[5],
                    "created_by_username": str(row[6]) if row[6] else None  # Using ID as username for now
                })
            
            return history