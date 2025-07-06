"""可观测性模块

实现监控和日志记录功能，提供全面的交互监控和调试支持。
"""

import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
from .exceptions import ObservabilityException


class LogLevel(Enum):
    """日志级别枚举"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class InteractionStatus(Enum):
    """交互状态枚举"""
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


@dataclass
class InteractionMetrics:
    """交互指标数据类"""
    # 基础信息
    interaction_id: str
    timestamp: datetime = field(default_factory=datetime.now)
    
    # 请求相关
    request_id: str = ""
    request_params: Dict[str, Any] = field(default_factory=dict)
    request_time: Optional[datetime] = None
    request_status: InteractionStatus = InteractionStatus.PENDING
    
    # 响应相关
    response_id: str = ""
    response_params: Dict[str, Any] = field(default_factory=dict)
    response_time: Optional[datetime] = None
    response_status: InteractionStatus = InteractionStatus.PENDING
    
    # 性能指标
    duration_ms: Optional[float] = None
    token_count: Optional[int] = None
    
    # 错误信息
    error_message: Optional[str] = None
    error_code: Optional[str] = None
    
    # 上下文信息
    agent_id: Optional[str] = None
    model_name: Optional[str] = None
    context_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LogEntry:
    """日志条目数据类"""
    timestamp: datetime = field(default_factory=datetime.now)
    level: LogLevel = LogLevel.INFO
    message: str = ""
    component: str = ""
    interaction_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "level": self.level.value,
            "message": self.message,
            "component": self.component,
            "interaction_id": self.interaction_id,
            "context": self.context
        }


class MetricsCollector:
    """指标收集器"""
    
    def __init__(self):
        self.metrics: Dict[str, InteractionMetrics] = {}
        self.aggregated_metrics: Dict[str, Any] = {}
        self._observers: List[Callable[[InteractionMetrics], None]] = []
    
    def start_interaction(self, interaction_id: Optional[str] = None) -> str:
        """开始一次交互记录
        
        Args:
            interaction_id: 可选的交互ID
            
        Returns:
            交互ID
        """
        if not interaction_id:
            interaction_id = str(uuid.uuid4())
        
        self.metrics[interaction_id] = InteractionMetrics(
            interaction_id=interaction_id,
            request_time=datetime.now(),
            request_status=InteractionStatus.IN_PROGRESS
        )
        
        return interaction_id
    
    def record_request(self, interaction_id: str, request_params: Dict[str, Any],
                      agent_id: Optional[str] = None, model_name: Optional[str] = None) -> None:
        """记录请求信息
        
        Args:
            interaction_id: 交互ID
            request_params: 请求参数
            agent_id: Agent ID
            model_name: 模型名称
        """
        if interaction_id not in self.metrics:
            raise ObservabilityException(f"Interaction {interaction_id} not found")
        
        metrics = self.metrics[interaction_id]
        metrics.request_id = str(uuid.uuid4())
        metrics.request_params = request_params
        metrics.agent_id = agent_id
        metrics.model_name = model_name
        metrics.request_time = datetime.now()
        metrics.request_status = InteractionStatus.IN_PROGRESS
    
    def record_response(self, interaction_id: str, response_params: Dict[str, Any],
                       status: InteractionStatus = InteractionStatus.SUCCESS) -> None:
        """记录响应信息
        
        Args:
            interaction_id: 交互ID
            response_params: 响应参数
            status: 响应状态
        """
        if interaction_id not in self.metrics:
            raise ObservabilityException(f"Interaction {interaction_id} not found")
        
        metrics = self.metrics[interaction_id]
        metrics.response_id = str(uuid.uuid4())
        metrics.response_params = response_params
        metrics.response_time = datetime.now()
        metrics.response_status = status
        
        # 计算持续时间
        if metrics.request_time:
            duration = (metrics.response_time - metrics.request_time).total_seconds() * 1000
            metrics.duration_ms = duration
        
        # 通知观察者
        self._notify_observers(metrics)
    
    def record_error(self, interaction_id: str, error_message: str, 
                    error_code: Optional[str] = None) -> None:
        """记录错误信息
        
        Args:
            interaction_id: 交互ID
            error_message: 错误消息
            error_code: 错误代码
        """
        if interaction_id not in self.metrics:
            raise ObservabilityException(f"Interaction {interaction_id} not found")
        
        metrics = self.metrics[interaction_id]
        metrics.error_message = error_message
        metrics.error_code = error_code
        metrics.response_status = InteractionStatus.FAILED
        metrics.response_time = datetime.now()
        
        # 计算持续时间
        if metrics.request_time:
            duration = (metrics.response_time - metrics.request_time).total_seconds() * 1000
            metrics.duration_ms = duration
        
        # 通知观察者
        self._notify_observers(metrics)
    
    def add_context(self, interaction_id: str, context_data: Dict[str, Any]) -> None:
        """添加上下文信息
        
        Args:
            interaction_id: 交互ID
            context_data: 上下文数据
        """
        if interaction_id not in self.metrics:
            raise ObservabilityException(f"Interaction {interaction_id} not found")
        
        metrics = self.metrics[interaction_id]
        metrics.context_data.update(context_data)
    
    def get_metrics(self, interaction_id: str) -> Optional[InteractionMetrics]:
        """获取指定交互的指标
        
        Args:
            interaction_id: 交互ID
            
        Returns:
            交互指标，如果不存在则返回None
        """
        return self.metrics.get(interaction_id)
    
    def get_all_metrics(self) -> Dict[str, InteractionMetrics]:
        """获取所有交互指标
        
        Returns:
            所有交互指标字典
        """
        return self.metrics.copy()
    
    def get_summary_statistics(self) -> Dict[str, Any]:
        """获取汇总统计信息
        
        Returns:
            汇总统计信息字典
        """
        if not self.metrics:
            return {}
        
        # 计算基础统计
        total_count = len(self.metrics)
        success_count = sum(1 for m in self.metrics.values() 
                          if m.response_status == InteractionStatus.SUCCESS)
        failed_count = sum(1 for m in self.metrics.values() 
                         if m.response_status == InteractionStatus.FAILED)
        
        # 计算性能统计
        durations = [m.duration_ms for m in self.metrics.values() if m.duration_ms]
        avg_duration = sum(durations) / len(durations) if durations else 0
        max_duration = max(durations) if durations else 0
        min_duration = min(durations) if durations else 0
        
        return {
            "total_interactions": total_count,
            "successful_interactions": success_count,
            "failed_interactions": failed_count,
            "success_rate": success_count / total_count if total_count > 0 else 0,
            "average_duration_ms": avg_duration,
            "max_duration_ms": max_duration,
            "min_duration_ms": min_duration
        }
    
    def add_observer(self, observer: Callable[[InteractionMetrics], None]) -> None:
        """添加观察者
        
        Args:
            observer: 观察者函数
        """
        self._observers.append(observer)
    
    def remove_observer(self, observer: Callable[[InteractionMetrics], None]) -> None:
        """移除观察者
        
        Args:
            observer: 观察者函数
        """
        if observer in self._observers:
            self._observers.remove(observer)
    
    def _notify_observers(self, metrics: InteractionMetrics) -> None:
        """通知观察者
        
        Args:
            metrics: 交互指标
        """
        for observer in self._observers:
            try:
                observer(metrics)
            except Exception as e:
                # 观察者异常不应该影响主流程
                pass
    
    def clear_metrics(self) -> None:
        """清除所有指标"""
        self.metrics.clear()
        self.aggregated_metrics.clear()


class Logger:
    """日志记录器"""
    
    def __init__(self, component: str = "AgentFramework"):
        self.component = component
        self.logs: List[LogEntry] = []
        self.handlers: List[Callable[[LogEntry], None]] = []
        self.min_level = LogLevel.INFO
    
    def set_level(self, level: LogLevel) -> None:
        """设置最小日志级别
        
        Args:
            level: 日志级别
        """
        self.min_level = level
    
    def add_handler(self, handler: Callable[[LogEntry], None]) -> None:
        """添加日志处理器
        
        Args:
            handler: 日志处理器函数
        """
        self.handlers.append(handler)
    
    def remove_handler(self, handler: Callable[[LogEntry], None]) -> None:
        """移除日志处理器
        
        Args:
            handler: 日志处理器函数
        """
        if handler in self.handlers:
            self.handlers.remove(handler)
    
    def log(self, level: LogLevel, message: str, 
           interaction_id: Optional[str] = None, 
           context: Optional[Dict[str, Any]] = None) -> None:
        """记录日志
        
        Args:
            level: 日志级别
            message: 日志消息
            interaction_id: 交互ID
            context: 上下文信息
        """
        if level.value < self.min_level.value:
            return
        
        entry = LogEntry(
            level=level,
            message=message,
            component=self.component,
            interaction_id=interaction_id,
            context=context or {}
        )
        
        self.logs.append(entry)
        
        # 调用处理器
        for handler in self.handlers:
            try:
                handler(entry)
            except Exception as e:
                # 处理器异常不应该影响主流程
                pass
    
    def debug(self, message: str, interaction_id: Optional[str] = None, 
             context: Optional[Dict[str, Any]] = None) -> None:
        """记录调试日志"""
        self.log(LogLevel.DEBUG, message, interaction_id, context)
    
    def info(self, message: str, interaction_id: Optional[str] = None, 
            context: Optional[Dict[str, Any]] = None) -> None:
        """记录信息日志"""
        self.log(LogLevel.INFO, message, interaction_id, context)
    
    def warning(self, message: str, interaction_id: Optional[str] = None, 
               context: Optional[Dict[str, Any]] = None) -> None:
        """记录警告日志"""
        self.log(LogLevel.WARNING, message, interaction_id, context)
    
    def error(self, message: str, interaction_id: Optional[str] = None, 
             context: Optional[Dict[str, Any]] = None) -> None:
        """记录错误日志"""
        self.log(LogLevel.ERROR, message, interaction_id, context)
    
    def critical(self, message: str, interaction_id: Optional[str] = None, 
                context: Optional[Dict[str, Any]] = None) -> None:
        """记录严重错误日志"""
        self.log(LogLevel.CRITICAL, message, interaction_id, context)
    
    def get_logs(self, level: Optional[LogLevel] = None, 
                interaction_id: Optional[str] = None) -> List[LogEntry]:
        """获取日志条目
        
        Args:
            level: 可选的日志级别过滤
            interaction_id: 可选的交互ID过滤
            
        Returns:
            日志条目列表
        """
        logs = self.logs
        
        if level:
            logs = [log for log in logs if log.level == level]
        
        if interaction_id:
            logs = [log for log in logs if log.interaction_id == interaction_id]
        
        return logs
    
    def clear_logs(self) -> None:
        """清除所有日志"""
        self.logs.clear()


class ObservabilityManager:
    """可观测性管理器
    
    统一管理指标收集和日志记录功能。
    """
    
    def __init__(self):
        self.metrics_collector = MetricsCollector()
        self.logger = Logger()
        self._interaction_stack: List[str] = []
    
    def start_interaction(self, interaction_id: Optional[str] = None,
                         context: Optional[Dict[str, Any]] = None) -> str:
        """开始一次交互
        
        Args:
            interaction_id: 可选的交互ID
            context: 可选的上下文信息
            
        Returns:
            交互ID
        """
        interaction_id = self.metrics_collector.start_interaction(interaction_id)
        self._interaction_stack.append(interaction_id)
        
        if context:
            self.metrics_collector.add_context(interaction_id, context)
        
        self.logger.info(f"Started interaction {interaction_id}", 
                        interaction_id=interaction_id, context=context)
        
        return interaction_id
    
    def record_llm_request(self, interaction_id: str, model_name: str,
                          messages: List[Dict[str, Any]], 
                          agent_id: Optional[str] = None,
                          **kwargs) -> None:
        """记录LLM请求
        
        Args:
            interaction_id: 交互ID
            model_name: 模型名称
            messages: 消息列表
            agent_id: Agent ID
            **kwargs: 其他请求参数
        """
        request_params = {
            "model": model_name,
            "messages": messages,
            **kwargs
        }
        
        self.metrics_collector.record_request(
            interaction_id, request_params, agent_id, model_name
        )
        
        self.logger.info(f"LLM request sent to {model_name}",
                        interaction_id=interaction_id,
                        context={"model": model_name, "message_count": len(messages)})
    
    def record_llm_response(self, interaction_id: str, response: Dict[str, Any],
                           status: InteractionStatus = InteractionStatus.SUCCESS) -> None:
        """记录LLM响应
        
        Args:
            interaction_id: 交互ID
            response: 响应数据
            status: 响应状态
        """
        self.metrics_collector.record_response(interaction_id, response, status)
        
        log_message = f"LLM response received with status {status.value}"
        if status == InteractionStatus.SUCCESS:
            self.logger.info(log_message, interaction_id=interaction_id)
        else:
            self.logger.error(log_message, interaction_id=interaction_id)
    
    def record_error(self, interaction_id: str, error: Exception) -> None:
        """记录错误
        
        Args:
            interaction_id: 交互ID
            error: 异常对象
        """
        error_message = str(error)
        error_code = getattr(error, 'error_code', None)
        
        self.metrics_collector.record_error(interaction_id, error_message, error_code)
        
        self.logger.error(f"Error occurred: {error_message}",
                         interaction_id=interaction_id,
                         context={"error_code": error_code, "error_type": type(error).__name__})
    
    def end_interaction(self, interaction_id: Optional[str] = None) -> None:
        """结束交互
        
        Args:
            interaction_id: 可选的交互ID，如果不提供则使用当前交互
        """
        if not interaction_id and self._interaction_stack:
            interaction_id = self._interaction_stack.pop()
        elif interaction_id and interaction_id in self._interaction_stack:
            self._interaction_stack.remove(interaction_id)
        
        if interaction_id:
            self.logger.info(f"Ended interaction {interaction_id}", 
                           interaction_id=interaction_id)
    
    def get_current_interaction(self) -> Optional[str]:
        """获取当前交互ID
        
        Returns:
            当前交互ID，如果没有则返回None
        """
        return self._interaction_stack[-1] if self._interaction_stack else None
    
    def get_metrics_summary(self) -> Dict[str, Any]:
        """获取指标摘要
        
        Returns:
            指标摘要字典
        """
        return self.metrics_collector.get_summary_statistics()
    
    def export_metrics(self, format: str = "dict") -> Any:
        """导出指标数据
        
        Args:
            format: 导出格式 ("dict", "json")
            
        Returns:
            导出的数据
        """
        metrics = self.metrics_collector.get_all_metrics()
        
        if format == "dict":
            return {
                interaction_id: {
                    "interaction_id": m.interaction_id,
                    "timestamp": m.timestamp.isoformat(),
                    "request_params": m.request_params,
                    "response_params": m.response_params,
                    "duration_ms": m.duration_ms,
                    "status": m.response_status.value,
                    "error_message": m.error_message,
                    "agent_id": m.agent_id,
                    "model_name": m.model_name
                }
                for interaction_id, m in metrics.items()
            }
        elif format == "json":
            import json
            return json.dumps(self.export_metrics("dict"), indent=2)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def clear_all_data(self) -> None:
        """清除所有数据"""
        self.metrics_collector.clear_metrics()
        self.logger.clear_logs()
        self._interaction_stack.clear()


# 全局可观测性管理器实例
observability_manager = ObservabilityManager()


def get_observability_manager() -> ObservabilityManager:
    """获取全局可观测性管理器实例
    
    Returns:
        可观测性管理器实例
    """
    return observability_manager 