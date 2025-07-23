from sqlalchemy import Column, Integer, String, Text, DateTime, func, ForeignKey, TypeDecorator
from sqlalchemy.dialects.postgresql import JSONB, INET
from sqlalchemy.dialects.sqlite import NUMERIC
from .base_table import Base


class IPAddress(TypeDecorator):
    """Database-agnostic IP address type"""
    impl = String
    cache_ok = True
    
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(INET())
        else:
            # For SQLite and other databases, use String
            return dialect.type_descriptor(String(45))
    
    def process_bind_param(self, value, dialect):
        # Handle None/NULL values
        if value is None:
            return None
        return str(value)
    
    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return str(value)


class UserActivityLogsTable(Base):
    """SQLAlchemy ORM model for user_activity_logs table"""
    __tablename__ = 'user_activity_logs'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('User.id'), nullable=True)
    activity_type = Column(String(50), nullable=False)
    resource_type = Column(String(50))
    resource_id = Column(Integer)
    action_details = Column(JSONB, default={})
    ip_address = Column(IPAddress)
    user_agent = Column(Text)
    session_id = Column(Integer, nullable=True)  # TODO: Add FK when user_sessions table is created
    api_key_id = Column(Integer, nullable=True)  # TODO: Add FK when user_api_keys table is created
    status = Column(String(20), default='success')
    error_message = Column(Text)
    created_at = Column(DateTime, server_default=func.current_timestamp())