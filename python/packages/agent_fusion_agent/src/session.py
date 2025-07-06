"""Session会话管理模块

提供统一的会话管理接口，支持单个Agent和群聊系统的会话管理。
"""

import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator, Union
from dataclasses import dataclass, field
from datetime import datetime

from .agent import AgentBase
from .group_chat import GroupChat
from .context_engine import ContextEngine
from .message_queue import MessageQueueBase, Message, InMemoryMessageQueue
from .llm_client import LLMResponse, LLMStreamChunk
from .observability import get_observability_manager
from .exceptions import AgentFrameworkException, ValidationException


@dataclass
class SessionConfig:
    """会话配置数据类"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Session"
    description: str = ""
    auto_create_components: bool = True
    context_variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "session_id": self.session_id,
            "name": self.name,
            "description": self.description,
            "auto_create_components": self.auto_create_components,
            "context_variables": self.context_variables,
            "metadata": self.metadata
        }


class SessionableAgent(AgentBase):
    """支持会话的Agent包装类"""
    
    def __init__(self, agent: AgentBase):
        """包装现有的Agent
        
        Args:
            agent: 原始Agent实例
        """
        # 复制原始agent的所有属性
        super().__init__(agent.config)
        self._original_agent = agent
        self.message_queue: Optional[MessageQueueBase] = None
        
        # 复制所有属性
        for attr_name in dir(agent):
            if not attr_name.startswith('_') and hasattr(agent, attr_name):
                attr_value = getattr(agent, attr_name)
                if not callable(attr_value):
                    setattr(self, attr_name, attr_value)
    
    def initialize_session_components(self, session_config: SessionConfig) -> Dict[str, Any]:
        """初始化会话组件"""
        if session_config.auto_create_components:
            # 直接创建message_queue
            self.message_queue = InMemoryMessageQueue()
            
            # 创建或使用现有的context_engine
            if not hasattr(self, 'context_engine') or self.context_engine is None:
                self.context_engine = ContextEngine()
            
            # 添加会话级别的上下文变量
            for var_name, var_value in session_config.context_variables.items():
                self.context_engine.register_variable(var_name, var_value)
        
        return {
            "message_queue": self.message_queue,
            "context_engine": getattr(self, 'context_engine', None)
        }
    
    def start_session(self) -> None:
        """启动会话 - Agent不需要特殊启动逻辑"""
        pass
    
    def end_session(self) -> None:
        """结束会话 - Agent不需要特殊结束逻辑"""
        pass
    
    #CR:这里需要新增一个参数Context
    async def process_message(self, message: str, **kwargs) -> Union[LLMResponse, List[Dict[str, Any]]]:
        """处理消息 - 委托给原始Agent"""
        return await self._original_agent.process_message(message, **kwargs)
    
    #CR:这里需要新增一个参数Context
    async def stream_process_message(self, message: str, **kwargs) -> AsyncGenerator[Union[LLMStreamChunk, Dict[str, Any]], None]:
        """流式处理消息 - 委托给原始Agent"""
        async for chunk in self._original_agent.stream_process_message(message, **kwargs):
            yield chunk
    
    def get_session_status_info(self) -> Dict[str, Any]:
        """获取会话状态信息"""
        return {
            "session_type": "single_agent",
            "agent": {
                "agent_id": self.config.agent_id,
                "name": self.config.name,
                "model": self.config.model
            }
        }


class SessionableGroupChat(GroupChat):
    """支持会话的GroupChat包装类"""
    
    def __init__(self, group_chat: GroupChat):
        """包装现有的GroupChat
        
        Args:
            group_chat: 原始GroupChat实例
        """
        super().__init__(group_chat.config)
        self._original_group_chat = group_chat
        self.agents = group_chat.agents
        self.context_engine = group_chat.context_engine
        self.message_queue: Optional[MessageQueueBase] = None
        self._session = None
        
        # 复制所有属性
        for attr_name in dir(group_chat):
            if not attr_name.startswith('_') and hasattr(group_chat, attr_name):
                attr_value = getattr(group_chat, attr_name)
                if not callable(attr_value):
                    setattr(self, attr_name, attr_value)
    
    def initialize_session_components(self, session_config: SessionConfig) -> Dict[str, Any]:
        """初始化会话组件"""
        # 如果群聊没有message_queue，直接创建一个
        if not hasattr(self, 'message_queue') or self.message_queue is None:
            self.message_queue = InMemoryMessageQueue()
        
        # 添加会话级别的上下文变量
        for var_name, var_value in session_config.context_variables.items():
            self.context_engine.register_variable(var_name, var_value)
        
        return {
            "message_queue": self.message_queue,
            "context_engine": self.context_engine
        }
    
    def start_session(self) -> None:
        """启动会话"""
        self._session = self._original_group_chat.start_session()
    
    def end_session(self) -> None:
        """结束会话"""
        if self._session:
            self._original_group_chat.end_session()
            self._session = None
    
    async def process_message(self, message: str, **kwargs) -> Union[LLMResponse, List[Dict[str, Any]]]:
        """处理消息 - 委托给原始GroupChat"""
        return await self._original_group_chat.process_message(message, **kwargs)
    
    async def stream_process_message(self, message: str, **kwargs) -> AsyncGenerator[Union[LLMStreamChunk, Dict[str, Any]], None]:
        """流式处理消息 - 委托给原始GroupChat"""
        async for response in self._original_group_chat.stream_process_message(message, **kwargs):
            yield response
    
    def get_session_status_info(self) -> Dict[str, Any]:
        """获取会话状态信息"""
        return {
            "session_type": "group_chat",
            "group_chat": {
                "group_id": self.config.group_id,
                "name": self.config.name,
                "agent_count": len(self.agents)
            }
        }


class Session:
    """会话管理器
    
    统一管理单个Agent和群聊的会话，提供一致的交互接口。
    """
    
    def __init__(self, 
                 agent_or_groupchat: Union[AgentBase, GroupChat],
                 config: Optional[SessionConfig] = None):
        """初始化会话
        
        Args:
            agent_or_groupchat: Agent实例或GroupChat实例
            config: 会话配置
        """
        self.config = config or SessionConfig()
        self.observability = get_observability_manager()
        
        # 包装为统一接口的对象
        if isinstance(agent_or_groupchat, AgentBase):
            self.sessionable = SessionableAgent(agent_or_groupchat)
        elif isinstance(agent_or_groupchat, GroupChat):
            self.sessionable = SessionableGroupChat(agent_or_groupchat)
        else:
            raise ValidationException(
                "agent_or_groupchat must be an instance of AgentBase or GroupChat"
            )
        
        # 初始化会话组件
        session_components = self.sessionable.initialize_session_components(self.config)
        self.message_queue = session_components.get("message_queue")
        self.context_engine = session_components.get("context_engine")
        
        # 会话状态
        self.is_active = False
        self.start_time: Optional[datetime] = None
        self.end_time: Optional[datetime] = None
        
        # 记录会话创建
        self.observability.logger.info(
            f"Session created: {self.config.session_id}",
            context={
                "session_id": self.config.session_id,
                "session_type": self.sessionable.get_session_status_info()["session_type"],
                "name": self.config.name
            }
        )
    
    def start(self) -> None:
        """开始会话"""
        if self.is_active:
            raise AgentFrameworkException("Session is already active")
        
        self.is_active = True
        self.start_time = datetime.now()
        
        # 统一调用start_session方法
        self.sessionable.start_session()
        
        self.observability.logger.info(
            f"Session started: {self.config.session_id}",
            context={
                "session_id": self.config.session_id,
                "session_type": self.sessionable.get_session_status_info()["session_type"],
                "start_time": self.start_time.isoformat()
            }
        )
    
    def end(self) -> None:
        """结束会话"""
        if not self.is_active:
            return
        
        self.is_active = False
        self.end_time = datetime.now()
        
        # 统一调用end_session方法
        self.sessionable.end_session()
        
        self.observability.logger.info(
            f"Session ended: {self.config.session_id}",
            context={
                "session_id": self.config.session_id,
                "session_type": self.sessionable.get_session_status_info()["session_type"],
                "end_time": self.end_time.isoformat(),
                "duration": (self.end_time - self.start_time).total_seconds() if self.start_time else None
            }
        )
    
    async def process_message(self, message: str, **kwargs) -> Union[LLMResponse, List[Dict[str, Any]]]:
        """处理消息
        
        Args:
            message: 输入消息
            **kwargs: 其他参数
            
        Returns:
            单个Agent返回LLMResponse，群聊返回响应列表
        """
        if not self.is_active:
            raise AgentFrameworkException("Session is not active. Call start() first.")
        
        # 记录用户消息
        self._add_message_to_history("user", message)
        
        interaction_id = self.observability.start_interaction()
        
        try:
            # 统一调用process_message方法
            response = await self.sessionable.process_message(message, **kwargs)
            
            # 记录响应
            if isinstance(response, LLMResponse):
                # 单个Agent响应
                agent_id = getattr(self.sessionable, 'config', {}).get('agent_id')
                self._add_message_to_history("assistant", response.content, agent_id=agent_id)
            else:
                # 群聊响应
                for resp in response:
                    self._add_message_to_history(
                        "assistant", 
                        resp.get("content", ""), 
                        agent_id=resp.get("agent_id"),
                        round_num=resp.get("round")
                    )
            
            self.observability.end_interaction(interaction_id)
            return response
                
        except Exception as e:
            self.observability.record_error(interaction_id, str(e))
            raise
    
    async def stream_process_message(self, message: str, **kwargs) -> AsyncGenerator[Union[LLMStreamChunk, Dict[str, Any]], None]:
        """流式处理消息
        
        Args:
            message: 输入消息
            **kwargs: 其他参数
            
        Yields:
            单个Agent返回LLMStreamChunk，群聊返回流式响应字典
        """
        if not self.is_active:
            raise AgentFrameworkException("Session is not active. Call start() first.")
        
        # 记录用户消息
        self._add_message_to_history("user", message)
        
        interaction_id = self.observability.start_interaction()
        
        try:
            # 统一调用stream_process_message方法
            session_type = self.sessionable.get_session_status_info()["session_type"]
            
            if session_type == "single_agent":
                # 单个Agent流式处理
                accumulated_content = ""
                async for chunk in self.sessionable.stream_process_message(message, **kwargs):
                    accumulated_content += chunk.content
                    yield chunk
                
                # 记录完整的Agent响应
                agent_id = getattr(self.sessionable, 'config', {}).get('agent_id')
                self._add_message_to_history("assistant", accumulated_content, agent_id=agent_id)
                
            else:
                # 群聊流式处理
                agent_responses = {}
                async for response in self.sessionable.stream_process_message(message, **kwargs):
                    agent_id = response.get("agent_id")
                    if agent_id:
                        if agent_id not in agent_responses:
                            agent_responses[agent_id] = ""
                        agent_responses[agent_id] += response.get("chunk", "")
                    
                    yield response
                
                # 记录完整的群聊响应
                for agent_id, content in agent_responses.items():
                    self._add_message_to_history("assistant", content, agent_id=agent_id)
                
            self.observability.end_interaction(interaction_id)
            
        except Exception as e:
            self.observability.record_error(interaction_id, str(e))
            raise
    
    def _add_message_to_history(self, role: str, content: str, agent_id: Optional[str] = None, **metadata) -> None:
        """添加消息到历史记录"""
        if self.message_queue:
            message = Message(
                role=role,
                content=content,
                agent_id=agent_id,
                metadata={
                    "session_id": self.config.session_id,
                    "session_type": self.sessionable.get_session_status_info()["session_type"],
                    **metadata
                }
            )
            self.message_queue.update(message)
    
    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取会话历史
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            消息历史列表
        """
        if not self.message_queue:
            return []
        
        messages = self.message_queue.get_messages(limit=limit)
        return [msg.to_dict() for msg in messages]
    
    def clear_history(self) -> None:
        """清空会话历史"""
        if self.message_queue:
            self.message_queue.clear_messages()
    
    def get_status(self) -> Dict[str, Any]:
        """获取会话状态
        
        Returns:
            会话状态字典
        """
        status = {
            "session_id": self.config.session_id,
            "name": self.config.name,
            "is_active": self.is_active,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "duration": (self.end_time - self.start_time).total_seconds() if self.start_time and self.end_time else None,
            "message_count": self.message_queue.get_message_count() if self.message_queue else 0
        }
        
        # 获取统一的状态信息
        status.update(self.sessionable.get_session_status_info())
        
        return status
    
    def add_context_variable(self, name: str, value: Any) -> None:
        """添加上下文变量
        
        Args:
            name: 变量名
            value: 变量值
        """
        if self.context_engine:
            self.context_engine.register_variable(name, value)
    
    def remove_context_variable(self, name: str) -> None:
        """移除上下文变量
        
        Args:
            name: 变量名
        """
        if self.context_engine:
            self.context_engine.unregister_variable(name)
    
    def get_context_variables(self) -> Dict[str, Any]:
        """获取所有上下文变量
        
        Returns:
            上下文变量字典
        """
        if self.context_engine:
            return self.context_engine.get_all_variables()
        return {}
    
    def __enter__(self):
        """上下文管理器入口"""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """上下文管理器出口"""
        self.end()
    
    async def __aenter__(self):
        """异步上下文管理器入口"""
        self.start()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器出口"""
        self.end()


class SessionManager:
    """会话管理器
    
    管理多个会话的生命周期。
    """
    
    def __init__(self):
        """初始化会话管理器"""
        self.sessions: Dict[str, Session] = {}
        self.observability = get_observability_manager()
    
    def create_session(self, 
                      agent_or_groupchat: Union[AgentBase, GroupChat],
                      config: Optional[SessionConfig] = None) -> Session:
        """创建新会话
        
        Args:
            agent_or_groupchat: Agent实例或GroupChat实例
            config: 会话配置
            
        Returns:
            Session实例
        """
        session = Session(agent_or_groupchat, config)
        self.sessions[session.config.session_id] = session
        
        self.observability.logger.info(
            f"Session created by manager: {session.config.session_id}",
            context={"session_id": session.config.session_id}
        )
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话
        
        Args:
            session_id: 会话ID
            
        Returns:
            Session实例，如果不存在则返回None
        """
        return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str) -> None:
        """移除会话
        
        Args:
            session_id: 会话ID
        """
        if session_id in self.sessions:
            session = self.sessions[session_id]
            if session.is_active:
                session.end()
            del self.sessions[session_id]
            
            self.observability.logger.info(
                f"Session removed: {session_id}",
                context={"session_id": session_id}
            )
    
    def list_sessions(self) -> List[str]:
        """列出所有会话ID
        
        Returns:
            会话ID列表
        """
        return list(self.sessions.keys())
    
    def get_active_sessions(self) -> List[Session]:
        """获取所有活跃会话
        
        Returns:
            活跃会话列表
        """
        return [session for session in self.sessions.values() if session.is_active]
    
    def end_all_sessions(self) -> None:
        """结束所有活跃会话"""
        for session in self.sessions.values():
            if session.is_active:
                session.end()
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """获取管理器统计信息
        
        Returns:
            统计信息字典
        """
        active_sessions = self.get_active_sessions()
        
        return {
            "total_sessions": len(self.sessions),
            "active_sessions": len(active_sessions),
            "session_types": {
                "single_agent": len([s for s in self.sessions.values() 
                                   if s.sessionable.get_session_status_info()["session_type"] == "single_agent"]),
                "group_chat": len([s for s in self.sessions.values() 
                                 if s.sessionable.get_session_status_info()["session_type"] == "group_chat"])
            }
        }


# 全局会话管理器实例
_session_manager = None


def get_session_manager() -> SessionManager:
    """获取全局会话管理器实例
    
    Returns:
        SessionManager实例
    """
    global _session_manager
    if _session_manager is None:
        _session_manager = SessionManager()
    return _session_manager


# 便捷函数
def create_session(agent_or_groupchat: Union[AgentBase, GroupChat],
                  name: str = "Session",
                  **kwargs) -> Session:
    """创建会话的便捷函数
    
    Args:
        agent_or_groupchat: Agent实例或GroupChat实例
        name: 会话名称
        **kwargs: 其他配置参数
        
    Returns:
        Session实例
    """
    config = SessionConfig(name=name, **kwargs)
    return Session(agent_or_groupchat, config) 