from sqlalchemy import Column, Integer, String, UUID
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from .base_table import BaseComponentTable


class ModelClientTable(BaseComponentTable):
    """SQLAlchemy ORM model for model_clients table"""
    __tablename__ = 'model_clients'
    
    client_uuid = Column(UUID, unique=True, server_default=func.gen_random_uuid())
    label = Column(String(255), nullable=False, unique=True)
    provider = Column(String(500), nullable=False)
    component_type_id = Column(Integer)
    version = Column(Integer, default=1)
    component_version = Column(Integer, default=1)
    model_name = Column(String(255))
    base_url = Column(String(500))
    api_key_type = Column(String(64))
    model_info = Column(JSONB, default={})
    config = Column(JSONB, default={})