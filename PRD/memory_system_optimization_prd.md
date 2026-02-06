# 记忆系统优化 PRD

## 文档信息
- **版本**: 1.0
- **日期**: 2026-02-06
- **状态**: 草案

---

## 1. 背景与现状

### 1.1 当前架构
当前记忆系统采用两层架构：
- **Layer 1**: 记忆摘要（summary）作为占位符存储在上下文中
- **Layer 2**: 完整内容（content）存储在数据库中

### 1.2 现有问题

#### 1.2.1 搜索能力局限
- **简单关键字匹配**: 使用 SQL `ILIKE` 进行子串匹配，无向量相似度
- **无语义理解**: 无法找到概念相关但关键词不同的记忆
- **无相关性排序**: 结果按时间而非相关性返回

#### 1.2.2 查询机制僵化
- **预生成查询**: `init_memory()` 在对话开始前一次性生成查询
- **无法动态扩展**: 对话过程中无法根据新上下文搜索更多记忆
- **Agent 无主动权**: Agent 不能自主决定何时搜索记忆

#### 1.2.3 关键词管理缺失
- **无关键词提取**: 不存储记忆的关键词标签
- **无关键词索引**: 无法通过关键词快速定位记忆
- **无权重机制**: 无法区分关键词重要性

---

## 2. 目标

### 2.1 主要目标
1. **工具化记忆查询**: 让 Agent 能够主动调用记忆工具搜索历史信息
2. **增强关键词搜索**: 支持多维度关键词搜索和智能匹配
3. **动态记忆加载**: 根据对话进展实时加载相关记忆

### 2.2 非目标
- 实现向量数据库存储（保留为后续迭代）
- 跨用户记忆共享
- 记忆自动合并与抽象

---

## 3. 需求详细设计

### 3.1 记忆工具 (Memory Tools)

#### 3.1.1 需求概述
将记忆查询封装为 Agent 可调用的工具，使 Agent 能够：
- 根据当前上下文决定何时搜索记忆
- 指定搜索策略和参数
- 获取结构化的记忆结果

#### 3.1.2 工具接口设计

```python
# 工具: search_memories
class SearchMemoriesInput(BaseModel):
    """记忆搜索工具输入"""
    query: str = Field(..., description="搜索查询，可以是自然语言描述或关键词")
    search_mode: Literal["semantic", "keyword", "hybrid"] = Field(
        default="hybrid",
        description="搜索模式: semantic-语义匹配, keyword-关键词匹配, hybrid-混合"
    )
    keywords: Optional[List[str]] = Field(
        default=None,
        description="可选的精确关键词列表，用于精确过滤"
    )
    memory_types: Optional[List[str]] = Field(
        default=None,
        description="按记忆类型过滤，如 ['user_preference', 'command_output']"
    )
    time_range: Optional[Tuple[datetime, datetime]] = Field(
        default=None,
        description="时间范围过滤"
    )
    limit: int = Field(default=5, ge=1, le=20, description="返回结果数量限制")
    min_relevance_score: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="最小相关性分数阈值"
    )

class MemorySearchResult(BaseModel):
    """记忆搜索结果"""
    memory_key: str
    summary: str
    content_preview: str  # 前200字符
    memory_type: Optional[str]
    relevance_score: float
    created_at: datetime
    keywords: List[str]
    metadata: Dict[str, Any]

class SearchMemoriesOutput(BaseModel):
    """记忆搜索工具输出"""
    total_found: int
    results: List[MemorySearchResult]
    search_strategy_used: str
    expanded_keywords: Optional[List[str]]  # 系统扩展的同义词/相关词
```

#### 3.1.3 工具注册与使用

```python
# 在 AgentBuilder 中注册记忆工具
class AgentBuilder:
    def _build_memory_tools(self) -> List[Tool]:
        """构建记忆相关工具"""
        return [
            FunctionTool(
                name="search_memories",
                description="""搜索用户的历史记忆。

使用场景:
1. 用户提到之前讨论过的话题时
2. 需要了解用户偏好或历史操作时
3. 需要验证或引用之前的结论时
4. 上下文出现不明确的引用时

示例:
- "我之前让你配置的参数" -> search_memories(query="配置参数", memory_types=["command_output"])
- "还是按之前的方式处理" -> search_memories(query="处理方式", search_mode="semantic")
""",
                func=self._search_memories_tool,
                input_model=SearchMemoriesInput,
                output_model=SearchMemoriesOutput
            ),
            FunctionTool(
                name="get_memory_detail",
                description="获取特定记忆的完整内容",
                func=self._get_memory_detail_tool,
                input_model=GetMemoryDetailInput,
                output_model=GetMemoryDetailOutput
            )
        ]
```

### 3.2 关键词搜索增强

#### 3.2.1 需求概述
建立完整的关键词管理体系，支持：
- 自动关键词提取与存储
- 关键词索引与快速检索
- 同义词扩展与语义关联

#### 3.2.2 数据库 Schema 扩展

```sql
-- 新增: 记忆关键词关联表
CREATE TABLE agent_memory_keywords (
    id SERIAL PRIMARY KEY,
    memory_id UUID NOT NULL REFERENCES agent_memories(id) ON DELETE CASCADE,
    keyword VARCHAR(100) NOT NULL,
    weight FLOAT DEFAULT 1.0,  -- 关键词权重 (0.0-1.0)
    extraction_source VARCHAR(20) DEFAULT 'llm',  -- 'llm', 'user_tag', 'system'
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_memory_keyword UNIQUE (memory_id, keyword)
);

-- 新增: 关键词同义词表
CREATE TABLE keyword_synonyms (
    id SERIAL PRIMARY KEY,
    keyword VARCHAR(100) NOT NULL,
    synonym VARCHAR(100) NOT NULL,
    similarity_score FLOAT DEFAULT 0.8,  -- 相似度分数

    CONSTRAINT unique_keyword_synonym UNIQUE (keyword, synonym)
);

-- 索引
CREATE INDEX idx_memory_keywords_memory ON agent_memory_keywords(memory_id);
CREATE INDEX idx_memory_keywords_keyword ON agent_memory_keywords(keyword);
CREATE INDEX idx_keyword_synonyms_keyword ON keyword_synonyms(keyword);
```

#### 3.2.3 SQLAlchemy 模型

```python
# data_layer/models/tables/agent_memory_keywords_table.py
class AgentMemoryKeywordsTable(Base):
    __tablename__ = "agent_memory_keywords"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    memory_id: Mapped[UUID] = mapped_column(
        ForeignKey("agent_memories.id", ondelete="CASCADE"),
        nullable=False
    )
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    weight: Mapped[float] = mapped_column(Float, default=1.0)
    extraction_source: Mapped[str] = mapped_column(String(20), default="llm")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

# data_layer/models/tables/keyword_synonyms_table.py
class KeywordSynonymsTable(Base):
    __tablename__ = "keyword_synonyms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    keyword: Mapped[str] = mapped_column(String(100), nullable=False)
    synonym: Mapped[str] = mapped_column(String(100), nullable=False)
    similarity_score: Mapped[float] = mapped_column(Float, default=0.8)
```

#### 3.2.4 关键词提取策略

```python
class KeywordExtractor:
    """记忆关键词提取器"""

    async def extract_keywords(
        self,
        content: str,
        summary: str,
        memory_type: Optional[str] = None,
        max_keywords: int = 5
    ) -> List[Tuple[str, float]]:
        """
        提取关键词并返回 (keyword, weight) 列表

        策略:
        1. LLM 提取: 使用 LLM 提取核心概念关键词
        2. 规则增强: 根据 memory_type 添加类型相关关键词
        3. 用户标签: 保留用户手动添加的标签
        4. 去重归一: 统一大小写，去除重复
        """

    async def expand_keywords(
        self,
        keywords: List[str],
        include_synonyms: bool = True,
        include_semantic: bool = True
    ) -> Dict[str, List[str]]:
        """
        扩展关键词以支持更广泛匹配

        Returns:
            {
                "original": ["原始关键词"],
                "synonyms": ["同义词"],
                "related": ["语义相关词"]
            }
        """
```

### 3.3 搜索算法优化

#### 3.3.1 混合搜索策略

```python
class HybridMemorySearch:
    """混合记忆搜索引擎"""

    async def search(
        self,
        query: str,
        keywords: Optional[List[str]] = None,
        search_mode: str = "hybrid",
        **filters
    ) -> List[ScoredMemoryResult]:
        """
        执行混合搜索

        算法:
        1. 关键词匹配 (40% 权重)
           - 精确匹配: 1.0 分
           - 前缀匹配: 0.8 分
           - 同义词匹配: 0.7 分

        2. 文本相似度 (40% 权重)
           - 标题/摘要相似度 (TF-IDF + BM25)
           - 内容预览相似度

        3. 时间衰减 (20% 权重)
           - 越新的记忆权重越高
           - 使用指数衰减函数
        """

    def _calculate_keyword_score(
        self,
        memory_keywords: List[AgentMemoryKeywordsTable],
        query_keywords: List[str]
    ) -> float:
        """计算关键词匹配分数"""

    def _calculate_text_similarity(
        self,
        query: str,
        summary: str,
        content: str
    ) -> float:
        """计算文本相似度分数"""

    def _apply_time_decay(
        self,
        base_score: float,
        created_at: datetime,
        half_life_days: float = 30.0
    ) -> float:
        """应用时间衰减"""
        age_days = (datetime.utcnow() - created_at).days
        decay_factor = 0.5 ** (age_days / half_life_days)
        return base_score * (0.5 + 0.5 * decay_factor)  # 保留至少50%分数
```

#### 3.3.2 搜索结果排序

```python
class SearchResultRanker:
    """搜索结果排序器"""

    def rank_results(
        self,
        results: List[ScoredMemoryResult],
        query_context: Optional[str] = None
    ) -> List[ScoredMemoryResult]:
        """
        对搜索结果进行最终排序

        排序因子:
        1. 基础相关性分数 (70%)
        2. 用户交互历史 (20%) - 被召回次数、上次访问时间
        3. 记忆类型优先级 (10%) - user_preference > command_output > general
        """
```

### 3.4 MemoryContext 优化

#### 3.4.1 工具调用集成

```python
class MemoryContext(ChatCompletionContext):
    """优化后的记忆上下文"""

    def __init__(
        self,
        *,
        data_layer: AgentFusionDataLayer,
        user_id: int,
        memory_model_client: ChatCompletionClient,
        enable_proactive_search: bool = True,
        proactive_search_threshold: float = 0.7
    ):
        self.data_layer = data_layer
        self.user_id = user_id
        self.memory_model_client = memory_model_client
        self.enable_proactive_search = enable_proactive_search
        self.proactive_search_threshold = proactive_search_threshold

        # 记忆工具注册
        self.memory_tools = self._init_memory_tools()

    async def get_messages(self) -> List[LLMMessage]:
        """
        获取消息列表，支持 Agent 调用记忆工具

        流程:
        1. 获取基础消息列表
        2. 如果 Agent 有 search_memories 工具调用，执行搜索
        3. 将搜索结果注入到上下文中
        4. 返回完整消息列表
        """

    async def _handle_tool_calls(
        self,
        tool_calls: List[ToolCall]
    ) -> List[ToolResult]:
        """处理记忆相关工具调用"""
        results = []
        for call in tool_calls:
            if call.name == "search_memories":
                result = await self._execute_memory_search(call.arguments)
                results.append(ToolResult(call_id=call.id, result=result))
        return results
```

#### 3.4.2 主动记忆提示

```python
# 系统提示模板，指导 Agent 使用记忆工具
MEMORY_TOOLS_SYSTEM_PROMPT = """你是一个智能助手，拥有访问用户历史记忆的权限。

## 记忆工具使用指南

当你需要以下信息时，请主动调用 `search_memories` 工具：

1. **用户提及历史内容**
   - 用户说："按照之前的配置"、"我之前问过"、"上次的方案"
   - 操作：调用 search_memories 搜索相关主题

2. **用户偏好与习惯**
   - 需要了解用户的风格偏好、常用设置
   - 操作：搜索 memory_types=["user_preference"] 的记忆

3. **复杂任务延续**
   - 多轮对话中需要引用之前步骤的结果
   - 操作：使用关键词搜索相关步骤

4. **不确定性澄清**
   - 对用户请求中的模糊引用不确定时
   - 操作：使用 semantic 模式搜索相关记忆

## 搜索策略建议

- **精确查找**: 使用 keywords 参数指定确切词汇
- **模糊匹配**: 使用 search_mode="semantic" 进行语义搜索
- **类型过滤**: 使用 memory_types 缩小搜索范围
- **时间范围**: 对于近期事件使用时间过滤

## 搜索结果使用

搜索结果会显示相关性分数（0-1），建议：
- 优先使用分数 > 0.8 的记忆
- 0.6-0.8 的记忆作为参考
- 多个相关记忆时综合判断
"""
```

---

## 4. 实现计划

### 4.1 阶段一: 基础设施 (Week 1-2)

#### 4.1.1 数据库迁移
- [ ] 创建 `agent_memory_keywords` 表
- [ ] 创建 `keyword_synonyms` 表
- [ ] 编写迁移脚本
- [ ] 更新 SQLAlchemy 模型

#### 4.1.2 关键词提取模块
- [ ] 实现 `KeywordExtractor` 类
- [ ] 集成 LLM 关键词提取 prompt
- [ ] 添加关键词权重计算逻辑
- [ ] 编写单元测试

### 4.2 阶段二: 搜索算法 (Week 2-3)

#### 4.2.1 混合搜索实现
- [ ] 实现 `HybridMemorySearch` 类
- [ ] 关键词匹配算法
- [ ] 文本相似度计算 (BM25/TF-IDF)
- [ ] 时间衰减函数

#### 4.2.2 MemoryModel 扩展
- [ ] 扩展 `search_memories` 方法支持新参数
- [ ] 添加关键词管理方法
- [ ] 实现同义词扩展查询

### 4.3 阶段三: 记忆工具 (Week 3-4)

#### 4.3.1 工具定义
- [ ] 创建工具输入/输出 Pydantic 模型
- [ ] 实现 `search_memories` 工具函数
- [ ] 实现 `get_memory_detail` 工具函数

#### 4.3.2 Agent 集成
- [ ] 修改 `AgentBuilder` 注册记忆工具
- [ ] 更新 `MemoryContext` 支持工具调用
- [ ] 添加系统提示词模板

### 4.4 阶段四: 优化与测试 (Week 4-5)

#### 4.4.1 性能优化
- [ ] 添加数据库查询缓存
- [ ] 优化关键词索引查询
- [ ] 并发搜索优化

#### 4.4.2 测试覆盖
- [ ] 集成测试：完整搜索流程
- [ ] 性能测试：大数据量搜索
- [ ] 端到端测试：Agent 使用记忆工具

---

## 5. 接口变更

### 5.1 向后兼容性

```python
# 保持现有接口兼容
class MemoryModel:
    async def search_memories(
        self,
        query: str,
        user_id: Optional[int] = None,
        limit: int = 5,
        # 新增可选参数
        search_mode: str = "keyword",  # 默认 keyword 保持兼容
        keywords: Optional[List[str]] = None,
        memory_types: Optional[List[str]] = None,
        time_range: Optional[Tuple[datetime, datetime]] = None,
        min_relevance_score: float = 0.0
    ) -> List[MemoryInfo]:
        ...
```

### 5.2 配置更新

```json
// config.json 新增记忆系统配置
{
  "memory_system": {
    "search": {
      "default_mode": "hybrid",
      "keyword_weight": 0.4,
      "text_similarity_weight": 0.4,
      "time_decay_weight": 0.2,
      "half_life_days": 30
    },
    "extraction": {
      "max_keywords_per_memory": 5,
      "min_keyword_weight": 0.3,
      "enable_synonym_expansion": true
    },
    "tools": {
      "enable_proactive_search": true,
      "proactive_search_threshold": 0.7,
      "max_results_per_search": 5
    }
  }
}
```

---

## 6. 度量指标

### 6.1 技术指标
- **搜索延迟**: P95 < 200ms
- **关键词提取延迟**: P95 < 500ms
- **索引覆盖率**: > 95% 的记忆有关联关键词
- **缓存命中率**: > 70%

### 6.2 效果指标
- **搜索准确率**: Top-3 相关记忆命中率 > 80%
- **Agent 工具使用率**: Agent 主动调用记忆工具的频率
- **用户满意度**: 用户对记忆引用的满意度评分
- **上下文相关性**: 加载记忆与用户查询的相关性分数

---

## 7. 风险评估与缓解

| 风险 | 概率 | 影响 | 缓解措施 |
|------|------|------|----------|
| 关键词提取质量不佳 | 中 | 高 | 使用 LLM 验证 + 人工审核样本 |
| 搜索性能下降 | 中 | 高 | 添加缓存、索引优化、查询限流 |
| Agent 滥用工具 | 低 | 中 | 限制调用频率、添加相关性阈值 |
| 数据迁移失败 | 低 | 高 | 完整备份、灰度发布、回滚计划 |

---

## 8. 附录

### 8.1 LLM Prompt 模板

#### 关键词提取 Prompt
```
从以下记忆中提取最多 {max_keywords} 个关键词。

记忆摘要: {summary}
记忆内容: {content}
记忆类型: {memory_type}

要求:
1. 提取核心概念和主题词
2. 包含用户、动作、对象等实体
3. 每个关键词给出重要性权重 (0.0-1.0)
4. 优先选择能区分此记忆与其他记忆的词

返回 JSON 格式:
{
  "keywords": [
    {"word": "关键词1", "weight": 0.9},
    {"word": "关键词2", "weight": 0.7}
  ]
}
```

#### 搜索查询扩展 Prompt
```
用户搜索查询: "{query}"

请扩展以下搜索查询，以帮助找到更相关的记忆:
1. 提取核心关键词
2. 生成同义词/近义词
3. 识别相关概念

返回 JSON 格式:
{
  "core_keywords": ["核心词1", "核心词2"],
  "synonyms": [["词1", "同义词1", "同义词2"]],
  "related_concepts": ["相关概念1", "相关概念2"]
}
```

### 8.2 数据库迁移脚本

```python
# migration_001_add_memory_keywords.py
"""
数据库迁移: 添加记忆关键词支持
"""

from sqlalchemy import text

async def upgrade(connection):
    # 创建关键词表
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS agent_memory_keywords (
            id SERIAL PRIMARY KEY,
            memory_id UUID NOT NULL REFERENCES agent_memories(id) ON DELETE CASCADE,
            keyword VARCHAR(100) NOT NULL,
            weight FLOAT DEFAULT 1.0,
            extraction_source VARCHAR(20) DEFAULT 'llm',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT unique_memory_keyword UNIQUE (memory_id, keyword)
        );

        CREATE INDEX idx_memory_keywords_memory ON agent_memory_keywords(memory_id);
        CREATE INDEX idx_memory_keywords_keyword ON agent_memory_keywords(keyword);
    """))

    # 创建同义词表
    await connection.execute(text("""
        CREATE TABLE IF NOT EXISTS keyword_synonyms (
            id SERIAL PRIMARY KEY,
            keyword VARCHAR(100) NOT NULL,
            synonym VARCHAR(100) NOT NULL,
            similarity_score FLOAT DEFAULT 0.8,
            CONSTRAINT unique_keyword_synonym UNIQUE (keyword, synonym)
        );

        CREATE INDEX idx_keyword_synonyms_keyword ON keyword_synonyms(keyword);
    """))

    # 为现有多有记忆提取关键词
    await connection.execute(text("""
        -- 标记需要重新索引的记忆
        ALTER TABLE agent_memories
        ADD COLUMN IF NOT EXISTS needs_keyword_extraction BOOLEAN DEFAULT TRUE;

        UPDATE agent_memories
        SET needs_keyword_extraction = TRUE
        WHERE is_active = TRUE;
    """))

async def downgrade(connection):
    await connection.execute(text("""
        DROP TABLE IF EXISTS agent_memory_keywords;
        DROP TABLE IF EXISTS keyword_synonyms;
        ALTER TABLE agent_memories DROP COLUMN IF EXISTS needs_keyword_extraction;
    """))
```

---

## 9. 相关文档

- [当前记忆系统实现](../python/packages/agent_fusion/src/agent_memory/context.py)
- [MemoryModel 数据层](../python/packages/agent_fusion/src/data_layer/models/memory_model.py)
- [数据库 Schema](../sql/progresdb.sql)
- [AgentBuilder 实现](../python/packages/agent_fusion/src/builders/agent_builder.py)
