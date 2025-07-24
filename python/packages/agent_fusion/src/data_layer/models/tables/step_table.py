from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from .base_table import Base


class StepsTable(Base):
    """SQLAlchemy ORM model for steps table"""
    __tablename__ = 'steps'
    
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('threads.id', ondelete='CASCADE'))
    parent_id = Column(String, ForeignKey('steps.id', ondelete='CASCADE'))
    input = Column(JSONB)  # Changed from Text to JSONB for better JSON handling
    step_metadata = Column(JSONB, default={})  # metadata is reserved in SQLAlchemy
    name = Column(String)
    output = Column(JSONB)  # Changed from Text to JSONB for better JSON handling
    type = Column(String, nullable=False)
    start_time = Column(DateTime, server_default=func.current_timestamp())
    end_time = Column(DateTime)
    show_input = Column(String, default='json')
    is_error = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp(), onupdate=func.current_timestamp())
    
    # Relationships
    thread = relationship("ThreadTable", back_populates="steps")
    parent = relationship("StepsTable", remote_side=[id], back_populates="children")  
    children = relationship("StepsTable", back_populates="parent")
    elements = relationship("ElementTable", back_populates="step")