"""Agent Framework - 灵活的智能体框架

一个灵活的智能体框架，用于构建和管理多智能体系统，支持与LLM的动态交互。

核心特性：
- 灵活的Agent构建：支持单个Agent和多Agent群聊系统
- 动态上下文加载：可插拔的变量系统，支持实时上下文更新
- MCP协议支持：集成MCP协议，扩展Agent能力
- 流式输出：支持实时流式响应
- 持久化存储：完整的状态持久化和热更新机制
- 可观测性：全面的交互监控和日志记录
"""

# 导出异常类
from .exceptions import (
    AgentFrameworkException,
    ContextEngineException,
    ContextVariableException,
    AgentException,
    GroupChatException,
    MessageQueueException,
    LLMClientException,
    MCPClientException,
    HookException,
    StreamingException,
    PersistenceException,
    ObservabilityException,
    ValidationException,
    ConfigurationException,
    TimeoutException,
    RetryException
)

# 导出上下文变量相关
from .context_variable import (
    Context,
    StaticContextVariable,
    DynamicContextVariable,
    HistoryContextVariable,
    GroupChatContextVariable
)

# 导出上下文引擎
from .context_engine import (
    ContextEngine,
    GroupChatContextEngine
)

# 导出可观测性相关
from .observability import (
    LogLevel,
    InteractionStatus,
    InteractionMetrics,
    LogEntry,
    MetricsCollector,
    Logger,
    ObservabilityManager,
    get_observability_manager
)

# 导出消息队列相关
from .message_queue import (
    Message,
    MessageQueueBase,
    InMemoryMessageQueue,
    FileMessageQueue,
    MessageQueueManager,
    get_message_queue_manager
)

# 导出LLM客户端相关
from .llm_client import (
    LLMResponse,
    LLMStreamChunk,
    LLMClientBase,
    LiteLLMClient,
    MockLLMClient,
    LLMClientManager,
    get_llm_client_manager
)

# 导出MCP客户端相关
from .mcp_client import (
    MCPTool,
    MCPResource,
    MCPPrompt,
    MCPClientBase,
    InMemoryMCPClient,
    MCPClientManager,
    get_mcp_client_manager
)

# 导出Agent相关
from .agent import (
    AgentConfig,
    AgentBase,
    SimpleAgent,
    MCPAgent,
    AgentManager,
    get_agent_manager
)

# 导出群聊相关
from .group_chat import (
    GroupChatConfig,
    GroupChatSession,
    GroupChat,
    GroupChatManager,
    get_group_chat_manager
)

# 导出会话相关
from .session import (
    SessionConfig,
    SessionHandler,
    AgentSessionHandler,
    GroupChatSessionHandler,
    Session,
    SessionManager,
    get_session_manager,
    create_session
)

# 导出会话工具
from .session_utils import (
    create_session_with_timeout,
    create_persistent_session,
    batch_process_messages,
    stream_batch_process_messages,
    get_session_summary,
    cleanup_inactive_sessions,
    export_session_history,
    SessionMonitor,
    auto_cleanup_sessions,
    get_all_session_summaries,
    create_session_monitor
)

# 版本信息
__version__ = "0.1.0"
__author__ = "Agent Framework Team"
__description__ = "A flexible agent framework for building and managing multi-agent systems"

# 主要接口
__all__ = [
    # 异常类
    "AgentFrameworkException",
    "ContextEngineException", 
    "ContextVariableException",
    "AgentException",
    "GroupChatException",
    "MessageQueueException",
    "LLMClientException",
    "MCPClientException",
    "HookException",
    "StreamingException",
    "PersistenceException",
    "ObservabilityException",
    "ValidationException",
    "ConfigurationException",
    "TimeoutException",
    "RetryException",
    
    # 上下文变量
    "Context",
    "StaticContextVariable",
    "DynamicContextVariable", 
    "HistoryContextVariable",
    "GroupChatContextVariable",
    
    # 上下文引擎
    "ContextEngine",
    "GroupChatContextEngine",
    
    # 可观测性
    "LogLevel",
    "InteractionStatus",
    "InteractionMetrics",
    "LogEntry",
    "MetricsCollector",
    "Logger",
    "ObservabilityManager",
    "get_observability_manager",
    
    # 消息队列
    "Message",
    "MessageQueueBase",
    "InMemoryMessageQueue",
    "FileMessageQueue", 
    "MessageQueueManager",
    "get_message_queue_manager",
    
    # LLM客户端
    "LLMResponse",
    "LLMStreamChunk",
    "LLMClientBase",
    "LiteLLMClient",
    "MockLLMClient",
    "LLMClientManager",
    "get_llm_client_manager",
    
    # MCP客户端
    "MCPTool",
    "MCPResource", 
    "MCPPrompt",
    "MCPClientBase",
    "InMemoryMCPClient",
    "MCPClientManager",
    "get_mcp_client_manager",
    
    # Agent
    "AgentConfig",
    "AgentBase",
    "SimpleAgent",
    "MCPAgent",
    "AgentManager",
    "get_agent_manager",
    
    # 群聊
    "GroupChatConfig",
    "GroupChatSession",
    "GroupChat",
    "GroupChatManager",
    "get_group_chat_manager",
    
    # 会话
    "SessionConfig",
    "SessionHandler",
    "AgentSessionHandler",
    "GroupChatSessionHandler",
    "Session",
    "SessionManager",
    "get_session_manager",
    "create_session",
    
    # 会话工具
    "create_session_with_timeout",
    "create_persistent_session",
    "batch_process_messages",
    "stream_batch_process_messages",
    "get_session_summary",
    "cleanup_inactive_sessions",
    "export_session_history",
    "SessionMonitor",
    "auto_cleanup_sessions",
    "get_all_session_summaries",
    "create_session_monitor"
]


def create_simple_agent(name: str, model: str = "gpt-3.5-turbo", 
                       system_prompt: str = "", mcp_tools: list = None, 
                       **kwargs) -> SimpleAgent:
    """创建简单Agent的便捷函数
    
    Args:
        name: Agent名称
        model: 模型名称
        system_prompt: 系统提示词
        mcp_tools: MCP工具列表 (List[StdioServerParameters])
        **kwargs: 其他配置参数
        
    Returns:
        SimpleAgent实例
    """
    config = AgentConfig(
        name=name,
        model=model,
        system_prompt=system_prompt,
        mcp_tools=mcp_tools or [],
        **kwargs
    )
    return SimpleAgent(config)


def create_mcp_agent(name: str, model: str = "gpt-3.5-turbo",
                    system_prompt: str = "", mcp_tools: list = None,
                    mcp_client_name: str = None, **kwargs) -> MCPAgent:
    """创建支持MCP的Agent的便捷函数
    
    Args:
        name: Agent名称
        model: 模型名称
        system_prompt: 系统提示词
        mcp_tools: MCP工具列表 (List[StdioServerParameters])
        mcp_client_name: MCP客户端名称（保留向后兼容性）
        **kwargs: 其他配置参数
        
    Returns:
        MCPAgent实例（现在等同于SimpleAgent）
    """
    config = AgentConfig(
        name=name,
        model=model,
        system_prompt=system_prompt,
        mcp_tools=mcp_tools or [],
        mcp_client_name=mcp_client_name,
        **kwargs
    )
    return MCPAgent(config)


def create_group_chat(name: str, selector_model: str = "gpt-3.5-turbo",
                     selector_prompt: str = "", **kwargs) -> GroupChat:
    """创建群聊的便捷函数
    
    Args:
        name: 群聊名称
        selector_model: 选择器模型
        selector_prompt: 选择器提示词
        **kwargs: 其他配置参数
        
    Returns:
        GroupChat实例
    """
    config = GroupChatConfig(
        name=name,
        selector_model=selector_model,
        selector_prompt=selector_prompt,
        **kwargs
    )
    return GroupChat(config)


def setup_default_clients():
    """设置默认客户端
    
    这个函数设置框架的默认客户端实例，方便快速开始使用。
    """
    # 设置默认LLM客户端
    llm_manager = get_llm_client_manager()
    if not llm_manager.list_clients():
        # 尝试创建LiteLLM客户端
        try:
            default_llm = LiteLLMClient()
            llm_manager.register_client("default", default_llm, is_default=True)
        except Exception:
            # 如果LiteLLM不可用，使用Mock客户端
            mock_llm = MockLLMClient()
            llm_manager.register_client("default", mock_llm, is_default=True)
    
    # 设置默认MCP客户端
    mcp_manager = get_mcp_client_manager()
    if not mcp_manager.list_clients():
        default_mcp = InMemoryMCPClient()
        mcp_manager.register_client("default", default_mcp, is_default=True)


def get_framework_info() -> dict:
    """获取框架信息
    
    Returns:
        框架信息字典
    """
    return {
        "name": "Agent Framework",
        "version": __version__,
        "author": __author__,
        "description": __description__,
        "components": {
            "context_engine": "Dynamic context management with variable templates",
            "llm_client": "Unified LLM interface with LiteLLM support", 
            "mcp_client": "MCP protocol support for tool integration",
            "message_queue": "Message storage and retrieval with persistence",
            "observability": "Comprehensive monitoring and logging",
            "agent": "Base agent classes with streaming support",
            "group_chat": "Multi-agent collaboration system"
        }
    }


# 框架初始化
def initialize_framework():
    """初始化框架
    
    执行必要的初始化步骤，设置默认配置。
    """
    # 设置默认客户端
    setup_default_clients()
    
    # 初始化可观测性
    observability = get_observability_manager()
    observability.logger.info("Agent Framework initialized", 
                             context=get_framework_info())


# 自动初始化（当模块被导入时）
initialize_framework() 