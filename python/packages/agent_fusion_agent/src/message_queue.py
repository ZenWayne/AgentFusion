"""消息队列模块

实现消息存储和回溯功能，支持同组内Agent之间的消息管理和持久化。
"""

import json
import uuid
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from .exceptions import MessageQueueException
from .context_variable import Context


@dataclass
class Message:
    """消息数据类"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.now)
    role: str = ""
    content: str = ""
    agent_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "role": self.role,
            "content": self.content,
            "agent_id": self.agent_id,
            "metadata": self.metadata
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """从字典创建消息实例"""
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            role=data.get("role", ""),
            content=data.get("content", ""),
            agent_id=data.get("agent_id"),
            metadata=data.get("metadata", {})
        )


class MessageQueueBase(ABC):
    """消息队列抽象基类"""
    
    @abstractmethod
    def update(self, message: Message) -> None:
        """更新消息到队列
        
        Args:
            message: 消息对象
        """
        pass
    
    @abstractmethod
    def get_messages(self, limit: Optional[int] = None, 
                    offset: int = 0) -> List[Message]:
        """获取消息列表
        
        Args:
            limit: 限制返回的消息数量
            offset: 偏移量
            
        Returns:
            消息列表
        """
        pass
    
    @abstractmethod
    def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """根据ID获取消息
        
        Args:
            message_id: 消息ID
            
        Returns:
            消息对象，如果不存在则返回None
        """
        pass
    
    @abstractmethod
    def clear_messages(self) -> None:
        """清空消息队列"""
        pass
    
    @abstractmethod
    def get_message_count(self) -> int:
        """获取消息数量
        
        Returns:
            消息数量
        """
        pass

    @abstractmethod
    def to_context(self) -> str:
        """获取消息队列的上下文表示"""
        pass


class InMemoryMessageQueue(MessageQueueBase, Context[Message]):
    """内存消息队列
    
    将消息存储在内存中，适用于临时或测试场景。
    """
    
    def __init__(self, max_messages: Optional[int] = None):
        """初始化内存消息队列
        
        Args:
            max_messages: 最大消息数量，超过时会删除旧消息
        """
        self.messages: List[Message] = []
        self.max_messages = max_messages
        self._message_index: Dict[str, Message] = {}

    def update(self, message: Message) -> None:
        """添加消息到队列"""
        if not isinstance(message, Message):
            raise MessageQueueException("Message must be a Message instance")
        
        # 检查消息数量限制
        if self.max_messages and len(self.messages) >= self.max_messages:
            # 删除最旧的消息
            old_message = self.messages.pop(0)
            del self._message_index[old_message.id]
        
        self.messages.append(message)
        self._message_index[message.id] = message

    def get_messages(self, limit: Optional[int] = None, 
                    offset: int = 0) -> List[Message]:
        """获取消息列表"""
        messages = self.messages[offset:]
        if limit:
            messages = messages[:limit]
        return messages
    
    def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """根据ID获取消息"""
        return self._message_index.get(message_id)
    
    def clear_messages(self) -> None:
        """清空消息队列"""
        self.messages.clear()
        self._message_index.clear()
    
    def get_message_count(self) -> int:
        """获取消息数量"""
        return len(self.messages)
    
    def get_messages_by_agent(self, agent_id: str) -> List[Message]:
        """获取特定Agent的消息
        
        Args:
            agent_id: Agent ID
            
        Returns:
            消息列表
        """
        return [msg for msg in self.messages if msg.agent_id == agent_id]
    
    def get_messages_by_role(self, role: str) -> List[Message]:
        """获取特定角色的消息
        
        Args:
            role: 消息角色
            
        Returns:
            消息列表
        """
        return [msg for msg in self.messages if msg.role == role]
    
    def get_recent_messages(self, count: int = 10) -> List[Message]:
        """获取最近的消息
        
        Args:
            count: 消息数量
            
        Returns:
            最近的消息列表
        """
        return self.messages[-count:] if self.messages else []
    
    def to_context(self) -> str:
        """获取消息队列的上下文表示"""
        return "\n".join([f"{msg.role}: {msg.content}" for msg in self.get_recent_messages()])


class FileMessageQueue(MessageQueueBase):
    """文件消息队列
    
    将消息持久化到文件中。
    """
    
    def __init__(self, file_path: str, auto_save: bool = True):
        """初始化文件消息队列
        
        Args:
            file_path: 文件路径
            auto_save: 是否自动保存
        """
        self.file_path = file_path
        self.auto_save = auto_save
        self.messages: List[Message] = []
        self._message_index: Dict[str, Message] = {}
        self._observers: List[Callable[[Message], None]] = []
        
        # 从文件加载消息
        self._load_from_file()
    
    def update(self, message: Message) -> None:
        """添加消息到队列"""
        if not isinstance(message, Message):
            raise MessageQueueException("Message must be a Message instance")
        
        self.messages.append(message)
        self._message_index[message.id] = message
        
        # 自动保存
        if self.auto_save:
            self._save_to_file()
        
        # 通知观察者
        self._notify_observers(message)
    
    def get_messages(self, limit: Optional[int] = None, 
                    offset: int = 0) -> List[Message]:
        """获取消息列表"""
        messages = self.messages[offset:]
        if limit:
            messages = messages[:limit]
        return messages
    
    def get_message_by_id(self, message_id: str) -> Optional[Message]:
        """根据ID获取消息"""
        return self._message_index.get(message_id)
    
    def clear_messages(self) -> None:
        """清空消息队列"""
        self.messages.clear()
        self._message_index.clear()
        
        if self.auto_save:
            self._save_to_file()
    
    def get_message_count(self) -> int:
        """获取消息数量"""
        return len(self.messages)
    
    def save(self) -> None:
        """手动保存到文件"""
        self._save_to_file()
    
    def reload(self) -> None:
        """从文件重新加载"""
        self._load_from_file()
    
    def _save_to_file(self) -> None:
        """保存消息到文件"""
        try:
            data = {
                "messages": [msg.to_dict() for msg in self.messages],
                "metadata": {
                    "saved_at": datetime.now().isoformat(),
                    "version": "1.0"
                }
            }
            
            with open(self.file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
                
        except Exception as e:
            raise MessageQueueException(f"Failed to save messages to file: {e}")
    
    def _load_from_file(self) -> None:
        """从文件加载消息"""
        try:
            with open(self.file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            messages_data = data.get("messages", [])
            self.messages = [Message.from_dict(msg_data) for msg_data in messages_data]
            self._message_index = {msg.id: msg for msg in self.messages}
            
        except FileNotFoundError:
            # 文件不存在，创建空队列
            self.messages = []
            self._message_index = {}
        except Exception as e:
            raise MessageQueueException(f"Failed to load messages from file: {e}")
    
    def add_observer(self, observer: Callable[[Message], None]) -> None:
        """添加观察者"""
        self._observers.append(observer)
    
    def remove_observer(self, observer: Callable[[Message], None]) -> None:
        """移除观察者"""
        if observer in self._observers:
            self._observers.remove(observer)
    
    def _notify_observers(self, message: Message) -> None:
        """通知观察者"""
        for observer in self._observers:
            try:
                observer(message)
            except Exception as e:
                pass


class MessageQueueManager:
    """消息队列管理器
    
    管理多个消息队列实例，支持GroupChat和Agent的消息管理。
    """
    
    def __init__(self):
        self.queues: Dict[str, MessageQueueBase] = {}
        self.default_queue_type = InMemoryMessageQueue
        self._global_observers: List[Callable[[str, Message], None]] = []
    
    def create_queue(self, queue_id: str, queue_type: str = "memory",
                    **kwargs) -> MessageQueueBase:
        """创建消息队列
        
        Args:
            queue_id: 队列ID
            queue_type: 队列类型 ("memory" 或 "file")
            **kwargs: 队列初始化参数
            
        Returns:
            消息队列实例
        """
        if queue_id in self.queues:
            raise MessageQueueException(f"Queue {queue_id} already exists")
        
        if queue_type == "memory":
            queue = InMemoryMessageQueue(**kwargs)
        elif queue_type == "file":
            queue = FileMessageQueue(**kwargs)
        else:
            raise MessageQueueException(f"Unsupported queue type: {queue_type}")
        
        # 添加全局观察者
        if hasattr(queue, 'add_observer'):
            queue.add_observer(lambda msg: self._notify_global_observers(queue_id, msg))
        
        self.queues[queue_id] = queue
        return queue
    
    def get_queue(self, queue_id: str) -> Optional[MessageQueueBase]:
        """获取消息队列
        
        Args:
            queue_id: 队列ID
            
        Returns:
            消息队列实例，如果不存在则返回None
        """
        return self.queues.get(queue_id)
    
    def get_or_create_queue(self, queue_id: str, queue_type: str = "memory",
                           **kwargs) -> MessageQueueBase:
        """获取或创建消息队列
        
        Args:
            queue_id: 队列ID
            queue_type: 队列类型
            **kwargs: 队列初始化参数
            
        Returns:
            消息队列实例
        """
        queue = self.get_queue(queue_id)
        if queue is None:
            queue = self.create_queue(queue_id, queue_type, **kwargs)
        return queue
    
    def delete_queue(self, queue_id: str) -> None:
        """删除消息队列
        
        Args:
            queue_id: 队列ID
        """
        if queue_id in self.queues:
            del self.queues[queue_id]
    
    def list_queues(self) -> List[str]:
        """列出所有队列ID
        
        Returns:
            队列ID列表
        """
        return list(self.queues.keys())
    
    def update_message_to_queue(self, queue_id: str, message: Message) -> None:
        """向指定队列添加消息
        
        Args:
            queue_id: 队列ID
            message: 消息对象
        """
        queue = self.get_queue(queue_id)
        if queue is None:
            raise MessageQueueException(f"Queue {queue_id} not found")
        
        queue.update(message)
    
    def get_messages_from_queue(self, queue_id: str, limit: Optional[int] = None,
                               offset: int = 0) -> List[Message]:
        """从指定队列获取消息
        
        Args:
            queue_id: 队列ID
            limit: 限制返回的消息数量
            offset: 偏移量
            
        Returns:
            消息列表
        """
        queue = self.get_queue(queue_id)
        if queue is None:
            raise MessageQueueException(f"Queue {queue_id} not found")
        
        return queue.get_messages(limit, offset)
    
    def get_queue_statistics(self) -> Dict[str, Any]:
        """获取队列统计信息
        
        Returns:
            统计信息字典
        """
        stats = {
            "total_queues": len(self.queues),
            "queue_details": {}
        }
        
        for queue_id, queue in self.queues.items():
            stats["queue_details"][queue_id] = {
                "message_count": queue.get_message_count(),
                "queue_type": queue.__class__.__name__
            }
        
        return stats
    
    def clear_all_queues(self) -> None:
        """清空所有队列"""
        for queue in self.queues.values():
            queue.clear_messages()
    
    def add_global_observer(self, observer: Callable[[str, Message], None]) -> None:
        """添加全局观察者
        
        Args:
            observer: 观察者函数，接收队列ID和消息
        """
        self._global_observers.append(observer)
    
    def remove_global_observer(self, observer: Callable[[str, Message], None]) -> None:
        """移除全局观察者
        
        Args:
            observer: 观察者函数
        """
        if observer in self._global_observers:
            self._global_observers.remove(observer)
    
    def _notify_global_observers(self, queue_id: str, message: Message) -> None:
        """通知全局观察者
        
        Args:
            queue_id: 队列ID
            message: 消息对象
        """
        for observer in self._global_observers:
            try:
                observer(queue_id, message)
            except Exception as e:
                pass


# 全局消息队列管理器实例
message_queue_manager = MessageQueueManager()


def get_message_queue_manager() -> MessageQueueManager:
    """获取全局消息队列管理器实例
    
    Returns:
        消息队列管理器实例
    """
    return message_queue_manager 