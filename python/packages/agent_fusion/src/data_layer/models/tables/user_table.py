from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey, CheckConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUuid
from sqlalchemy.orm import relationship
from .base_table import Base


class UserTable(Base):
    """SQLAlchemy ORM model for User table"""
    __tablename__ = 'User'
    
    id = Column(Integer, primary_key=True)
    user_uuid = Column(PGUuid, unique=True, server_default=func.gen_random_uuid())
    username = Column(String(100), unique=True, nullable=False)
    identifier = Column(String(100), unique=True, nullable=False)
    email = Column(String(255), unique=True, nullable=False)
    password_hash = Column(String(255))
    role = Column(String(50), default='user')
    first_name = Column(String(100))
    last_name = Column(String(100))
    is_active = Column(Boolean, default=True)
    is_verified = Column(Boolean, default=False)
    failed_login_attempts = Column(Integer, default=0)
    locked_until = Column(DateTime)
    last_login = Column(DateTime)
    avatar_url = Column(String(500))
    timezone = Column(String(50), default='UTC')
    language = Column(String(10), default='en')
    email_verified_at = Column(DateTime)
    phone = Column(String(20))
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)  # Self-referencing FK to User.id
    user_metadata = Column(JSONB, default={})
    
    # Relationships
    threads = relationship("ThreadTable", back_populates="user")
    feedbacks = relationship("FeedbackTable", back_populates="user")
    
    __table_args__ = (
        CheckConstraint('role IN ("user", "admin", "reviewer", "developer", "system")', name='check_role'),
    )