"""
基础模型类

提供所有模型的通用功能和接口
"""

from abc import abstractmethod
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from chainlit_web.data_layer.base_data_layer import DBDataLayer

from schemas.agent import ComponentInfo


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

    @abstractmethod
    async def to_component_info(self, component_name: str) -> ComponentInfo:
        """将组件信息转换为ComponentInfo对象"""
        pass

    @abstractmethod
    async def get_all_components(self, filter_active: bool = True) -> Dict[str, ComponentInfo]:
        """获取所有组件信息,filter_active为True时，只获取active为True的组件，否则不考虑is_active是否为True都选"""
        pass

    @abstractmethod
    async def get_component_by_name(self, component_name: str) -> ComponentInfo:
        """根据组件名称获取组件信息"""
        pass
    
    @abstractmethod
    async def get_component_id_by_uuid(self, component_uuid: str) -> int:
        """根据组件UUID获取组件主键ID"""
        pass
    
    @abstractmethod
    async def get_component_by_uuid(self, component_uuid: str) -> ComponentInfo:
        """根据组件UUID获取组件信息"""
        _id = await self.get_component_id_by_uuid(component_uuid)
        return await self.get_component_by_id(_id)
    
    @abstractmethod
    async def update_component(self, component_uuid: str, component_info: ComponentInfo) -> ComponentInfo:
        """根据组件UUID更新组件信息"""
        _id = await self.get_component_id_by_uuid(component_uuid)
        return await self.update_component_by_id(_id, component_info)
    
    @abstractmethod
    async def update_component_by_id(self, component_id: int, component_info: ComponentInfo) -> ComponentInfo:
        """根据组件主键ID更新组件信息"""
        pass
    
    @abstractmethod
    async def get_component_by_id(self, component_id: str) -> ComponentInfo:
        """根据组件主键ID获取组件信息需要两段select，第一段根据uuid select获取组件的id，第二段根据主键id select获取组件信息"""
        pass