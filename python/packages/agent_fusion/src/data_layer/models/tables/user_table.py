from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUuid
from .base_table import Base


class UserTable(Base):
    """SQLAlchemy ORM model for User table"""
    __tablename__ = 'User'
    
    id = Column(Integer, primary_key=True)
    user_uuid = Column(PGUuid, unique=True, server_default=func.gen_random_uuid())
    username = Column(String(255), unique=True, nullable=False)
    identifier = Column(String(255), unique=True, nullable=False)
    email = Column(String(255), nullable=False)
    password_hash = Column(String(255))
    role = Column(String(50), default='user')
    first_name = Column(String(255))
    last_name = Column(String(255))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    last_login = Column(DateTime)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    user_metadata = Column(JSONB, default={})