# OpenTelemetry集成指南

本目录包含了OpenTelemetry在Agent框架中的集成示例，提供了完整的分布式追踪、监控和可观测性解决方案。

## 📁 文件结构

```
src/agent/
├── opentelemetry_config.py      # OpenTelemetry配置和设置
├── opentelemetry_examples.py    # 各种使用示例
├── opentelemetry_integration.py # 与现有observability模块集成
├── demo_opentelemetry.py        # 演示程序
├── observability.py             # 原有可观测性模块
└── README_OpenTelemetry.md      # 本文档
```

## 🚀 快速开始

### 1. 安装依赖

```bash
pip install -r opentelemetry_requirements.txt
```

### 2. 运行演示

```bash
python -m src.agent.demo_opentelemetry
```

### 3. 基本使用

```python
from src.agent.opentelemetry_config import setup_opentelemetry
from src.agent.opentelemetry_integration import TracedAgent

# 设置OpenTelemetry
setup_opentelemetry(
    service_name="my-agent-service",
    service_version="1.0.0",
    console_export=True
)

# 创建带追踪的Agent
agent = TracedAgent("my_agent", "gpt-4")

# 处理消息
result = agent.process_message("user_123", "Hello!")
print(result)
```

## 📊 核心功能

### 1. 分布式追踪 (Distributed Tracing)
- **Trace**: 完整的请求生命周期
- **Span**: 单个操作或服务调用
- **Context Propagation**: 跨服务追踪传播

### 2. 指标收集 (Metrics Collection)
- 请求/响应时间
- 错误率和成功率
- 资源使用情况
- 自定义业务指标

### 3. 日志关联 (Log Correlation)
- 自动关联追踪ID和日志
- 结构化日志输出
- 上下文信息保持

### 4. 可观测性增强
- 实时性能监控
- 错误和异常追踪
- 服务依赖关系可视化

## 🔧 配置说明

### 基础配置

```python
from src.agent.opentelemetry_config import setup_opentelemetry

setup_opentelemetry(
    service_name="agent-fusion",           # 服务名称
    service_version="1.0.0",               # 服务版本
    jaeger_endpoint="http://localhost:14268/api/traces",  # Jaeger端点
    console_export=True                    # 控制台输出
)
```

### 高级配置

```python
# 自定义资源属性
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION

resource = Resource.create({
    SERVICE_NAME: "my-agent-service",
    SERVICE_VERSION: "1.0.0",
    "environment": "production",
    "deployment.environment": "prod",
    "service.namespace": "ai-agents"
})
```

## 📈 监控后端

### 1. Jaeger (推荐)
```bash
# 使用Docker运行Jaeger
docker run -d \
  -p 16686:16686 \
  -p 14268:14268 \
  jaegertracing/all-in-one:latest
```

访问 http://localhost:16686 查看追踪数据

### 2. Zipkin
```bash
# 使用Docker运行Zipkin
docker run -d -p 9411:9411 openzipkin/zipkin
```

访问 http://localhost:9411 查看追踪数据

### 3. 云服务
- **AWS X-Ray**: 适用于AWS环境
- **Google Cloud Trace**: 适用于GCP环境
- **Azure Monitor**: 适用于Azure环境

## 🎯 使用示例

### 1. 基本Agent追踪

```python
from src.agent.opentelemetry_integration import TracedAgent

agent = TracedAgent("my_agent", "gpt-4")
result = agent.process_message("user_123", "Hello, world!")
```

### 1.1 群聊系统追踪

```python
from src.agent.group_chat import GroupChat, GroupChatConfig

# 创建群聊配置
config = GroupChatConfig(
    group_id="tech_discussion",
    name="技术讨论组",
    max_rounds=5
)

# 创建群聊（自动添加追踪）
group_chat = GroupChat(config)

# 添加Agent（自动追踪）
group_chat.add_agent(agent1, role="专家")
group_chat.add_agent(agent2, role="顾问")

# 开始会话（自动追踪）
session = group_chat.start_session()

# 处理消息（包含完整的span层次结构）
responses = await group_chat.process_message("讨论AI的未来发展")

# 查看群聊演示
python -m src.agent.group_chat_demo
```

### 2. 使用装饰器注解

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@tracer.start_as_current_span("custom_operation")
def process_data():
    """使用装饰器注解的函数"""
    span = trace.get_current_span()
    span.set_attribute("operation.type", "data_processing")
    span.add_event("Processing started")
    
    # 你的业务逻辑
    result = do_work()
    
    span.add_event("Processing completed")
    return result

# 对于需要更多控制的情况，仍可使用上下文管理器
def complex_operation():
    with tracer.start_as_current_span("complex_operation") as span:
        span.set_attribute("operation.type", "complex")
        # 复杂逻辑
        return result
```

### 3. 分布式追踪

```python
from opentelemetry.propagate import inject, extract

# 服务A - 发送方
def service_a():
    headers = {}
    inject(headers)  # 注入追踪上下文
    
    # 发送HTTP请求，包含追踪头
    response = requests.post("http://service-b/process", 
                           json=data, headers=headers)

# 服务B - 接收方
def service_b(request_headers):
    parent_context = extract(request_headers)  # 提取追踪上下文
    
    with tracer.start_as_current_span("service_b_operation", 
                                     context=parent_context):
        # 处理请求
        return process_request()
```

### 4. 错误处理

```python
with tracer.start_as_current_span("risky_operation") as span:
    try:
        result = risky_function()
        span.set_status(trace.Status(trace.StatusCode.OK))
        return result
    except Exception as e:
        span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
        span.record_exception(e)
        raise
```

### 5. 异步操作

```python
async def async_operation():
    with tracer.start_as_current_span("async_operation") as span:
        # 并发任务
        tasks = [
            analyze_sentiment(message),
            extract_entities(message),
            generate_response(message)
        ]
        
        results = await asyncio.gather(*tasks)
        span.add_event("All tasks completed")
        return results
```

## 🔍 最佳实践

### 1. Span命名
- 使用描述性名称：`llm_request`, `user_authentication`, `data_processing`
- 避免高基数名称：不要包含用户ID或时间戳

### 2. 属性设置
```python
# 推荐
span.set_attribute("user.id", user_id)
span.set_attribute("llm.model", "gpt-4")
span.set_attribute("request.size", len(data))

# 避免
span.set_attribute("debug.full_request", json.dumps(large_object))
```

### 3. 事件记录
```python
# 关键业务事件
span.add_event("user_authenticated", {"method": "oauth2"})
span.add_event("llm_response_received", {"tokens": 150})
span.add_event("error_handled", {"error_type": "timeout"})
```

### 4. 采样策略
```python
# 生产环境建议设置采样率
from opentelemetry.sdk.trace.sampling import TraceIdRatioBased

# 采样10%的追踪
sampler = TraceIdRatioBased(rate=0.1)
```

## 📊 监控指标

### 关键指标监控
- **延迟**: 响应时间分布
- **吞吐量**: 每秒请求数
- **错误率**: 失败请求比例
- **资源使用**: CPU、内存、网络

### 自定义指标
```python
from opentelemetry import metrics

meter = metrics.get_meter(__name__)

# 计数器
request_counter = meter.create_counter(
    "agent_requests_total",
    description="Total number of agent requests"
)

# 直方图
response_time_histogram = meter.create_histogram(
    "agent_response_time_seconds",
    description="Agent response time in seconds"
)

# 使用指标
request_counter.add(1, {"agent_id": "my_agent"})
response_time_histogram.record(0.5, {"agent_id": "my_agent"})
```

## 🚨 故障排除

### 1. 常见问题

**Q: 看不到追踪数据？**
A: 检查导出器配置和网络连接

**Q: 性能影响？**
A: 使用采样和异步导出

**Q: 内存泄漏？**
A: 确保正确结束span和清理资源

### 2. 调试技巧

```python
# 启用详细日志
import logging
logging.getLogger("opentelemetry").setLevel(logging.DEBUG)

# 验证span创建
with tracer.start_as_current_span("debug_span") as span:
    print(f"Span ID: {span.get_span_context().span_id}")
    print(f"Trace ID: {span.get_span_context().trace_id}")
```

## 🔄 与现有系统集成

### 1. 渐进式集成
1. 首先配置OpenTelemetry
2. 为关键路径添加追踪
3. 逐步扩展到所有组件
4. 添加自定义指标和仪表板

### 2. 兼容性
- 与现有日志系统兼容
- 支持多种导出格式
- 可与现有监控系统集成

## 📚 参考资源

- [OpenTelemetry官方文档](https://opentelemetry.io/docs/)
- [Python SDK文档](https://opentelemetry-python.readthedocs.io/)
- [Jaeger文档](https://www.jaegertracing.io/docs/)
- [Zipkin文档](https://zipkin.io/pages/quickstart.html)

## 🤝 贡献

欢迎提交Issue和Pull Request来改进OpenTelemetry集成！

---

*最后更新: 2024年* 