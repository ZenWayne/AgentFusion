"""
元素模型

处理元素相关的所有数据库操作
"""

import json
import aiofiles
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass

from chainlit.element import ElementDict
from chainlit.logger import logger

from data_layer.models.base_model import BaseModel
from .tables.element_table import ElementTable

from sqlalchemy import select, insert, update, delete, and_, or_
from sqlalchemy.sql import func

if TYPE_CHECKING:
    from chainlit.element import Element

@dataclass
class ElementInfo:
    """Element信息数据类"""
    id: str
    thread_id: Optional[str]
    step_id: Optional[str]
    metadata: Dict[str, Any]
    mime_type: Optional[str]
    name: Optional[str]
    object_key: Optional[str]
    url: Optional[str]
    chainlit_key: Optional[str]
    display: Optional[str]
    size_bytes: Optional[int]
    language: Optional[str]
    page_number: Optional[int]
    props: Dict[str, Any]


class ElementModel(BaseModel):
    """元素数据模型"""
    
    def _element_to_info(self, element: ElementTable) -> ElementInfo:
        """Convert SQLAlchemy ElementTable to ElementInfo"""
        return ElementInfo(
            id=element.id,
            thread_id=element.thread_id,
            step_id=element.step_id,
            metadata=element.element_metadata if element.element_metadata else {},
            mime_type=element.mime_type,
            name=element.name,
            object_key=element.object_key,
            url=element.url,
            chainlit_key=element.chainlit_key,
            display=element.display,
            size_bytes=element.size_bytes,
            language=element.language,
            page_number=element.page_number,
            props=element.props if element.props else {}
        )
    
    def _element_to_dict(self, element: ElementTable) -> ElementDict:
        """Convert SQLAlchemy ElementTable to ElementDict"""
        metadata = element.element_metadata if element.element_metadata else {}
        return ElementDict(
            id=str(element.id),
            threadId=str(element.thread_id) if element.thread_id else None,
            type=metadata.get("type", "file"),
            url=element.url,
            name=element.name,
            mime=element.mime_type,
            objectKey=element.object_key,
            forId=str(element.step_id) if element.step_id else None,
            chainlitKey=element.chainlit_key,
            display=element.display,
            size=element.size_bytes,
            language=element.language,
            page=element.page_number,
            autoPlay=metadata.get("autoPlay"),
            playerConfig=metadata.get("playerConfig"),
            props=element.props if element.props else {},
        )
    
    async def create_element(self, element: "Element", storage_client=None):
        """创建元素"""
        if not element.for_id:
            return

        async with await self.db.get_session() as session:
            # 检查线程是否存在（如果需要）
            if element.thread_id:
                # Note: Thread existence check moved to calling code
                pass

            # 检查步骤是否存在（如果需要）
            if element.for_id:
                # Note: Step existence check moved to calling code
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

            # 构建元素数据
            metadata = {
                "size": element.size,
                "language": element.language,
                "display": element.display,
                "type": element.type,
                "page": getattr(element, "page", None),
            }
            
            props = getattr(element, "props", {})

            try:
                # 首先尝试插入
                new_element = ElementTable(
                    id=element.id,
                    thread_id=element.thread_id,
                    step_id=element.for_id,
                    metadata=metadata,
                    mime_type=element.mime,
                    name=element.name,
                    object_key=path,
                    url=element.url,
                    chainlit_key=element.chainlit_key,
                    display=element.display,
                    size_bytes=element.size,
                    language=element.language,
                    page_number=getattr(element, "page", None),
                    props=props
                )
                
                session.add(new_element)
                await session.commit()
                
            except Exception:
                # 如果插入失败（冲突），则更新props
                await session.rollback()
                
                stmt = update(ElementTable).where(
                    ElementTable.id == element.id
                ).values(props=props)
                
                await session.execute(stmt)
                await session.commit()

    async def get_element(
        self, thread_id: str, element_id: str
    ) -> Optional[ElementDict]:
        """获取元素"""
        async with await self.db.get_session() as session:
            stmt = select(ElementTable).where(and_(
                ElementTable.id == element_id,
                ElementTable.thread_id == thread_id
            ))
            
            result = await session.execute(stmt)
            element = result.scalar_one_or_none()
            
            if not element:
                return None
            
            return self._element_to_dict(element)

    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        """删除元素"""
        async with await self.db.get_session() as session:
            # 先获取元素信息
            if thread_id:
                stmt = select(ElementTable).where(and_(
                    ElementTable.id == element_id,
                    ElementTable.thread_id == thread_id
                ))
            else:
                stmt = select(ElementTable).where(
                    ElementTable.id == element_id
                )
            
            result = await session.execute(stmt)
            element = result.scalar_one_or_none()
            
            if not element:
                return None
            
            # 保存元素信息以便返回
            element_dict = self._convert_element_row_to_dict({
                "id": element.id,
                "thread_id": element.thread_id,
                "step_id": element.step_id,
                "metadata": json.dumps(element.element_metadata if element.element_metadata else {}),
                "mime_type": element.mime_type,
                "name": element.name,
                "object_key": element.object_key,
                "url": element.url,
                "chainlit_key": element.chainlit_key,
                "display": element.display,
                "size_bytes": element.size_bytes,
                "language": element.language,
                "page_number": element.page_number,
                "props": json.dumps(element.props if element.props else {})
            })
            
            # 删除元素
            if thread_id:
                delete_stmt = delete(ElementTable).where(and_(
                    ElementTable.id == element_id,
                    ElementTable.thread_id == thread_id
                ))
            else:
                delete_stmt = delete(ElementTable).where(
                    ElementTable.id == element_id
                )
            
            await session.execute(delete_stmt)
            await session.commit()
            
            return element_dict  # 返回元素信息供存储客户端删除文件

    async def get_elements_by_thread(self, thread_id: str) -> List[ElementDict]:
        """获取线程的所有元素"""
        async with await self.db.get_session() as session:
            stmt = select(ElementTable).where(
                ElementTable.thread_id == thread_id
            ).order_by(ElementTable.id)
            
            result = await session.execute(stmt)
            elements = result.scalars().all()
            
            return [self._element_to_dict(element) for element in elements]

    async def get_elements_by_step(self, step_id: str) -> List[ElementDict]:
        """获取步骤的所有元素"""
        async with await self.db.get_session() as session:
            stmt = select(ElementTable).where(
                ElementTable.step_id == step_id
            ).order_by(ElementTable.id)
            
            result = await session.execute(stmt)
            elements = result.scalars().all()
            
            return [self._element_to_dict(element) for element in elements]

    async def get_elements_by_type(self, element_type: str, thread_id: Optional[str] = None) -> List[ElementDict]:
        """根据类型获取元素"""
        async with await self.db.get_session() as session:
            stmt = select(ElementTable).where(
                ElementTable.element_metadata['type'].astext == element_type
            )
            
            if thread_id:
                stmt = stmt.where(ElementTable.thread_id == thread_id)
                
            stmt = stmt.order_by(ElementTable.id)
            
            result = await session.execute(stmt)
            elements = result.scalars().all()
            
            return [self._element_to_dict(element) for element in elements]

    async def update_element_url(self, element_id: str, url: str):
        """更新元素URL"""
        async with await self.db.get_session() as session:
            stmt = update(ElementTable).where(
                ElementTable.id == element_id
            ).values(url=url)
            
            await session.execute(stmt)
            await session.commit()

    async def update_element_props(self, element_id: str, props: Dict[str, Any]):
        """更新元素属性"""
        async with await self.db.get_session() as session:
            stmt = update(ElementTable).where(
                ElementTable.id == element_id
            ).values(props=props)
            
            await session.execute(stmt)
            await session.commit()

    async def get_element_statistics(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """获取元素统计信息"""
        async with await self.db.get_session() as session:
            stmt = select(
                func.count().label('total_elements'),
                func.count(func.distinct(ElementTable.mime_type)).label('unique_mime_types'),
                func.sum(ElementTable.size_bytes).label('total_size_bytes'),
                func.avg(ElementTable.size_bytes).label('avg_size_bytes')
            )
            
            if thread_id:
                stmt = stmt.where(ElementTable.thread_id == thread_id)
            
            result = await session.execute(stmt)
            row = result.first()
            
            if not row:
                return {
                    "total_elements": 0,
                    "unique_mime_types": 0,
                    "total_size_bytes": 0,
                    "avg_size_bytes": 0
                }
            
            return {
                "total_elements": row[0] or 0,
                "unique_mime_types": row[1] or 0,
                "total_size_bytes": row[2] or 0,
                "avg_size_bytes": float(row[3]) if row[3] else 0.0
            }

    async def get_elements_by_mime_type(self, mime_type: str, thread_id: Optional[str] = None) -> List[ElementDict]:
        """根据MIME类型获取元素"""
        async with await self.db.get_session() as session:
            stmt = select(ElementTable).where(
                ElementTable.mime_type == mime_type
            )
            
            if thread_id:
                stmt = stmt.where(ElementTable.thread_id == thread_id)
                
            stmt = stmt.order_by(ElementTable.id)
            
            result = await session.execute(stmt)
            elements = result.scalars().all()
            
            return [self._element_to_dict(element) for element in elements]

    async def search_elements(self, search_term: str, thread_id: Optional[str] = None) -> List[ElementDict]:
        """搜索元素"""
        async with await self.db.get_session() as session:
            stmt = select(ElementTable).where(
                ElementTable.name.ilike(f"%{search_term}%")
            )
            
            if thread_id:
                stmt = stmt.where(ElementTable.thread_id == thread_id)
                
            stmt = stmt.order_by(ElementTable.id)
            
            result = await session.execute(stmt)
            elements = result.scalars().all()
            
            return [self._element_to_dict(element) for element in elements]

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