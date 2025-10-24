from sqlalchemy import Column, Integer, String, func, UUID
from sqlalchemy.dialects.postgresql import JSONB
from .base_table import BaseComponentTable


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
    read_timeout_seconds = Column(Integer, default=5)