"""
步骤模型

处理步骤相关的所有数据库操作
"""

import json
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
from dataclasses import dataclass
from chainlit.step import StepDict
from chainlit.types import FeedbackDict
from chainlit.logger import logger

from data_layer.models.base_model import BaseModel
from .tables.step_table import StepsTable

from sqlalchemy import select, insert, update, delete, and_, text, or_
from sqlalchemy.sql import func
from sqlalchemy.orm import selectinload

if TYPE_CHECKING:
    from chainlit.step import StepDict

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass
class StepInfo:
    """步骤信息数据类"""
    id: str
    thread_id: Optional[str]
    parent_id: Optional[str]
    input: Any
    metadata: Dict[str, Any]
    name: Optional[str]
    output: Any
    type: str
    start_time: datetime
    end_time: Optional[datetime]
    show_input: str
    is_error: bool
    created_at: datetime
    updated_at: datetime


class StepModel(BaseModel):
    """步骤数据模型"""
    
    def _model_to_info(self, model: StepsTable) -> StepInfo:
        """Convert SQLAlchemy model to StepInfo"""
        return StepInfo(
            id=model.id,
            thread_id=model.thread_id,
            parent_id=model.parent_id,
            input=model.input,
            metadata=model.step_metadata if model.step_metadata else {},
            name=model.name,
            output=model.output,
            type=model.type,
            start_time=model.start_time,
            end_time=model.end_time,
            show_input=model.show_input,
            is_error=model.is_error,
            created_at=model.created_at,
            updated_at=model.updated_at
        )
    
    async def create_step(self, step_dict: StepDict):
        """创建步骤"""
        async with await self.db.get_session() as session:
            try:
                # 检查父步骤是否存在
                if step_dict.get("parentId"):
                    parent_stmt = select(StepsTable).where(StepsTable.id == step_dict["parentId"])
                    parent_result = await session.execute(parent_stmt)
                    parent = parent_result.scalar_one_or_none()
                    if not parent:
                        await self.create_step({
                            "id": step_dict["parentId"],
                            "metadata": {},
                            "type": "run",
                            "createdAt": step_dict.get("createdAt"),
                        })

                timestamp = datetime.utcnow()
                created_at = step_dict.get("createdAt")
                if created_at:
                    timestamp = datetime.strptime(created_at, ISO_FORMAT)

                # 检查步骤是否已存在
                existing_stmt = select(StepsTable).where(StepsTable.id == step_dict["id"])
                existing_result = await session.execute(existing_stmt)
                existing_step = existing_result.scalar_one_or_none()

                if existing_step:
                    # 更新现有步骤
                    if step_dict.get("parentId") is not None:
                        existing_step.parent_id = step_dict["parentId"]
                    if step_dict.get("input") is not None:
                        existing_step.input = step_dict["input"]
                    if step_dict.get("metadata") and step_dict["metadata"] != {}:
                        existing_step.step_metadata = step_dict["metadata"]
                    if step_dict.get("name") is not None:
                        existing_step.name = step_dict["name"]
                    if step_dict.get("output") is not None:
                        existing_step.output = step_dict["output"]
                    if step_dict["type"] != "run":
                        existing_step.type = step_dict["type"]
                    if step_dict.get("threadId") is not None:
                        existing_step.thread_id = step_dict["threadId"]
                    if step_dict.get("showInput") is not None:
                        existing_step.show_input = str(step_dict["showInput"])
                    if step_dict.get("isError") is not None:
                        existing_step.is_error = step_dict["isError"]
                    
                    existing_step.updated_at = func.current_timestamp()
                else:
                    # 创建新步骤
                    new_step = StepsTable(
                        id=step_dict["id"],
                        thread_id=step_dict.get("threadId"),
                        parent_id=step_dict.get("parentId"),
                        input=step_dict.get("input"),
                        step_metadata=step_dict.get("metadata", {}),
                        name=step_dict.get("name"),
                        output=step_dict.get("output"),
                        type=step_dict["type"],
                        start_time=timestamp,
                        end_time=timestamp,
                        show_input=str(step_dict.get("showInput", "json")),
                        is_error=step_dict.get("isError", False)
                    )
                    session.add(new_step)
                
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Error creating step: {e}")
                raise

    async def update_step(self, step_dict: StepDict):
        """更新步骤"""
        await self.create_step(step_dict)

    async def delete_step(self, step_id: str):
        """删除步骤及其相关数据"""
        async with await self.db.get_session() as session:
            try:
                # 删除相关的元素和反馈（保持原生 SQL，因为可能不在同一个 ORM 模型中）
                await session.execute(
                    text('DELETE FROM elements WHERE step_id = :step_id'),
                    {'step_id': step_id}
                )
                await session.execute(
                    text('DELETE FROM feedbacks WHERE for_id = :step_id'),
                    {'step_id': step_id}
                )
                
                # 删除步骤
                stmt = delete(StepsTable).where(StepsTable.id == step_id)
                await session.execute(stmt)
                
                await session.commit()
            except Exception as e:
                await session.rollback()
                logger.error(f"Error deleting step: {e}")
                raise
    
    async def get_step(self, step_id: str) -> Optional[StepDict]:
        """获取步骤详情"""
        async with await self.db.get_session() as session:
            # 使用原生 SQL 查询，因为需要 LEFT JOIN feedbacks
            query = """
            SELECT s.*, 
                   f.id feedback_id, 
                   f.value feedback_value, 
                   f.comment feedback_comment
            FROM steps s 
            LEFT JOIN feedbacks f ON s.id = f.for_id
            WHERE s.id = :step_id
            """
            result = await session.execute(
                text(query),
                {'step_id': step_id}
            )
            row = result.first()
            
            if not row:
                return None
            
            return self._convert_step_row_to_dict(dict(row._mapping))
    
    async def get_step_by_id(self, step_id: str) -> Optional[StepInfo]:
        """根据ID获取步骤信息（纯ORM版本）"""
        async with await self.db.get_session() as session:
            stmt = select(StepsTable).where(StepsTable.id == step_id)
            result = await session.execute(stmt)
            step = result.scalar_one_or_none()
            
            if step:
                return self._model_to_info(step)
            return None
    
    async def get_steps_by_thread(self, thread_id: str) -> List[StepDict]:
        """获取线程的所有步骤"""
        async with await self.db.get_session() as session:
            query = """
            SELECT s.*, 
                   f.id feedback_id, 
                   f.value feedback_value, 
                   f.comment feedback_comment
            FROM steps s 
            LEFT JOIN feedbacks f ON s.id = f.for_id
            WHERE s.thread_id = :thread_id
            ORDER BY s.start_time
            """
            result = await session.execute(
                text(query),
                {'thread_id': thread_id}
            )
            rows = result.fetchall()
            
            return [self._convert_step_row_to_dict(dict(row._mapping)) for row in rows]
    
    async def get_steps_by_thread_orm(self, thread_id: str) -> List[StepInfo]:
        """获取线程的所有步骤（纯ORM版本）"""
        async with await self.db.get_session() as session:
            stmt = (
                select(StepsTable)
                .where(StepsTable.thread_id == thread_id)
                .order_by(StepsTable.start_time)
            )
            result = await session.execute(stmt)
            steps = result.scalars().all()
            
            return [self._model_to_info(step) for step in steps]
    
    async def get_child_steps(self, parent_id: str) -> List[StepDict]:
        """获取子步骤"""
        async with await self.db.get_session() as session:
            query = """
            SELECT s.*, 
                   f.id feedback_id, 
                   f.value feedback_value, 
                   f.comment feedback_comment
            FROM steps s 
            LEFT JOIN feedbacks f ON s.id = f.for_id
            WHERE s.parent_id = :parent_id
            ORDER BY s.start_time
            """
            result = await session.execute(
                text(query),
                {'parent_id': parent_id}
            )
            rows = result.fetchall()
            
            return [self._convert_step_row_to_dict(dict(row._mapping)) for row in rows]
    
    async def get_child_steps_orm(self, parent_id: str) -> List[StepInfo]:
        """获取子步骤（纯ORM版本）"""
        async with await self.db.get_session() as session:
            stmt = (
                select(StepsTable)
                .where(StepsTable.parent_id == parent_id)
                .order_by(StepsTable.start_time)
            )
            result = await session.execute(stmt)
            steps = result.scalars().all()
            
            return [self._model_to_info(step) for step in steps]
    
    async def get_root_steps(self, thread_id: str) -> List[StepDict]:
        """获取根步骤（没有父步骤的步骤）"""
        async with await self.db.get_session() as session:
            query = """
            SELECT s.*, 
                   f.id feedback_id, 
                   f.value feedback_value, 
                   f.comment feedback_comment
            FROM steps s 
            LEFT JOIN feedbacks f ON s.id = f.for_id
            WHERE s.thread_id = :thread_id AND s.parent_id IS NULL
            ORDER BY s.start_time
            """
            result = await session.execute(
                text(query),
                {'thread_id': thread_id}
            )
            rows = result.fetchall()
            
            return [self._convert_step_row_to_dict(dict(row._mapping)) for row in rows]
    
    async def get_root_steps_orm(self, thread_id: str) -> List[StepInfo]:
        """获取根步骤（纯ORM版本）"""
        async with await self.db.get_session() as session:
            stmt = (
                select(StepsTable)
                .where(and_(
                    StepsTable.thread_id == thread_id,
                    StepsTable.parent_id.is_(None)
                ))
                .order_by(StepsTable.start_time)
            )
            result = await session.execute(stmt)
            steps = result.scalars().all()
            
            return [self._model_to_info(step) for step in steps]
    
    async def update_step_output(self, step_id: str, output: Any):
        """更新步骤输出"""
        async with await self.db.get_session() as session:
            try:
                stmt = (
                    update(StepsTable)
                    .where(StepsTable.id == step_id)
                    .values(
                        output=output,
                        end_time=func.current_timestamp(),
                        updated_at=func.current_timestamp()
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating step output: {e}")
                raise
    
    async def mark_step_as_error(self, step_id: str, error_message: str = None):
        """标记步骤为错误状态"""
        async with await self.db.get_session() as session:
            try:
                # 获取现有步骤
                stmt_select = select(StepsTable).where(StepsTable.id == step_id)
                result = await session.execute(stmt_select)
                step = result.scalar_one_or_none()
                
                if step:
                    step.is_error = True
                    step.end_time = func.current_timestamp()
                    step.updated_at = func.current_timestamp()
                    if error_message is not None:
                        step.output = error_message
                    
                    await session.commit()
                    return True
                return False
            except Exception as e:
                await session.rollback()
                logger.error(f"Error marking step as error: {e}")
                raise
    
    async def get_step_statistics(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """获取步骤统计信息"""
        async with await self.db.get_session() as session:
            # Check database type to use appropriate duration calculation
            engine_dialect = session.bind.dialect.name
            
            if engine_dialect == 'postgresql':
                duration_calc = "AVG(EXTRACT(EPOCH FROM (end_time - start_time)))"
            else:  # SQLite and other databases
                duration_calc = "AVG(CAST((julianday(end_time) - julianday(start_time)) * 86400 AS REAL))"
            
            base_query = f"""
            SELECT 
                COUNT(*) as total_steps,
                COUNT(CASE WHEN is_error = 1 THEN 1 END) as error_steps,
                COUNT(CASE WHEN is_error = 0 THEN 1 END) as success_steps,
                {duration_calc} as avg_duration_seconds
            FROM steps
            """
            params = {}
            
            if thread_id:
                base_query += " WHERE thread_id = :thread_id"
                params['thread_id'] = thread_id
            
            result = await session.execute(text(base_query), params)
            row = result.first()
            
            if row:
                return dict(row._mapping)
            else:
                return {
                    "total_steps": 0,
                    "error_steps": 0,
                    "success_steps": 0,
                    "avg_duration_seconds": 0
                }
    
    async def get_steps_by_type(self, step_type: str, thread_id: Optional[str] = None) -> List[StepDict]:
        """根据类型获取步骤"""
        async with await self.db.get_session() as session:
            query = """
            SELECT s.*, 
                   f.id feedback_id, 
                   f.value feedback_value, 
                   f.comment feedback_comment
            FROM steps s 
            LEFT JOIN feedbacks f ON s.id = f.for_id
            WHERE s.type = :step_type
            """
            params = {'step_type': step_type}
            
            if thread_id:
                query += " AND s.thread_id = :thread_id"
                params['thread_id'] = thread_id
            
            query += " ORDER BY s.start_time"
            
            result = await session.execute(text(query), params)
            rows = result.fetchall()
            
            return [self._convert_step_row_to_dict(dict(row._mapping)) for row in rows]
    
    async def get_steps_by_type_orm(self, step_type: str, thread_id: Optional[str] = None) -> List[StepInfo]:
        """根据类型获取步骤（纯ORM版本）"""
        async with await self.db.get_session() as session:
            conditions = [StepsTable.type == step_type]
            if thread_id:
                conditions.append(StepsTable.thread_id == thread_id)
            
            stmt = (
                select(StepsTable)
                .where(and_(*conditions))
                .order_by(StepsTable.start_time)
            )
            result = await session.execute(stmt)
            steps = result.scalars().all()
            
            return [self._model_to_info(step) for step in steps]
    
    async def get_steps_by_error_status(self, is_error: bool, thread_id: Optional[str] = None) -> List[StepInfo]:
        """根据错误状态获取步骤"""
        async with await self.db.get_session() as session:
            conditions = [StepsTable.is_error == is_error]
            if thread_id:
                conditions.append(StepsTable.thread_id == thread_id)
            
            stmt = (
                select(StepsTable)
                .where(and_(*conditions))
                .order_by(StepsTable.start_time)
            )
            result = await session.execute(stmt)
            steps = result.scalars().all()
            
            return [self._model_to_info(step) for step in steps]
    
    async def get_steps_by_time_range(self, start_time: datetime, end_time: datetime, thread_id: Optional[str] = None) -> List[StepInfo]:
        """根据时间范围获取步骤"""
        async with await self.db.get_session() as session:
            conditions = [
                StepsTable.start_time >= start_time,
                StepsTable.start_time <= end_time
            ]
            if thread_id:
                conditions.append(StepsTable.thread_id == thread_id)
            
            stmt = (
                select(StepsTable)
                .where(and_(*conditions))
                .order_by(StepsTable.start_time)
            )
            result = await session.execute(stmt)
            steps = result.scalars().all()
            
            return [self._model_to_info(step) for step in steps]
    
    async def update_step_metadata(self, step_id: str, metadata: Dict[str, Any]) -> bool:
        """更新步骤元数据"""
        async with await self.db.get_session() as session:
            try:
                stmt = (
                    update(StepsTable)
                    .where(StepsTable.id == step_id)
                    .values(
                        step_metadata=metadata,
                        updated_at=func.current_timestamp()
                    )
                )
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount > 0
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating step metadata: {e}")
                raise
    
    async def bulk_update_steps(self, step_updates: List[Dict[str, Any]]) -> int:
        """批量更新步骤"""
        async with await self.db.get_session() as session:
            try:
                updated_count = 0
                for update_data in step_updates:
                    step_id = update_data.pop('id')
                    update_data['updated_at'] = func.current_timestamp()
                    
                    stmt = (
                        update(StepsTable)
                        .where(StepsTable.id == step_id)
                        .values(**update_data)
                    )
                    result = await session.execute(stmt)
                    updated_count += result.rowcount
                
                await session.commit()
                return updated_count
            except Exception as e:
                await session.rollback()
                logger.error(f"Error bulk updating steps: {e}")
                raise
    
    async def delete_steps_by_thread(self, thread_id: str) -> int:
        """删除线程的所有步骤"""
        async with await self.db.get_session() as session:
            try:
                # 删除相关的元素和反馈
                await session.execute(
                    text('DELETE FROM elements WHERE step_id IN (SELECT id FROM steps WHERE thread_id = :thread_id)'),
                    {'thread_id': thread_id}
                )
                await session.execute(
                    text('DELETE FROM feedbacks WHERE for_id IN (SELECT id FROM steps WHERE thread_id = :thread_id)'),
                    {'thread_id': thread_id}
                )
                
                # 删除步骤
                stmt = delete(StepsTable).where(StepsTable.thread_id == thread_id)
                result = await session.execute(stmt)
                deleted_count = result.rowcount
                
                await session.commit()
                return deleted_count
            except Exception as e:
                await session.rollback()
                logger.error(f"Error deleting steps by thread: {e}")
                raise
    
    def _extract_feedback_dict_from_step_row(self, row: Dict) -> Optional[FeedbackDict]:
        """从步骤行数据中提取反馈信息"""
        if row.get("feedback_id") is not None:
            return FeedbackDict(
                forId=str(row["id"]),
                id=str(row["feedback_id"]),
                value=row["feedback_value"],
                comment=row["feedback_comment"],
            )
        return None

    def _convert_step_row_to_dict(self, row: Dict) -> StepDict:
        """将数据库行转换为步骤字典"""
        metadata = row.get("metadata", {})
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, ValueError):
                metadata = {}
        
        return StepDict(
            id=str(row["id"]),
            threadId=str(row["thread_id"]) if row.get("thread_id") else "",
            parentId=str(row["parent_id"]) if row.get("parent_id") else None,
            name=str(row.get("name", "")),
            type=row["type"],
            input=row.get("input", {}),
            output=row.get("output", {}),
            metadata=metadata,
            createdAt=row["created_at"].isoformat() if row.get("created_at") else None,
            start=row["start_time"].isoformat() if row.get("start_time") else None,
            showInput=row.get("show_input"),
            isError=row.get("is_error"),
            end=row["end_time"].isoformat() if row.get("end_time") else None,
            feedback=self._extract_feedback_dict_from_step_row(row),
        ) 