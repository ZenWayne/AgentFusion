from sqlalchemy import Column, Integer, String, Text, UUID, ARRAY
from sqlalchemy.sql import func
from .base_table import BaseComponentTable


class GroupChatTable(BaseComponentTable):
    """SQLAlchemy ORM model for group_chats table"""
    __tablename__ = 'group_chats'
    
    group_chat_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    name = Column(String(255), nullable=False, unique=True)
    type = Column(String(100), nullable=False)
    labels = Column(ARRAY(Text), default=[])
    selector_prompt = Column(Text)
    handoff_target = Column(String(255), default='user')
    termination_condition = Column(String(255), default='handoff')
    model_client = Column(String(255))
    component_type_id = Column(Integer)
    version = Column(Integer, default=1)
    component_version = Column(Integer, default=1)