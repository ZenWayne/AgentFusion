import asyncio
import asyncpg
from typing import Optional, Dict, Any, List, Union
from datetime import datetime
from chainlit.logger import logger
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker


class DBDataLayer:
    """基础数据库操作层，提供连接管理和基础查询执行功能"""
    
    def __init__(self, database_url: str, show_logger: bool = False):
        """
        初始化数据库操作层
        
        Args:
            database_url: 数据库连接URL
            show_logger: 是否显示日志
        """
        self.database_url = database_url
        self.pool: Optional[asyncpg.Pool] = None
        self.show_logger = show_logger

    async def connect(self):
        """创建数据库连接池"""
        if not self.pool:
            self.pool = await asyncpg.create_pool(self.database_url)

    async def disconnect(self):
        """关闭数据库连接池"""
        if self.pool:
            await self.pool.close()
            self.pool = None

    async def get_current_timestamp(self) -> datetime:
        """获取当前时间戳"""
        return datetime.now()

    async def execute_query(
        self, query: str, params: Union[Dict, List, None] = None
    ) -> List[Dict[str, Any]]:
        """
        执行查询并返回结果
        
        Args:
            query: SQL查询语句
            params: 查询参数，可以是字典或列表
            
        Returns:
            查询结果列表
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as connection:
            try:
                if params:
                    if isinstance(params, dict):
                        # 如果是字典，使用命名参数
                        records = await connection.fetch(query, *params.values())
                    else:
                        # 如果是列表，直接使用位置参数
                        records = await connection.fetch(query, *params)
                else:
                    records = await connection.fetch(query)
                return [dict(record) for record in records]
            except Exception as e:
                if self.show_logger:
                    logger.error(f"Database query error: {e}")
                raise

    async def execute_single_query(
        self, query: str, params: Union[Dict, List, None] = None
    ) -> Optional[Dict[str, Any]]:
        """
        执行查询并返回单条结果
        
        Args:
            query: SQL查询语句
            params: 查询参数
            
        Returns:
            单条查询结果或None
        """
        results = await self.execute_query(query, params)
        return results[0] if results else None

    async def execute_command(
        self, query: str, params: Union[Dict, List, None] = None
    ) -> str:
        """
        执行命令（INSERT, UPDATE, DELETE等）并返回状态
        
        Args:
            query: SQL命令语句
            params: 命令参数
            
        Returns:
            执行状态
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as connection:
            try:
                if params:
                    if isinstance(params, dict):
                        result = await connection.execute(query, *params.values())
                    else:
                        result = await connection.execute(query, *params)
                else:
                    result = await connection.execute(query)
                return result
            except Exception as e:
                if self.show_logger:
                    logger.error(f"Database command error: {e}")
                raise

    async def execute_with_connection(self, func, *args, **kwargs):
        """
        使用数据库连接执行函数
        
        Args:
            func: 需要执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as connection:
            return await func(connection, *args, **kwargs)

    async def transaction(self, func, *args, **kwargs):
        """
        在事务中执行函数
        
        Args:
            func: 需要在事务中执行的函数
            *args: 函数参数
            **kwargs: 函数关键字参数
            
        Returns:
            函数执行结果
        """
        if not self.pool:
            await self.connect()

        async with self.pool.acquire() as connection:
            async with connection.transaction():
                return await func(connection, *args, **kwargs)

    #CR除了这个方法其他的可以去掉了，因为使用了sqlalchemy的orm去执行sql语句
    async def get_session(self):
        """Get SQLAlchemy async session using existing connection pool"""
        
        if not hasattr(self, '_engine'):
            # Create async engine using the existing database URL
            self._engine = create_async_engine(
                self.database_url.replace('postgresql://', 'postgresql+asyncpg://'),
                echo=self.show_logger
            )
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
        
        return self._session_factory()

    async def cleanup(self):
        """清理数据库连接"""
        if hasattr(self, '_engine'):
            await self._engine.dispose()
        await self.disconnect()

    def _truncate(self, text: Optional[str], max_length: int = 255) -> Optional[str]:
        """
        截断文本到指定长度
        
        Args:
            text: 要截断的文本
            max_length: 最大长度
            
        Returns:
            截断后的文本
        """
        return None if text is None else text[:max_length] 