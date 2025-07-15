"""
反馈模型

处理反馈相关的所有数据库操作
"""

import json
import uuid
from typing import Optional, Dict, Any, List
from chainlit.types import Feedback, FeedbackDict
from chainlit.logger import logger

from chainlit_web.data_layer.models.base_model import BaseModel


class FeedbackModel(BaseModel):
    """反馈数据模型"""
    
    async def upsert_feedback(self, feedback: Feedback) -> str:
        """创建或更新反馈"""
        feedback_id = feedback.id or str(uuid.uuid4())
        
        # 从步骤获取thread_id（如果没有提供的话）
        thread_id = None
        if feedback.forId:
            step_query = """SELECT thread_id FROM steps WHERE id = $1"""
            step_result = await self.execute_single_query(step_query, [feedback.forId])
            thread_id = step_result["thread_id"] if step_result else None
        
        query = """
        INSERT INTO feedbacks (id, for_id, thread_id, user_id, value, comment, feedback_type)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (id) DO UPDATE
        SET value = EXCLUDED.value, comment = EXCLUDED.comment
        RETURNING id
        """
        
        params = [
            feedback_id,
            feedback.forId,
            thread_id,
            None,  # user_id 将由认证上下文设置
            float(feedback.value),
            feedback.comment,
            "rating",  # 默认反馈类型
        ]
        
        result = await self.execute_single_query(query, params)
        return str(result["id"])

    async def delete_feedback(self, feedback_id: str) -> bool:
        """删除反馈"""
        query = """
        DELETE FROM feedbacks WHERE id = $1
        """
        await self.execute_command(query, [feedback_id])
        return True

    async def get_feedback(self, feedback_id: str) -> Optional[FeedbackDict]:
        """获取反馈详情"""
        query = """
        SELECT * FROM feedbacks WHERE id = $1
        """
        result = await self.execute_single_query(query, [feedback_id])
        
        if not result:
            return None
        
        return self._convert_feedback_row_to_dict(result)

    async def get_feedbacks_by_step(self, step_id: str) -> List[FeedbackDict]:
        """获取步骤的所有反馈"""
        query = """
        SELECT * FROM feedbacks 
        WHERE for_id = $1
        ORDER BY created_at DESC
        """
        results = await self.execute_query(query, [step_id])
        
        return [self._convert_feedback_row_to_dict(row) for row in results]

    async def get_feedbacks_by_thread(self, thread_id: str) -> List[FeedbackDict]:
        """获取线程的所有反馈"""
        query = """
        SELECT * FROM feedbacks 
        WHERE thread_id = $1
        ORDER BY created_at DESC
        """
        results = await self.execute_query(query, [thread_id])
        
        return [self._convert_feedback_row_to_dict(row) for row in results]

    async def get_feedbacks_by_user(self, user_id: str) -> List[FeedbackDict]:
        """获取用户的所有反馈"""
        query = """
        SELECT * FROM feedbacks 
        WHERE user_id = $1
        ORDER BY created_at DESC
        """
        results = await self.execute_query(query, [user_id])
        
        return [self._convert_feedback_row_to_dict(row) for row in results]

    async def get_feedback_statistics(self, thread_id: Optional[str] = None) -> Dict[str, Any]:
        """获取反馈统计信息"""
        base_query = """
        SELECT 
            COUNT(*) as total_feedbacks,
            AVG(value) as avg_rating,
            MAX(value) as max_rating,
            MIN(value) as min_rating,
            COUNT(CASE WHEN value >= 4 THEN 1 END) as positive_feedbacks,
            COUNT(CASE WHEN value <= 2 THEN 1 END) as negative_feedbacks
        FROM feedbacks
        """
        params = []
        
        if thread_id:
            base_query += " WHERE thread_id = $1"
            params.append(thread_id)
        
        result = await self.execute_single_query(base_query, params)
        return dict(result) if result else {
            "total_feedbacks": 0,
            "avg_rating": 0,
            "max_rating": 0,
            "min_rating": 0,
            "positive_feedbacks": 0,
            "negative_feedbacks": 0
        }

    async def get_feedback_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """获取反馈趋势（按天统计）"""
        query = """
        SELECT 
            DATE(created_at) as date,
            COUNT(*) as total_count,
            AVG(value) as avg_rating
        FROM feedbacks 
        WHERE created_at >= CURRENT_DATE - INTERVAL '%s days'
        GROUP BY DATE(created_at)
        ORDER BY date
        """
        results = await self.execute_query(query % days, [])
        
        return [
            {
                "date": row["date"].isoformat(),
                "total_count": row["total_count"],
                "avg_rating": float(row["avg_rating"]) if row["avg_rating"] else 0
            }
            for row in results
        ]

    async def get_top_rated_steps(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取评分最高的步骤"""
        query = """
        SELECT 
            s.id as step_id,
            s.name as step_name,
            s.type as step_type,
            s.thread_id,
            AVG(f.value) as avg_rating,
            COUNT(f.id) as feedback_count
        FROM steps s
        JOIN feedbacks f ON s.id = f.for_id
        GROUP BY s.id, s.name, s.type, s.thread_id
        HAVING COUNT(f.id) >= 2  -- 至少有2个反馈
        ORDER BY avg_rating DESC, feedback_count DESC
        LIMIT $1
        """
        results = await self.execute_query(query, [limit])
        
        return [
            {
                "step_id": row["step_id"],
                "step_name": row["step_name"],
                "step_type": row["step_type"],
                "thread_id": row["thread_id"],
                "avg_rating": float(row["avg_rating"]),
                "feedback_count": row["feedback_count"]
            }
            for row in results
        ]

    async def get_feedbacks_with_comments(self, thread_id: Optional[str] = None) -> List[FeedbackDict]:
        """获取带有评论的反馈"""
        query = """
        SELECT * FROM feedbacks 
        WHERE comment IS NOT NULL AND comment != ''
        """
        params = []
        
        if thread_id:
            query += " AND thread_id = $1"
            params.append(thread_id)
        
        query += " ORDER BY created_at DESC"
        
        results = await self.execute_query(query, params)
        return [self._convert_feedback_row_to_dict(row) for row in results]

    async def update_feedback_value(self, feedback_id: str, value: float) -> bool:
        """更新反馈评分"""
        query = """
        UPDATE feedbacks 
        SET value = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """
        await self.execute_command(query, [value, feedback_id])
        return True

    async def update_feedback_comment(self, feedback_id: str, comment: str) -> bool:
        """更新反馈评论"""
        query = """
        UPDATE feedbacks 
        SET comment = $1, updated_at = CURRENT_TIMESTAMP
        WHERE id = $2
        """
        await self.execute_command(query, [comment, feedback_id])
        return True

    async def batch_delete_feedbacks(self, feedback_ids: List[str]) -> int:
        """批量删除反馈"""
        if not feedback_ids:
            return 0
        
        query = """
        DELETE FROM feedbacks 
        WHERE id = ANY($1)
        """
        await self.execute_command(query, [feedback_ids])
        return len(feedback_ids)

    async def get_feedback_summary_by_type(self, feedback_type: str = "rating") -> Dict[str, Any]:
        """根据反馈类型获取汇总统计"""
        query = """
        SELECT 
            feedback_type,
            COUNT(*) as total_count,
            AVG(value) as avg_value,
            STDDEV(value) as std_deviation
        FROM feedbacks 
        WHERE feedback_type = $1
        GROUP BY feedback_type
        """
        result = await self.execute_single_query(query, [feedback_type])
        
        return dict(result) if result else {
            "feedback_type": feedback_type,
            "total_count": 0,
            "avg_value": 0,
            "std_deviation": 0
        }

    def _convert_feedback_row_to_dict(self, row: Dict) -> FeedbackDict:
        """将数据库行转换为反馈字典"""
        return FeedbackDict(
            id=str(row["id"]),
            forId=str(row["for_id"]),
            value=row["value"],
            comment=row.get("comment"),
        ) 