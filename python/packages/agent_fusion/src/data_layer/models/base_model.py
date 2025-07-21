"""
基础模型类

提供所有模型的通用功能和接口
"""

import asyncio
from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union, Type

if TYPE_CHECKING:
    from data_layer.base_data_layer import DBDataLayer

from schemas.component import ComponentInfo
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, UUID, select, and_, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB

Base = declarative_base()

# Relationship tables
class AgentMcpServerTable(Base):
    """SQLAlchemy ORM model for agent_mcp_servers relationship table"""
    __tablename__ = 'agent_mcp_servers'
    
    id = Column(Integer, primary_key=True)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=False)
    mcp_server_id = Column(Integer, ForeignKey('mcp_servers.id'), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    created_by = Column(Integer, nullable=True)


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


class BaseModel:
    """所有数据模型的基类"""
    
    def __init__(self, db_layer: "DBDataLayer"):
        """
        初始化基础模型
        
        Args:
            db_layer: 数据库操作层实例
        """
        self.db = db_layer
    
    async def execute_query(
        self, query: str, params: Union[Dict, List, None] = None
    ) -> List[Dict[str, Any]]:
        """执行查询"""
        return await self.db.execute_query(query, params)
    
    async def execute_single_query(
        self, query: str, params: Union[Dict, List, None] = None
    ) -> Optional[Dict[str, Any]]:
        """执行单条查询"""
        return await self.db.execute_single_query(query, params)
    
    async def execute_command(
        self, query: str, params: Union[Dict, List, None] = None
    ) -> str:
        """执行命令"""
        return await self.db.execute_command(query, params)
    
    async def execute_with_connection(self, func, *args, **kwargs):
        """使用连接执行函数"""
        return await self.db.execute_with_connection(func, *args, **kwargs)
    
    async def transaction(self, func, *args, **kwargs):
        """在事务中执行函数"""
        return await self.db.transaction(func, *args, **kwargs)
    
    async def get_current_timestamp(self):
        """获取当前时间戳"""
        return await self.db.get_current_timestamp()
    
    def _truncate(self, text: Optional[str], max_length: int = 255) -> Optional[str]:
        """截断文本"""
        return self.db._truncate(text, max_length) 

class ComponentModel(BaseModel):
    """组件模型"""
    table_class: Optional[Type[BaseComponentTable]] = None  # 子类需要设置对应的Table类
    uuid_column_name: str = "client_uuid"  # UUID字段名，子类可覆盖
    name_column_name: str = "label"  # 名称字段名，子类可覆盖
    
    @abstractmethod
    async def to_component_info(self, table_row: Any) -> ComponentInfo:
        """将数据库行转换为ComponentInfo对象"""
        pass

    async def get_all_components(self, filter_active: bool = True) -> List[ComponentInfo]:
        """获取所有组件信息,filter_active为True时，只获取active为True的组件，否则不考虑is_active是否为True都选"""
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            name_column = getattr(self.table_class, self.name_column_name)
            stmt = select(self.table_class).order_by(name_column)
            
            if filter_active:
                stmt = stmt.where(self.table_class.is_active == True)
            
            result = await session.execute(stmt)
            table_rows = result.scalars().all()
            
            return await asyncio.gather(*[self.to_component_info(table_row) for table_row in table_rows])

    async def get_all_active_components(self) -> List[ComponentInfo]:
        """获取所有活跃的组件"""
        return await self.get_all_components(filter_active=True)

    async def get_component_by_name(self, component_name: str) -> Optional[ComponentInfo]:
        """根据组件名称获取组件信息"""
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            name_column = getattr(self.table_class, self.name_column_name)
            stmt = select(self.table_class).where(
                and_(
                    name_column == component_name,
                    self.table_class.is_active == True
                )
            )
            
            result = await session.execute(stmt)
            table_row = result.scalar_one_or_none()
            
            if not table_row:
                return None
                
            return await self.to_component_info(table_row)
    
    async def get_component_id_by_uuid(self, component_uuid: str) -> int:
        """根据组件UUID获取组件主键ID"""
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            uuid_column = getattr(self.table_class, self.uuid_column_name)
            stmt = select(self.table_class.id).where(uuid_column == component_uuid)
            result = await session.execute(stmt)
            component_id = result.scalar_one_or_none()
            
            if not component_id:
                raise ValueError(f"Component with UUID '{component_uuid}' not found")
            return component_id
    
    async def get_component_by_uuid(self, component_uuid: str) -> Optional[ComponentInfo]:
        """根据组件UUID获取组件信息"""
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            uuid_column = getattr(self.table_class, self.uuid_column_name)
            stmt = select(self.table_class).where(uuid_column == component_uuid)
            result = await session.execute(stmt)
            table_row = result.scalar_one_or_none()
            
            if not table_row:
                return None
                
            return await self.to_component_info(table_row)
    
    async def update_component(self, component_uuid: str, component_info: ComponentInfo) -> Optional[ComponentInfo]:
        """根据组件UUID更新组件信息"""
        _id = await self.get_component_id_by_uuid(component_uuid)
        return await self.update_component_by_id(_id, component_info)
    
    @abstractmethod
    async def update_component_by_id(self, component_id: int, component_info: ComponentInfo) -> Optional[ComponentInfo]:
        """根据组件主键ID更新组件信息"""
        pass
    
    async def get_component_by_id(self, component_id: int) -> Optional[ComponentInfo]:
        """根据组件主键ID获取组件信息"""
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            stmt = select(self.table_class).where(self.table_class.id == component_id)
            result = await session.execute(stmt)
            table_row = result.scalar_one_or_none()
            
            if not table_row:
                return None
                
            return await self.to_component_info(table_row)
    
    async def deactivate_component(self, component_id: int) -> bool:
        """停用组件"""
        if not self.table_class:
            raise NotImplementedError("table_class must be set in subclass")
            
        async with await self.db.get_session() as session:
            try:
                stmt = select(self.table_class).where(self.table_class.id == component_id)
                result = await session.execute(stmt)
                component = result.scalar_one_or_none()
                
                if not component:
                    return False
                
                component.is_active = False
                component.updated_at = func.current_timestamp()
                
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                print(f"Error deactivating component: {e}")
                return False