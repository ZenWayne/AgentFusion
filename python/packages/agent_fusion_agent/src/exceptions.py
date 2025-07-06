"""Agent Framework异常定义模块

本模块定义了Agent框架中使用的自定义异常类。
"""

from typing import Optional, Dict, Any


class AgentFrameworkException(Exception):
    """Agent框架基础异常类"""
    
    def __init__(self, message: str, error_code: Optional[str] = None, 
                 context: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.error_code = error_code
        self.context = context or {}


class ContextEngineException(AgentFrameworkException):
    """上下文引擎异常"""
    pass


class ContextVariableException(AgentFrameworkException):
    """上下文变量异常"""
    pass


class AgentException(AgentFrameworkException):
    """Agent异常"""
    pass


class GroupChatException(AgentFrameworkException):
    """群聊系统异常"""
    pass


class MessageQueueException(AgentFrameworkException):
    """消息队列异常"""
    pass


class LLMClientException(AgentFrameworkException):
    """LLM客户端异常"""
    pass


class MCPClientException(AgentFrameworkException):
    """MCP客户端异常"""
    pass


class HookException(AgentFrameworkException):
    """Hook机制异常"""
    pass


class StreamingException(AgentFrameworkException):
    """流式输出异常"""
    pass


class PersistenceException(AgentFrameworkException):
    """持久化异常"""
    pass


class ObservabilityException(AgentFrameworkException):
    """可观测性异常"""
    pass


class ValidationException(AgentFrameworkException):
    """验证异常"""
    pass


class ConfigurationException(AgentFrameworkException):
    """配置异常"""
    pass


class TimeoutException(AgentFrameworkException):
    """超时异常"""
    pass


class RetryException(AgentFrameworkException):
    """重试异常"""
    pass 