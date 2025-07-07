"""上下文变量模块

定义ContextVariable的抽象基类和各种具体实现。
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, TYPE_CHECKING
from .exceptions import ContextVariableException
from typing import TypeVar, Generic

if TYPE_CHECKING:
    from .context_engine import ContextEngine

T = TypeVar('T')

class Context(Generic[T], ABC):
    """上下文变量抽象基类
    
    ContextVariable是Hook机制的核心组件，负责实际的上下文更新逻辑。
    可以传入ContextEngine引用来获取全局的context信息。
    """
    
    def __init__(self, context_engine: Optional['ContextEngine'] = None):
        """初始化上下文变量
        
        Args:
            context_engine: ContextEngine引用，用于获取全局上下文信息
        """
        self.context_engine = context_engine
    
    @abstractmethod
    def to_context(self) -> str:
        """返回变量的字符串表示，用于模板填充
        
        Returns:
            变量的字符串表示
        """
        pass
    
    @abstractmethod
    def update(self, context_data: T) -> None:
        """Hook调用的更新函数
        
        在Hook时机触发时执行的更新逻辑。
        子类可以重写此方法来实现自定义的更新逻辑。
        """
        pass


class StaticContextVariable(Context):
    """静态上下文变量
    
    用于包装简单的静态值。
    """
    
    def __init__(self, value: Any, context_engine: Optional['ContextEngine'] = None):
        super().__init__(context_engine)
        self._value = value
    
    def to_context(self) -> str:
        """返回变量的字符串表示"""
        return str(self._value)
    
    def update(self, context_data: Any) -> None:
        """更新值"""
        self._value = context_data
    
    def get_value(self) -> Any:
        """获取当前值"""
        return self._value


#这里改为MessageContext
class HistoryContextVariable(Context):
    """历史记录上下文变量
    
    用于管理聊天历史记录的变量。
    """
    
    #这里需要加入message_queue做入参
    def __init__(self, context_engine: Optional['ContextEngine'] = None, message_queue: Optional['MessageQueueBase'] = None):
        super().__init__(context_engine)
        self._message_queue = message_queue
   
    def get_value(self) -> list:
        return self._message_queue.to_context()
    
    def add_message(self, role: str, content: str) -> None:
        """添加消息到历史记录
        
        Args:
            role: 消息角色
            content: 消息内容
        """
        self._history.append({
            'role': role,
            'content': content,
            'timestamp': self._get_timestamp()
        })
        self.invalidate_cache()
    
    def clear_history(self) -> None:
        """清空历史记录"""
        self._history.clear()
        self.invalidate_cache()
    
    def _get_timestamp(self) -> str:
        """获取当前时间戳"""
        from datetime import datetime
        return datetime.now().isoformat()
    
    def _update_with_context(self, global_vars: Dict[str, Any]) -> None:
        """基于全局上下文更新历史记录"""
        # 可以根据全局上下文过滤或增强历史记录
        pass
    
    def _get_agent_specific_context(self, agent_id: str, 
                                   agent_context: Dict[str, Any]) -> str:
        """获取Agent特定的历史记录"""
        # 过滤出与特定Agent相关的历史记录
        agent_history = [
            entry for entry in self._history 
            if entry.get('agent_id') == agent_id
        ]
        
        if not agent_history:
            return ""
        
        formatted = []
        for entry in agent_history:
            role = entry.get('role', 'unknown')
            content = entry.get('content', '')
            formatted.append(f"{role}: {content}")
        
        return "\n".join(formatted)


class GroupChatContextVariable(Context):
    """群聊上下文变量
    
    专门用于群聊场景的上下文变量。
    """
    
    def __init__(self, context_engine: Optional['ContextEngine'] = None):
        super().__init__(context_engine)
        self._group_data = {}
    
    def __repr__(self) -> str:
        return self.get_group_summary()
    
    def get_value(self) -> Dict[str, Any]:
        return self._group_data
    
    def get_group_summary(self) -> str:
        """获取群聊摘要信息
        
        Returns:
            群聊摘要字符串
        """
        if not self._group_data:
            return "No group data available"
        
        summary_parts = []
        for key, value in self._group_data.items():
            summary_parts.append(f"{key}: {value}")
        
        return "; ".join(summary_parts)
    
    def set_group_data(self, key: str, value: Any) -> None:
        """设置群聊数据
        
        Args:
            key: 数据键
            value: 数据值
        """
        self._group_data[key] = value
        self.invalidate_cache()
    
    def get_group_data(self, key: str, default: Any = None) -> Any:
        """获取群聊数据
        
        Args:
            key: 数据键
            default: 默认值
            
        Returns:
            数据值
        """
        return self._group_data.get(key, default)
    
    def _update_with_context(self, global_vars: Dict[str, Any]) -> None:
        """基于全局上下文更新群聊数据"""
        # 可以从全局上下文中提取群聊相关信息
        pass
    
    def _get_agent_specific_context(self, agent_id: str, 
                                   agent_context: Dict[str, Any]) -> str:
        """获取Agent在群聊中的特定上下文"""
        agent_data = self._group_data.get(f"agent_{agent_id}", {})
        
        if not agent_data:
            return f"Agent {agent_id} context not available"
        
        context_parts = []
        for key, value in agent_data.items():
            context_parts.append(f"{key}: {value}")
        
        return "; ".join(context_parts) 