from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UUID, ARRAY
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
    subcategories = Column(ARRAY(String))  # PostgreSQL TEXT[] array type
    agent_id = Column(Integer, ForeignKey('agents.id'))
    group_chat_id = Column(Integer, ForeignKey('group_chats.id'))
    
    # Relationships
    versions = relationship("PromptVersionTable", back_populates="prompt")


class PromptVersionTable(Base):
    """SQLAlchemy ORM model for prompt_versions table"""
    __tablename__ = 'prompt_versions'

    id = Column(Integer, primary_key=True)
    version_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    prompt_id = Column(Integer, ForeignKey('prompts.id'), nullable=False)
    version_number = Column(Integer, nullable=False)
    version_label = Column(String(100))  # e.g., 'v1.0', 'v1.1-beta'
    content = Column(Text, nullable=False)
    content_hash = Column(String(64))  # SHA256 hash of content for integrity
    status = Column(String(50), default='draft')  # draft, review, approved, deprecated
    created_by = Column(Integer, ForeignKey('User.id'))
    created_at = Column(DateTime, server_default=func.current_timestamp())
    approved_by = Column(Integer, ForeignKey('User.id'))
    approved_at = Column(DateTime)
    is_current = Column(Boolean, default=False)

    # Relationships
    prompt = relationship("PromptTable", back_populates="versions")