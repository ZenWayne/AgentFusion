# Agent Framework

一个灵活的智能体框架，用于构建和管理多智能体系统，支持与LLM的动态交互。

## 目录
- [安装与配置](#安装与配置)
- [快速开始](#快速开始)
- [核心特性](#核心特性)
- [会话管理](#会话管理)
- [LLM交互](#llm交互)
- [动态上下文引擎](#动态上下文引擎)
- [MCP集成](#mcp集成)
- [群聊系统](#群聊系统)
- [消息队列](#消息队列)
- [流式输出](#流式输出)
- [可观测性](#可观测性)
- [API参考](#api参考)
- [系统架构](#系统架构)

## 安装与配置

### 环境要求
- Python 3.8+
- 可选：LiteLLM (用于真实LLM交互)

### 安装依赖
```bash
# 核心依赖（框架自身无外部依赖）
pip install dataclasses  # Python 3.6需要

# 可选依赖
pip install litellm      # 用于真实LLM交互
```

### 导入框架
```python
from agent import (
    # 快速创建函数
    create_simple_agent, 
    create_mcp_agent, 
    create_group_chat,
    create_session,
    
    # 核心类
    AgentConfig,
    GroupChatConfig,
    SessionConfig,
    ContextEngine,
    
    # 管理器
    get_agent_manager,
    get_group_chat_manager,
    get_session_manager,
    get_llm_client_manager,
    get_mcp_client_manager
)
```

## 快速开始

### 1. 创建简单Agent
```python
from agent import create_simple_agent, LiteLLMClient, get_llm_client_manager

# 注册LLM客户端
llm_manager = get_llm_client_manager()
llm_client = LiteLLMClient(default_model="gpt-4")
llm_manager.register_client("default", llm_client, is_default=True)

# 创建Agent
agent = create_simple_agent(
    name="AI助手",
    model="gpt-4",
    system_prompt="你是一个有用的AI助手。"
)

# 异步对话
response = await agent.process_message("你好！")
print(response.content)

# 同步对话
response = agent.get_llm_client().sync_chat_completion(
    messages=[{"role": "user", "content": "你好！"}],
    model="gpt-4"
)
print(response.content)
```

### 2. 创建群聊系统
```python
from agent import create_simple_agent, create_group_chat

# 创建多个Agent
agent1 = create_simple_agent("Alice", system_prompt="你是Alice，一个技术专家。")
agent2 = create_simple_agent("Bob", system_prompt="你是Bob，一个产品经理。")

# 创建群聊
group = create_group_chat("技术讨论组")
group.add_agent(agent1)
group.add_agent(agent2)

# 开始群聊会话
session = group.start_session()
responses = await group.process_message("我们需要开发一个新功能")

for response in responses:
    print(f"{response['agent_name']}: {response['content']}")
```

### 3. 流式对话
```python
# Agent流式对话
async for chunk in agent.stream_process_message("讲一个故事"):
    print(chunk.content, end="", flush=True)

# 群聊流式对话
async for response in group.stream_process_message("讨论技术方案"):
    if not response['is_final']:
        print(f"{response['agent_name']}: {response['chunk']}", end="")
    else:
        print(f"\n[{response['agent_name']} 发言完毕]")
```

## 核心特性

- **🤖 灵活的Agent构建**: 支持单个Agent和多Agent群聊系统
- **🔄 动态上下文加载**: 可插拔的变量系统，支持实时上下文更新
- **🔧 MCP协议支持**: 集成MCP协议，扩展Agent能力
- **⚡ 流式输出**: 支持实时流式响应
- **💾 持久化存储**: 完整的状态持久化和热更新机制
- **📊 可观测性**: 全面的交互监控和日志记录
- **🎯 异步优先**: 全面支持异步操作，提升并发性能
- **🎪 统一会话管理**: 提供统一的Session接口，自动管理组件

## 会话管理

### Session类概述
Session类是框架的高级封装，提供统一的会话管理接口。它能够：
- 自动为单个Agent创建必要的组件（MessageQueue、ContextEngine）
- 直接使用GroupChat的内置组件
- 提供一致的交互接口和生命周期管理
- 支持上下文管理器模式

### 1. 创建单Agent会话
```python
from agent import create_simple_agent, create_session

# 创建Agent
agent = create_simple_agent(
    name="AI助手",
    model="gpt-4",
    system_prompt="你是一个有用的AI助手。"
)

# 创建会话（自动创建MessageQueue和ContextEngine）
session = create_session(agent, name="AI助手会话")

# 开始会话
session.start()

# 处理消息
response = await session.process_message("你好！")
print(response.content)

# 结束会话
session.end()
```

### 2. 创建群聊会话
```python
from agent import create_simple_agent, create_group_chat, create_session

# 创建多个Agent
agent1 = create_simple_agent("Alice", system_prompt="你是Alice，一个技术专家。")
agent2 = create_simple_agent("Bob", system_prompt="你是Bob，一个产品经理。")

# 创建群聊
group = create_group_chat("技术讨论组")
group.add_agent(agent1)
group.add_agent(agent2)

# 创建群聊会话（使用群聊内置组件）
session = create_session(group, name="技术讨论会话")

# 开始会话
session.start()

# 处理消息
responses = await session.process_message("我们需要开发一个新功能")
for response in responses:
    print(f"{response['agent_name']}: {response['content']}")

# 结束会话
session.end()
```

### 3. 使用上下文管理器
```python
# 同步上下文管理器
with create_session(agent, name="同步会话") as session:
    response = await session.process_message("Hello")
    print(response.content)

# 异步上下文管理器
async with create_session(agent, name="异步会话") as session:
    response = await session.process_message("Hello")
    print(response.content)
```

### 4. 流式会话
```python
# 单Agent流式会话
async def single_agent_stream():
    with create_session(agent, name="流式会话") as session:
        async for chunk in session.stream_process_message("讲一个故事"):
            print(chunk.content, end="", flush=True)

# 群聊流式会话
async def group_chat_stream():
    with create_session(group, name="群聊流式会话") as session:
        async for response in session.stream_process_message("讨论技术方案"):
            if not response.get('is_final'):
                print(f"{response['agent_name']}: {response['chunk']}", end="")
            else:
                print(f"\n[{response['agent_name']} 发言完毕]")

# 运行流式会话
await single_agent_stream()
await group_chat_stream()
```

### 5. 会话状态管理
```python
# 创建会话
session = create_session(agent, name="状态管理会话")

# 添加上下文变量
session.add_context_variable("user_name", "张三")
session.add_context_variable("session_start", datetime.now())

# 开始会话
session.start()

# 获取会话状态
status = session.get_status()
print(f"会话状态: {status}")

# 获取会话历史
history = session.get_conversation_history(limit=10)
for msg in history:
    print(f"{msg['role']}: {msg['content']}")

# 清空历史
session.clear_history()

# 结束会话
session.end()
```

### 6. 会话管理器
```python
from agent import get_session_manager

# 获取会话管理器
session_manager = get_session_manager()

# 创建多个会话
session1 = session_manager.create_session(agent1, name="会话1")
session2 = session_manager.create_session(group, name="群聊会话")

# 启动会话
session1.start()
session2.start()

# 获取活跃会话
active_sessions = session_manager.get_active_sessions()
print(f"活跃会话数: {len(active_sessions)}")

# 获取统计信息
stats = session_manager.get_manager_statistics()
print(f"总会话数: {stats['total_sessions']}")
print(f"活跃会话数: {stats['active_sessions']}")

# 结束所有会话
session_manager.end_all_sessions()
```

### 7. 会话配置
```python
from agent import SessionConfig

# 创建详细配置
config = SessionConfig(
    name="高级会话",
    description="带有自定义配置的会话",
    auto_create_components=True,  # 自动创建组件
    context_variables={
        "environment": "production",
        "debug_mode": False
    },
    metadata={
        "version": "1.0",
        "created_by": "system"
    }
)

# 使用配置创建会话
session = Session(agent, config)
```

### Session类优势
1. **统一接口**: 无论是单Agent还是群聊，使用相同的接口
2. **自动管理**: 自动创建和管理所需的组件
3. **生命周期**: 完整的会话生命周期管理
4. **上下文管理**: 支持Python的上下文管理器协议
5. **可观测性**: 内置的监控和日志记录
6. **灵活配置**: 支持自定义配置和上下文变量

### 8. Session工具函数
```python
from agent import (
    create_session_with_timeout,
    create_persistent_session,
    batch_process_messages,
    get_session_summary,
    SessionMonitor,
    auto_cleanup_sessions
)

# 创建带超时的会话
session = create_session_with_timeout(
    agent,
    timeout_minutes=30,
    name="超时会话"
)

# 创建持久化会话
persistent_session = create_persistent_session(
    agent,
    session_id="user_123_session",
    name="用户会话"
)

# 批量处理消息
messages = ["消息1", "消息2", "消息3"]
session.start()
responses = await batch_process_messages(session, messages)

# 获取会话摘要
summary = get_session_summary(session)
print(f"会话统计: {summary['message_statistics']}")

# 导出会话历史
history_json = export_session_history(session, format="json")
history_md = export_session_history(session, format="markdown")

# 清理非活跃会话
cleanup_count = auto_cleanup_sessions(timeout_minutes=60)
print(f"清理了 {cleanup_count} 个会话")
```

### 9. 会话监控
```python
from agent import SessionMonitor

# 创建监控器
monitor = SessionMonitor()

# 启动监控（每60秒检查一次）
monitor.start_monitoring(interval_seconds=60)

# 获取监控状态
status = monitor.get_monitor_status()
print(f"监控状态: {status}")

# 停止监控
monitor.stop_monitoring()
```

### 10. 流式批处理
```python
# 流式批量处理消息
async def demo_stream_batch():
    messages = ["问题1", "问题2", "问题3"]
    
    async with create_session(agent) as session:
        async for result in stream_batch_process_messages(session, messages):
            if result.get("status") == "processing":
                print(f"正在处理: {result['message']}")
            elif result.get("chunk"):
                print(result["chunk"], end="", flush=True)
            elif result.get("status") == "completed":
                print(f"\n完成: {result['message']}")

await demo_stream_batch()
```

## LLM交互

### LLM客户端管理
框架使用LiteLLM与各种LLM进行交互，提供统一的API接口。

```python
from agent import LiteLLMClient, MockLLMClient, get_llm_client_manager

# 获取LLM客户端管理器
llm_manager = get_llm_client_manager()

# 注册LiteLLM客户端（用于真实LLM交互）
litellm_client = LiteLLMClient(
    default_model="gpt-4",
    timeout=30
)
llm_manager.register_client("gpt4", litellm_client)

# 注册Mock客户端（用于测试）
mock_client = MockLLMClient(
    default_response="这是一个测试响应",
    delay=0.1
)
llm_manager.register_client("mock", mock_client)

# 设置默认客户端
llm_manager.set_default_client("gpt4")
```

### 基本LLM交互
```python
# 异步调用
response = await llm_manager.chat_completion(
    messages=[{"role": "user", "content": "Hello!"}],
    model="gpt-4"
)

# 流式调用
async for chunk in llm_manager.stream_chat_completion(
    messages=[{"role": "user", "content": "Tell me a story"}],
    model="gpt-4"
):
    print(chunk.content, end="")
```

## 动态上下文引擎

### 概述
动态上下文引擎(ContextEngine)支持变量模板渲染和Hook机制，集成在每次LLM交互中自动处理提示词变量。

### 上下文变量类型

#### 1. 静态变量
```python
from agent import StaticContextVariable, ContextEngine

engine = ContextEngine()

# 静态变量
user_var = StaticContextVariable("张三")
engine.register_variable("user_name", user_var)
```

#### 2. 动态变量
```python
from agent import DynamicContextVariable
import datetime

# 动态变量
time_var = DynamicContextVariable(
    lambda: datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
)
engine.register_variable("current_time", time_var)
```

#### 3. 历史记录变量
```python
from agent import HistoryContextVariable

# 历史记录变量
history_var = HistoryContextVariable(context_engine=engine)
history_var.add_message("user", "你好")
history_var.add_message("assistant", "你好！有什么我可以帮助你的吗？")
engine.register_variable("chat_history", history_var)
```

### 模板渲染
```python
# 模板字符串
template = """
当前时间：{current_time}
用户：{user_name}
历史对话：
{chat_history}

请回答用户的问题。
"""

# 渲染模板
rendered = engine.render_template(template)
print(rendered)
```

### Hook机制
```python
from agent import ContextEngine

engine = ContextEngine()

# 注册Hook
engine.register_hook("before_llm", history_var)
engine.register_hook("after_llm", history_var)

# Hook会在LLM交互前后自动触发
rendered_prompt = engine.prepare_for_llm_interaction(template)
# ... LLM调用 ...
engine.post_llm_interaction(response)
```

### GroupChat上下文引擎
```python
from agent import GroupChatContextEngine, GroupChatContextVariable

# 群聊上下文引擎
group_engine = GroupChatContextEngine()

# 群聊专用变量
class GroupStatusVariable(GroupChatContextVariable):
    def get_group_summary(self):
        return f"群聊成员：{len(self.get_group_data('members', []))}人"
    
    def _get_agent_specific_context(self, agent_id, agent_context):
        return f"当前发言者：{agent_id}"

# 注册群聊变量
group_var = GroupStatusVariable(context_engine=group_engine)
group_engine.register_groupchat_variable("group_status", group_var)
```

## MCP集成

### 概述
框架支持MCP(Model Context Protocol)协议，扩展Agent的工具调用能力。

### MCP客户端管理
```python
from agent import InMemoryMCPClient, MCPTool, get_mcp_client_manager

# 获取MCP客户端管理器
mcp_manager = get_mcp_client_manager()

# 创建MCP客户端
mcp_client = InMemoryMCPClient()

# 定义工具
def search_web(params):
    query = params.get("query", "")
    return f"搜索结果：{query} 的相关信息..."

search_tool = MCPTool(
    name="search_web",
    description="搜索网络信息",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "搜索查询"}
        },
        "required": ["query"]
    },
    handler=search_web
)

# 注册工具
mcp_client.register_tool(search_tool)
mcp_manager.register_client("default", mcp_client, is_default=True)
```

### 创建支持MCP的Agent
```python
from agent import create_mcp_agent

# 创建支持MCP的Agent
mcp_agent = create_mcp_agent(
    name="搜索助手",
    system_prompt="你是一个搜索助手，可以帮助用户搜索信息。",
    mcp_client_name="default"
)

# MCP Agent会自动检测并调用工具
response = await mcp_agent.process_message("帮我搜索Python教程")
```

### MCP资源和提示
```python
from agent import MCPResource, MCPPrompt

# 注册资源
resource = MCPResource(
    name="user_manual",
    description="用户手册",
    mime_type="text/plain",
    data="这是用户手册的内容..."
)
mcp_client.register_resource(resource)

# 注册提示模板
prompt = MCPPrompt(
    name="summarize",
    description="总结提示模板",
    template="请总结以下内容：{{content}}",
    parameters={"content": {"type": "string"}}
)
mcp_client.register_prompt(prompt)

# 使用资源和提示
resource_data = mcp_client.get_resource("user_manual")
rendered_prompt = mcp_client.get_prompt("summarize", {"content": "要总结的内容"})
```

## 群聊系统

### 创建和配置群聊
```python
from agent import GroupChatConfig, GroupChat

# 详细配置群聊
config = GroupChatConfig(
    name="AI团队",
    description="多个AI Agent协作讨论",
    selector_model="gpt-4",
    max_rounds=5,
    max_messages_per_round=2,
    allow_self_talk=False,
    selector_prompt="""
你是对话协调员，需要选择最适合回应的Agent。

可用Agent：
{agent_list}

对话历史：
{conversation_history}

当前消息：{message}
当前发言者：{current_speaker}

请选择最适合回应的Agent ID。
"""
)

group_chat = GroupChat(config)
```

### Agent管理
```python
# 添加Agent到群聊
group_chat.add_agent(agent1, role="技术专家")
group_chat.add_agent(agent2, role="产品经理")
group_chat.add_agent(agent3, role="设计师")

# 查看群聊状态
status = group_chat.get_status()
print(f"群聊名称：{status['name']}")
print(f"Agent数量：{status['agent_count']}")

# 列出所有Agent
agents = group_chat.list_agents()
for agent_info in agents:
    print(f"- {agent_info['name']}: {agent_info['description']}")
```

### 群聊会话管理
```python
# 开始会话
session = group_chat.start_session(participants=["agent1", "agent2"])

# 处理消息
responses = await group_chat.process_message(
    "我们需要设计一个新的用户界面",
    sender_id="agent1"  # 可选，指定第一个发言者
)

# 查看响应
for resp in responses:
    print(f"轮次 {resp['round']}: {resp['agent_name']} 说：{resp['content']}")

# 结束会话
group_chat.end_session()
```

### 群聊观察者
```python
def on_group_event(event_type, data):
    print(f"群聊事件：{event_type}, 数据：{data}")

# 添加观察者
group_chat.add_observer(on_group_event)

# 移除观察者
group_chat.remove_observer(on_group_event)
```

## 消息队列

### 消息队列类型
```python
from agent import InMemoryMessageQueue, FileMessageQueue, Message

# 内存队列（适合临时使用）
memory_queue = InMemoryMessageQueue(max_messages=100)

# 文件队列（支持持久化）
file_queue = FileMessageQueue("chat_history.json", auto_save=True)
```

### 消息管理
```python
# 创建消息
message = Message(
    role="user",
    content="你好",
    agent_id="user_001",
    metadata={"session_id": "session_123"}
)

# 添加消息
memory_queue.update(message)

# 查询消息
messages = memory_queue.get_messages(limit=10)
specific_msg = memory_queue.get_message_by_id(message.id)

# 按条件查询
user_messages = memory_queue.get_messages_by_role("user")
agent_messages = memory_queue.get_messages_by_agent("agent_001")
recent_messages = memory_queue.get_recent_messages(5)
```

### 消息队列管理器
```python
from agent import get_message_queue_manager

queue_manager = get_message_queue_manager()

# 创建队列
queue = queue_manager.create_queue(
    "chat_001", 
    queue_type="file",
    file_path="chat_001.json"
)

# 获取或创建队列
queue = queue_manager.get_or_create_queue("chat_002", queue_type="memory")

# 队列统计
stats = queue_manager.get_queue_statistics()
print(f"总队列数：{stats['total_queues']}")
```

## 流式输出

### Agent流式对话
```python
# 流式处理单个Agent
async def stream_chat(agent, message):
    print(f"用户：{message}")
    print("AI：", end="")
    
    accumulated = ""
    async for chunk in agent.stream_process_message(message):
        print(chunk.content, end="", flush=True)
        accumulated += chunk.content
        
        if chunk.is_final:
            print(f"\n[完成，总计 {len(accumulated)} 字符]")

# 使用示例
await stream_chat(agent, "写一篇关于AI的文章")
```

### 群聊流式对话
```python
# 群聊流式处理
async def stream_group_chat(group, message):
    print(f"问题：{message}")
    
    async for response in group.stream_process_message(message):
        agent_name = response['agent_name']
        
        if not response['is_final']:
            # 实时显示正在输入的内容
            print(f"\r{agent_name} 正在输入：{response['accumulated_content']}", end="")
        else:
            # 完成后显示完整消息
            print(f"\n{agent_name}：{response['accumulated_content']}")

# 使用示例
await stream_group_chat(group, "讨论如何提升用户体验")
```

## 可观测性

### 监控和日志
```python
from agent import get_observability_manager, LogLevel

# 获取可观测性管理器
obs_manager = get_observability_manager()

# 设置日志级别
obs_manager.logger.set_level(LogLevel.INFO)

# 添加自定义日志处理器
def custom_log_handler(log_entry):
    print(f"[{log_entry.level.value}] {log_entry.message}")

obs_manager.logger.add_handler(custom_log_handler)

# 记录自定义日志
obs_manager.logger.info("系统启动", context={"version": "1.0"})
obs_manager.logger.error("处理失败", context={"error": "网络超时"})
```

### 交互指标
```python
# 开始交互追踪
interaction_id = obs_manager.start_interaction()

# 记录LLM请求
obs_manager.record_llm_request(
    interaction_id, 
    model="gpt-4",
    messages=[{"role": "user", "content": "Hello"}],
    agent_id="agent_001"
)

# 记录LLM响应
obs_manager.record_llm_response(
    interaction_id,
    {"content": "Hello!", "model": "gpt-4"}
)

# 结束交互
obs_manager.end_interaction(interaction_id)

# 获取统计信息
stats = obs_manager.get_metrics_summary()
print(f"成功率：{stats['success_rate']:.2%}")
print(f"平均耗时：{stats['average_duration_ms']:.2f}ms")
```

### 导出指标数据
```python
# 导出为字典格式
metrics_dict = obs_manager.export_metrics("dict")

# 导出为JSON格式
metrics_json = obs_manager.export_metrics("json")

# 清理数据
obs_manager.clear_all_data()
```

## API参考

### 核心类

#### AgentConfig
```python
@dataclass
class AgentConfig:
    agent_id: str                           # Agent唯一标识
    name: str                               # Agent名称
    description: str                        # Agent描述
    model: str                              # 使用的模型
    system_prompt: str                      # 系统提示词
    max_tokens: Optional[int]               # 最大令牌数
    temperature: Optional[float]            # 温度参数
    llm_client_name: Optional[str]          # LLM客户端名称
    mcp_client_name: Optional[str]          # MCP客户端名称
    message_queue_id: Optional[str]         # 消息队列ID
    context_variables: Dict[str, Any]       # 上下文变量
    metadata: Dict[str, Any]                # 元数据
```

#### GroupChatConfig
```python
@dataclass
class GroupChatConfig:
    group_id: str                           # 群聊唯一标识
    name: str                               # 群聊名称
    description: str                        # 群聊描述
    selector_model: str                     # 选择器模型
    selector_prompt: str                    # 选择器提示词
    max_rounds: int                         # 最大轮次
    max_messages_per_round: int             # 每轮最大消息数
    allow_self_talk: bool                   # 是否允许自言自语
    message_queue_id: Optional[str]         # 消息队列ID
    context_variables: Dict[str, Any]       # 上下文变量
    metadata: Dict[str, Any]                # 元数据
```

#### SessionConfig
```python
@dataclass
class SessionConfig:
    session_id: str                         # 会话唯一标识
    name: str                               # 会话名称
    description: str                        # 会话描述
    auto_create_components: bool            # 是否自动创建组件
    context_variables: Dict[str, Any]       # 上下文变量
    metadata: Dict[str, Any]                # 元数据
```

### 便捷函数

#### create_simple_agent
```python
def create_simple_agent(
    name: str, 
    model: str = "gpt-3.5-turbo", 
    system_prompt: str = "", 
    **kwargs
) -> SimpleAgent
```

#### create_mcp_agent
```python
def create_mcp_agent(
    name: str, 
    model: str = "gpt-3.5-turbo",
    system_prompt: str = "", 
    mcp_client_name: str = None,
    **kwargs
) -> MCPAgent
```

#### create_group_chat
```python
def create_group_chat(
    name: str, 
    selector_model: str = "gpt-3.5-turbo",
    selector_prompt: str = "", 
    **kwargs
) -> GroupChat
```

#### create_session
```python
def create_session(
    agent_or_groupchat: Union[AgentBase, GroupChat],
    name: str = "Session",
    **kwargs
) -> Session
```

### 管理器函数

```python
# 获取各种管理器实例
get_agent_manager() -> AgentManager
get_group_chat_manager() -> GroupChatManager
get_session_manager() -> SessionManager
get_llm_client_manager() -> LLMClientManager
get_mcp_client_manager() -> MCPClientManager
get_message_queue_manager() -> MessageQueueManager
get_observability_manager() -> ObservabilityManager
```

## 系统架构

### 架构概览
```
┌─────────────────────────────────────────────────────────────────────┐
│                          Session Layer                             │
│                                                                     │
│ Session           SessionManager        SessionConfig               │
│ 统一接口           会话管理              会话配置                      │
│ 自动组件管理       生命周期管理          上下文管理                    │
└─────────────────────────────────────────────────────────────────────┘
         │                       │                       │
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Agent Layer   │    │  GroupChat      │    │  观察者模式      │
│                 │    │  Layer          │    │                 │
│ SimpleAgent     │    │ GroupChat       │    │ 事件通知         │
│ MCPAgent        │    │ Session         │    │ 状态监控         │
│ AgentManager    │    │ Context         │    │ 日志记录         │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
┌─────────────────────────────────┼─────────────────────────────────┐
│                    Core Infrastructure                            │
├─────────────────┬─────────────────┬─────────────────┬─────────────┤
│ Context Engine  │ LLM Client      │ MCP Client      │ Message     │
│                 │                 │                 │ Queue       │
│ ContextVariable │ LiteLLMClient   │ MCPTool         │ Memory/File │
│ Hook Mechanism  │ MockLLMClient   │ MCPResource     │ Queue       │
│ Template        │ Async Support   │ MCPPrompt       │ Persistence │
│ Rendering       │ Stream Support  │ Tool Calling    │ History     │
└─────────────────┴─────────────────┴─────────────────┴─────────────┘
         │                       │                       │
┌─────────────────────────────────┼─────────────────────────────────┐
│                     Observability Layer                           │
│                                 │                                 │
│ MetricsCollector    Logger    ObservabilityManager                │
│ InteractionMetrics  LogEntry  Statistics & Monitoring             │
└───────────────────────────────────────────────────────────────────┘
```

### 数据流向
```
用户输入 
    ↓
Session Layer (会话管理)
    ↓
┌─────────────────────────────────┐
│        Session决策分支          │
│                                │
│  单Agent模式    │   群聊模式     │
│      ↓         │      ↓        │
│  Agent处理      │  GroupChat处理 │
└─────────────────────────────────┘
    ↓
Context Engine (变量解析)
    ↓
Agent Selection (群聊模式)
    ↓
LLM Client (模型调用)
    ↓
MCP Client (工具调用, 可选)
    ↓
Response Processing
    ↓
Message Queue (历史存储)
    ↓
Observability (指标记录)
    ↓
Session Layer (响应整合)
    ↓
用户输出
```

### 组件职责

#### 会话层组件
- **Session**: 统一会话管理接口，支持单Agent和群聊
- **SessionManager**: Session生命周期管理
- **SessionMonitor**: 会话监控和统计
- **Session Utils**: 会话工具函数和批处理

#### 核心组件
- **Agent**: 智能体实例，处理对话逻辑
- **GroupChat**: 多Agent协作管理
- **ContextEngine**: 动态上下文和模板管理
- **MessageQueue**: 消息存储和历史管理

#### 接口组件
- **LLMClient**: 统一LLM访问接口
- **MCPClient**: MCP协议工具调用
- **Observability**: 监控和日志系统

#### 管理组件
- **各种Manager**: 组件生命周期管理
- **配置系统**: 灵活的配置管理
- **异常处理**: 统一异常体系

---

## 最佳实践

### 1. Agent设计
```python
# 为Agent设计清晰的角色和职责
agent = create_simple_agent(
    name="技术顾问",
    system_prompt="""
你是一名资深技术顾问，专长：
- 软件架构设计
- 技术选型建议  
- 性能优化方案

请始终：
- 提供专业、准确的建议
- 考虑实际业务场景
- 给出可执行的方案
""",
    model="gpt-4",
    temperature=0.7
)
```

### 2. 群聊协作
```python
# 设计有意义的Agent角色分工
product_manager = create_simple_agent(
    "产品经理", 
    system_prompt="负责需求分析和产品规划"
)
tech_lead = create_simple_agent(
    "技术负责人", 
    system_prompt="负责技术方案设计和架构决策"
)
ui_designer = create_simple_agent(
    "UI设计师", 
    system_prompt="负责用户界面设计和用户体验"
)

# 创建专业的群聊
team = create_group_chat(
    "产品团队",
    selector_prompt="根据讨论内容选择最合适的专家回应"
)
```

### 3. 上下文管理
```python
# 合理使用上下文变量
from agent import ContextEngine, DynamicContextVariable

engine = ContextEngine()

# 动态获取用户信息
user_context = DynamicContextVariable(
    lambda: get_current_user_info()
)
engine.register_variable("user_info", user_context)

# 注册Hook以自动更新
engine.register_hook("before_llm", user_context)
```

### 4. 错误处理
```python
from agent import AgentException, LLMClientException

try:
    response = await agent.process_message("处理这个复杂问题")
except LLMClientException as e:
    print(f"LLM调用失败：{e}")
except AgentException as e:
    print(f"Agent处理失败：{e}")
except Exception as e:
    print(f"未知错误：{e}")
```

### 5. 性能监控
```python
# 启用详细监控
obs_manager = get_observability_manager()
obs_manager.logger.set_level(LogLevel.DEBUG)

# 定期检查性能指标
stats = obs_manager.get_metrics_summary()
if stats['average_duration_ms'] > 5000:
    print("警告：响应时间过长")
```

## 故障排除

### 常见问题

1. **LiteLLM导入失败**
   ```python
   # 使用Mock客户端进行测试
   from agent import MockLLMClient
   mock_client = MockLLMClient("测试响应")
   ```

2. **消息队列持久化失败**
   ```python
   # 检查文件权限和路径
   file_queue = FileMessageQueue("/tmp/messages.json")
   ```

3. **群聊选择器不工作**
   ```python
   # 检查选择器提示词和模型配置
   group.config.selector_model = "gpt-4"
   group.config.selector_prompt = "选择最合适的Agent..."
   ```

4. **上下文变量未更新**
   ```python
   # 手动触发Hook
   engine.trigger_hook("before_llm")
   ```

---

## 更新日志

### v0.1.0 (当前版本)
- ✅ 基础Agent系统
- ✅ 群聊协作功能
- ✅ 动态上下文引擎
- ✅ MCP协议支持
- ✅ 流式输出
- ✅ 可观测性系统
- ✅ 消息队列和持久化

### 计划功能
- 🔄 更多LLM提供商支持
- 🔄 图形化配置界面
- 🔄 插件系统
- 🔄 分布式部署支持

---

## 贡献指南

欢迎提交Issue和Pull Request！请确保：
- 代码符合PEP 8规范
- 添加适当的类型注解
- 包含必要的文档字符串
- 通过现有测试

## 许可证

本项目采用 MIT 许可证。详见 LICENSE 文件。
