"""
反馈模型

处理反馈相关的所有数据库操作
"""

import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass
from chainlit.types import Feedback, FeedbackDict
from chainlit.logger import logger

from chainlit_web.data_layer.models.base_model import BaseModel

from sqlalchemy import select, insert, update, delete, and_, text, UUID, Column, Integer, String, Text, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

class FeedbackTable(Base):
    """SQLAlchemy ORM model for feedbacks table"""
    __tablename__ = 'feedbacks'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    for_id = Column(UUID, nullable=False)
    thread_id = Column(UUID, ForeignKey('threads.id', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.id', ondelete='SET NULL'))
    value = Column(Integer, nullable=False)
    comment = Column(Text)
    feedback_type = Column(String(50), default='rating')
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())


@dataclass
class FeedbackInfo:
    """反馈信息数据类"""
    id: str
    for_id: str
    thread_id: str
    user_id: Optional[int]
    value: int
    comment: Optional[str]
    feedback_type: str
    metadata: Dict[str, Any]
    created_at: datetime
    updated_at: datetime


class FeedbackModel(BaseModel):
    """反馈数据模型"""
    
    def _feedback_to_info(self, feedback: FeedbackTable) -> FeedbackInfo:
        """Convert SQLAlchemy model to FeedbackInfo"""
        return FeedbackInfo(
            id=str(feedback.id),
            for_id=str(feedback.for_id),
            thread_id=str(feedback.thread_id),
            user_id=feedback.user_id,
            value=feedback.value,
            comment=feedback.comment,
            feedback_type=feedback.feedback_type,
            metadata=feedback.metadata if feedback.metadata else {},
            created_at=feedback.created_at,
            updated_at=feedback.updated_at
        )
    
    def _convert_feedback_info_to_dict(self, feedback_info: FeedbackInfo) -> FeedbackDict:
        """Convert FeedbackInfo to FeedbackDict"""
        return FeedbackDict(
            id=feedback_info.id,
            forId=feedback_info.for_id,
            value=feedback_info.value,
            comment=feedback_info.comment,
        )
    
    async def upsert_feedback(self, feedback: Feedback) -> str:
        """创建或更新反馈"""
        feedback_id = feedback.id or str(uuid.uuid4())
        
        async with await self.db.get_session() as session:
            try:
                # 从步骤获取thread_id（如果没有提供的话）
                thread_id = None
                if feedback.forId:
                    step_result = await session.execute(
                        text("SELECT thread_id FROM steps WHERE id = :step_id"), 
                        {'step_id': feedback.forId}
                    )
                    step_row = step_result.first()
                    thread_id = step_row[0] if step_row else None
                
                # 检查是否已存在
                existing_stmt = select(FeedbackTable).where(FeedbackTable.id == feedback_id)
                existing_result = await session.execute(existing_stmt)
                existing_feedback = existing_result.scalar_one_or_none()
                
                if existing_feedback:
                    # 更新现有反馈
                    existing_feedback.value = int(feedback.value)
                    existing_feedback.comment = feedback.comment
                    existing_feedback.updated_at = func.current_timestamp()
                else:
                    # 创建新反馈
                    new_feedback = FeedbackTable(
                        id=feedback_id,
                        for_id=feedback.forId,
                        thread_id=thread_id,
                        user_id=None,  # user_id 将由认证上下文设置
                        value=int(feedback.value),
                        comment=feedback.comment,
                        feedback_type="rating",
                        metadata={}
                    )
                    session.add(new_feedback)
                
                await session.commit()
                return feedback_id
            except Exception as e:
                await session.rollback()
                logger.error(f"Error upserting feedback: {e}")
                raise

    async def delete_feedback(self, feedback_id: str) -> bool:
        """删除反馈"""
        async with await self.db.get_session() as session:
            try:
                stmt = delete(FeedbackTable).where(FeedbackTable.id == feedback_id)
                await session.execute(stmt)
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Error deleting feedback: {e}")
                return False

    async def get_feedback(self, feedback_id: str) -> Optional[FeedbackDict]:
        """获取反馈详情"""
        async with await self.db.get_session() as session:
            stmt = select(FeedbackTable).where(FeedbackTable.id == feedback_id)
            result = await session.execute(stmt)
            feedback = result.scalar_one_or_none()
            
            if not feedback:
                return None
            
            feedback_info = self._feedback_to_info(feedback)
            return self._convert_feedback_info_to_dict(feedback_info)

    async def get_feedbacks_by_step(self, step_id: str) -> List[FeedbackDict]:
        """获取步骤的所有反馈"""
        async with await self.db.get_session() as session:
            stmt = select(FeedbackTable).where(
                FeedbackTable.for_id == step_id
            ).order_by(FeedbackTable.created_at.desc())
            
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()
            
            return [self._convert_feedback_info_to_dict(self._feedback_to_info(f)) for f in feedbacks]

    async def get_feedbacks_by_thread(self, thread_id: str) -> List[FeedbackDict]:
        """获取线程的所有反馈"""
        async with await self.db.get_session() as session:
            stmt = select(FeedbackTable).where(
                FeedbackTable.thread_id == thread_id
            ).order_by(FeedbackTable.created_at.desc())
            
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()
            
            return [self._convert_feedback_info_to_dict(self._feedback_to_info(f)) for f in feedbacks]

    async def get_feedbacks_by_user(self, user_id: str) -> List[FeedbackDict]:
        """获取用户的所有反馈"""
        async with await self.db.get_session() as session:
            stmt = select(FeedbackTable).where(
                FeedbackTable.user_id == int(user_id)
            ).order_by(FeedbackTable.created_at.desc())
            
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()
            
            return [self._convert_feedback_info_to_dict(self._feedback_to_info(f)) for f in feedbacks]

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

