"""
线程模型

处理线程相关的所有数据库操作
"""

import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from chainlit.types import (
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.logger import logger

from data_layer.models.base_model import BaseModel
from .tables.thread_table import ThreadTable
from .tables.user_table import UserTable
from .tables.step_table import StepsTable
from .tables.element_table import ElementTable
from .tables.feedback_table import FeedbackTable

from sqlalchemy import select, insert, update, delete, and_, or_
from sqlalchemy.sql import func
from sqlalchemy.orm import selectinload, joinedload


@dataclass
class ThreadInfo:
    """线程信息数据类"""
    id: str
    name: Optional[str]
    user_id: int
    user_identifier: Optional[str]
    tags: Optional[List[str]]
    metadata: Dict[str, Any]
    is_active: bool
    created_at: datetime
    deleted_at: Optional[datetime]
    updated_at: datetime


class ThreadModel(BaseModel):
    """thread表示一行消息，这里包含用户的线程数据模型，包含用户信息，线程信息，步骤信息，元素信息，反馈信息"""
    
    def _deserialize_tags(self, tags):
        """Deserialize tags from database format"""
        if not tags:
            return []
        if isinstance(tags, list):
            return tags
        if isinstance(tags, str):
            try:
                import json
                return json.loads(tags)
            except (json.JSONDecodeError, TypeError):
                return []
        return []
    
    def _thread_to_info(self, thread: ThreadTable) -> ThreadInfo:
        """Convert SQLAlchemy model to ThreadInfo"""
        return ThreadInfo(
            id=str(thread.id),
            name=thread.name,
            user_id=thread.user_id,
            user_identifier=thread.user_identifier,
            tags=self._deserialize_tags(thread.tags),
            metadata=thread.thread_metadata if thread.thread_metadata else {},
            is_active=thread.is_active,
            created_at=thread.created_at,
            deleted_at=thread.deleted_at,
            updated_at=thread.updated_at
        )
    
    async def get_thread_author(self, thread_id: str) -> str:
        """获取线程作者"""
        async with await self.db.get_session() as session:
            stmt = select(UserTable.identifier).select_from(
                ThreadTable.__table__.join(UserTable.__table__, ThreadTable.user_id == UserTable.id)
            ).where(ThreadTable.id == thread_id)
            
            result = await session.execute(stmt)
            identifier = result.scalar_one_or_none()
            
            if not identifier:
                raise ValueError(f"Thread {thread_id} not found")
            return identifier

    async def delete_thread(self, thread_id: str):
        """删除线程及其相关数据"""
        async with await self.db.get_session() as session:
            # 先获取需要删除的文件信息
            elements_stmt = select(ElementTable).where(ElementTable.thread_id == thread_id)
            elements_result = await session.execute(elements_stmt)
            elements_list = elements_result.scalars().all()

            # 删除线程（级联删除会处理相关的steps, elements, feedbacks）
            stmt = delete(ThreadTable).where(ThreadTable.id == thread_id)
            await session.execute(stmt)
            await session.commit()
            
            return elements_list  # 返回元素信息供存储客户端删除文件

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        """列出线程"""
        async with await self.db.get_session() as session:
            # 构建基础查询使用 ORM
            stmt = select(ThreadTable, UserTable.identifier, UserTable.user_uuid).select_from(
                ThreadTable.__table__.join(UserTable.__table__, ThreadTable.user_id == UserTable.id, isouter=True)
            ).where(ThreadTable.deleted_at.is_(None))

            # 添加过滤条件
            if filters.search:
                stmt = stmt.where(ThreadTable.name.ilike(f"%{filters.search}%"))

            if filters.userId:
                stmt = stmt.where(ThreadTable.user_id == int(filters.userId))

            if pagination.cursor:
                # 获取游标线程的创建时间
                cursor_stmt = select(ThreadTable.created_at).where(ThreadTable.id == pagination.cursor)
                cursor_result = await session.execute(cursor_stmt)
                cursor_time = cursor_result.scalar_one_or_none()
                if cursor_time:
                    stmt = stmt.where(ThreadTable.created_at < cursor_time)

            # 排序和限制
            stmt = stmt.order_by(ThreadTable.created_at.desc()).limit(pagination.first + 1)

            result = await session.execute(stmt)
            rows = result.all()

            has_next_page = len(rows) > pagination.first
            if has_next_page:
                rows = rows[:-1]

            thread_dicts = []
            for thread, user_identifier, user_uuid in rows:
                thread_dict = ThreadDict(
                    id=str(thread.id),
                    createdAt=thread.created_at.isoformat(),
                    name=thread.name,
                    userId=str(user_uuid) if user_uuid else None,
                    userIdentifier=user_identifier,
                    metadata=thread.thread_metadata if thread.thread_metadata else {},
                    steps=[],
                    elements=[],
                    tags=self._deserialize_tags(thread.tags),
                )
                thread_dicts.append(thread_dict)

            return PaginatedResponse(
                pageInfo=PageInfo(
                    hasNextPage=has_next_page,
                    startCursor=thread_dicts[0]["id"] if thread_dicts else None,
                    endCursor=thread_dicts[-1]["id"] if thread_dicts else None,
                ),
                data=thread_dicts,
            )

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        """获取线程详情"""
        async with await self.db.get_session() as session:
            # 使用 relationships 来预加载相关数据
            thread_stmt = select(ThreadTable).options(
                joinedload(ThreadTable.user),
                selectinload(ThreadTable.steps),
                selectinload(ThreadTable.elements)
            ).where(
                and_(ThreadTable.id == thread_id, ThreadTable.deleted_at.is_(None))
            )
            
            result = await session.execute(thread_stmt)
            thread = result.scalar_one_or_none()

            if not thread:
                return None
            
            # 获取步骤的反馈信息（由于复杂的关联，单独查询）
            if thread.steps:
                step_ids = [step.id for step in thread.steps]
                feedbacks_stmt = select(FeedbackTable).where(FeedbackTable.for_id.in_(step_ids))
                feedbacks_result = await session.execute(feedbacks_stmt)
                feedbacks = feedbacks_result.scalars().all()
                
                # 创建反馈映射
                feedback_map = {str(f.for_id): f for f in feedbacks}
            else:
                feedback_map = {}

            return {
                "thread": thread,
                "user_identifier": thread.user.identifier if thread.user else None,
                "user_uuid": str(thread.user.user_uuid) if thread.user else None,
                "steps": thread.steps,
                "elements": thread.elements,
                "feedback_map": feedback_map
            }

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        """更新线程"""
        async with await self.db.get_session() as session:
            thread_name = self._truncate(
                name
                if name is not None
                else (metadata.get("name") if metadata and "name" in metadata else None)
            )

            # Convert UUID user_id to internal SERIAL ID for database storage
            internal_user_id = None
            if user_id:
                try:
                    # Try to parse as UUID - if successful, convert to internal ID
                    import uuid as uuid_module
                    uuid_module.UUID(user_id)  # Validate UUID format
                    # Query to get internal SERIAL ID from UUID using ORM
                    user_stmt = select(UserTable.id).where(UserTable.user_uuid == user_id)
                    user_result = await session.execute(user_stmt)
                    internal_user_id = user_result.scalar_one_or_none()
                except (ValueError, TypeError):
                    # If not a valid UUID, assume it's already an internal ID (legacy)
                    internal_user_id = user_id

            # 构建更新数据
            update_data = {}
            if thread_name is not None:
                update_data["name"] = thread_name
            if internal_user_id is not None:
                update_data["user_id"] = internal_user_id
            if tags is not None:
                # Handle tags for SQLite compatibility
                import json
                if isinstance(tags, list):
                    # For SQLite, store as JSON string
                    update_data["tags"] = json.dumps(tags) if tags else None
                else:
                    update_data["tags"] = tags
            if metadata is not None:
                update_data["thread_metadata"] = metadata

            if update_data:
                update_data["updated_at"] = func.current_timestamp()
                
                # Check if thread exists
                existing_stmt = select(ThreadTable).where(ThreadTable.id == thread_id)
                existing_result = await session.execute(existing_stmt)
                existing_thread = existing_result.scalar_one_or_none()
                
                if existing_thread:
                    # Update existing thread
                    update_stmt = update(ThreadTable).where(
                        ThreadTable.id == thread_id
                    ).values(**update_data)
                    await session.execute(update_stmt)
                else:
                    # Insert new thread
                    insert_data = {"id": thread_id, **update_data}
                    insert_stmt = insert(ThreadTable).values(**insert_data)
                    await session.execute(insert_stmt)
                
                await session.commit()
    
    async def create_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        """创建新线程"""
        await self.update_thread(
            thread_id=thread_id,
            name=name,
            user_id=user_id,
            metadata=metadata,
            tags=tags
        )
    
    async def get_thread_count_by_user(self, user_id: str) -> int:
        """获取用户的线程数量"""
        async with await self.db.get_session() as session:
            stmt = select(func.count(ThreadTable.id)).where(
                and_(
                    ThreadTable.user_id == user_id,
                    ThreadTable.deleted_at.is_(None)
                )
            )
            result = await session.execute(stmt)
            return result.scalar() or 0
    
    async def get_recent_threads(self, user_id: str, limit: int = 10) -> List[ThreadDict]:
        """获取用户最近的线程"""
        async with await self.db.get_session() as session:
            # 使用 ORM 进行 JOIN 查询
            stmt = select(ThreadTable, UserTable.identifier, UserTable.user_uuid).select_from(
                ThreadTable.__table__.join(UserTable.__table__, ThreadTable.user_id == UserTable.id, isouter=True)
            ).where(
                and_(ThreadTable.user_id == user_id, ThreadTable.deleted_at.is_(None))
            ).order_by(ThreadTable.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            rows = result.all()
            
            thread_dicts = []
            for thread, user_identifier, user_uuid in rows:
                thread_dict = ThreadDict(
                    id=str(thread.id),
                    createdAt=thread.created_at.isoformat(),
                    name=thread.name,
                    userId=str(user_uuid) if user_uuid else None,
                    userIdentifier=user_identifier,
                    metadata=thread.thread_metadata if thread.thread_metadata else {},
                    steps=[],
                    elements=[],
                    tags=self._deserialize_tags(thread.tags),
                )
                thread_dicts.append(thread_dict)
            
            return thread_dicts
    
    async def soft_delete_thread(self, thread_id: str):
        """软删除线程"""
        async with await self.db.get_session() as session:
            stmt = update(ThreadTable).where(
                ThreadTable.id == thread_id
            ).values(
                deleted_at=func.current_timestamp(),
                updated_at=func.current_timestamp()
            )
            await session.execute(stmt)
            await session.commit()
    
    async def restore_thread(self, thread_id: str):
        """恢复已软删除的线程"""
        async with await self.db.get_session() as session:
            stmt = update(ThreadTable).where(
                ThreadTable.id == thread_id
            ).values(
                deleted_at=None,
                updated_at=func.current_timestamp()
            )
            await session.execute(stmt)
            await session.commit()
    
    async def get_thread_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """获取线程统计信息"""
        async with await self.db.get_session() as session:
            # 构建条件
            conditions = []
            if user_id:
                conditions.append(ThreadTable.user_id == user_id)
            
            where_clause = and_(*conditions) if conditions else True
            
            # 使用 SQLAlchemy 进行聚合查询
            stmt = select(
                func.count().label('total_threads'),
                func.count().filter(ThreadTable.deleted_at.is_(None)).label('active_threads'),
                func.count().filter(ThreadTable.deleted_at.isnot(None)).label('deleted_threads')
            ).where(where_clause)
            
            result = await session.execute(stmt)
            row = result.fetchone()
            
            return {
                "total_threads": row.total_threads if row else 0,
                "active_threads": row.active_threads if row else 0,
                "deleted_threads": row.deleted_threads if row else 0
            } if row else {
                "total_threads": 0,
                "active_threads": 0,
                "deleted_threads": 0
            }

    async def get_thread_by_id(self, thread_id: str) -> Optional[ThreadInfo]:
        """根据ID获取线程信息"""
        async with await self.db.get_session() as session:
            stmt = select(ThreadTable).where(
                and_(
                    ThreadTable.id == thread_id,
                    ThreadTable.deleted_at.is_(None)
                )
            )
            result = await session.execute(stmt)
            thread = result.scalar_one_or_none()
            
            if not thread:
                return None
            
            return self._thread_to_info(thread)
    
    async def get_thread_with_relationships(self, thread_id: str) -> Optional[ThreadTable]:
        """使用 ORM relationships 获取线程及其相关数据"""
        async with await self.db.get_session() as session:
            stmt = select(ThreadTable).options(
                joinedload(ThreadTable.user),
                selectinload(ThreadTable.steps),
                selectinload(ThreadTable.elements),
                selectinload(ThreadTable.feedbacks)
            ).where(
                and_(ThreadTable.id == thread_id, ThreadTable.deleted_at.is_(None))
            )
            
            result = await session.execute(stmt)
            return result.scalar_one_or_none()
    
    async def get_threads_with_user_info(self, user_id: Optional[int] = None, limit: int = 50) -> List[ThreadTable]:
        """获取带用户信息的线程列表"""
        async with await self.db.get_session() as session:
            stmt = select(ThreadTable).options(
                joinedload(ThreadTable.user)
            ).where(ThreadTable.deleted_at.is_(None))
            
            if user_id:
                stmt = stmt.where(ThreadTable.user_id == user_id)
                
            stmt = stmt.order_by(ThreadTable.created_at.desc()).limit(limit)
            
            result = await session.execute(stmt)
            return result.scalars().all()
    
    async def get_thread_steps_with_elements(self, thread_id: str) -> List[StepsTable]:
        """获取线程的步骤及其元素"""
        async with await self.db.get_session() as session:
            stmt = select(StepsTable).options(
                selectinload(StepsTable.elements)
            ).where(StepsTable.thread_id == thread_id).order_by(StepsTable.start_time)
            
            result = await session.execute(stmt)
            return result.scalars().all() 