from sqlalchemy import Column, Integer, String, Text, DateTime, func, ForeignKey
from .base_table import Base


class UserActivityLogsTable(Base):
    """SQLAlchemy ORM model for user_activity_logs table"""
    __tablename__ = 'user_activity_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.id'), nullable=True)
    activity_type = Column(String(255), nullable=False)
    action_details = Column(Text)
    ip_address = Column(String(45))  # IPv6 max length
    status = Column(String(50), default='success')
    created_at = Column(DateTime, server_default=func.current_timestamp())