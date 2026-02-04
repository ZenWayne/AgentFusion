from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from .base_table import Base

class AgentMemoriesTable(Base):
    """SQLAlchemy ORM model for agent_memories table"""
    __tablename__ = 'agent_memories'
    
    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Integer, ForeignKey('User.id', ondelete='CASCADE'), nullable=False)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('threads.id'), nullable=True)
    memory_key = Column(String(255), nullable=False, index=True)
    memory_type = Column(String(50))
    summary = Column(Text)
    content = Column(Text)
    content_metadata = Column(JSONB, default={})
    created_at = Column(DateTime, server_default=func.current_timestamp())
    is_active = Column(Boolean, default=True)
    
    # Relationships
    # user = relationship("UserTable") # Add if UserTable is available and needed
    # agent = relationship("AgentTable")
    # thread = relationship("ThreadTable")
