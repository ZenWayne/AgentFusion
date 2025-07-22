from sqlalchemy import Column, Integer, String, Text, DateTime, ForeignKey, UUID
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from .base_table import Base


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
    feedback_metadata = Column(JSONB, default={})
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())