"""
基础模型类

提供所有模型的通用功能和接口
"""

from typing import TYPE_CHECKING, Any, Dict, List, Optional, Union

if TYPE_CHECKING:
    from chainlit_web.data_layer.base_data_layer import DBDataLayer


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