from sqlalchemy import Column, Integer, Boolean, DateTime, ForeignKey, String
from sqlalchemy.sql import func
from .base_table import Base


class AgentMcpServerTable(Base):
    """SQLAlchemy ORM model for agent_mcp_servers relationship table"""
    __tablename__ = 'agent_mcp_servers'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=False)
    mcp_server_id = Column(Integer, ForeignKey('mcp_servers.id'), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer, nullable=True)


class GroupChatParticipantsTable(Base):
    """SQLAlchemy ORM model for group_chat_participants relationship table"""
    __tablename__ = 'group_chat_participants'
    
    id = Column(Integer, primary_key=True)
    group_chat_id = Column(Integer, ForeignKey('group_chats.id'), nullable=False)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=False)
    participant_role = Column(String(100), default='participant')
    join_order = Column(Integer, default=0)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer, nullable=True)