"""
Memory Model

Handles all database operations related to agent memories.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass
from chainlit.logger import logger

from data_layer.models.base_model import BaseModel
from .tables.memory_table import AgentMemoriesTable

from sqlalchemy import select, delete, and_, or_, text
from sqlalchemy.sql import func

@dataclass
class MemoryInfo:
    id: str
    user_id: int
    memory_key: str
    memory_type: Optional[str]
    summary: Optional[str]
    content: Optional[str]
    content_metadata: Dict[str, Any]
    created_at: datetime
    is_active: bool
    agent_id: Optional[int] = None
    thread_id: Optional[str] = None

class MemoryModel(BaseModel):
    """Memory data model"""

    def _model_to_info(self, model: AgentMemoriesTable) -> MemoryInfo:
        return MemoryInfo(
            id=str(model.id),
            user_id=model.user_id,
            agent_id=model.agent_id,
            thread_id=str(model.thread_id) if model.thread_id else None,
            memory_key=model.memory_key,
            memory_type=model.memory_type,
            summary=model.summary,
            content=model.content,
            content_metadata=model.content_metadata if model.content_metadata else {},
            created_at=model.created_at,
            is_active=model.is_active
        )

    async def store_memory(self, 
                           user_id: int, 
                           memory_key: str, 
                           content: str, 
                           summary: Optional[str] = None, 
                           memory_type: str = "command_output",
                           agent_id: Optional[int] = None,
                           thread_id: Optional[str] = None,
                           metadata: Optional[Dict] = None) -> str:
        """Store a new memory"""
        async with await self.db.get_session() as session:
            try:
                new_memory = AgentMemoriesTable(
                    user_id=user_id,
                    agent_id=agent_id,
                    thread_id=thread_id,
                    memory_key=memory_key,
                    memory_type=memory_type,
                    summary=summary,
                    content=content,
                    content_metadata=metadata or {}
                )
                session.add(new_memory)
                await session.commit()
                # Refresh to get ID and other server-defaults if needed
                await session.refresh(new_memory)
                return str(new_memory.memory_key)
            except Exception as e:
                await session.rollback()
                logger.error(f"Error storing memory: {e}")
                raise

    async def retrieve_memory(self, memory_key: str) -> Optional[MemoryInfo]:
        """Retrieve memory by key"""
        async with await self.db.get_session() as session:
            stmt = select(AgentMemoriesTable).where(AgentMemoriesTable.memory_key == memory_key)
            result = await session.execute(stmt)
            memory = result.scalar_one_or_none()
            if memory:
                return self._model_to_info(memory)
            return None

    async def search_memories(self, query: str, user_id: Optional[int] = None, limit: int = 5) -> List[MemoryInfo]:
        """Simple keyword search for memories"""
        async with await self.db.get_session() as session:
            conditions = [AgentMemoriesTable.is_active == True]
            if user_id:
                conditions.append(AgentMemoriesTable.user_id == user_id)
            
            search_filter = or_(
                AgentMemoriesTable.summary.ilike(f"%{query}%"),
                AgentMemoriesTable.content.ilike(f"%{query}%")
            )
            conditions.append(search_filter)

            stmt = select(AgentMemoriesTable).where(and_(*conditions)).limit(limit)
            result = await session.execute(stmt)
            memories = result.scalars().all()
            return [self._model_to_info(m) for m in memories]
