from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .base_table import BaseComponentTable, Base


class PromptTable(BaseComponentTable):
    """SQLAlchemy ORM model for prompts table"""
    __tablename__ = 'prompts'
    
    prompt_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    prompt_id = Column(String(255), nullable=False, unique=True)
    name = Column(String(255), nullable=False)
    category = Column(String(100))
    subcategory = Column(String(100))
    agent_id = Column(Integer, ForeignKey('agents.id'))
    group_chat_id = Column(Integer, ForeignKey('group_chats.id'))
    
    # Relationships
    versions = relationship("PromptVersionTable", back_populates="prompt")


class PromptVersionTable(Base):
    """SQLAlchemy ORM model for prompt_versions table"""
    __tablename__ = 'prompt_versions'
    
    id = Column(Integer, primary_key=True)
    prompt_id = Column(Integer, ForeignKey('prompts.id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    version_label = Column(String(255))
    content = Column(Text, nullable=False)
    status = Column(String(50), default='active')
    is_current = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    change_description = Column(Text)
    
    # Relationships
    prompt = relationship("PromptTable", back_populates="versions")