# MemRecallAgent 工具函数文档

## 文档信息
- **版本**: 1.0
- **日期**: 2026-02-06
- **状态**: 草案

---

## 1. 概述

MemRecallAgent 使用固定的工具集，专门用于记忆搜索和召回。这些工具设计为简单、原子化操作，Agent 通过组合这些工具来完成复杂的记忆召回任务。

---

## 2. 工具列表

### 2.1 search_memories

**描述**: 搜索用户的历史记忆，支持关键词、语义和混合搜索模式。

**输入模型**:
```python
class SearchMemoriesInput(BaseModel):
    """记忆搜索工具输入"""
    query: str = Field(
        ...,
        description="搜索查询，可以是自然语言描述或关键词。例如：'用户之前配置的数据库参数'"
    )
    search_mode: Literal["semantic", "keyword", "hybrid"] = Field(
        default="hybrid",
        description="搜索模式: semantic-语义匹配, keyword-关键词匹配, hybrid-混合"
    )
    keywords: Optional[List[str]] = Field(
        default=None,
        description="可选的精确关键词列表，用于精确过滤。例如：['database', 'config']"
    )
    memory_types: Optional[List[str]] = Field(
        default=None,
        description="按记忆类型过滤，如 ['user_preference', 'command_output', 'general']"
    )
    time_range_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="时间范围过滤，最近 N 天内的记忆"
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="返回结果数量限制"
    )
    min_relevance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="最小相关性分数阈值，低于此值的记忆将被过滤"
    )
```

**输出模型**:
```python
class MemorySearchResultItem(BaseModel):
    """单个记忆搜索结果"""
    memory_key: str = Field(..., description="记忆的唯一标识符")
    summary: str = Field(..., description="记忆摘要")
    content_preview: str = Field(..., description="内容预览（前200字符）")
    memory_type: Optional[str] = Field(None, description="记忆类型")
    relevance_score: float = Field(..., description="相关性分数 0.0-1.0")
    created_at: str = Field(..., description="创建时间 ISO 格式")
    keywords: List[str] = Field(default=[], description="关联的关键词列表")

class SearchMemoriesOutput(BaseModel):
    """记忆搜索工具输出"""
    success: bool = Field(..., description="搜索是否成功")
    total_found: int = Field(..., description="找到的记忆总数")
    results: List[MemorySearchResultItem] = Field(default=[], description="搜索结果列表")
    search_query_expanded: Optional[str] = Field(None, description="扩展后的搜索查询")
    message: Optional[str] = Field(None, description="附加信息或错误消息")
```

**实现**:
```python
async def search_memories_tool(
    data_layer: AgentFusionDataLayer,
    user_id: int,
    input_data: SearchMemoriesInput
) -> SearchMemoriesOutput:
    """
    执行记忆搜索

    算法:
    1. 根据 search_mode 选择搜索策略
    2. 如需要，使用 LLM 扩展查询关键词
    3. 应用所有过滤器 (memory_types, time_range, min_relevance_score)
    4. 按相关性分数排序并返回结果
    """
    try:
        # 关键词扩展（如果是 hybrid 或 semantic 模式）
        expanded_keywords = input_data.keywords or []
        if input_data.search_mode in ["semantic", "hybrid"]:
            expanded_keywords = await _expand_search_keywords(input_data.query, expanded_keywords)

        # 构建搜索条件
        search_conditions = {
            "query": input_data.query,
            "keywords": expanded_keywords,
            "memory_types": input_data.memory_types,
            "time_range_days": input_data.time_range_days,
            "min_relevance_score": input_data.min_relevance_score,
            "limit": input_data.limit
        }

        # 调用数据层搜索
        memories = await data_layer.memory.search_memories_advanced(
            user_id=user_id,
            **search_conditions
        )

        # 转换为输出格式
        results = [
            MemorySearchResultItem(
                memory_key=mem.memory_key,
                summary=mem.summary or "",
                content_preview=mem.content[:200] + "..." if mem.content and len(mem.content) > 200 else (mem.content or ""),
                memory_type=mem.memory_type,
                relevance_score=mem.relevance_score,
                created_at=mem.created_at.isoformat(),
                keywords=mem.keywords or []
            )
            for mem in memories
        ]

        return SearchMemoriesOutput(
            success=True,
            total_found=len(results),
            results=results,
            search_query_expanded=", ".join(expanded_keywords) if expanded_keywords else None
        )

    except Exception as e:
        return SearchMemoriesOutput(
            success=False,
            total_found=0,
            results=[],
            message=f"搜索失败: {str(e)}"
        )
```

---

### 2.2 get_memory_detail

**描述**: 获取特定记忆的完整内容。

**输入模型**:
```python
class GetMemoryDetailInput(BaseModel):
    """获取记忆详情输入"""
    memory_key: str = Field(
        ...,
        description="记忆的唯一标识符（从 search_memories 结果中获取）"
    )
```

**输出模型**:
```python
class GetMemoryDetailOutput(BaseModel):
    """获取记忆详情输出"""
    success: bool = Field(..., description="是否成功获取")
    memory_key: Optional[str] = Field(None, description="记忆标识符")
    summary: Optional[str] = Field(None, description="记忆摘要")
    content: Optional[str] = Field(None, description="完整内容")
    memory_type: Optional[str] = Field(None, description="记忆类型")
    created_at: Optional[str] = Field(None, description="创建时间")
    metadata: Optional[Dict[str, Any]] = Field(None, description="附加元数据")
    message: Optional[str] = Field(None, description="错误或状态信息")
```

**实现**:
```python
async def get_memory_detail_tool(
    data_layer: AgentFusionDataLayer,
    user_id: int,
    input_data: GetMemoryDetailInput
) -> GetMemoryDetailOutput:
    """获取记忆的完整内容"""
    try:
        memory = await data_layer.memory.retrieve_memory(
            memory_key=input_data.memory_key,
            user_id=user_id  # 确保用户只能访问自己的记忆
        )

        if not memory:
            return GetMemoryDetailOutput(
                success=False,
                message=f"未找到记忆: {input_data.memory_key}"
            )

        return GetMemoryDetailOutput(
            success=True,
            memory_key=memory.memory_key,
            summary=memory.summary,
            content=memory.content,
            memory_type=memory.memory_type,
            created_at=memory.created_at.isoformat(),
            metadata=memory.content_metadata
        )

    except Exception as e:
        return GetMemoryDetailOutput(
            success=False,
            message=f"获取记忆详情失败: {str(e)}"
        )
```

---

### 2.3 extract_search_keywords

**描述**: 从用户查询中提取搜索关键词（辅助工具，用于复杂查询分析）。

**输入模型**:
```python
class ExtractKeywordsInput(BaseModel):
    """提取关键词输入"""
    query: str = Field(..., description="用户原始查询")
    context: Optional[str] = Field(
        default=None,
        description="可选的上下文信息，帮助更准确地提取关键词"
    )
    max_keywords: int = Field(
        default=5,
        ge=1,
        le=10,
        description="最多提取的关键词数量"
    )
```

**输出模型**:
```python
class KeywordExtractionItem(BaseModel):
    """提取的关键词项"""
    keyword: str = Field(..., description="关键词")
    weight: float = Field(..., description="重要性权重 0.0-1.0")
    type: str = Field(..., description="类型: entity(实体), action(动作), concept(概念), time(时间)")

class ExtractKeywordsOutput(BaseModel):
    """提取关键词输出"""
    success: bool = Field(..., description="是否成功")
    keywords: List[KeywordExtractionItem] = Field(default=[], description="提取的关键词列表")
    expanded_query: Optional[str] = Field(None, description="扩展后的搜索查询")
    message: Optional[str] = Field(None, description="状态或错误信息")
```

**实现**:
```python
async def extract_search_keywords_tool(
    model_client: ChatCompletionClient,
    input_data: ExtractKeywordsInput
) -> ExtractKeywordsOutput:
    """使用 LLM 从查询中提取关键词"""
    prompt = f"""从以下查询中提取搜索关键词。

用户查询: {input_data.query}
{"上下文: " + input_data.context if input_data.context else ""}

请提取最多 {input_data.max_keywords} 个关键词，按重要性排序。
关键词类型包括:
- entity: 人名、地名、系统名、文件名等实体
- action: 操作、动作、命令等行为
- concept: 概念、主题、技术术语
- time: 时间相关词汇（如"上周"、"昨天"等）

返回 JSON 格式:
{{
    "keywords": [
        {{"keyword": "词1", "weight": 0.9, "type": "entity"}},
        {{"keyword": "词2", "weight": 0.7, "type": "action"}}
    ],
    "expanded_query": "扩展后的查询描述"
}}"""

    try:
        response = await model_client.create(
            messages=[UserMessage(content=prompt, source="system")],
            json_output=True
        )

        result = json.loads(response.content)

        return ExtractKeywordsOutput(
            success=True,
            keywords=[KeywordExtractionItem(**kw) for kw in result.get("keywords", [])],
            expanded_query=result.get("expanded_query")
        )

    except Exception as e:
        return ExtractKeywordsOutput(
            success=False,
            message=f"关键词提取失败: {str(e)}"
        )
```

---

### 2.4 expand_context_window

**描述**: 请求拓展上下文窗口大小。调用此工具后会立即结束当前迭代，MemoryContext 将重新发起调用并提供更多历史消息。

**输入模型**:
```python
class ExpandContextWindowInput(BaseModel):
    """请求拓展上下文窗口"""
    reason: str = Field(
        ...,
        description="需要拓展的原因，例如：'搜索结果不理想，需要查看更早的对话'"
    )
    current_size: int = Field(
        ...,
        description="当前使用的消息数"
    )
    requested_size: int = Field(
        ...,
        description="请求拓展到的消息数"
    )
```

**输出模型**:
```python
class ExpandContextWindowOutput(BaseModel):
    """拓展上下文窗口输出"""
    approved: bool = Field(..., description="是否批准拓展")
    new_size: int = Field(..., description="新的上下文窗口大小")
    iteration: int = Field(..., description="下一迭代轮数（从1开始）")
    max_iterations: int = Field(..., description="最大允许迭代次数")
    message: str = Field(..., description="状态信息")
```

**实现**:
```python
async def expand_context_window_tool(
    input_data: ExpandContextWindowInput,
    current_iteration: int,
    max_iterations: int
) -> ExpandContextWindowOutput:
    """
    处理上下文窗口拓展请求

    注意: 此工具被调用后，MemRecallAgent 会立即结束当前迭代，
    MemoryContext 将使用新的窗口大小重新发起调用。
    """
    # 检查是否还有迭代次数
    if current_iteration >= max_iterations:
        return ExpandContextWindowOutput(
            approved=False,
            new_size=input_data.current_size,
            iteration=current_iteration,
            max_iterations=max_iterations,
            message=f"已达到最大迭代次数 ({max_iterations})，无法继续拓展"
        )

    # 批准拓展
    next_iteration = current_iteration + 1

    return ExpandContextWindowOutput(
        approved=True,
        new_size=input_data.requested_size,
        iteration=next_iteration,
        max_iterations=max_iterations,
        message=f"批准拓展到 {input_data.requested_size} 条消息，进入第 {next_iteration} 轮迭代"
    )
```

---

### 2.5 handoff

**描述**: 完成记忆召回任务并结束 Agent。这是 MemRecallAgent 的终止工具，必须在最后调用。

**输入模型**:
```python
class HandoffInput(BaseModel):
    """完成记忆召回任务的输入"""
    reason: str = Field(
        ...,
        description="结束任务的原因，例如：'已找到相关记忆，搜索完成' 或 '达到最大迭代次数，返回当前最佳结果'"
    )
    search_summary: str = Field(
        ...,
        description="搜索结果的总结，包括找到的相关记忆和关键信息"
    )
    relevant_memory_keys: List[str] = Field(
        default=[],
        description="相关记忆的 key 列表"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="对搜索结果相关性的信心度 0.0-1.0"
    )
    needs_more_info: bool = Field(
        default=False,
        description="是否需要更多信息来精确定位记忆"
    )
    follow_up_question: Optional[str] = Field(
        default=None,
        description="如果需要更多信息，向用户提出的问题"
    )

    # 迭代状态记录
    iteration_used: int = Field(
        default=1,
        description="完成时使用的迭代轮数"
    )
    context_window_used: int = Field(
        default=5,
        description="最终使用的上下文窗口大小（消息数）"
    )
```

**输出模型**:
```python
class HandoffOutput(BaseModel):
    """完成记忆召回输出"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="最终结果消息")
    task_completed: bool = Field(True, description="任务是否完成")
```

**实现**:
```python
async def handoff_tool(
    input_data: HandoffInput
) -> HandoffOutput:
    """
    完成记忆召回任务

    注意: 此工具被调用后，MemRecallAgent 会立即结束运行。
    """
    # 构建结果消息
    message_parts = [
        f"## 记忆搜索完成 (信心度: {input_data.confidence:.0%})",
        "",
        f"### 搜索总结",
        input_data.search_summary,
        "",
        f"### 相关性分析",
        input_data.reasoning,
    ]

    if input_data.relevant_memory_keys:
        message_parts.extend([
            "",
            f"### 相关记忆标识",
            f"共找到 {len(input_data.relevant_memory_keys)} 个相关记忆:",
            *[f"- {key}" for key in input_data.relevant_memory_keys]
        ])

    if input_data.needs_more_info and input_data.follow_up_question:
        message_parts.extend([
            "",
            f"### 需要进一步澄清",
            input_data.follow_up_question
        ])

    return HandoffOutput(
        success=True,
        message="\n".join(message_parts),
        task_completed=True
    )
```

---

## 3. 工具注册表

```python
from typing import Dict, Callable, Any
from pydantic import BaseModel

# 工具函数注册表
MEMRECALL_TOOLS: Dict[str, Dict[str, Any]] = {
    "search_memories": {
        "name": "search_memories",
        "description": """搜索用户的历史记忆。

使用场景:
1. 用户提到之前讨论过的话题时
2. 需要了解用户偏好或历史操作时
3. 需要验证或引用之前的结论时
4. 上下文出现不明确的引用时（如"按照之前的配置"）

搜索策略:
- 模糊查询时使用 search_mode="semantic"
- 有明确关键词时使用 search_mode="keyword"
- 不确定时使用默认的 "hybrid" 模式

示例:
- "我之前的数据库配置" -> keywords=["数据库", "配置"]
- "上次的方案" -> search_mode="semantic", query="上次讨论的方案"
""",
        "input_model": SearchMemoriesInput,
        "output_model": SearchMemoriesOutput,
        "func": search_memories_tool,
    },
    "get_memory_detail": {
        "name": "get_memory_detail",
        "description": """获取特定记忆的完整内容。

使用场景:
1. search_memories 返回的记忆摘要不完整
2. 需要查看记忆的具体内容细节
3. 需要确认记忆的具体元数据

注意: 必须通过 search_memories 获取 memory_key 后再调用此工具
""",
        "input_model": GetMemoryDetailInput,
        "output_model": GetMemoryDetailOutput,
        "func": get_memory_detail_tool,
    },
    "extract_search_keywords": {
        "name": "extract_search_keywords",
        "description": """从复杂查询中提取关键词（辅助工具）。

使用场景:
1. 用户查询很长很复杂
2. 不确定应该搜索哪些关键词
3. 需要系统性地分析用户意图

通常不需要直接调用，search_memories 会自动处理关键词提取
""",
        "input_model": ExtractKeywordsInput,
        "output_model": ExtractKeywordsOutput,
        "func": extract_search_keywords_tool,
    },
    "expand_context_window": {
        "name": "expand_context_window",
        "description": """请求拓展上下文窗口大小。

使用场景:
1. 当前搜索结果不理想，需要查看更多历史消息
2. 用户查询涉及久远的对话，需要回溯更早的上下文
3. 当前上下文不足以理解用户意图

重要: 调用此工具后会立即结束当前迭代，系统将重新发起调用并提供更多消息！
此工具只能在未达到最大迭代次数时使用。

示例:
- reason="搜索结果太少，需要查看更早的对话来找到相关记忆"
- current_size=5, requested_size=10
""",
        "input_model": ExpandContextWindowInput,
        "output_model": ExpandContextWindowOutput,
        "func": expand_context_window_tool,
        "is_expansion": True,  # 标记为拓展工具
    },
    "handoff": {
        "name": "handoff",
        "description": """完成记忆搜索任务并结束 Agent。

使用场景:
1. 已完成记忆搜索并整理出结果
2. 无法找到相关记忆，需要报告完成情况
3. 已达到最大迭代次数，必须结束

重要: 调用此工具后 MemRecallAgent 会立即结束！这是唯一的正常退出方式。

示例:
- reason="已找到3个相关记忆，搜索完成"
- reason="达到最大迭代次数，返回当前最佳结果"
""",
        "input_model": HandoffInput,
        "output_model": HandoffOutput,
        "func": handoff_tool,
        "is_handoff": True,  # 标记为 handoff 工具
    },
}
```

---

## 4. 使用流程示例

### 4.1 标准搜索流程

```
用户: "按照我之前的数据库配置来"

MemRecallAgent:
1. 分析意图 -> 需要搜索 "数据库配置" 相关记忆
2. 调用 search_memories(
       query="用户之前的数据库配置",
       search_mode="hybrid",
       keywords=["数据库", "配置", "database"]
   )
3. 获得 3 个相关记忆
4. 评估相关性，发现第一个最相关
5. 调用 get_memory_detail(memory_key="db_config_001") 获取详情
6. 整理结果
7. 调用 handoff(
       search_summary="找到用户之前的数据库配置...",
       relevant_memory_keys=["db_config_001"],
       confidence=0.85
   )
8. Agent 结束
```

### 4.2 多轮搜索流程

```
用户: "上次说的那个方案"

MemRecallAgent:
1. 首次搜索 search_memories(query="上次说的方案", search_mode="semantic")
2. 返回结果过多，需要进一步过滤
3. 第二次搜索 search_memories(
       query="上次说的方案",
       memory_types=["command_output"],
       time_range_days=7
   )
4. 缩小到 2 个记忆
5. 获取详情并评估
6. handoff(...)
```

### 4.3 未找到记忆流程

```
用户: "我之前让你做的那个东西"

MemRecallAgent:
1. 搜索 search_memories(query="之前做的东西", search_mode="semantic")
2. 返回 0 个结果
3. 扩大范围再次搜索 search_memories(
       query="之前做的东西",
       min_relevance_score=0.3,
       limit=10
   )
4. 仍然返回 0 个结果
5. handoff(
       search_summary="未找到用户提到的历史记忆",
       confidence=0.0,
       needs_more_info=True,
       follow_up_question="您能否提供更多细节，比如大概什么时间或什么主题？"
   )
```

---

## 5. 错误处理

### 5.1 常见错误码

| 错误类型 | 处理建议 |
|---------|---------|
| 搜索超时 | 缩小搜索范围，使用更精确的关键词 |
| 无权限访问 | 报告给父 Agent，可能需要重新认证 |
| 记忆不存在 | 尝试模糊搜索或询问用户更多信息 |
| 数据库错误 | 重试一次，仍然失败则报告错误 |

### 5.2 错误响应格式

```python
{
    "success": False,
    "total_found": 0,
    "results": [],
    "message": "具体错误信息，包含建议的解决方案"
}
```

---

## 6. 性能优化

### 6.1 缓存策略

- 关键词扩展结果缓存 5 分钟
- 同一用户的最近搜索结果缓存 1 分钟
- 热门记忆内容缓存 10 分钟

### 6.2 查询限制

- 单次搜索最多返回 10 条结果
- 最多连续调用 3 次搜索工具（防止无限循环）
- 每个记忆内容最大 100KB（超过则截断）

---

## 7. 安全考虑

1. **用户隔离**: 所有工具强制要求 user_id，防止跨用户访问
2. **输入验证**: 所有输入参数经过 Pydantic 验证
3. **SQL 注入防护**: 使用 ORM 参数化查询，禁止原生 SQL
4. **内容过滤**: 敏感记忆内容需要额外权限验证
