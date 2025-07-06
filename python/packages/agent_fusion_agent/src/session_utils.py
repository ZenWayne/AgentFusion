"""Session工具模块

提供Session管理的工具函数和常用操作。
"""

import asyncio
from typing import Dict, List, Optional, Any, Union, AsyncGenerator
from datetime import datetime, timedelta

from .agent import AgentBase
from .group_chat import GroupChat
from .session import Session, SessionConfig, SessionManager, get_session_manager
from .observability import get_observability_manager


def create_session_with_timeout(
    agent_or_groupchat: Union[AgentBase, GroupChat],
    timeout_minutes: int = 30,
    name: str = "Session",
    **kwargs
) -> Session:
    """创建带超时的会话
    
    Args:
        agent_or_groupchat: Agent或GroupChat实例
        timeout_minutes: 超时时间（分钟）
        name: 会话名称
        **kwargs: 其他配置参数
        
    Returns:
        Session实例
    """
    config = SessionConfig(
        name=name,
        metadata={
            "timeout_minutes": timeout_minutes,
            "created_at": datetime.now().isoformat(),
            **kwargs.get("metadata", {})
        },
        **{k: v for k, v in kwargs.items() if k != "metadata"}
    )
    
    return Session(agent_or_groupchat, config)


def create_persistent_session(
    agent_or_groupchat: Union[AgentBase, GroupChat],
    session_id: str,
    name: str = "Persistent Session",
    **kwargs
) -> Session:
    """创建持久化会话
    
    Args:
        agent_or_groupchat: Agent或GroupChat实例
        session_id: 指定的会话ID
        name: 会话名称
        **kwargs: 其他配置参数
        
    Returns:
        Session实例
    """
    config = SessionConfig(
        session_id=session_id,
        name=name,
        metadata={
            "persistent": True,
            "created_at": datetime.now().isoformat(),
            **kwargs.get("metadata", {})
        },
        **{k: v for k, v in kwargs.items() if k != "metadata"}
    )
    
    return Session(agent_or_groupchat, config)


async def batch_process_messages(
    session: Session,
    messages: List[str],
    delay_seconds: float = 0.1
) -> List[Any]:
    """批量处理消息
    
    Args:
        session: 会话实例
        messages: 消息列表
        delay_seconds: 消息间延迟（秒）
        
    Returns:
        响应列表
    """
    if not session.is_active:
        raise ValueError("Session must be active before processing messages")
    
    responses = []
    for message in messages:
        try:
            response = await session.process_message(message)
            responses.append(response)
            
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
                
        except Exception as e:
            responses.append({"error": str(e), "message": message})
    
    return responses


async def stream_batch_process_messages(
    session: Session,
    messages: List[str],
    delay_seconds: float = 0.1
) -> AsyncGenerator[Dict[str, Any], None]:
    """流式批量处理消息
    
    Args:
        session: 会话实例
        messages: 消息列表
        delay_seconds: 消息间延迟（秒）
        
    Yields:
        包含消息索引和响应的字典
    """
    if not session.is_active:
        raise ValueError("Session must be active before processing messages")
    
    for index, message in enumerate(messages):
        try:
            yield {
                "message_index": index,
                "message": message,
                "status": "processing"
            }
            
            if session.session_type == "single_agent":
                # 单Agent流式处理
                content = ""
                async for chunk in session.stream_process_message(message):
                    content += chunk.content
                    yield {
                        "message_index": index,
                        "message": message,
                        "chunk": chunk.content,
                        "accumulated_content": content,
                        "is_final": chunk.is_final
                    }
            else:
                # 群聊流式处理
                async for response in session.stream_process_message(message):
                    yield {
                        "message_index": index,
                        "message": message,
                        "response": response
                    }
            
            yield {
                "message_index": index,
                "message": message,
                "status": "completed"
            }
            
            if delay_seconds > 0:
                await asyncio.sleep(delay_seconds)
                
        except Exception as e:
            yield {
                "message_index": index,
                "message": message,
                "status": "error",
                "error": str(e)
            }


def get_session_summary(session: Session) -> Dict[str, Any]:
    """获取会话摘要信息
    
    Args:
        session: 会话实例
        
    Returns:
        会话摘要字典
    """
    status = session.get_status()
    history = session.get_conversation_history()
    
    # 计算统计信息
    user_messages = [msg for msg in history if msg["role"] == "user"]
    assistant_messages = [msg for msg in history if msg["role"] == "assistant"]
    
    summary = {
        "session_id": status["session_id"],
        "name": status["name"],
        "session_type": status["session_type"],
        "is_active": status["is_active"],
        "duration": status.get("duration"),
        "message_statistics": {
            "total_messages": len(history),
            "user_messages": len(user_messages),
            "assistant_messages": len(assistant_messages)
        },
        "context_variables": len(session.get_context_variables()),
        "created_at": session.config.metadata.get("created_at"),
        "last_activity": history[-1]["timestamp"] if history else None
    }
    
    if session.session_type == "single_agent":
        summary["agent_info"] = {
            "name": session.agent.config.name,
            "model": session.agent.config.model
        }
    else:
        summary["group_info"] = {
            "name": session.group_chat.config.name,
            "agent_count": len(session.group_chat.agents)
        }
    
    return summary


def cleanup_inactive_sessions(
    session_manager: Optional[SessionManager] = None,
    timeout_minutes: int = 60
) -> int:
    """清理非活跃会话
    
    Args:
        session_manager: 会话管理器实例
        timeout_minutes: 超时时间（分钟）
        
    Returns:
        清理的会话数量
    """
    if session_manager is None:
        session_manager = get_session_manager()
    
    current_time = datetime.now()
    cleanup_count = 0
    sessions_to_remove = []
    
    for session_id, session in session_manager.sessions.items():
        # 检查会话是否超时
        if session.start_time:
            elapsed_time = current_time - session.start_time
            if elapsed_time > timedelta(minutes=timeout_minutes):
                sessions_to_remove.append(session_id)
                cleanup_count += 1
    
    # 移除超时的会话
    for session_id in sessions_to_remove:
        session_manager.remove_session(session_id)
    
    return cleanup_count


def export_session_history(
    session: Session,
    format: str = "json",
    include_metadata: bool = True
) -> Union[str, Dict[str, Any]]:
    """导出会话历史
    
    Args:
        session: 会话实例
        format: 导出格式（json, text, markdown）
        include_metadata: 是否包含元数据
        
    Returns:
        导出的数据
    """
    history = session.get_conversation_history()
    status = session.get_status()
    
    if format == "json":
        export_data = {
            "session_info": status,
            "conversation_history": history
        }
        
        if include_metadata:
            export_data["metadata"] = {
                "export_time": datetime.now().isoformat(),
                "total_messages": len(history),
                "context_variables": session.get_context_variables()
            }
        
        return export_data
    
    elif format == "text":
        lines = []
        lines.append(f"Session: {status['name']} ({status['session_id']})")
        lines.append(f"Type: {status['session_type']}")
        lines.append(f"Active: {status['is_active']}")
        lines.append("-" * 50)
        
        for msg in history:
            timestamp = msg.get("timestamp", "")
            role = msg["role"]
            content = msg["content"]
            lines.append(f"[{timestamp}] {role}: {content}")
        
        return "\n".join(lines)
    
    elif format == "markdown":
        lines = []
        lines.append(f"# Session: {status['name']}")
        lines.append(f"- **Session ID**: {status['session_id']}")
        lines.append(f"- **Type**: {status['session_type']}")
        lines.append(f"- **Active**: {status['is_active']}")
        lines.append("")
        lines.append("## Conversation History")
        lines.append("")
        
        for msg in history:
            timestamp = msg.get("timestamp", "")
            role = msg["role"]
            content = msg["content"]
            role_display = "🧑 User" if role == "user" else "🤖 Assistant"
            lines.append(f"### {role_display}")
            lines.append(f"*{timestamp}*")
            lines.append("")
            lines.append(content)
            lines.append("")
        
        return "\n".join(lines)
    
    else:
        raise ValueError(f"Unsupported format: {format}")


class SessionMonitor:
    """会话监控器
    
    监控会话活动，提供统计信息和警报。
    """
    
    def __init__(self, session_manager: Optional[SessionManager] = None):
        """初始化监控器
        
        Args:
            session_manager: 会话管理器实例
        """
        self.session_manager = session_manager or get_session_manager()
        self.observability = get_observability_manager()
        self.monitoring_active = False
        self.monitor_task = None
    
    def start_monitoring(self, interval_seconds: int = 60):
        """启动监控
        
        Args:
            interval_seconds: 监控间隔（秒）
        """
        if self.monitoring_active:
            return
        
        self.monitoring_active = True
        self.monitor_task = asyncio.create_task(
            self._monitor_loop(interval_seconds)
        )
    
    def stop_monitoring(self):
        """停止监控"""
        self.monitoring_active = False
        if self.monitor_task:
            self.monitor_task.cancel()
    
    async def _monitor_loop(self, interval_seconds: int):
        """监控循环"""
        while self.monitoring_active:
            try:
                await self._collect_metrics()
                await asyncio.sleep(interval_seconds)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.observability.logger.error(
                    f"Session monitoring error: {e}",
                    context={"error": str(e)}
                )
                await asyncio.sleep(interval_seconds)
    
    async def _collect_metrics(self):
        """收集监控指标"""
        stats = self.session_manager.get_manager_statistics()
        active_sessions = self.session_manager.get_active_sessions()
        
        # 记录基本统计信息
        self.observability.logger.info(
            "Session monitoring report",
            context={
                "total_sessions": stats["total_sessions"],
                "active_sessions": stats["active_sessions"],
                "session_types": stats["session_types"]
            }
        )
        
        # 检查长时间运行的会话
        long_running_sessions = []
        current_time = datetime.now()
        
        for session in active_sessions:
            if session.start_time:
                duration = current_time - session.start_time
                if duration > timedelta(hours=2):  # 超过2小时
                    long_running_sessions.append({
                        "session_id": session.config.session_id,
                        "name": session.config.name,
                        "duration_hours": duration.total_seconds() / 3600
                    })
        
        if long_running_sessions:
            self.observability.logger.warning(
                "Long-running sessions detected",
                context={"sessions": long_running_sessions}
            )
    
    def get_monitor_status(self) -> Dict[str, Any]:
        """获取监控状态
        
        Returns:
            监控状态字典
        """
        return {
            "monitoring_active": self.monitoring_active,
            "session_count": len(self.session_manager.sessions),
            "active_session_count": len(self.session_manager.get_active_sessions())
        }


# 便捷函数
def auto_cleanup_sessions(timeout_minutes: int = 60) -> int:
    """自动清理会话的便捷函数
    
    Args:
        timeout_minutes: 超时时间（分钟）
        
    Returns:
        清理的会话数量
    """
    return cleanup_inactive_sessions(timeout_minutes=timeout_minutes)


def get_all_session_summaries() -> List[Dict[str, Any]]:
    """获取所有会话摘要的便捷函数
    
    Returns:
        会话摘要列表
    """
    session_manager = get_session_manager()
    summaries = []
    
    for session in session_manager.sessions.values():
        try:
            summary = get_session_summary(session)
            summaries.append(summary)
        except Exception as e:
            summaries.append({
                "session_id": session.config.session_id,
                "error": str(e)
            })
    
    return summaries


def create_session_monitor() -> SessionMonitor:
    """创建会话监控器的便捷函数
    
    Returns:
        SessionMonitor实例
    """
    return SessionMonitor() 