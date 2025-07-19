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

from chainlit_web.data_layer.models.base_model import BaseModel

from sqlalchemy import select, insert, update, delete, and_, or_, UUID, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class ThreadTable(Base):
    """SQLAlchemy ORM model for threads table"""
    __tablename__ = 'threads'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    name = Column(Text)
    user_id = Column(Integer, ForeignKey('"User".id', ondelete='CASCADE'), nullable=False)
    user_identifier = Column(Text)  # Legacy compatibility field
    tags = Column(ARRAY(Text))
    metadata = Column(JSONB, default={})
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    deleted_at = Column(DateTime)
    updated_at = Column(DateTime, server_default=func.current_timestamp())


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
    
    def _thread_to_info(self, thread: ThreadTable) -> ThreadInfo:
        """Convert SQLAlchemy model to ThreadInfo"""
        return ThreadInfo(
            id=str(thread.id),
            name=thread.name,
            user_id=thread.user_id,
            user_identifier=thread.user_identifier,
            tags=thread.tags,
            metadata=thread.metadata if thread.metadata else {},
            is_active=thread.is_active,
            created_at=thread.created_at,
            deleted_at=thread.deleted_at,
            updated_at=thread.updated_at
        )
    
    async def get_thread_author(self, thread_id: str) -> str:
        """获取线程作者"""
        async with await self.db.get_session() as session:
            # 需要导入 User 表，这里先使用原始查询
            query = """
            SELECT u.identifier 
            FROM threads t
            JOIN "User" u ON t."user_id" = u.id
            WHERE t.id = $1
            """
            result = await session.execute(query, [thread_id])
            row = result.fetchone()
            if not row:
                raise ValueError(f"Thread {thread_id} not found")
            return row[0]

    async def delete_thread(self, thread_id: str):
        """删除线程及其相关数据"""
        async with await self.db.get_session() as session:
            # 先获取需要删除的文件信息
            elements_query = """
            SELECT * FROM elements 
            WHERE thread_id = $1
            """
            elements_result = await session.execute(elements_query, [thread_id])
            elements_results = elements_result.fetchall()

            # 删除线程（级联删除会处理相关的steps, elements, feedbacks）
            stmt = delete(ThreadTable).where(ThreadTable.id == thread_id)
            await session.execute(stmt)
            await session.commit()
            
            return elements_results  # 返回元素信息供存储客户端删除文件

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        """列出线程"""
        async with await self.db.get_session() as session:
            # 构建基础查询 - 由于复杂的 JOIN 和计算，暂时保持原始 SQL
            query = """
            SELECT 
                t.*, 
                u.identifier as user_identifier,
                u.user_uuid as user_uuid,
                (SELECT COUNT(*) FROM threads WHERE "user_id" = t."user_id") as total
            FROM threads t
            LEFT JOIN "User" u ON t."user_id" = u.id
            WHERE t."deleted_at" IS NULL
            """
            params = []
            param_count = 1

            if filters.search:
                query += f" AND t.name ILIKE ${param_count}"
                params.append(f"%{filters.search}%")
                param_count += 1

            if filters.userId:
                query += f' AND t."user_id" = ${param_count}'
                params.append(int(filters.userId))
                param_count += 1

            if pagination.cursor:
                query += f' AND t."created_at" < (SELECT "created_at" FROM threads WHERE id = ${param_count})'
                params.append(pagination.cursor)
                param_count += 1

            query += f' ORDER BY t."created_at" DESC LIMIT ${param_count}'
            params.append(pagination.first + 1)

            result = await session.execute(query, params)
            threads = result.fetchall()

            has_next_page = len(threads) > pagination.first
            if has_next_page:
                threads = threads[:-1]

            thread_dicts = []
            for thread in threads:
                thread_dict = ThreadDict(
                    id=str(thread.id),
                    createdAt=thread.created_at.isoformat(),
                    name=thread.name,
                    userId=str(thread.user_uuid) if thread.user_uuid else None,
                    userIdentifier=thread.user_identifier,
                    metadata=thread.metadata if thread.metadata else {},
                    steps=[],
                    elements=[],
                    tags=[],
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
            query = """
            SELECT t.*, u.identifier as user_identifier, u.user_uuid as user_uuid
            FROM threads t
            LEFT JOIN "User" u ON t."user_id" = u.id
            WHERE t.id = $1 AND t."deleted_at" IS NULL
            """
            result = await session.execute(query, [thread_id])
            thread = result.fetchone()

            if not thread:
                return None
            
            # 获取步骤和相关反馈
            steps_query = """
            SELECT  s.*, 
                    f.id feedback_id, 
                    f.value feedback_value, 
                    f.comment feedback_comment
            FROM steps s left join feedbacks f on s.id = f.for_id
            WHERE s.thread_id = $1
            ORDER BY start_time
            """
            steps_result = await session.execute(steps_query, [thread_id])
            steps_results = steps_result.fetchall()

            # 获取元素
            elements_query = """
            SELECT * FROM elements 
            WHERE thread_id = $1
            """
            elements_result = await session.execute(elements_query, [thread_id])
            elements_results = elements_result.fetchall()

            return {
                "thread": thread,
                "steps": steps_results,
                "elements": elements_results
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
                    # Query to get internal SERIAL ID from UUID
                    user_query = """SELECT id FROM "User" WHERE user_uuid = $1"""
                    user_result = await session.execute(user_query, [user_id])
                    user_row = user_result.fetchone()
                    if user_row:
                        internal_user_id = user_row[0]
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
                update_data["tags"] = tags
            if metadata is not None:
                update_data["metadata"] = metadata

            if update_data:
                update_data["updated_at"] = func.current_timestamp()
                
                # 使用 UPSERT 操作
                from sqlalchemy.dialects.postgresql import insert
                stmt = insert(ThreadTable).values(
                    id=thread_id,
                    **update_data
                )
                stmt = stmt.on_conflict_do_update(
                    index_elements=['id'],
                    set_=update_data
                )
                
                await session.execute(stmt)
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
            # 由于需要 JOIN 用户信息，暂时保持原始 SQL
            query = """
            SELECT t.*, u.identifier as user_identifier, u.user_uuid as user_uuid
            FROM threads t
            LEFT JOIN "User" u ON t."user_id" = u.id
            WHERE t."user_id" = $1 AND t."deleted_at" IS NULL
            ORDER BY t."created_at" DESC
            LIMIT $2
            """
            result = await session.execute(query, [user_id, limit])
            results = result.fetchall()
            
            thread_dicts = []
            for thread in results:
                thread_dict = ThreadDict(
                    id=str(thread.id),
                    createdAt=thread.created_at.isoformat(),
                    name=thread.name,
                    userId=str(thread.user_uuid) if thread.user_uuid else None,
                    userIdentifier=thread.user_identifier,
                    metadata=thread.metadata if thread.metadata else {},
                    steps=[],
                    elements=[],
                    tags=[],
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