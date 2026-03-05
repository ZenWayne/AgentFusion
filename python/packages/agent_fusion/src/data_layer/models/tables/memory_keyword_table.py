"""
记忆关键词关联表

用于关键词搜索功能。
"""

from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, Index
from sqlalchemy.sql import func
from .base_table import Base


class AgentMemoryKeywordsTable(Base):
    """记忆关键词关联表"""
    __tablename__ = 'agent_memory_keywords'

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_key = Column(String(255), ForeignKey('agent_memories.memory_key', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.id', ondelete='CASCADE'), nullable=False)
    keyword = Column(String(255), nullable=False, index=True)
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime, server_default=func.current_timestamp())

    # 复合索引
    __table_args__ = (
        Index('idx_memory_keywords_user_key', 'user_id', 'memory_key'),
        Index('idx_memory_keywords_user_kw', 'user_id', 'keyword'),
    )
