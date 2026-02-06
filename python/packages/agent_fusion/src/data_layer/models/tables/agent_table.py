from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime, func, UUID
from .base_table import BaseComponentTable
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy import String as SQLString


class AgentTable(BaseComponentTable):
    """SQLAlchemy ORM model for agents table"""
    __tablename__ = 'agents'
    
    agent_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    name = Column(String(255), nullable=False, unique=True)
    label = Column(String(255))
    provider = Column(String(500), nullable=False)
    component_type_id = Column(Integer, nullable=True)
    version = Column(Integer, default=1)
    component_version = Column(Integer, default=1)
    model_client_id = Column(Integer, ForeignKey('model_clients.id'), nullable=True)
    memory_model_client_id = Column(Integer, ForeignKey('model_clients.id'), nullable=True)
    agent_type = Column(String(50), default='assistant_agent')
    labels = Column(ARRAY(Text), default="[]")
    input_func = Column(String(50), default='input')
    handoff_tools = Column(JSONB, default=[])