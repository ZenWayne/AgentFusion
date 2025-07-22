from sqlalchemy import Column, String, Text, BigInteger, Integer, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from .base_table import Base


class ElementTable(Base):
    """SQLAlchemy ORM model for elements table"""
    __tablename__ = 'elements'
    
    id = Column(String, primary_key=True)
    thread_id = Column(String, ForeignKey('threads.id'))
    step_id = Column(String, ForeignKey('steps.id'))
    element_metadata = Column(JSONB, default={})
    mime_type = Column(String)
    name = Column(String)
    object_key = Column(String)
    url = Column(String)
    chainlit_key = Column(String)
    display = Column(String)
    size_bytes = Column(BigInteger)
    language = Column(String)
    page_number = Column(Integer)
    props = Column(JSONB, default={})