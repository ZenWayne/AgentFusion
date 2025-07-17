"""
重构后的数据层

使用继承模式整合所有模型，让调用更直接
"""

import json
from typing import Optional, Dict, Any, List, Union, TYPE_CHECKING
from datetime import datetime
from chainlit.data.base import BaseDataLayer
from chainlit.data.storage_clients.base import BaseStorageClient
from chainlit.data.utils import queue_until_user_message
from chainlit.element import ElementDict
from chainlit.logger import logger
from chainlit.step import StepDict
from chainlit.types import (
    Feedback,
    FeedbackDict,
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)
from chainlit.user import User

# 导入基础数据层和所有模型
from chainlit_web.data_layer.base_data_layer import DBDataLayer
from chainlit_web.data_layer.models import (
    UserModel, 
    ThreadModel, 
    StepModel, 
    ElementModel, 
    FeedbackModel,
    LLMModel,
    AgentModel,
    PersistedUser,
    PersistedUserFields,
    AgentFusionUser
)

if TYPE_CHECKING:
    from chainlit.element import Element
    from chainlit.step import StepDict

ISO_FORMAT = "%Y-%m-%dT%H:%M:%S.%fZ"


class AgentFusionDataLayer( 
    UserModel, 
    ThreadModel, 
    StepModel, 
    ElementModel, 
    FeedbackModel,
    LLMModel,
    AgentModel
    ):
    """
    重构后的数据层，使用继承模式整合所有模型
    直接继承所有模型类，让方法调用更直接
    """
    
    def __init__(
        self,
        database_url: str,
        storage_client: Optional[BaseStorageClient] = None,
        show_logger: bool = False,
        **kwargs
    ):
        # 先调用BaseDataLayer的初始化
        BaseDataLayer.__init__(self)
        
        self.database_url = database_url
        self.storage_client = storage_client
        self.show_logger = show_logger
        
        # 创建基础数据库操作层
        self.db_layer = DBDataLayer(database_url, show_logger)
        
        # 初始化所有模型的基础部分
        UserModel.__init__(self, self.db_layer)
        ThreadModel.__init__(self, self.db_layer)
        StepModel.__init__(self, self.db_layer)
        ElementModel.__init__(self, self.db_layer)
        FeedbackModel.__init__(self, self.db_layer)
        LLMModel.__init__(self, self.db_layer)
        AgentModel.__init__(self, self.db_layer)

    async def connect(self):
        """连接数据库"""
        await self.db_layer.connect()

    async def get_current_timestamp(self) -> datetime:
        """获取当前时间戳"""
        return await self.db_layer.get_current_timestamp()

    async def execute_query(
        self, query: str, params: Union[Dict, None] = None
    ) -> List[Dict[str, Any]]:
        """执行查询"""
        return await self.db_layer.execute_query(query, params)

    # ===== BaseDataLayer 抽象方法现在由继承的模型类实现 =====
    # 以下方法已移除，因为它们由继承的模型类直接提供：
    # - get_user (UserModel)
    # - create_user (UserModel)
    # - delete_feedback (FeedbackModel)
    # - upsert_feedback (FeedbackModel)
    # - get_element (ElementModel)
    # - get_thread_author (ThreadModel)
    # - list_threads (ThreadModel)

    # ===== 线程相关方法的重写（需要处理存储客户端）=====
    async def delete_thread(self, thread_id: str):
        """删除线程（重写以处理存储客户端）"""
        elements_results = await super().delete_thread(thread_id)
        
        # 删除存储的文件
        if self.storage_client is not None:
            for elem in elements_results:
                if elem.get("object_key"):
                    await self.storage_client.delete_file(
                        object_key=elem["object_key"]
                    )

    async def get_thread(self, thread_id: str) -> Optional[ThreadDict]:
        """获取线程（重写以处理存储文件URL）"""
        result = await super().get_thread(thread_id)
        if not result:
            return None
        
        thread = result["thread"]
        steps_results = result["steps"]
        elements_results = result["elements"]
        
        # 处理存储文件的URL
        if self.storage_client is not None:
            for elem in elements_results:
                if not elem["url"] and elem["object_key"]:
                    elem["url"] = await self.storage_client.get_read_url(
                        object_key=elem["object_key"],
                    )

        return ThreadDict(
            id=str(thread["id"]),
            createdAt=thread["created_at"].isoformat(),
            name=thread["name"],
            userId=str(thread["user_uuid"]) if thread["user_uuid"] else None,
            userIdentifier=thread["user_identifier"],
            metadata=json.loads(thread["metadata"]),
            steps=[self._convert_step_row_to_dict(step) for step in steps_results],
            elements=[
                self._convert_element_row_to_dict(elem) for elem in elements_results
            ],
            tags=[],
        )

    async def update_thread(
        self,
        thread_id: str,
        name: Optional[str] = None,
        user_id: Optional[str] = None,
        metadata: Optional[Dict] = None,
        tags: Optional[List[str]] = None,
    ):
        """更新线程（重写以添加日志）"""
        if self.show_logger:
            logger.info(f"asyncpg: update_thread, thread_id={thread_id}")
        
        await super().update_thread(
            thread_id=thread_id,
            name=name,
            user_id=user_id,
            metadata=metadata,
            tags=tags
        )

    # ===== 步骤相关方法的重写（需要处理队列装饰器）=====
    @queue_until_user_message()
    async def create_step(self, step_dict: StepDict):
        """创建步骤（重写以确保线程存在）"""
        # 确保线程存在
        if step_dict.get("threadId"):
            await self.update_thread(thread_id=step_dict["threadId"])
        
        await super().create_step(step_dict)

    @queue_until_user_message()
    async def update_step(self, step_dict: StepDict):
        """更新步骤"""
        await super().update_step(step_dict)

    @queue_until_user_message()
    async def delete_step(self, step_id: str):
        """删除步骤"""
        await super().delete_step(step_id)

    # ===== 元素相关方法的重写（需要处理存储客户端）=====
    @queue_until_user_message()
    async def create_element(self, element: "Element"):
        """创建元素（重写以处理存储客户端）"""
        if not self.storage_client:
            logger.warning(
                "Data Layer: create_element error. No cloud storage configured!"
            )
            return

        # 确保线程存在
        if element.thread_id:
            await self.update_thread(thread_id=element.thread_id)

        # 确保步骤存在
        if element.for_id:
            await self.create_step({
                "id": element.for_id,
                "metadata": {},
                "type": "run",
                "start_time": await self.get_current_timestamp(),
                "end_time": await self.get_current_timestamp(),
            })

        await super().create_element(element, self.storage_client)

    @queue_until_user_message()
    async def delete_element(self, element_id: str, thread_id: Optional[str] = None):
        """删除元素（重写以处理存储客户端）"""
        element = await super().delete_element(element_id, thread_id)
        
        # 删除存储的文件
        if self.storage_client is not None and element and element.get("object_key"):
            await self.storage_client.delete_file(
                object_key=element["object_key"]
            )

    # ===== BaseDataLayer 需要的方法 =====
    async def build_debug_url(self) -> str:
        """构建调试URL"""
        return ""

    async def cleanup(self):
        """清理资源"""
        await self.db_layer.cleanup()

    def _truncate(self, text: Optional[str], max_length: int = 255) -> Optional[str]:
        """截断文本"""
        return self.db_layer._truncate(text, max_length)
    
    async def get_model_list(self) -> List[Dict[str, Any]]:
        """获取模型列表用于聊天设置"""
        return await self.get_model_labels_for_chat_settings()


# 为了向后兼容，导出原有的类
__all__ = [
    'AgentFusionDataLayer',
    'PersistedUser',
    'PersistedUserFields',
    'AgentFusionUser'
]
    
