from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UUID, ARRAY
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .base_table import Base


class ThreadTable(Base):
    """SQLAlchemy ORM model for threads table"""
    __tablename__ = 'threads'
    
    id = Column(UUID, primary_key=True, server_default=func.gen_random_uuid())
    name = Column(Text)
    user_id = Column(Integer, ForeignKey('User.id', ondelete='CASCADE'), nullable=False)
    user_identifier = Column(Text)  # Legacy compatibility field
    tags = Column(ARRAY(Text))
    thread_metadata = Column(JSONB, default={})
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    deleted_at = Column(DateTime)
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    
    # Relationships
    user = relationship("UserTable", back_populates="threads")
    steps = relationship("StepsTable", back_populates="thread", cascade="all, delete-orphan")
    elements = relationship("ElementTable", back_populates="thread", cascade="all, delete-orphan")
    feedbacks = relationship("FeedbackTable", back_populates="thread", cascade="all, delete-orphan")