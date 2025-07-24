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

from data_layer.models.base_model import BaseModel
from .tables.feedback_table import FeedbackTable
from .tables.step_table import StepsTable

from sqlalchemy import select, insert, update, delete, and_, func, desc, case
from sqlalchemy.sql import func as sql_func


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
            metadata=feedback.feedback_metadata if feedback.feedback_metadata else {},
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
                    step_stmt = select(StepsTable.thread_id).where(StepsTable.id == feedback.forId)
                    step_result = await session.execute(step_stmt)
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
                    existing_feedback.updated_at = datetime.utcnow()
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
        async with await self.db.get_session() as session:
            # Build base query
            stmt = select(
                func.count().label('total_feedbacks'),
                func.avg(FeedbackTable.value).label('avg_rating'),
                func.max(FeedbackTable.value).label('max_rating'),
                func.min(FeedbackTable.value).label('min_rating'),
                func.count(case((FeedbackTable.value >= 4, 1))).label('positive_feedbacks'),
                func.count(case((FeedbackTable.value <= 2, 1))).label('negative_feedbacks')
            )
            
            if thread_id:
                stmt = stmt.where(FeedbackTable.thread_id == thread_id)
            
            result = await session.execute(stmt)
            row = result.first()
            
            if row:
                return {
                    "total_feedbacks": row.total_feedbacks or 0,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else 0,
                    "max_rating": row.max_rating or 0,
                    "min_rating": row.min_rating or 0,
                    "positive_feedbacks": row.positive_feedbacks or 0,
                    "negative_feedbacks": row.negative_feedbacks or 0
                }
            else:
                return {
                    "total_feedbacks": 0,
                    "avg_rating": 0,
                    "max_rating": 0,
                    "min_rating": 0,
                    "positive_feedbacks": 0,
                    "negative_feedbacks": 0
                }

    async def get_feedback_trends(self, days: int = 30) -> List[Dict[str, Any]]:
        """获取反馈趋势（按天统计）"""
        from datetime import timedelta
        
        async with await self.db.get_session() as session:
            cutoff_date = datetime.utcnow() - timedelta(days=days)
            
            stmt = select(
                func.date(FeedbackTable.created_at).label('date'),
                func.count().label('total_count'),
                func.avg(FeedbackTable.value).label('avg_rating')
            ).where(
                FeedbackTable.created_at >= cutoff_date
            ).group_by(
                func.date(FeedbackTable.created_at)
            ).order_by('date')
            
            result = await session.execute(stmt)
            rows = result.all()
            
            return [
                {
                    "date": row.date.isoformat() if row.date else None,
                    "total_count": row.total_count or 0,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else 0
                }
                for row in rows
            ]

    async def get_top_rated_steps(self, limit: int = 10) -> List[Dict[str, Any]]:
        """获取评分最高的步骤"""
        async with await self.db.get_session() as session:
            stmt = select(
                StepsTable.id.label('step_id'),
                StepsTable.name.label('step_name'),
                StepsTable.type.label('step_type'),
                StepsTable.thread_id,
                func.avg(FeedbackTable.value).label('avg_rating'),
                func.count(FeedbackTable.id).label('feedback_count')
            ).join(
                FeedbackTable, StepsTable.id == FeedbackTable.for_id
            ).group_by(
                StepsTable.id, StepsTable.name, StepsTable.type, StepsTable.thread_id
            ).having(
                func.count(FeedbackTable.id) >= 2  # 至少有2个反馈
            ).order_by(
                desc('avg_rating'), desc('feedback_count')
            ).limit(limit)
            
            result = await session.execute(stmt)
            rows = result.all()
            
            return [
                {
                    "step_id": row.step_id,
                    "step_name": row.step_name,
                    "step_type": row.step_type,
                    "thread_id": row.thread_id,
                    "avg_rating": float(row.avg_rating) if row.avg_rating else 0,
                    "feedback_count": row.feedback_count or 0
                }
                for row in rows
            ]

    async def get_feedbacks_with_comments(self, thread_id: Optional[str] = None) -> List[FeedbackDict]:
        """获取带有评论的反馈"""
        async with await self.db.get_session() as session:
            stmt = select(FeedbackTable).where(
                and_(
                    FeedbackTable.comment.isnot(None),
                    FeedbackTable.comment != ''
                )
            )
            
            if thread_id:
                stmt = stmt.where(FeedbackTable.thread_id == thread_id)
            
            stmt = stmt.order_by(desc(FeedbackTable.created_at))
            
            result = await session.execute(stmt)
            feedbacks = result.scalars().all()
            
            return [self._convert_feedback_info_to_dict(self._feedback_to_info(f)) for f in feedbacks]

    async def update_feedback_value(self, feedback_id: str, value: float) -> bool:
        """更新反馈评分"""
        async with await self.db.get_session() as session:
            try:
                stmt = update(FeedbackTable).where(
                    FeedbackTable.id == feedback_id
                ).values(
                    value=int(value),
                    updated_at=datetime.utcnow()
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating feedback value: {e}")
                return False

    async def update_feedback_comment(self, feedback_id: str, comment: str) -> bool:
        """更新反馈评论"""
        async with await self.db.get_session() as session:
            try:
                stmt = update(FeedbackTable).where(
                    FeedbackTable.id == feedback_id
                ).values(
                    comment=comment,
                    updated_at=datetime.utcnow()
                )
                await session.execute(stmt)
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating feedback comment: {e}")
                return False

    async def batch_delete_feedbacks(self, feedback_ids: List[str]) -> int:
        """批量删除反馈"""
        if not feedback_ids:
            return 0
        
        async with await self.db.get_session() as session:
            try:
                stmt = delete(FeedbackTable).where(FeedbackTable.id.in_(feedback_ids))
                result = await session.execute(stmt)
                await session.commit()
                return result.rowcount
            except Exception as e:
                await session.rollback()
                logger.error(f"Error batch deleting feedbacks: {e}")
                return 0

    async def get_feedback_summary_by_type(self, feedback_type: str = "rating") -> Dict[str, Any]:
        """根据反馈类型获取汇总统计"""
        async with await self.db.get_session() as session:
            stmt = select(
                FeedbackTable.feedback_type,
                func.count().label('total_count'),
                func.avg(FeedbackTable.value).label('avg_value'),
                func.stddev(FeedbackTable.value).label('std_deviation')
            ).where(
                FeedbackTable.feedback_type == feedback_type
            ).group_by(FeedbackTable.feedback_type)
            
            result = await session.execute(stmt)
            row = result.first()
            
            if row:
                return {
                    "feedback_type": row.feedback_type,
                    "total_count": row.total_count or 0,
                    "avg_value": float(row.avg_value) if row.avg_value else 0,
                    "std_deviation": float(row.std_deviation) if row.std_deviation else 0
                }
            else:
                return {
                    "feedback_type": feedback_type,
                    "total_count": 0,
                    "avg_value": 0,
                    "std_deviation": 0
                }

