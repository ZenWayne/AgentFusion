from sqlalchemy import Column, Integer, String, ForeignKey, Boolean, Text, DateTime, func, UUID
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base
from .base_table import BaseComponentTable

Base = declarative_base()


class McpServerTable(BaseComponentTable):
    """SQLAlchemy ORM model for mcp_servers table"""
    __tablename__ = 'mcp_servers'
    
    server_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    name = Column(String(255), nullable=False, unique=True)
    command = Column(String(500))
    args = Column(JSONB, default=[])
    env = Column(JSONB, default={})
    url = Column(String(500))
    headers = Column(JSONB, default={})
    timeout = Column(Integer, default=30)
    sse_read_timeout = Column(Integer, default=30)