"""
步骤模型

处理步骤相关的所有数据库操作
"""

import json
from typing import Optional, Dict, Any, List, TYPE_CHECKING
from datetime import datetime
from chainlit.step import StepDict
from chainlit.types import FeedbackDict
from chainlit.logger import logger

from chainlit_web.data_layer.models.base_model import BaseModel

if TYPE_CHECKING:
    from chainlit.step import StepDict

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class StepModel(BaseModel):
    """步骤数据模型"""
    
    async def create_step(self, step_dict: StepDict):
        """创建步骤"""
        # 检查线程是否存在
        if step_dict.get("threadId"):
            thread_query = 'SELECT id FROM threads WHERE id = $1'
            thread_results = await self.execute_query(thread_query, [step_dict["threadId"]])
            if not thread_results:
                # 如果线程不存在，需要先创建（这通常由调用者处理）
                pass

        # 检查父步骤是否存在
        if step_dict.get("parentId"):
            parent_query = 'SELECT id FROM steps WHERE id = $1'
            parent_results = await self.execute_query(parent_query, [step_dict["parentId"]])
            if not parent_results:
                await self.create_step({
                    "id": step_dict["parentId"],
                    "metadata": {},
                    "type": "run",
                    "createdAt": step_dict.get("createdAt"),
                })

        query = """
        INSERT INTO steps (
            id, thread_id, parent_id, input, metadata, name, output,
            type, start_time, end_time, show_input, is_error
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
        )
        ON CONFLICT (id) DO UPDATE SET
            parent_id = COALESCE(EXCLUDED.parent_id, steps.parent_id),
            input = COALESCE(EXCLUDED.input, steps.input),
            metadata = CASE 
                WHEN EXCLUDED.metadata <> '{}' THEN EXCLUDED.metadata 
                ELSE steps.metadata 
            END,
            name = COALESCE(EXCLUDED.name, steps.name),
            output = COALESCE(EXCLUDED.output, steps.output),
            type = CASE 
                WHEN EXCLUDED.type = 'run' THEN steps.type 
                ELSE EXCLUDED.type 
            END,
            thread_id = COALESCE(EXCLUDED.thread_id, steps.thread_id),
            end_time = COALESCE(EXCLUDED.end_time, steps.end_time),
            start_time = LEAST(EXCLUDED.start_time, steps.start_time),
            show_input = COALESCE(EXCLUDED.show_input, steps.show_input),
            is_error = COALESCE(EXCLUDED.is_error, steps.is_error)
        """

        timestamp = await self.get_current_timestamp()
        created_at = step_dict.get("createdAt")
        if created_at:
            timestamp = datetime.strptime(created_at, ISO_FORMAT)

        params = [
            step_dict["id"],
            step_dict.get("threadId"),
            step_dict.get("parentId"),
            step_dict.get("input"),
            json.dumps(step_dict.get("metadata", {})),
            step_dict.get("name"),
            step_dict.get("output"),
            step_dict["type"],
            timestamp,
            timestamp,
            str(step_dict.get("showInput", "json")),
            step_dict.get("isError", False),
        ]
        await self.execute_command(query, params)

    async def update_step(self, step_dict: StepDict):
        """更新步骤"""
        await self.create_step(step_dict)

    async def delete_step(self, step_id: str):
        """删除步骤及其相关数据"""
        # 删除相关的元素和反馈
        await self.execute_command(
            'DELETE FROM elements WHERE step_id = $1', [step_id]
        )
        await self.execute_command(
            'DELETE FROM feedbacks WHERE for_id = $1', [step_id]
        )
        # 删除步骤
        await self.execute_command(
            'DELETE FROM steps WHERE id = $1', [step_id]
        )
    
    async def get_step(self, step_id: str) -> Optional[StepDict]:
        """获取步骤详情"""
        query = """
        SELECT s.*, 
               f.id feedback_id, 
               f.value feedback_value, 
               f.comment feedback_comment
        FROM steps s 
        LEFT JOIN feedbacks f ON s.id = f.for_id
        WHERE s.id = $1
        """
        result = await self.execute_single_query(query, [step_id])
        
        if not result:
            return None
        
        return self._convert_step_row_to_dict(result)
    
    async def get_steps_by_thread(self, thread_id: str) -> List[StepDict]:
        """获取线程的所有步骤"""
        query = """
        SELECT s.*, 
               f.id feedback_id, 
               f.value feedback_value, 
               f.comment feedback_comment
        FROM steps s 
        LEFT JOIN feedbacks f ON s.id = f.for_id
        WHERE s.thread_id = $1
        ORDER BY s.start_time
        """
        results = await self.execute_query(query, [thread_id])
        
        return [self._convert_step_row_to_dict(row) for row in results]
    
    async def get_child_steps(self, parent_id: str) -> List[StepDict]:
        """获取子步骤"""
        query = """
        SELECT s.*, 
               f.id feedback_id, 
               f.value feedback_value, 
               f.comment feedback_comment
        FROM steps s 
        LEFT JOIN feedbacks f ON s.id = f.for_id
        WHERE s.parent_id = $1
        ORDER BY s.start_time
        """
        results = await self.execute_query(query, [parent_id])
        
        return [self._convert_step_row_to_dict(row) for row in results]
    
    async def get_root_steps(self, thread_id: str) -> List[StepDict]:
        """获取根步骤（没有父步骤的步骤）"""
        query = """
        SELECT s.*, 
               f.id feedback_id, 
               f.value feedback_value, 
               f.comment feedback_comment
        FROM steps s 
        LEFT JOIN feedbacks f ON s.id = f.for_id
        WHERE s.thread_id = $1 AND s.parent_id IS NULL
        ORDER BY s.start_time
        """
        results = await self.execute_query(query, [thread_id])
        
        return [self._convert_step_row_to_dict(row) for row in results]
    
    async def update_step_output(self, step_id: str, output: Any):
        """更新步骤输出"""
        query = """
        UPDATE steps 
        SET output = $1, end_time = CURRENT_TIMESTAMP
        WHERE id = $2
        """
        await self.execute_command(query, [output, step_id])
    
    async def mark_step_as_error(self, step_id: str, error_message: str = None):
        """标记步骤为错误状态"""
        query = """
        UPDATE steps 
        SET is_error = TRUE, 
            end_time = CURRENT_TIMESTAMP,
            output = COALESCE($1, output)
        WHERE id = $2
        """
        await self.execute_command(query, [error_message, step_id])
    
    async def get_step_statistics(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """获取步骤统计信息"""
        base_query = """
        SELECT 
            COUNT(*) as total_steps,
            COUNT(CASE WHEN is_error = TRUE THEN 1 END) as error_steps,
            COUNT(CASE WHEN is_error = FALSE THEN 1 END) as success_steps,
            AVG(EXTRACT(EPOCH FROM (end_time - start_time))) as avg_duration_seconds
        FROM steps
        """
        params = []
        
        if thread_id:
            base_query += " WHERE thread_id = $1"
            params.append(thread_id)
        
        result = await self.execute_single_query(base_query, params)
        return dict(result) if result else {
            "total_steps": 0,
            "error_steps": 0,
            "success_steps": 0,
            "avg_duration_seconds": 0
        }
    
    async def get_steps_by_type(self, step_type: str, thread_id: Optional[str] = None) -> List[StepDict]:
        """根据类型获取步骤"""
        query = """
        SELECT s.*, 
               f.id feedback_id, 
               f.value feedback_value, 
               f.comment feedback_comment
        FROM steps s 
        LEFT JOIN feedbacks f ON s.id = f.for_id
        WHERE s.type = $1
        """
        params = [step_type]
        
        if thread_id:
            query += " AND s.thread_id = $2"
            params.append(thread_id)
        
        query += " ORDER BY s.start_time"
        
        results = await self.execute_query(query, params)
        return [self._convert_step_row_to_dict(row) for row in results]
    
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
        return StepDict(
            id=str(row["id"]),
            threadId=str(row["thread_id"]) if row.get("thread_id") else "",
            parentId=str(row["parent_id"]) if row.get("parent_id") else None,
            name=str(row.get("name", "")),
            type=row["type"],
            input=row.get("input", {}),
            output=row.get("output", {}),
            metadata=json.loads(row.get("metadata", "{}")),
            createdAt=row["created_at"].isoformat() if row.get("created_at") else None,
            start=row["start_time"].isoformat() if row.get("start_time") else None,
            showInput=row.get("show_input"),
            isError=row.get("is_error"),
            end=row["end_time"].isoformat() if row.get("end_time") else None,
            feedback=self._extract_feedback_dict_from_step_row(row),
        ) 