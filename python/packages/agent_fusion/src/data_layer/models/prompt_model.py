"""
Prompt model for handling prompt-related database operations.

This module provides functionality to manage prompts and prompt versions in the database.
"""

from typing import Dict, List, Any, Optional, TYPE_CHECKING
from datetime import datetime

from .base_model import ComponentModel
from schemas.component import ComponentInfo
from schemas.types import ComponentType
from .group_chat_model import GroupChatTable
from builders.prompt_builder import PromptBuilder
from .tables.prompt_table import PromptTable, PromptVersionTable

from sqlalchemy import select, insert, update, and_
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from data_layer.base_data_layer import DBDataLayer


class PromptModel(ComponentModel, PromptBuilder):
    """Prompt model class"""
    table_class = PromptTable
    uuid_column_name = "prompt_uuid"
    name_column_name = "name"
    
    def __init__(self, db_layer: "DBDataLayer"):
        super().__init__(db_layer)
    
    async def get_prompt_by_catagory_and_name(self, component_type: ComponentType, component_name: str, ) -> Optional[ComponentInfo]:
        async with await self.db.get_session() as session:
            stmt = select(PromptTable).where(
                and_(
                    PromptTable.name == component_name,
                    PromptTable.category == component_type.value
                )
            )
            result = await session.execute(stmt)
            prompt = result.scalar_one_or_none()
            if prompt:
                return await self.to_component_info(prompt)
            return None

    #CR这里不用ComponentInfo，用PromptConfig了
    async def to_component_info(self, table_row: PromptTable) -> ComponentInfo:
        """将数据库行转换为ComponentInfo对象"""
        # Get current prompt version content
        async with await self.db.get_session() as session:
            stmt = select(PromptVersionTable.content).where(
                and_(
                    PromptVersionTable.prompt_id == table_row.id,
                    PromptVersionTable.is_current == True
                )
            )
            result = await session.execute(stmt)
            current_content = result.scalar_one_or_none() or ""
        
        return ComponentInfo(
            type="prompt",
            name=table_row.name,
            description=table_row.description or "",
            labels=[],
            content=current_content
        )
    
    async def update_agent_prompt(self, component_type: ComponentType, component_name: str, new_prompt: str, version_label: Optional[str] = None, changed_by: int = 1) -> bool:
        """
        Update agent prompt
        
        Args:
            component_type: Component type
            component_name: Component name
            new_prompt: New prompt content
            version_label: Version label
            changed_by: User ID who made the change
            
        Returns:
            bool: Whether update was successful
        """
        try:
            async with await self.db.get_session() as session:
                # Import here to avoid circular import
                from .agent_model import AgentTable
                
                # Find agent info with existing prompt
                stmt = select(
                    AgentTable.id,
                    PromptTable.id.label('prompt_id'),
                    PromptTable.prompt_id.label('prompt_business_id')
                ).select_from(
                    AgentTable.__table__.outerjoin(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                )
                if component_type == ComponentType.AGENT:
                    stmt = stmt.join(AgentTable.__table__, PromptTable.agent_id == AgentTable.id)
                elif component_type == ComponentType.GROUP_CHAT:
                    stmt = stmt.join(GroupChatTable.__table__, PromptTable.group_chat_id == GroupChatTable.id)
                
                
                result = await session.execute(stmt)
                row = result.first()
                
                if not row:
                    return False
                
                agent_id = row[0]
                prompt_id = row[1]
                prompt_business_id = row[2]
                
                # Create prompt if it doesn't exist
                if not prompt_id:
                    prompt_business_id = f"{component_name}_system"
                    new_prompt_obj = PromptTable(
                        prompt_id=prompt_business_id,
                        name=f"{component_name} System Message",
                        category='agent',
                        subcategory='system_message',
                        description=f"System message for {component_name} {component_type}",
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
            # Import here to avoid circular import
            from .agent_model import AgentTable
            
            # Build query with joins for prompt history
            stmt = select(
                PromptVersionTable.version_number,
                PromptVersionTable.version_label,
                PromptVersionTable.content,
                PromptVersionTable.status,
                PromptVersionTable.created_at,
                PromptVersionTable.is_current,
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
    
    async def get_current_prompt_content(self, component_type: ComponentType, component_name: str) -> Optional[str]:
        """
        Get current prompt content for an agent
        
        Args:
            component_type: Component type
            component_name: Component name
            
        Returns:
            Optional[str]: Current prompt content or None if not found
        """
        async with await self.db.get_session() as session:
            # Import here to avoid circular import
            from .agent_model import AgentTable
            
            if component_type == ComponentType.AGENT:
                stmt = select(PromptVersionTable.content).select_from(
                    AgentTable.__table__
                    .join(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                    .join(PromptVersionTable.__table__, and_(
                        PromptTable.id == PromptVersionTable.prompt_id,
                        PromptVersionTable.is_current == True
                    ))
                ).where(and_(
                    PromptTable.name == component_name,
                    PromptTable.category == component_type,
                    PromptTable.is_active == True
                ))
            elif component_type == ComponentType.GROUP_CHAT:
                stmt = select(PromptVersionTable.content).select_from(
                    GroupChatTable.__table__
                    .join(PromptTable.__table__, GroupChatTable.id == PromptTable.group_chat_id)
                    .join(PromptVersionTable.__table__, and_(
                        PromptTable.id == PromptVersionTable.prompt_id,
                        PromptVersionTable.is_current == True
                    ))
                ).where(and_(
                    PromptTable.name == component_name,
                    PromptTable.category == component_type,
                    PromptTable.is_active == True
                ))
            
            result = await session.execute(stmt)
            return result.scalar_one_or_none()