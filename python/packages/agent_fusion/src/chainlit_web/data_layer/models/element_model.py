"""
元素模型

处理元素相关的所有数据库操作
"""

import json
import aiofiles
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from chainlit.element import ElementDict
from chainlit.logger import logger

from chainlit_web.data_layer.models.base_model import BaseModel

if TYPE_CHECKING:
    from chainlit.element import Element


class ElementModel(BaseModel):
    """元素数据模型"""
    
    async def create_element(self, element: "Element", storage_client=None):
        """创建元素"""
        if not element.for_id:
            return

        # 检查线程是否存在
        if element.thread_id:
            query = 'SELECT id FROM threads WHERE id = $1'
            results = await self.execute_query(query, [element.thread_id])
            if not results:
                # 如果线程不存在，需要先创建（这通常由调用者处理）
                pass

        # 检查步骤是否存在
        if element.for_id:
            query = 'SELECT id FROM steps WHERE id = $1'
            results = await self.execute_query(query, [element.for_id])
            if not results:
                # 如果步骤不存在，需要先创建（这通常由调用者处理）
                pass

        content: Optional[Union[bytes, str]] = None

        if element.path:
            async with aiofiles.open(element.path, "rb") as f:
                content = await f.read()
        elif element.content:
            content = element.content
        elif not element.url:
            raise ValueError("Element url, path or content must be provided")

        # 构建存储路径
        if element.thread_id:
            path = f"threads/{element.thread_id}/files/{element.id}"
        else:
            path = f"files/{element.id}"

        # 如果有存储客户端，上传文件
        if content is not None and storage_client:
            await storage_client.upload_file(
                object_key=path,
                data=content,
                mime=element.mime or "application/octet-stream",
                overwrite=True,
            )

        query = """
        INSERT INTO elements (
            id, thread_id, step_id, metadata, mime_type, name, object_key, url,
            chainlit_key, display, size_bytes, language, page_number, props
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14
        )
        ON CONFLICT (id) DO UPDATE SET
            props = EXCLUDED.props
        """
        params = [
            element.id,
            element.thread_id,
            element.for_id,
            json.dumps({
                "size": element.size,
                "language": element.language,
                "display": element.display,
                "type": element.type,
                "page": getattr(element, "page", None),
            }),
            element.mime,
            element.name,
            path,
            element.url,
            element.chainlit_key,
            element.display,
            element.size,
            element.language,
            getattr(element, "page", None),
            json.dumps(getattr(element, "props", {})),
        ]
        await self.execute_command(query, params)

    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional[ElementDict]:
        """获取元素"""
        query = """
        SELECT * FROM elements
        WHERE id = $1 AND thread_id = $2
        """
        result = await self.execute_single_query(query, [element_id, thread_id])

        if not result:
            return None

        return self._convert_element_row_to_dict(result)

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        """删除元素"""
        # 先获取元素信息
        if thread_id:
            query = """
            SELECT * FROM elements
            WHERE id = $1 AND thread_id = $2
            """
            element = await self.execute_single_query(query, [element_id, thread_id])
        else:
            query = """
            SELECT * FROM elements
            WHERE id = $1
            """
            element = await self.execute_single_query(query, [element_id])

        # 删除元素
        if thread_id:
            delete_query = """
            DELETE FROM elements 
            WHERE id = $1 AND thread_id = $2
            """
            await self.execute_command(delete_query, [element_id, thread_id])
        else:
            delete_query = """
            DELETE FROM elements 
            WHERE id = $1
            """
            await self.execute_command(delete_query, [element_id])

        return element  # 返回元素信息供存储客户端删除文件

    async def get_elements_by_thread(self, thread_id: str) -> List[ElementDict]:
        """获取线程的所有元素"""
        query = """
        SELECT * FROM elements 
        WHERE thread_id = $1
        ORDER BY id
        """
        results = await self.execute_query(query, [thread_id])
        
        return [self._convert_element_row_to_dict(row) for row in results]

    async def get_elements_by_step(self, step_id: str) -> List[ElementDict]:
        """获取步骤的所有元素"""
        query = """
        SELECT * FROM elements 
        WHERE step_id = $1
        ORDER BY id
        """
        results = await self.execute_query(query, [step_id])
        
        return [self._convert_element_row_to_dict(row) for row in results]

    async def get_elements_by_type(self, element_type: str, thread_id: Optional[str] = None) -> List[ElementDict]:
        """根据类型获取元素"""
        query = """
        SELECT * FROM elements 
        WHERE metadata->>'type' = $1
        """
        params = [element_type]
        
        if thread_id:
            query += " AND thread_id = $2"
            params.append(thread_id)
        
        query += " ORDER BY id"
        
        results = await self.execute_query(query, params)
        return [self._convert_element_row_to_dict(row) for row in results]

    async def update_element_url(self, element_id: str, url: str):
        """更新元素URL"""
        query = """
        UPDATE elements 
        SET url = $1
        WHERE id = $2
        """
        await self.execute_command(query, [url, element_id])

    async def update_element_props(self, element_id: str, props: Dict[str, Any]):
        """更新元素属性"""
        query = """
        UPDATE elements 
        SET props = $1
        WHERE id = $2
        """
        await self.execute_command(query, [json.dumps(props), element_id])

    async def get_element_statistics(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """获取元素统计信息"""
        base_query = """
        SELECT 
            COUNT(*) as total_elements,
            COUNT(DISTINCT mime_type) as unique_mime_types,
            SUM(size_bytes) as total_size_bytes,
            AVG(size_bytes) as avg_size_bytes
        FROM elements
        """
        params = []
        
        if thread_id:
            base_query += " WHERE thread_id = $1"
            params.append(thread_id)
        
        result = await self.execute_single_query(base_query, params)
        return dict(result) if result else {
            "total_elements": 0,
            "unique_mime_types": 0,
            "total_size_bytes": 0,
            "avg_size_bytes": 0
        }

    async def get_elements_by_mime_type(self, mime_type: str, thread_id: Optional[str] = None) -> List[ElementDict]:
        """根据MIME类型获取元素"""
        query = """
        SELECT * FROM elements 
        WHERE mime_type = $1
        """
        params = [mime_type]
        
        if thread_id:
            query += " AND thread_id = $2"
            params.append(thread_id)
        
        query += " ORDER BY id"
        
        results = await self.execute_query(query, params)
        return [self._convert_element_row_to_dict(row) for row in results]

    async def search_elements(self, search_term: str, thread_id: Optional[str] = None) -> List[ElementDict]:
        """搜索元素"""
        query = """
        SELECT * FROM elements 
        WHERE name ILIKE $1
        """
        params = [f"%{search_term}%"]
        
        if thread_id:
            query += " AND thread_id = $2"
            params.append(thread_id)
        
        query += " ORDER BY id"
        
        results = await self.execute_query(query, params)
        return [self._convert_element_row_to_dict(row) for row in results]

    def _convert_element_row_to_dict(self, row: Dict) -> ElementDict:
        """将数据库行转换为元素字典"""
        metadata = json.loads(row.get("metadata", "{}"))
        return ElementDict(
            id=str(row["id"]),
            threadId=str(row["thread_id"]) if row.get("thread_id") else None,
            type=metadata.get("type", "file"),
            url=row["url"],
            name=row["name"],
            mime=row["mime_type"],
            objectKey=row["object_key"],
            forId=str(row["step_id"]),
            chainlitKey=row.get("chainlit_key"),
            display=row["display"],
            size=row["size_bytes"],
            language=row["language"],
            page=row["page_number"],
            autoPlay=row.get("autoPlay"),
            playerConfig=row.get("playerConfig"),
            props=json.loads(row.get("props") or "{}"),
        ) 