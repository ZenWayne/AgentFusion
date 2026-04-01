# GraphRAG 集成改动计划

## 一、整体架构变更

**当前流程：**
```
PDF → OCR → slice_to_chunk → ContextManager (Chroma) → context_search (regex)
```

**目标流程（完全替换）：**
```
PDF → OCR → Markdown → ArticleStore
                            ↓
                      GraphRAG build_index()
                       (内部 token-based chunking + 实体抽取 + 社区报告)
                            ↓
                      Parquet + LanceDB 知识图谱
                            ↓
               ┌────────────┴────────────┐
         graphrag_search            graphrag_trace
        (LocalSearch/GlobalSearch)  (溯源：answer → entity → text_unit → document)
```

**关键决策：**
- **彻底删除** `slice_to_chunk`、`context_search`、`ContextManager`（含 Chroma、RAG Pipeline）
- 整篇 Markdown 直接传入 GraphRAG，由它负责全部文本处理
- 新建两个 FunctionTool：`graphrag_search`（查询）+ `graphrag_trace`（溯源）
- 利用 GraphRAG 原生溯源链：`SearchResult.context_data` → `text_units(document_id)` → 原始文档

---

## 二、删除模块清单

| 文件 | 说明 |
|------|------|
| `src/tools/slice_to_chunk.py` | 删除：Markdown 分片工具 |
| `src/tools/context_search.py` | 删除：regex grep 搜索工具 |
| `src/agents/search_agent/context_manager.py` | 删除：Chunk 存储 + Chroma 向量索引 |
| `src/agents/search_agent/rag_pipeline.py` | 删除：recall → rerank → LLM dropout pipeline |
| `src/tools/rerank.py` | 删除：DashScope rerank 工具（不再需要） |
| `schemas/agent.py` 中的 `context_search_enable` 字段 | 删除 |
| `agent_builder.py` 中的 context_search 工具注入逻辑 | 删除 |

**保留：**
- `src/agents/search_agent/ocr.py` — PDF → Markdown（GraphRAG 的输入源）
- `src/agents/search_agent/scholar.py` — 论文搜索
- `src/agents/search_agent/validator.py` — 幻觉验证（改为调用 graphrag_trace 做溯源验证）
- `src/agents/search_agent/todo_tracker.py` — 进度追踪

---

## 三、新增模块

### 3.1 `src/agents/search_agent/article_store.py` — 文章存储

**职责：** 存储 OCR 产出的完整 Markdown 和元数据，供 GraphRAG 索引消费。替代 ContextManager。

```python
@dataclass
class ArticleEntry:
    article_name: str
    source_url: str
    full_markdown: str

class ArticleStore:
    """存储完整 Markdown 文档，供 GraphRAG 索引消费"""

    def __init__(self) -> None:
        self.articles: dict[str, ArticleEntry] = {}

    def add_article(self, name: str, url: str, markdown: str) -> None:
        self.articles[name] = ArticleEntry(name, url, markdown)

    def to_dataframe(self) -> pd.DataFrame:
        """导出为 GraphRAG build_index() 可消费的 DataFrame，每行一篇完整文章"""
        rows = []
        for entry in self.articles.values():
            rows.append({
                "id": entry.article_name,
                "text": f"[Article: {entry.article_name} | URL: {entry.source_url}]\n{entry.full_markdown}",
                "title": entry.article_name,
            })
        return pd.DataFrame(rows)

    def get_article(self, name: str) -> ArticleEntry | None:
        return self.articles.get(name)

    def list_articles(self) -> list[str]:
        return list(self.articles.keys())

    def get_metadata_map(self) -> dict[str, dict[str, str]]:
        """返回 article_name → {source_url, ...} 映射，供溯源时关联 document_id"""
        return {
            name: {"source_url": entry.source_url}
            for name, entry in self.articles.items()
        }
```

### 3.2 `src/tools/graphrag_config_builder.py` — GraphRAG 配置构造器

**职责：** 将 AgentFusion 的模型配置映射为 GraphRAG 的 `GraphRagConfig`。

```python
def build_graphrag_config(
    completion_model_label: str,  # e.g. "deepseek-chat_DeepSeek"
    embedding_model_label: str,   # e.g. "text-embedding-v4_DashScope"
    output_dir: str = "graphrag_output"
) -> GraphRagConfig:
    # 1. 从 AgentFusion 的 ModelInfo 获取 base_url, api_key, model_name
    # 2. 构造 GraphRAG ModelConfig (type="litellm", model_provider="openai", ...)
    # 3. 设置:
    #    - chunking: 使用 GraphRAG 默认 token-based chunking
    #    - output_storage: StorageConfig(type=File, base_dir=output_dir)
    #    - vector_store: VectorStoreConfig(type=LanceDB, db_uri=f"{output_dir}/vectors")
    #    - extract_graph.model: completion model
    #    - community_reports.model: completion model
    #    - embedding_models: embedding model
    # 4. 返回完整 GraphRagConfig
```

### 3.3 `src/tools/graphrag_index.py` — 索引构建工具

**职责：** 从 ArticleStore 获取整篇 Markdown，调用 `graphrag.api.build_index()` 构建知识图谱。

```python
class GraphRAGIndexTool(FunctionToolWithType):
    """将所有文章的完整Markdown构建为GraphRAG知识图谱索引"""

    # 注入: article_store, graphrag_config

    async def _run(self, output_dir: str = "graphrag_output") -> str:
        # 1. df = self.article_store.to_dataframe()
        # 2. config = self.graphrag_config  (或动态构建)
        # 3. results = await build_index(
        #        config=config,
        #        input_documents=df,  # 每行=一篇完整文章
        #        callbacks=[...],
        #        verbose=True
        #    )
        # 4. 返回索引状态摘要 (文档数、实体数、社区数等)
```

**`build_index()` 签名（来自源码）：**
```python
async def build_index(
    config: GraphRagConfig,
    method: IndexingMethod | str = IndexingMethod.Standard,
    is_update_run: bool = False,
    callbacks: list[WorkflowCallbacks] | None = None,
    additional_context: dict[str, Any] | None = None,
    verbose: bool = False,
    input_documents: pd.DataFrame | None = None,  # ← 直接传 DataFrame
) -> list[PipelineRunResult]
```

### 3.4 `src/tools/graphrag_search.py` — 图谱查询工具

**职责：** 封装 GraphRAG 的 `local_search()` / `global_search()` API，提供语义搜索能力。

**GraphRAG 返回类型（来自源码）：**
```python
# graphrag/query/structured_search/base.py
@dataclass
class SearchResult:
    response: str | dict[str, Any] | list[dict[str, Any]]
    context_data: str | list[pd.DataFrame] | dict[str, pd.DataFrame]
    context_text: str | list[str] | dict[str, str]
    completion_time: float
    llm_calls: int
    prompt_tokens: int
    output_tokens: int

# GlobalSearch 额外返回
@dataclass
class GlobalSearchResult(SearchResult):
    map_responses: list[SearchResult]
    reduce_context_data: str | list[pd.DataFrame] | dict[str, pd.DataFrame]
    reduce_context_text: str | list[str] | dict[str, str]
```

**接口设计：**
```python
class GraphRAGSearchTool(FunctionToolWithType):
    """基于知识图谱的语义搜索，支持局部精查和全局摘要

    - local: 细粒度实体/关系查询（适合查具体概念、实现细节、引用验证）
    - global: 宏观摘要查询（适合跨文档综述、共识分析、趋势总结）
    """

    async def _run(
        self,
        query: str,
        mode: str = "local",  # "local" | "global"
        community_level: int = 2,
        response_type: str = "Multiple Paragraphs"
    ) -> str:
        # 1. 加载 Parquet 数据 (首次加载后缓存)
        #    entities, communities, community_reports, text_units, relationships
        #
        # 2. 根据 mode 调用对应 API:
        #    if mode == "local":
        #        response, context_data = await local_search(
        #            config, entities, communities, community_reports,
        #            text_units, relationships, covariates=None,
        #            community_level=community_level,
        #            response_type=response_type,
        #            query=query
        #        )
        #    elif mode == "global":
        #        response, context_data = await global_search(
        #            config, entities, communities, community_reports,
        #            community_level=community_level,
        #            response_type=response_type,
        #            query=query
        #        )
        #
        # 3. 格式化输出:
        #    - response (LLM 生成的回答)
        #    - 从 context_data 中提取引用摘要 (entities, sources/text_units)
        #    - 返回格式化文本
```

**`local_search()` API 签名（来自源码）：**
```python
async def local_search(
    config: GraphRagConfig,
    entities: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    text_units: pd.DataFrame,
    relationships: pd.DataFrame,
    covariates: pd.DataFrame | None,
    community_level: int,
    response_type: str,
    query: str,
    callbacks: list[QueryCallbacks] | None = None,
    verbose: bool = False,
) -> tuple[str | dict[str, Any] | list[dict[str, Any]], str | list[pd.DataFrame] | dict[str, pd.DataFrame]]
# 返回: (response, context_data)
```

**`global_search()` API 签名（来自源码）：**
```python
async def global_search(
    config: GraphRagConfig,
    entities: pd.DataFrame,
    communities: pd.DataFrame,
    community_reports: pd.DataFrame,
    community_level: int,
    response_type: str,
    query: str,
    dynamic_community_selection: bool = False,
    callbacks: list[QueryCallbacks] | None = None,
    verbose: bool = False,
) -> tuple[str | dict[str, Any] | list[dict[str, Any]], str | list[pd.DataFrame] | dict[str, pd.DataFrame]]
# 返回: (response, context_data)
```

**Parquet 数据缓存设计：**
```python
# 模块级缓存，避免每次搜索重复读盘
_cached_data: dict[str, pd.DataFrame] | None = None

def _load_parquet_data(output_dir: str) -> dict[str, pd.DataFrame]:
    global _cached_data
    if _cached_data is not None:
        return _cached_data
    _cached_data = {
        "entities": pd.read_parquet(f"{output_dir}/entities.parquet"),
        "communities": pd.read_parquet(f"{output_dir}/communities.parquet"),
        "community_reports": pd.read_parquet(f"{output_dir}/community_reports.parquet"),
        "text_units": pd.read_parquet(f"{output_dir}/text_units.parquet"),
        "relationships": pd.read_parquet(f"{output_dir}/relationships.parquet"),
    }
    return _cached_data
```

### 3.5 `src/tools/graphrag_trace.py` — 溯源追踪工具（核心新增）

**职责：** 利用 GraphRAG 原生的溯源链，从查询结果反向追踪到原始文档片段，为 agent 提供引用验证能力。

**GraphRAG 溯源链（来自源码数据模型）：**
```
SearchResult.context_data (dict[str, pd.DataFrame])
    ↓ "entities" DataFrame
Entity(text_unit_ids: list[str])     # 实体关联到原始文本块
    ↓
TextUnit(document_id: str, text: str, entity_ids, relationship_ids)  # 文本块关联到原始文档
    ↓
Document(id: str, title: str, text: str, text_unit_ids: list[str])   # 原始文档 = 我们传入的整篇 Markdown
    ↓
ArticleStore.get_metadata_map()      # document_id → article_name → source_url
```

**GraphRAG 数据模型关键字段（来自源码）：**
```python
# graphrag/data_model/text_unit.py
@dataclass
class TextUnit(Identified):
    text: str
    entity_ids: list[str] | None = None
    relationship_ids: list[str] | None = None
    n_tokens: int | None = None
    document_id: str | None = None        # ← 关联回原始文档
    attributes: dict[str, Any] | None = None

# graphrag/data_model/entity.py
@dataclass
class Entity(Named):
    type: str | None = None
    description: str | None = None
    text_unit_ids: list[str] | None = None  # ← 关联到 TextUnit
    community_ids: list[str] | None = None
    rank: int | None = None

# graphrag/data_model/document.py
@dataclass
class Document(Named):
    type: str = "text"
    text: str = ""
    text_unit_ids: list[str] | None = None  # ← 包含的 TextUnit 列表
    attributes: dict[str, Any] | None = None
```

**接口设计：**
```python
class GraphRAGTraceTool(FunctionToolWithType):
    """溯源追踪：从查询结果反向定位到原始文档片段

    用途：
    - 验证 graphrag_search 返回的答案是否有原文支撑
    - 提取被引用的具体原文片段（text_units）
    - 关联回原始文章（article_name + source_url）
    - 列出命中的实体和关系，便于交叉验证
    """

    async def _run(
        self,
        query: str,
        community_level: int = 2
    ) -> str:
        # 1. 执行 local_search 获取 SearchResult
        #    response, context_data = await local_search(...)
        #
        # 2. 从 context_data 提取溯源数据:
        #
        #    context_data 是 dict[str, pd.DataFrame]，包含以下 key:
        #    - "entities": id, entity, description, rank, ...
        #    - "relationships": id, source, target, description, weight, ...
        #    - "sources" / "text_units": id, text, document_id, ...
        #    - "reports": community reports (if present)
        #
        # 3. 构建溯源链:
        #    sources_df = context_data.get("sources") or context_data.get("text_units")
        #    for row in sources_df.itertuples():
        #        text_unit_id = row.id
        #        raw_text = row.text            # 原始文本片段
        #        document_id = row.document_id  # 关联回原始文档 (= article_name)
        #        source_url = metadata_map[document_id]["source_url"]
        #
        # 4. 格式化输出:
        #    ## 查询: {query}
        #    ## LLM 回答: {response}
        #
        #    ## 溯源引用 (共 N 个原文片段)
        #    ### [引用 1] 来源: {article_name} ({source_url})
        #    > {raw_text_excerpt}
        #    命中实体: entity_a, entity_b
        #
        #    ### [引用 2] ...
        #
        #    ## 命中实体列表
        #    | 实体 | 类型 | 描述 | 来源文档 |
        #    |------|------|------|----------|
        #
        #    ## 命中关系列表
        #    | 源实体 | 目标实体 | 关系描述 | 权重 |
        #    |--------|----------|----------|------|
```

**与 `graphrag_search` 的区别：**
| | graphrag_search | graphrag_trace |
|---|---|---|
| **目的** | 获取 LLM 生成的语义回答 | 获取回答背后的原文证据 |
| **输出重点** | `response`（答案文本） | `context_data`（溯源数据） |
| **使用者** | analyzer、reporter（需要信息） | critics、validator（需要验证） |
| **模式** | local / global 可选 | 仅 local（溯源需要实体→文本块关联） |

**设计考量：**
- 溯源只用 `local_search`，因为 `GlobalSearch` 的 map-reduce 架构在 reduce 阶段丢失了细粒度的 text_unit 关联
- `context_data` 中 `"sources"` 或 `"text_units"` key 的存在取决于 GraphRAG 版本，代码中做兼容处理
- `document_id` 等于我们传入 `build_index()` 时 DataFrame 的 `id` 列（= `article_name`），因此可以直接关联回 `ArticleStore.get_metadata_map()`

---

## 四、现有模块改动

### 4.1 `src/schemas/agent.py` — AgentConfig 字段变更

```python
class AssistantAgentConfig(BaseAgentConfig):
    # 删除:
    # context_search_enable: bool = False
    # context_search_path: str | None = None

    # 新增:
    graphrag_enable: bool = False              # 启用 GraphRAG 搜索 + 溯源
    graphrag_index_enable: bool = False        # 启用 GraphRAG 索引构建（仅 explorer）
    graphrag_model: str | None = None          # GraphRAG LLM（实体抽取/社区报告）
    graphrag_embedding_model: str | None = None  # GraphRAG embedding 模型
```

### 4.2 `src/builders/agent_builder.py` — 工具注入逻辑替换

```python
# 删除整块:
# if agent_info.context_search_enable:
#     from agents.search_agent.context_manager import ContextManager
#     from tools.context_search import ContextSearchTool
#     from tools.slice_to_chunk import SliceToChunkTool
#     _cm = ContextManager()
#     tools.append(ContextSearchTool(context_manager=_cm))
#     tools.append(SliceToChunkTool(context_manager=_cm))

# 替换为:
if agent_info.graphrag_enable:
    from agents.search_agent.article_store import ArticleStore
    from tools.graphrag_search import GraphRAGSearchTool
    from tools.graphrag_trace import GraphRAGTraceTool

    _store = ArticleStore()

    if agent_info.graphrag_index_enable:
        from tools.graphrag_index import GraphRAGIndexTool
        graphrag_config = build_graphrag_config(
            agent_info.graphrag_model,
            agent_info.graphrag_embedding_model
        )
        tools.append(GraphRAGIndexTool(article_store=_store, config=graphrag_config))

    tools.append(GraphRAGSearchTool(output_dir=graphrag_output_dir))
    tools.append(GraphRAGTraceTool(output_dir=graphrag_output_dir, metadata_map=_store.get_metadata_map()))
```

### 4.3 `config.json` — Agent 配置更新

```json
{
  "agents": {
    "asci_explorer": {
      "graphrag_enable": true,
      "graphrag_index_enable": true,
      "graphrag_model": "deepseek-chat_DeepSeek",
      "graphrag_embedding_model": "text-embedding-v4_DashScope"
    },
    "asci_analyzer": {
      "graphrag_enable": true
    },
    "asci_critics": {
      "graphrag_enable": true
    },
    "asci_reporter": {
      "graphrag_enable": true
    }
  }
}
```

### 4.4 `src/schemas/model_info.py` — 新增 embedding 模型

```python
"text-embedding-v4_DashScope": ModelClientConfig(
    model_name="text-embedding-v4",
    base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
    env_key="DASHSCOPE_API_KEY",
    family=ModelFamily.UNKNOWN,
)
```

### 4.5 `src/agents/search_agent/validator.py` — 改用 GraphRAG 溯源

**改动：** `HallucinationValidator` 的验证逻辑从 regex 匹配改为调用 `graphrag_trace` 做溯源验证。

```python
# 旧: 用 ContextManager.search(pattern) 做 regex 匹配
# 新: 用 GraphRAGTraceTool._run(claim_query) 获取原文片段，判断是否有源

# 验证循环:
# 1. 提取 claims
# 2. 对每个 claim 调用 graphrag_trace 获取溯源
# 3. 检查溯源结果中是否有匹配的 text_units
# 4. 无源 claims 标记为 unsourced
```

### 4.6 Prompt 更新

更新以下 prompt 文件，移除 `context_search` / `slice_to_chunk` 工具说明，替换为 GraphRAG 工具：

- `config/prompt/agent/asci/explorer_pt.md` — OCR 后直接 add_article → 全部完成后 graphrag_index
- `config/prompt/agent/asci/analyzer_pt.md` — 用 graphrag_search(mode="local") 查询
- `config/prompt/agent/asci/critics_pt.md` — 用 graphrag_trace 做引用验证
- `config/prompt/agent/asci/reporter_pt.md` — 用 graphrag_search(mode="global") 综述 + local 补细节
- `config/prompt/agent/search_agent_pt.md` — 重写搜索流程

**Explorer prompt 示例：**
```markdown
### Phase 2: OCR & STORE
For each paper:
1. OCR the PDF to Markdown
2. Call `add_article_for_graph(article_name, source_url, full_markdown)` to store

### Phase 3: GRAPH INDEX BUILD
After ALL articles have been OCR'd and stored:
1. Call `graphrag_index` to build knowledge graph from all stored documents
2. GraphRAG internally: token chunking → entity extraction → community detection → reports
3. Once complete, graphrag_search and graphrag_trace tools become available

### Phase 4: HANDOFF
Pass control to analyzer with graph index ready
```

**Analyzer/Critics/Reporter prompt 工具说明：**
```markdown
## Available Tools
- `graphrag_search(query, mode, community_level)` — 语义搜索
  - mode="local": 查具体概念、实体、实现细节
  - mode="global": 跨文档综述、趋势分析
- `graphrag_trace(query, community_level)` — 溯源追踪
  - 返回原文片段 + 来源文章 + URL
  - 用于验证引用、交叉检查
```

---

## 五、数据流与生命周期

```
┌─────────────────────────────────────────────────────────────────┐
│                    Complete Data Flow                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Explorer Agent                                                  │
│  ├─ scholar.py → 搜索论文 PDF                                     │
│  ├─ ocr.py → PDF → full_markdown                                │
│  ├─ ArticleStore.add_article(name, url, markdown)               │
│  ├─ [循环处理所有论文...]                                          │
│  │                                                               │
│  └─ graphrag_index tool                                          │
│       └─ ArticleStore.to_dataframe() → 每行=整篇文章              │
│            └─ graphrag.api.build_index(input_documents=df)       │
│                 ├─ 内部 token-based chunking → TextUnit           │
│                 ├─ 实体抽取 (LLM) → Entity(text_unit_ids)        │
│                 ├─ 关系抽取 → Relationship(text_unit_ids)         │
│                 ├─ 社区检测 → Community                           │
│                 ├─ 社区报告 (LLM) → CommunityReport              │
│                 └─ 持久化 → Parquet + LanceDB                    │
│                                                                  │
│  ────── 索引完成，后续 agent 可查询+溯源 ──────                     │
│                                                                  │
│  Analyzer Agent                                                  │
│  └─ graphrag_search(query, mode="local")                         │
│       → SearchResult.response (LLM 生成的回答)                    │
│       → 附带引用摘要                                               │
│                                                                  │
│  Critics Agent                                                   │
│  ├─ graphrag_trace(claim_query)                                  │
│  │    → context_data["sources"] → TextUnit.text (原文片段)        │
│  │    → TextUnit.document_id → article_name → source_url         │
│  │    → context_data["entities"] → 命中实体列表                    │
│  └─ 判定: 有源 / 无源 / 需补充                                     │
│                                                                  │
│  Reporter Agent                                                  │
│  ├─ graphrag_search(query, mode="global") → 宏观综述              │
│  ├─ graphrag_search(query, mode="local") → 补充细节               │
│  └─ graphrag_trace(key_claim) → 关键引用溯源                      │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**GraphRAG 内部溯源链（Parquet 中的关联关系）：**
```
Document (id=article_name, text=full_markdown)
    │ text_unit_ids
    ↓
TextUnit (id, text=chunk片段, document_id → Document, entity_ids, relationship_ids)
    │ entity_ids
    ↓
Entity (id, title, type, description, text_unit_ids → TextUnit, community_ids)
    │ community_ids
    ↓
Community → CommunityReport (summary, full_content, rank)
    │
    ↓
SearchResult.context_data = {
    "entities": pd.DataFrame,       # 命中的实体
    "relationships": pd.DataFrame,  # 命中的关系
    "sources": pd.DataFrame,        # 命中的原文片段 (TextUnit)
    "reports": pd.DataFrame,        # 命中的社区报告
}
```

---

## 六、实施顺序

| 步骤 | 文件 | 内容 |
|------|------|------|
| **1** | `src/agents/search_agent/article_store.py` | 新建：ArticleStore，存储完整 Markdown |
| **2** | `src/tools/graphrag_config_builder.py` | 新建：GraphRAG 配置构造器 |
| **3** | `src/tools/graphrag_index.py` | 新建：索引构建工具，调用 `build_index()` |
| **4** | `src/tools/graphrag_search.py` | 新建：查询工具，封装 `local_search()` / `global_search()` |
| **5** | `src/tools/graphrag_trace.py` | 新建：溯源追踪工具，从 `context_data` 提取原文片段 |
| **6** | `src/schemas/agent.py` | 改动：删除 `context_search_enable`，新增 graphrag 字段 |
| **7** | `src/schemas/model_info.py` | 改动：新增 embedding 模型配置 |
| **8** | `src/builders/agent_builder.py` | 改动：删除旧工具注入，替换为 GraphRAG 工具注入 |
| **9** | 删除旧文件 | 删除 `slice_to_chunk.py`, `context_search.py`, `context_manager.py`, `rag_pipeline.py`, `rerank.py` |
| **10** | `config.json` | 改动：各 agent 配置 graphrag 字段 |
| **11** | `config/prompt/agent/asci/*.md` | 改动：重写工具使用说明 |
| **12** | `src/agents/search_agent/validator.py` | 改动：验证逻辑改用 graphrag_trace |
| **13** | 测试 | 单元测试 + 端到端验证 |

---

## 七、风险与注意事项

1. **索引耗时：** `build_index()` 涉及大量 LLM 调用（实体抽取、社区报告生成），10+ 篇论文可能需要数分钟。应在 explorer 完成所有文章 OCR 后一次性执行。
2. **Token 成本：** GraphRAG 对每个内部 chunk 调用 LLM 做实体抽取。建议使用 DeepSeek（便宜）而非 Gemini 作为 `graphrag_model`。
3. **context_data key 兼容性：** 不同 GraphRAG 版本中原文片段的 key 可能是 `"sources"` 或 `"text_units"`，代码中需做兼容：`context_data.get("sources") or context_data.get("text_units")`。
4. **GlobalSearch 溯源限制：** `global_search` 的 map-reduce 架构在 reduce 阶段聚合了 text_unit 信息，细粒度溯源精度下降。因此 `graphrag_trace` 只用 `local_search`。
5. **Embedding 模型兼容性：** DashScope text-embedding-v4 通过 LiteLLM 调用需确认兼容。备选：`sentence-transformers` 本地模型。
6. **不可逆删除风险：** 删除 `context_manager.py` / `rag_pipeline.py` 后无法回退到旧的 chunk-based 搜索。建议在 GraphRAG 端到端验证通过后再执行删除步骤（步骤 9）。
7. **document_id 映射：** `build_index()` 传入的 DataFrame `id` 列值（= article_name）会成为 `TextUnit.document_id`，溯源时通过此值关联回 `ArticleStore` 获取 source_url。确保 id 值唯一且一致。

---

## 八、依赖管理

### 8.1 pyproject.toml 变更

```toml
# 已存在 (确认版本兼容):
"graphrag>=3.0.0"

# 新增:
"lancedb>=0.6.0"     # GraphRAG 默认 vector store backend
"pyarrow>=15.0.0"    # Parquet 读写 (graphrag 依赖，显式声明)

# 可删除:
# "chromadb" — 如果项目中除 ContextManager 外无其他消费者
```

### 8.2 依赖兼容性验证清单

| 依赖 | 验证点 | 备注 |
|------|--------|------|
| graphrag>=3.0.0 | `build_index()` 接受 `input_documents: pd.DataFrame` | v3.x API 签名稳定 |
| graphrag | `local_search()` / `global_search()` 返回 `(response, context_data)` | 确认 tuple 返回而非 SearchResult |
| lancedb | GraphRAG VectorStoreConfig(type=LanceDB) 正常初始化 | 需与 graphrag 版本匹配 |
| litellm | DashScope embedding 通过 `litellm.embedding(model="dashscope/text-embedding-v4")` 调用 | graphrag 使用 litellm 作为 model adapter |
| pandas | `pd.read_parquet()` 能读取 graphrag 输出的 Parquet 文件 | pyarrow engine |

### 8.3 LiteLLM 模型映射

GraphRAG 通过 LiteLLM 调用模型，需确认 AgentFusion 的模型标签到 LiteLLM model string 的映射：

```python
# AgentFusion label → LiteLLM model string
LITELLM_MODEL_MAP = {
    "deepseek-chat_DeepSeek": "openai/deepseek-chat",        # base_url 透传
    "deepseek-v3_Aliyun": "openai/deepseek-v3",              # DashScope endpoint
    "text-embedding-v4_DashScope": "openai/text-embedding-v4", # DashScope embedding
}

# 在 graphrag_config_builder.py 中使用:
# GraphRagConfig.models[model_name] = ModelConfig(
#     type="litellm",
#     model=litellm_model_string,
#     api_base=base_url,
#     api_key=api_key,
# )
```

---

## 九、跨 Agent 状态共享设计

### 9.1 核心问题

在 GraphFlow 中，每个 Agent 由 `AgentBuilder.build()` 独立构造。Explorer 构建索引后，Analyzer/Critics/Reporter 需要访问同一份索引数据。

### 9.2 方案：文件系统 + metadata.json 共享

**与旧方案（ContextManager 内存单例）的区别：** GraphRAG 索引天然持久化到 Parquet + LanceDB，不依赖内存共享。

```
graphrag_output/                    # 所有 agent 共享的 output_dir
├── entities.parquet
├── communities.parquet
├── community_reports.parquet
├── text_units.parquet
├── relationships.parquet
├── documents.parquet
├── vectors/                        # LanceDB
│   └── default-lancedb/
└── article_metadata.json           # ← 新增：ArticleStore 元数据快照
```

**article_metadata.json 格式：**
```json
{
  "articles": {
    "attention_is_all_you_need": {
      "source_url": "https://arxiv.org/abs/1706.03762",
      "indexed_at": "2026-04-01T10:30:00"
    }
  },
  "index_built_at": "2026-04-01T10:35:00",
  "document_count": 5,
  "entity_count": 342
}
```

### 9.3 状态共享流程

```
GraphFlowBuilder 构建所有 Agent
    │
    ├─ Explorer (graphrag_index_enable=true)
    │   ├─ ArticleStore (in-memory) → add_article() 存储文章
    │   ├─ graphrag_index tool:
    │   │   ├─ ArticleStore.to_dataframe() → build_index()
    │   │   └─ ArticleStore.get_metadata_map() → article_metadata.json (写入磁盘)
    │   └─ handoff → Analyzer
    │
    ├─ Analyzer (graphrag_enable=true, graphrag_index_enable=false)
    │   ├─ graphrag_search tool: 读取 Parquet 文件 (output_dir)
    │   └─ graphrag_trace tool: 读取 Parquet + article_metadata.json
    │
    ├─ Critics (同 Analyzer)
    └─ Reporter (同 Analyzer)
```

### 9.4 output_dir 配置

`output_dir` 通过 agent config 中的 `graphrag_output_dir` 字段统一指定，默认值 `graphrag_output`。所有参与同一 graph flow 的 agent 必须指向同一路径。

```json
{
  "agents": {
    "asci_explorer": {
      "graphrag_output_dir": "graphrag_output/asci_session"
    },
    "asci_analyzer": {
      "graphrag_output_dir": "graphrag_output/asci_session"
    }
  }
}
```

### 9.5 ArticleStore metadata 序列化

在 `article_store.py` 中增加持久化方法：

```python
class ArticleStore:
    # ... 已有方法 ...

    def save_metadata(self, output_dir: str) -> None:
        """索引构建完成后，将元数据写入磁盘供其他 agent 读取"""
        metadata = {
            "articles": {
                name: {"source_url": entry.source_url}
                for name, entry in self.articles.items()
            },
            "index_built_at": datetime.now().isoformat(),
            "document_count": len(self.articles),
        }
        path = Path(output_dir) / "article_metadata.json"
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2))

    @staticmethod
    def load_metadata(output_dir: str) -> dict[str, dict[str, str]]:
        """从磁盘读取元数据（供 graphrag_trace 使用）"""
        path = Path(output_dir) / "article_metadata.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text())
        return data.get("articles", {})
```

### 9.6 agent_builder.py 修正

基于状态共享方案，修正第四节的 agent_builder 注入逻辑：

```python
if agent_info.graphrag_enable:
    output_dir = agent_info.graphrag_output_dir or "graphrag_output"

    if agent_info.graphrag_index_enable:
        # Explorer: 需要 ArticleStore + IndexTool + SearchTool + TraceTool
        from agents.search_agent.article_store import ArticleStore
        from tools.graphrag_index import GraphRAGIndexTool
        from tools.graphrag_config_builder import build_graphrag_config

        _store = ArticleStore()
        graphrag_config = build_graphrag_config(
            agent_info.graphrag_model,
            agent_info.graphrag_embedding_model,
            output_dir=output_dir,
        )
        tools.append(GraphRAGIndexTool(
            article_store=_store,
            config=graphrag_config,
            output_dir=output_dir,
        ))
        # Explorer 也注册 add_article 的 FunctionTool
        tools.append(_build_add_article_tool(_store))

    # 所有 graphrag_enable agent 都注册 search + trace
    from tools.graphrag_search import GraphRAGSearchTool
    from tools.graphrag_trace import GraphRAGTraceTool

    tools.append(GraphRAGSearchTool(output_dir=output_dir))
    tools.append(GraphRAGTraceTool(output_dir=output_dir))
```

---

## 十、测试策略

### 10.1 测试分层

```
┌──────────────────────────────────────────────┐
│ Layer 1: 单元测试 (无 LLM, 无磁盘 I/O)        │
│   Mock GraphRAG API, 验证数据转换和工具逻辑      │
├──────────────────────────────────────────────┤
│ Layer 2: 集成测试 (有磁盘 I/O, 无 LLM)         │
│   使用 fixture Parquet 文件, 验证读写流程        │
├──────────────────────────────────────────────┤
│ Layer 3: 端到端测试 (有 LLM 调用)               │
│   真实 build_index + search, 验证完整流程        │
│   标记 @pytest.mark.slow, CI 中可选跳过         │
└──────────────────────────────────────────────┘
```

### 10.2 Layer 1: 单元测试

**文件：** `tests/tools/test_article_store.py`
```python
class TestArticleStore:
    def test_add_article(self):
        store = ArticleStore()
        store.add_article("paper1", "https://example.com/1", "# Title\nContent...")
        assert "paper1" in store.list_articles()

    def test_to_dataframe_format(self):
        store = ArticleStore()
        store.add_article("paper1", "url1", "markdown1")
        df = store.to_dataframe()
        assert list(df.columns) == ["id", "text", "title"]
        assert df.iloc[0]["id"] == "paper1"
        assert "url1" in df.iloc[0]["text"]

    def test_metadata_roundtrip(self, tmp_path):
        store = ArticleStore()
        store.add_article("paper1", "https://url1", "md1")
        store.save_metadata(str(tmp_path))
        loaded = ArticleStore.load_metadata(str(tmp_path))
        assert loaded["paper1"]["source_url"] == "https://url1"

    def test_get_nonexistent_article(self):
        store = ArticleStore()
        assert store.get_article("nope") is None
```

**文件：** `tests/tools/test_graphrag_config_builder.py`
```python
class TestGraphRAGConfigBuilder:
    def test_builds_valid_config(self):
        config = build_graphrag_config(
            "deepseek-chat_DeepSeek",
            "text-embedding-v4_DashScope",
            output_dir="/tmp/test_output"
        )
        assert config is not None
        # 验证 model 配置正确映射
        # 验证 output storage 路径
        # 验证 vector store 配置

    def test_unknown_model_raises(self):
        with pytest.raises(KeyError):
            build_graphrag_config("nonexistent_model", "also_nonexistent")
```

**文件：** `tests/tools/test_graphrag_search.py`
```python
class TestGraphRAGSearchTool:
    @pytest.mark.asyncio
    async def test_search_local_mode(self, mock_parquet_dir):
        """Mock pd.read_parquet 返回 fixture DataFrame, 验证格式化输出"""
        tool = GraphRAGSearchTool(output_dir=str(mock_parquet_dir))
        with patch("tools.graphrag_search.local_search") as mock_search:
            mock_search.return_value = ("LLM answer here", {"entities": pd.DataFrame()})
            result = await tool._run(query="attention mechanism", mode="local")
            assert "LLM answer here" in result
            mock_search.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_global_mode(self, mock_parquet_dir):
        """验证 global mode 调用 global_search"""
        ...

    @pytest.mark.asyncio
    async def test_index_not_built_error(self, tmp_path):
        """output_dir 中无 Parquet 文件时返回友好错误"""
        tool = GraphRAGSearchTool(output_dir=str(tmp_path))
        result = await tool._run(query="test")
        assert "error" in result.lower() or "not found" in result.lower()
```

**文件：** `tests/tools/test_graphrag_trace.py`
```python
class TestGraphRAGTraceTool:
    @pytest.mark.asyncio
    async def test_trace_extracts_sources(self, mock_parquet_dir):
        """验证溯源从 context_data 正确提取 text_unit → document_id → source_url"""
        with patch("tools.graphrag_trace.local_search") as mock_search:
            mock_search.return_value = (
                "answer",
                {
                    "sources": pd.DataFrame({
                        "id": ["tu1"],
                        "text": ["original text chunk"],
                        "document_id": ["paper1"],
                    }),
                    "entities": pd.DataFrame({
                        "entity": ["Transformer"],
                        "description": ["A neural network architecture"],
                    }),
                }
            )
            tool = GraphRAGTraceTool(output_dir=str(mock_parquet_dir))
            result = await tool._run(query="transformer architecture")
            assert "original text chunk" in result
            assert "paper1" in result

    @pytest.mark.asyncio
    async def test_trace_with_text_units_key(self):
        """兼容性：context_data 使用 'text_units' 而非 'sources' key"""
        ...
```

### 10.3 Layer 2: 集成测试

**文件：** `tests/integration/test_graphrag_pipeline.py`

```python
@pytest.fixture
def fixture_parquet_dir(tmp_path):
    """创建 fixture Parquet 文件模拟 build_index 的输出"""
    entities_df = pd.DataFrame({
        "id": ["e1", "e2"],
        "title": ["Transformer", "Attention"],
        "type": ["CONCEPT", "MECHANISM"],
        "description": ["Neural network arch", "Weighted focus mechanism"],
        "text_unit_ids": [["tu1"], ["tu1", "tu2"]],
        "community_ids": [["c1"], ["c1"]],
    })
    entities_df.to_parquet(tmp_path / "entities.parquet")
    # ... 同理创建 communities, community_reports, text_units, relationships
    return tmp_path


class TestGraphRAGPipelineIntegration:
    @pytest.mark.asyncio
    async def test_search_reads_parquet_correctly(self, fixture_parquet_dir):
        """验证 search tool 能正确加载和缓存 Parquet 数据"""
        ...

    @pytest.mark.asyncio
    async def test_trace_metadata_integration(self, fixture_parquet_dir):
        """验证 trace tool 通过 article_metadata.json 正确关联 source_url"""
        ...

    def test_article_store_to_index_to_search_flow(self):
        """验证 ArticleStore → DataFrame → (mock) build_index → Parquet → search 完整流程"""
        ...
```

### 10.4 Layer 3: 端到端测试 (需 LLM API Key)

**文件：** `tests/e2e/test_graphrag_e2e.py`

```python
@pytest.mark.slow
@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY"),
    reason="Requires DEEPSEEK_API_KEY for LLM calls"
)
class TestGraphRAGE2E:
    @pytest.mark.asyncio
    async def test_full_pipeline(self, tmp_path):
        """
        完整流程: ArticleStore → build_index → local_search → trace
        使用 2-3 篇短文本 (< 500 tokens each) 控制成本
        """
        store = ArticleStore()
        store.add_article(
            "test_article",
            "https://test.com",
            "# Transformer\nThe Transformer is a neural network architecture..."
        )

        config = build_graphrag_config(
            "deepseek-chat_DeepSeek",
            "text-embedding-v4_DashScope",
            output_dir=str(tmp_path),
        )

        # Build index
        results = await build_index(
            config=config,
            input_documents=store.to_dataframe(),
        )
        assert all(r.status == "success" for r in results)

        # Search
        response, context_data = await local_search(
            config=config, query="What is Transformer?", ...
        )
        assert response  # 非空回答
        assert "entities" in context_data or "sources" in context_data
```

### 10.5 测试 Fixture 与 conftest

```python
# tests/conftest.py

@pytest.fixture
def mock_parquet_dir(tmp_path):
    """标准化的 mock Parquet 输出目录"""
    _write_fixture_parquets(tmp_path)
    _write_fixture_metadata(tmp_path)
    return tmp_path

@pytest.fixture(autouse=True)
def clear_parquet_cache():
    """每个测试前清理模块级 Parquet 缓存"""
    import tools.graphrag_search as gs
    gs._cached_data = None
    yield
    gs._cached_data = None
```

---

## 十一、回滚与渐进迁移方案

### 11.1 渐进迁移策略（推荐）

将实施顺序（第六节）分为三个阶段，每阶段可独立验证和回滚：

```
Phase 1: 新增 (无破坏性)          Phase 2: 切换               Phase 3: 清理
───────────────────────────     ─────────────────────      ──────────────────
步骤 1-5: 新建所有模块             步骤 6-8: schema/builder   步骤 9: 删除旧模块
步骤 7: 新增 embedding 模型        步骤 10-12: config/prompt   删除 chromadb 依赖

验证: 独立单元测试通过              验证: 端到端流程通过         验证: 全量测试通过
回滚: 删除新文件即可               回滚: git revert schema     回滚: git revert
```

### 11.2 Phase 1 具体步骤

1. 新建 `article_store.py`, `graphrag_config_builder.py`, `graphrag_index.py`, `graphrag_search.py`, `graphrag_trace.py`
2. 新增 `model_info.py` 中的 embedding 模型
3. **不修改任何现有文件**
4. 运行 Layer 1 + Layer 2 测试，确认新模块工作正常
5. 可选：运行 Layer 3 E2E 测试验证真实 LLM 调用

**回滚方式：** 直接删除新文件，无任何副作用。

### 11.3 Phase 2 具体步骤

1. 修改 `schemas/agent.py`：新增 graphrag 字段（保留 `context_search_enable` 字段但标记 deprecated）
2. 修改 `agent_builder.py`：新增 graphrag 工具注入逻辑（保留旧逻辑）
3. 更新 `config.json`：agent 配置新增 graphrag 字段
4. 更新 prompt 文件

**关键：Phase 2 中 `context_search_enable` 和 `graphrag_enable` 可以共存。** 这允许逐个 agent 迁移，而非一次性全部切换。

```python
# agent_builder.py - Phase 2 兼容逻辑
if agent_info.graphrag_enable:
    # 新的 GraphRAG 工具注入
    ...
elif agent_info.context_search_enable:
    # 旧的 ContextSearch 工具注入 (deprecated, 保留兼容)
    ...
```

**回滚方式：** `git revert` schema 和 builder 变更，将 config 中的 `graphrag_enable` 改回 `false`。

### 11.4 Phase 3 具体步骤

仅在 Phase 2 端到端验证通过且稳定运行一段时间后执行：

1. 删除 `context_search_enable` 字段和旧工具注入逻辑
2. 删除旧文件：`slice_to_chunk.py`, `context_search.py`, `context_manager.py`, `rag_pipeline.py`, `rerank.py`
3. 如果 chromadb 无其他消费者，从 `pyproject.toml` 移除

**回滚方式：** `git revert`，但此阶段回滚代价较高，因此建议确认稳定后再执行。

---

## 十二、性能优化与缓存策略

### 12.1 索引构建优化

| 优化点 | 策略 | 预期效果 |
|--------|------|----------|
| **批量索引** | 所有文章 OCR 完成后一次性调用 `build_index()`，而非逐篇 | 减少 GraphRAG 内部 workflow 开销 |
| **增量索引** | 利用 `build_index(is_update_run=True)` 追加新文档 | 避免全量重建 |
| **Chunk size 调优** | GraphRAG 默认 chunk size 300 tokens，可根据学术论文特点调大至 500-800 | 减少 LLM 调用次数，降低成本 |
| **并行度控制** | GraphRAG config 中设置 `max_concurrent_requests` 避免 rate limit | 防止 API 429 错误 |

```python
# graphrag_config_builder.py 中的性能参数
config.extract_graph.max_gleanings = 1      # 实体抽取轮数 (默认1, 加大提高召回但增加成本)
config.chunking.chunk_size = 600            # 学术论文建议比默认值大
config.chunking.chunk_overlap = 100         # 片段重叠 tokens
config.parallelization.max_workers = 4      # 并行 LLM 调用数
```

### 12.2 查询性能优化

**Parquet 缓存（已在 3.4 节设计）：**
- 模块级 `_cached_data` 字典，首次查询时从磁盘加载，后续查询复用
- `graphrag_index` 工具执行后主动使缓存失效（`_cached_data = None`）

**LanceDB 向量缓存：**
- LanceDB 本身有内存映射机制，首次查询后自动缓存到内存
- 无需额外缓存层

### 12.3 session 级索引隔离

不同对话 session 可能处理不同的论文集合。`graphrag_output_dir` 应包含 session 标识：

```python
# 方案 A: config 中硬编码 (适合固定研究项目)
"graphrag_output_dir": "graphrag_output/asci_session"

# 方案 B: 运行时动态生成 (适合多会话并行)
output_dir = f"graphrag_output/session_{session_id}"
```

当前阶段采用方案 A（固定路径），后续可扩展为方案 B。

### 12.4 磁盘空间管理

GraphRAG 索引会产生显著的磁盘文件：

| 组件 | 预估大小 (10篇论文) | 说明 |
|------|---------------------|------|
| Parquet 文件 | 10-50 MB | entities, text_units, relationships 等 |
| LanceDB 向量 | 20-100 MB | embedding 向量存储 |
| 合计 | 30-150 MB | 随文档量线性增长 |

**清理策略：**
- 提供 `graphrag_clear` 工具或 CLI 命令，删除指定 output_dir
- 在 ArticleStore metadata 中记录 `index_built_at`，便于判断索引时效性

---

## 十三、config.json 完整变更示例

基于所有改动，展示完整的 config.json 变更（仅 asci 相关 agent）：

```json
{
  "agents": {
    "asci_explorer": {
      "name": "asci_explorer",
      "type": "assistant_agent",
      "prompt_path": "agent/asci/explorer_pt.md",
      "model_client": "deepseek-chat_DeepSeek",
      "graphrag_enable": true,
      "graphrag_index_enable": true,
      "graphrag_model": "deepseek-chat_DeepSeek",
      "graphrag_embedding_model": "text-embedding-v4_DashScope",
      "graphrag_output_dir": "graphrag_output/asci_session",
      "mcp_tools": ["file_system"],
      "handoff_tools": [
        {
          "target": "asci_analyzer",
          "message": "Graph index built. All articles indexed and ready for analysis."
        }
      ]
    },
    "asci_analyzer": {
      "name": "asci_analyzer",
      "type": "assistant_agent",
      "prompt_path": "agent/asci/analyzer_pt.md",
      "model_client": "deepseek-chat_DeepSeek",
      "graphrag_enable": true,
      "graphrag_output_dir": "graphrag_output/asci_session",
      "handoff_tools": [
        {
          "target": "asci_critics",
          "message": "Analysis complete. Please verify claims against source material."
        }
      ]
    },
    "asci_critics": {
      "name": "asci_critics",
      "type": "assistant_agent",
      "prompt_path": "agent/asci/critics_pt.md",
      "model_client": "deepseek-chat_DeepSeek",
      "graphrag_enable": true,
      "graphrag_output_dir": "graphrag_output/asci_session",
      "handoff_tools": [
        {
          "target": "asci_reporter",
          "message": "Verification complete. Claims validated with source tracing."
        }
      ]
    },
    "asci_reporter": {
      "name": "asci_reporter",
      "type": "assistant_agent",
      "prompt_path": "agent/asci/reporter_pt.md",
      "model_client": "deepseek-chat_DeepSeek",
      "graphrag_enable": true,
      "graphrag_output_dir": "graphrag_output/asci_session",
      "mcp_tools": ["file_system"]
    }
  }
}
```

---

## 十四、验收标准

### 14.1 功能验收

| 编号 | 验收项 | 验证方法 |
|------|--------|----------|
| F1 | ArticleStore 能存储完整 Markdown 并导出为 DataFrame | 单元测试 |
| F2 | `graphrag_index` 工具能成功调用 `build_index()` 并生成 Parquet 文件 | E2E 测试 |
| F3 | `graphrag_search(mode="local")` 返回语义相关的 LLM 回答 | E2E 测试 |
| F4 | `graphrag_search(mode="global")` 返回跨文档综述 | E2E 测试 |
| F5 | `graphrag_trace` 能从回答溯源到原文片段和源文档 URL | E2E 测试 |
| F6 | Explorer → Analyzer → Critics → Reporter 完整 graph flow 能正常运行 | 手动验证 |
| F7 | 旧的 `context_search` 工具不再被任何 agent 引用 | grep 验证 |

### 14.2 非功能验收

| 编号 | 验收项 | 标准 |
|------|--------|------|
| NF1 | 10 篇论文索引构建时间 | < 10 分钟 (DeepSeek API) |
| NF2 | 单次 local_search 响应时间 | < 15 秒 |
| NF3 | 单次 global_search 响应时间 | < 30 秒 |
| NF4 | Parquet 缓存命中后查询时间 | < 5 秒 |
| NF5 | Layer 1 + Layer 2 测试全部通过 | 100% pass rate |
| NF6 | 无 import 路径使用 `..` 父目录遍历 | grep 验证 |

---

## TODO

| # | 问题 | 原因 | 优先级 |
|---|------|------|--------|
| T1 | `create_community_reports` 全部失败，`global` 搜索不可用 | DeepSeek 不支持 `response_format={"type":"json_schema"}`（structured output），LiteLLM 将 Pydantic model 转为 json_schema 后 DeepSeek 报 `This response_format type is unavailable now` | 中 |
| T2 | 当前 `mode="global"` 的验收项 F4 / NF3 无法通过 | 依赖 T1 修复 | 中 |

### T1 可选解法

1. **换模型**：为社区报告单独配置支持 structured output 的模型（OpenAI `gpt-4o` 或 Gemini），需确认 `GraphRagConfig` 是否支持按 workflow 分模型
2. **等 DeepSeek**：DeepSeek 错误信息含 "unavailable now"，可能是临时限制，后续版本可能支持
3. **降级 json_object**：在 LiteLLM 层将 Pydantic schema 调用拦截并降级为 `json_object` + prompt 指导输出格式，需 patch `lite_llm_completion.py` 或 fork graphrag_llm
