"""
线程模型

处理线程相关的所有数据库操作
"""

import json
import uuid
from typing import Optional, Dict, Any, List
from chainlit.types import (
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.logger import logger

from chainlit_web.data_layer.models.base_model import BaseModel


class ThreadModel(BaseModel):
    """线程数据模型"""
    
    async def get_thread_author(self, thread_id: str) -> str:
        """获取线程作者"""
        query = """
        SELECT u.identifier 
        FROM threads t
        JOIN "User" u ON t."user_id" = u.id
        WHERE t.id = $1
        """
        result = await self.execute_single_query(query, [thread_id])
        if not result:
            raise ValueError(f"Thread {thread_id} not found")
        return result["identifier"]

    async def delete_thread(self, thread_id: str):
        """删除线程及其相关数据"""
        # 先获取需要删除的文件信息
        elements_query = """
        SELECT * FROM elements 
        WHERE thread_id = $1
        """
        elements_results = await self.execute_query(elements_query, [thread_id])

        # 删除线程（级联删除会处理相关的steps, elements, feedbacks）
        await self.execute_command(
            'DELETE FROM threads WHERE id = $1', [thread_id]
        )
        
        return elements_results  # 返回元素信息供存储客户端删除文件

    async def list_threads(
        self, pagination: Pagination, filters: ThreadFilter
    ) -> PaginatedResponse[ThreadDict]:
        """列出线程"""
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

        results = await self.execute_query(query, params)
        threads = results

        has_next_page = len(threads) > pagination.first
        if has_next_page:
            threads = threads[:-1]

        thread_dicts = []
        for thread in threads:
            thread_dict = ThreadDict(
                id=str(thread["id"]),
                createdAt=thread["created_at"].isoformat(),
                name=thread["name"],
                userId=str(thread["user_uuid"]) if thread["user_uuid"] else None,
                userIdentifier=thread["user_identifier"],
                metadata=json.loads(thread["metadata"]),
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
        query = """
        SELECT t.*, u.identifier as user_identifier, u.user_uuid as user_uuid
        FROM threads t
        LEFT JOIN "User" u ON t."user_id" = u.id
        WHERE t.id = $1 AND t."deleted_at" IS NULL
        """
        result = await self.execute_single_query(query, [thread_id])

        if not result:
            return None

        thread = result
        
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
        steps_results = await self.execute_query(steps_query, [thread_id])

        # 获取元素
        elements_query = """
        SELECT * FROM elements 
        WHERE thread_id = $1
        """
        elements_results = await self.execute_query(elements_query, [thread_id])

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
                user_result = await self.execute_single_query(user_query, [user_id])
                if user_result:
                    internal_user_id = user_result["id"]
            except (ValueError, TypeError):
                # If not a valid UUID, assume it's already an internal ID (legacy)
                internal_user_id = user_id

        data = {
            "id": thread_id,
            "name": thread_name,
            "user_id": internal_user_id,
            "tags": tags,
            "metadata": json.dumps(metadata) if metadata is not None else None,
        }

        # Remove None values
        data = {k: v for k, v in data.items() if v is not None}

        # Build the query dynamically based on available fields
        columns = [f'"{k}"' for k in data.keys()]
        placeholders = [f"${i + 1}" for i in range(len(data))]
        values = list(data.values())

        update_sets = [f'"{k}" = EXCLUDED."{k}"' for k in data.keys() if k != "id"]

        query = f"""
            INSERT INTO threads ({", ".join(columns)})
            VALUES ({", ".join(placeholders)})
            ON CONFLICT (id) DO UPDATE
            SET {", ".join(update_sets)};
        """

        await self.execute_command(query, values)
    
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
        query = """
        SELECT COUNT(*) as count FROM threads 
        WHERE "user_id" = $1 AND "deleted_at" IS NULL
        """
        result = await self.execute_single_query(query, [user_id])
        return result["count"] if result else 0
    
    async def get_recent_threads(self, user_id: str, limit: int = 10) -> List[ThreadDict]:
        """获取用户最近的线程"""
        query = """
        SELECT t.*, u.identifier as user_identifier, u.user_uuid as user_uuid
        FROM threads t
        LEFT JOIN "User" u ON t."user_id" = u.id
        WHERE t."user_id" = $1 AND t."deleted_at" IS NULL
        ORDER BY t."created_at" DESC
        LIMIT $2
        """
        results = await self.execute_query(query, [user_id, limit])
        
        thread_dicts = []
        for thread in results:
            thread_dict = ThreadDict(
                id=str(thread["id"]),
                createdAt=thread["created_at"].isoformat(),
                name=thread["name"],
                userId=str(thread["user_uuid"]) if thread["user_uuid"] else None,
                userIdentifier=thread["user_identifier"],
                metadata=json.loads(thread["metadata"]),
                steps=[],
                elements=[],
                tags=[],
            )
            thread_dicts.append(thread_dict)
        
        return thread_dicts
    
    async def soft_delete_thread(self, thread_id: str):
        """软删除线程"""
        query = """
        UPDATE threads 
        SET "deleted_at" = CURRENT_TIMESTAMP 
        WHERE id = $1
        """
        await self.execute_command(query, [thread_id])
    
    async def restore_thread(self, thread_id: str):
        """恢复已软删除的线程"""
        query = """
        UPDATE threads 
        SET "deleted_at" = NULL 
        WHERE id = $1
        """
        await self.execute_command(query, [thread_id])
    
    async def get_thread_statistics(self, user_id: Optional[str] = None) -> Dict[str, Any]:
        """获取线程统计信息"""
        base_query = """
        SELECT 
            COUNT(*) as total_threads,
            COUNT(CASE WHEN "deleted_at" IS NULL THEN 1 END) as active_threads,
            COUNT(CASE WHEN "deleted_at" IS NOT NULL THEN 1 END) as deleted_threads
        FROM threads
        """
        params = []
        
        if user_id:
            base_query += " WHERE \"user_id\" = $1"
            params.append(user_id)
        
        result = await self.execute_single_query(base_query, params)
        return dict(result) if result else {
            "total_threads": 0,
            "active_threads": 0,
            "deleted_threads": 0
        } 