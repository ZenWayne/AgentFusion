# MCP集成指南

## 概述

我们已经将MCP（Model Context Protocol）集成重构为更优雅的架构，使用MCPMixin来提供MCP功能，并实现了完整的handle_response机制。

## 新架构设计

### 1. MCPMixin模式

- **MCPMixin**: 独立的MCP功能混入类
- **SimpleAgent**: 继承AgentBase和MCPMixin
- **MCPAgent**: 保留作为向后兼容性别名
- 更清晰的职责分离和代码组织

### 2. handle_response机制

- 在处理响应后自动调用`handle_response`方法
- 递归调用所有底层组件的`handle_response`方法
- 支持自定义响应处理逻辑

### 3. 配置更新

#### AgentConfig 新增字段

```python
@dataclass
class AgentConfig:
    # ... 其他字段
    mcp_tools: List[StdioServerParameters] = field(default_factory=list)
```

#### 使用方式

```python
from mcp import StdioServerParameters
from agent import create_simple_agent, AgentConfig, SimpleAgent, MCPMixin

# 创建MCP工具配置
mcp_tools = [
    StdioServerParameters(
        command="python",
        args=["-c", "print('Hello from MCP tool!')"],
        env={}
    )
]

# 方式1：使用便利函数
agent = create_simple_agent(
    name="MCP助手",
    model="gpt-3.5-turbo",
    mcp_tools=mcp_tools
)

# 方式2：使用AgentConfig
config = AgentConfig(
    name="MCP助手",
    model="gpt-3.5-turbo",
    mcp_tools=mcp_tools
)
agent = SimpleAgent(config)

# 验证MCP功能
print(f"是否为MCPMixin实例: {isinstance(agent, MCPMixin)}")
```

### 4. 新增功能

#### 自动工具初始化

```python
# MCP工具会在第一次使用时自动初始化
await agent.process_message("使用工具帮我计算")
```

#### 工具状态监控

```python
# 获取Agent状态，包括MCP工具信息
status = agent.get_status()
print(f"MCP工具数量: {status['mcp_tools_count']}")
print(f"MCP工具包数量: {status['mcp_toolkits_count']}")

# 获取MCP专门状态
mcp_status = agent.get_mcp_status()
print(f"MCP初始化状态: {mcp_status['mcp_initialized']}")
```

#### 流式处理支持

```python
# 流式处理也支持MCP工具调用
async for chunk in agent.stream_process_message("使用工具"):
    print(chunk.content)
```

#### handle_response机制

```python
# 自定义响应处理
class CustomAgent(SimpleAgent):
    async def handle_response(self, response, **context):
        print(f"处理响应: {response.content}")
        # 调用父类的handle_response
        await super().handle_response(response, **context)

# 使用自定义Agent
agent = CustomAgent(config)
await agent.process_message("测试")  # 会自动调用handle_response
```

### 5. 技术实现

#### 架构层次

```
SimpleAgent
├── AgentBase (基础Agent功能)
│   ├── process_message()
│   ├── handle_response()
│   └── 组件管理
└── MCPMixin (MCP功能混入)
    ├── initialize_mcp_tools()
    ├── _execute_tool_call()
    └── _handle_tool_calls()
```

#### 核心方法

**AgentBase方法：**
- `handle_response()`: 调用所有组件的handle_response
- `process_message()`: 处理消息的抽象方法
- `prepare_messages()`: 准备消息列表

**MCPMixin方法：**
- `initialize_mcp_tools()`: 初始化MCP工具
- `_ensure_mcp_initialized()`: 确保工具已初始化
- `_execute_tool_call()`: 执行工具调用
- `_handle_tool_calls()`: 处理工具调用逻辑
- `get_mcp_status()`: 获取MCP状态

#### 工具调用流程

1. 用户发送消息
2. Agent准备LLM参数，包括可用工具
3. LLM返回响应，可能包含工具调用
4. MCPMixin处理工具调用
5. 将工具结果发送回LLM
6. 返回最终响应
7. 自动调用handle_response处理响应

### 6. 向后兼容性

#### MCPAgent 仍然可用

```python
# 旧的MCPAgent仍然工作（现在等同于SimpleAgent）
agent = create_mcp_agent(
    name="MCP代理",
    mcp_tools=mcp_tools
)

# 新的推荐方式
agent = create_simple_agent(
    name="MCP代理",
    mcp_tools=mcp_tools
)
```

#### 现有代码无需修改

- 所有现有的Agent代码都可以继续工作
- 只需添加 `mcp_tools` 参数即可启用MCP功能
- handle_response机制是自动的，不需要修改现有代码

### 7. 错误处理

#### 工具初始化失败

```python
try:
    await agent._ensure_mcp_initialized()
except AgentException as e:
    print(f"MCP工具初始化失败: {e}")
```

#### 工具调用失败

- 单个工具调用失败不会影响整个对话
- 错误会被记录到日志中
- Agent会继续处理其他工具调用

#### handle_response失败

- 组件的handle_response失败不会影响主流程
- 错误会被记录为警告
- 其他组件的handle_response仍会继续执行

```python
# handle_response错误处理示例
class SafeAgent(SimpleAgent):
    async def handle_response(self, response, **context):
        try:
            # 自定义处理逻辑
            print(f"处理响应: {response.content}")
            await super().handle_response(response, **context)
        except Exception as e:
            self.observability.logger.error(f"Response handling failed: {e}")
```

### 8. 最佳实践

#### 工具配置

```python
# 推荐：使用明确的命令和参数
mcp_tools = [
    StdioServerParameters(
        command="python",
        args=["-c", "your_script.py"],
        env={"PYTHONPATH": "/your/path"}
    )
]
```

#### 错误处理

```python
# 在生产环境中使用try-catch
try:
    response = await agent.process_message(message)
except AgentException as e:
    # 处理Agent异常
    pass
```

#### 监控

```python
# 定期检查Agent状态
status = agent.get_status()
if status['mcp_tools_count'] == 0:
    print("警告：没有可用的MCP工具")

# 检查MCP初始化状态
mcp_status = agent.get_mcp_status()
if not mcp_status['mcp_initialized']:
    print("MCP工具尚未初始化")
```

#### 自定义handle_response

```python
# 推荐的handle_response实现模式
class MyAgent(SimpleAgent):
    async def handle_response(self, response, **context):
        # 1. 执行自定义逻辑
        await self._custom_response_processing(response, **context)
        
        # 2. 调用父类的handle_response
        await super().handle_response(response, **context)
        
        # 3. 执行后续处理
        await self._post_response_processing(response, **context)
```

## 示例

参考 `example_mcp_usage.py` 文件查看完整的使用示例，包括：

- MCPMixin功能演示
- handle_response机制演示
- 组件handle_response调用示例
- 继承层次结构演示
- 自定义Agent实现示例

## 升级指南

### 从旧版本升级

1. 更新Agent创建代码：
   ```python
   # 旧版本
   agent = create_simple_agent(name="test")
   
   # 新版本（可选添加MCP工具）
   agent = create_simple_agent(name="test", mcp_tools=mcp_tools)
   ```

2. 更新状态检查代码：
   ```python
   # 新增的状态字段
   status = agent.get_status()
   mcp_tools_count = status.get('mcp_tools_count', 0)
   mcp_initialized = status.get('mcp_initialized', False)
   ```

3. 利用新的handle_response机制：
   ```python
   # 可选：添加自定义响应处理
   class MyAgent(SimpleAgent):
       async def handle_response(self, response, **context):
           # 自定义处理逻辑
           await self._my_custom_processing(response)
           await super().handle_response(response, **context)
   ```

### 迁移MCPAgent

```python
# 旧版本
agent = MCPAgent(config)

# 新版本（推荐）
agent = SimpleAgent(config)  # 功能完全相同，更清晰的架构
```

### 架构升级优势

- **更清晰的职责分离**: MCPMixin专门处理MCP功能
- **更强的扩展性**: 可以轻松添加其他Mixin
- **更好的错误处理**: handle_response机制提供统一的响应处理
- **更容易测试**: 可以单独测试MCP功能和响应处理

## 故障排除

### 常见问题

1. **MCP工具初始化失败**
   - 检查命令路径是否正确
   - 确认环境变量设置
   - 查看日志获取详细错误信息

2. **工具调用不生效**
   - 确认LLM客户端支持工具调用
   - 检查系统提示是否提到工具使用
   - 验证工具参数格式

3. **性能问题**
   - MCP工具初始化是异步的
   - 首次调用可能较慢
   - 考虑预先初始化工具

### 调试技巧

```python
# 启用详细日志
from observability import get_observability_manager
observability = get_observability_manager()
observability.logger.set_level("DEBUG")

# 检查工具状态
print(f"工具数量: {len(agent.mcp_tools)}")
print(f"工具包数量: {len(agent.mcp_toolkits)}")

# 检查MCP状态
mcp_status = agent.get_mcp_status()
print(f"MCP状态: {mcp_status}")

# 验证继承层次
print(f"类继承: {agent.__class__.__mro__}")
print(f"是否为MCPMixin: {isinstance(agent, MCPMixin)}")

# 调试handle_response
class DebugAgent(SimpleAgent):
    async def handle_response(self, response, **context):
        print(f"🔍 Debug: 响应长度={len(response.content)}")
        print(f"🔍 Debug: 上下文={list(context.keys())}")
        await super().handle_response(response, **context)
``` 