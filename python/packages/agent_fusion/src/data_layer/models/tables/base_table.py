from sqlalchemy import Column, Integer, Text, DateTime, Boolean, func
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class BaseComponentTable(Base):
    """组件表的基类，包含所有组件共有的字段"""
    __abstract__ = True
    
    id = Column(Integer, primary_key=True)
    description = Column(Text)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    updated_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer)
    updated_by = Column(Integer)
    is_active = Column(Boolean, default=True)