from sqlalchemy import Column, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from .base_table import Base


class StepsTable(Base):
    """SQLAlchemy ORM model for steps table"""
    __tablename__ = 'steps'
    
    id = Column(String, primary_key=True)
    thread_id = Column(String)
    parent_id = Column(String)
    input = Column(Text)
    step_metadata = Column(JSONB, default={})
    name = Column(String)
    output = Column(Text)
    type = Column(String, nullable=False)
    start_time = Column(DateTime, server_default=func.current_timestamp())
    end_time = Column(DateTime)
    show_input = Column(String, default='json')
    is_error = Column(Boolean, default=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())