# Memory Data Layer PRD

## 文档信息
- **版本**: 1.0
- **日期**: 2026-02-10
- **状态**: 草案
- **依赖**: memory_system_optimization_prd.md

---

## 1. 概述

Memory Data Layer 负责记忆数据的存储、检索和高级搜索。本文档定义 `search_memories_advanced` 方法的实现规范，使用 SQLAlchemy ORM（禁止 raw SQL），支持 MemRecallAgent 的多维度记忆搜索需求。

---

## 2. 数据表定义

### 2.1 关键词表

```python
# data_layer/models/tables/memory_keyword_table.py
from sqlalchemy import Column, String, Float, DateTime, Integer, ForeignKey, Index
from sqlalchemy.sql import func
from .base_table import Base

class AgentMemoryKeywordsTable(Base):
    """记忆关键词关联表"""
    __tablename__ = 'agent_memory_keywords'

    id = Column(Integer, primary_key=True, autoincrement=True)
    memory_key = Column(String(255), ForeignKey('agent_memories.memory_key', ondelete='CASCADE'), nullable=False)
    user_id = Column(Integer, ForeignKey('User.id', ondelete='CASCADE'), nullable=False)
    keyword = Column(String(255), nullable=False, index=True)
    weight = Column(Float, default=1.0)
    created_at = Column(DateTime, server_default=func.current_timestamp())

    # 复合索引
    __table_args__ = (
        Index('idx_memory_keywords_user_key', 'user_id', 'memory_key'),
        Index('idx_memory_keywords_user_kw', 'user_id', 'keyword'),
    )
```

### 2.2 更新记忆表（添加向量字段）

```python
# data_layer/models/tables/memory_table.py
from sqlalchemy import Column, String, Text, Boolean, DateTime, ForeignKey, Integer
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB, UUID, VECTOR
from sqlalchemy.orm import relationship
from .base_table import Base

class AgentMemoriesTable(Base):
    """SQLAlchemy ORM model for agent_memories table"""
    __tablename__ = 'agent_memories'

    id = Column(UUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    user_id = Column(Integer, ForeignKey('User.id', ondelete='CASCADE'), nullable=False)
    agent_id = Column(Integer, ForeignKey('agents.id'), nullable=True)
    thread_id = Column(UUID(as_uuid=True), ForeignKey('threads.id'), nullable=True)
    memory_key = Column(String(255), nullable=False, index=True)
    memory_type = Column(String(50), index=True)  # 添加索引
    summary = Column(Text)
    content = Column(Text)
    content_metadata = Column(JSONB, default={})
    embedding = Column(VECTOR(1536), nullable=True)  # 向量字段
    created_at = Column(DateTime, server_default=func.current_timestamp())
    is_active = Column(Boolean, default=True, index=True)  # 添加索引

    # Relationships
    keywords = relationship("AgentMemoryKeywordsTable", back_populates="memory", cascade="all, delete-orphan")
```

---

## 3. 接口定义

### 3.1 search_memories_advanced

```python
# data_layer/models/memory_model.py

from typing import Optional, Dict, Any, List, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass
from sqlalchemy import select, and_, or_, func, desc
from sqlalchemy.orm import joinedload

@dataclass
class MemorySearchResult:
    """记忆搜索结果"""
    memory_key: str
    summary: Optional[str]
    content_preview: str
    memory_type: Optional[str]
    relevance_score: float
    created_at: datetime
    keywords: List[str]
    metadata: Dict[str, Any]

class MemoryModel(BaseModel):
    """Memory data model with advanced search capabilities"""

    async def search_memories_advanced(
        self,
        user_id: int,
        query: str,
        keywords: Optional[List[str]] = None,
        memory_types: Optional[List[str]] = None,
        time_range_days: Optional[int] = None,
        min_relevance_score: float = 0.5,
        limit: int = 5,
        search_mode: Literal["semantic", "keyword", "hybrid"] = "hybrid"
    ) -> List[MemorySearchResult]:
        """
        高级记忆搜索

        Args:
            user_id: 用户ID（数据隔离）
            query: 自然语言查询
            keywords: 精确关键词列表
            memory_types: 记忆类型过滤
            time_range_days: 时间范围（最近N天）
            min_relevance_score: 最小相关性分数
            limit: 返回结果数量限制
            search_mode: 搜索模式

        Returns:
            按相关性排序的记忆列表
        """
        if search_mode == "semantic":
            return await self._semantic_search(
                user_id, query, limit, min_relevance_score
            )
        elif search_mode == "keyword":
            return await self._keyword_search(
                user_id, keywords or [query], limit, min_relevance_score
            )
        else:  # hybrid
            return await self._hybrid_search(
                user_id, query, keywords, memory_types,
                time_range_days, limit, min_relevance_score
            )
```

---

## 4. 搜索实现

### 4.1 语义搜索

```python
async def _semantic_search(
    self,
    user_id: int,
    query: str,
    limit: int,
    min_score: float
) -> List[MemorySearchResult]:
    """
    语义搜索 - 使用向量相似度

    注意：向量搜索使用 PostgreSQL pgvector 扩展
    """
    # 获取 query 向量
    query_vector = await self._embed_query(query)

    async with await self.db.get_session() as session:
        # 使用 pgvector 的 <=> 操作符（欧氏距离）
        # 1 - distance 转换为相似度
        similarity_score = (1 - AgentMemoriesTable.embedding.op('<=>')(query_vector)).label('relevance_score')

        stmt = (
            select(
                AgentMemoriesTable,
                similarity_score
            )
            .where(
                and_(
                    AgentMemoriesTable.user_id == user_id,
                    AgentMemoriesTable.is_active == True,
                    AgentMemoriesTable.embedding.isnot(None),
                    similarity_score >= min_score
                )
            )
            .order_by(AgentMemoriesTable.embedding.op('<=>')(query_vector))
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

        return [
            self._row_to_search_result(row[0], row[1], [])
            for row in rows
        ]
```

### 4.2 关键词搜索

```python
async def _keyword_search(
    self,
    user_id: int,
    keywords: List[str],
    limit: int,
    min_score: float
) -> List[MemorySearchResult]:
    """
    关键词搜索 - 基于关键词表
    """
    from data_layer.models.tables.memory_keyword_table import AgentMemoryKeywordsTable

    async with await self.db.get_session() as session:
        # 构建关键词匹配条件
        keyword_conditions = [
            AgentMemoryKeywordsTable.keyword.ilike(f"%{kw}%")
            for kw in keywords
        ]

        # 子查询：计算每个 memory_key 的匹配分数
        keyword_scores = (
            select(
                AgentMemoryKeywordsTable.memory_key,
                func.sum(AgentMemoryKeywordsTable.weight).label('total_weight'),
                func.count(AgentMemoryKeywordsTable.keyword.distinct()).label('match_count'),
                func.array_agg(AgentMemoryKeywordsTable.keyword.distinct()).label('matched_keywords')
            )
            .where(
                and_(
                    AgentMemoryKeywordsTable.user_id == user_id,
                    or_(*keyword_conditions)
                )
            )
            .group_by(AgentMemoryKeywordsTable.memory_key)
            .subquery()
        )

        # 计算相关性分数：total_weight * 0.3 + match_count * 0.2
        relevance_score = (
            func.least(
                keyword_scores.c.total_weight * 0.3 + keyword_scores.c.match_count * 0.2,
                1.0
            )
        ).label('relevance_score')

        # 主查询
        stmt = (
            select(
                AgentMemoriesTable,
                relevance_score,
                keyword_scores.c.matched_keywords
            )
            .join(keyword_scores, AgentMemoriesTable.memory_key == keyword_scores.c.memory_key)
            .where(
                and_(
                    AgentMemoriesTable.user_id == user_id,
                    AgentMemoriesTable.is_active == True,
                    relevance_score >= min_score
                )
            )
            .order_by(desc(relevance_score))
            .limit(limit)
        )

        result = await session.execute(stmt)
        rows = result.all()

        return [
            self._row_to_search_result(row[0], row[1], row[2] or [])
            for row in rows
        ]
```

### 4.3 混合搜索

```python
async def _hybrid_search(
    self,
    user_id: int,
    query: str,
    keywords: Optional[List[str]],
    memory_types: Optional[List[str]],
    time_range_days: Optional[int],
    limit: int,
    min_score: float
) -> List[MemorySearchResult]:
    """
    混合搜索 - 语义 + 关键词加权融合
    """
    import asyncio

    # 并行执行两种搜索（获取更多结果用于融合）
    semantic_task = self._semantic_search(
        user_id, query, limit * 2, min_score * 0.8
    )
    keyword_task = self._keyword_search(
        user_id, keywords or [query], limit * 2, min_score * 0.8
    )

    semantic_results, keyword_results = await asyncio.gather(
        semantic_task, keyword_task,
        return_exceptions=True
    )

    # 处理异常
    if isinstance(semantic_results, Exception):
        logger.error(f"Semantic search failed: {semantic_results}")
        semantic_results = []
    if isinstance(keyword_results, Exception):
        logger.error(f"Keyword search failed: {keyword_results}")
        keyword_results = []

    # 应用额外过滤器（memory_types, time_range）
    if memory_types or time_range_days:
        semantic_results = await self._apply_filters(
            semantic_results, user_id, memory_types, time_range_days
        )
        keyword_results = await self._apply_filters(
            keyword_results, user_id, memory_types, time_range_days
        )

    # 融合结果
    merged = self._merge_search_results(
        semantic_results, keyword_results,
        semantic_weight=0.6, keyword_weight=0.4
    )

    # 过滤和排序
    filtered = [r for r in merged if r.relevance_score >= min_score]
    filtered.sort(key=lambda x: x.relevance_score, reverse=True)

    return filtered[:limit]
```

### 4.4 过滤器应用

```python
async def _apply_filters(
    self,
    results: List[MemorySearchResult],
    user_id: int,
    memory_types: Optional[List[str]],
    time_range_days: Optional[int]
) -> List[MemorySearchResult]:
    """
    对搜索结果应用额外过滤器

    由于结果已经是 ORM 对象转换而来，这里需要重新查询数据库
    """
    if not results:
        return []

    memory_keys = [r.memory_key for r in results]

    async with await self.db.get_session() as session:
        conditions = [
            AgentMemoriesTable.user_id == user_id,
            AgentMemoriesTable.memory_key.in_(memory_keys),
            AgentMemoriesTable.is_active == True
        ]

        if memory_types:
            conditions.append(AgentMemoriesTable.memory_type.in_(memory_types))

        if time_range_days:
            cutoff_date = datetime.utcnow() - timedelta(days=time_range_days)
            conditions.append(AgentMemoriesTable.created_at >= cutoff_date)

        stmt = select(AgentMemoriesTable).where(and_(*conditions))
        result = await session.execute(stmt)
        valid_memories = {m.memory_key: m for m in result.scalars().all()}

        # 过滤并保留原分数
        filtered = []
        for r in results:
            if r.memory_key in valid_memories:
                m = valid_memories[r.memory_key]
                filtered.append(self._row_to_search_result(m, r.relevance_score, r.keywords))

        return filtered
```

---

## 5. 辅助方法

### 5.1 结果融合

```python
def _merge_search_results(
    self,
    semantic_results: List[MemorySearchResult],
    keyword_results: List[MemorySearchResult],
    semantic_weight: float = 0.6,
    keyword_weight: float = 0.4
) -> List[MemorySearchResult]:
    """
    融合两种搜索结果
    """
    # 构建 memory_key -> result 映射
    semantic_map = {r.memory_key: r for r in semantic_results}
    keyword_map = {r.memory_key: r for r in keyword_results}

    all_keys = set(semantic_map.keys()) | set(keyword_map.keys())

    merged = []
    for key in all_keys:
        semantic_result = semantic_map.get(key)
        keyword_result = keyword_map.get(key)

        if semantic_result and keyword_result:
            # 两者都有，加权融合
            final_score = (
                semantic_result.relevance_score * semantic_weight +
                keyword_result.relevance_score * keyword_weight
            )
            # 合并关键词
            all_keywords = list(set(
                semantic_result.keywords + keyword_result.keywords
            ))
            result = MemorySearchResult(
                memory_key=key,
                summary=semantic_result.summary,
                content_preview=semantic_result.content_preview,
                memory_type=semantic_result.memory_type,
                relevance_score=final_score,
                created_at=semantic_result.created_at,
                keywords=all_keywords,
                metadata=semantic_result.metadata
            )
        elif semantic_result:
            # 只有语义搜索结果
            result = MemorySearchResult(
                **semantic_result.__dict__,
                relevance_score=semantic_result.relevance_score * 0.7
            )
        else:
            # 只有关键词搜索结果
            result = MemorySearchResult(
                **keyword_result.__dict__,
                relevance_score=keyword_result.relevance_score * 0.7
            )

        merged.append(result)

    return merged
```

### 5.2 结果转换

```python
def _row_to_search_result(
    self,
    model: AgentMemoriesTable,
    relevance_score: float,
    keywords: List[str]
) -> MemorySearchResult:
    """将 ORM 模型转换为搜索结果"""
    return MemorySearchResult(
        memory_key=model.memory_key,
        summary=model.summary,
        content_preview=model.content[:200] if model.content else "",
        memory_type=model.memory_type,
        relevance_score=relevance_score,
        created_at=model.created_at,
        keywords=keywords,
        metadata=model.content_metadata or {}
    )
```

### 5.3 向量化

```python
async def _embed_query(self, query: str) -> List[float]:
    """
    将查询文本转换为向量

    使用配置好的 embedding 服务
    """
    # 从配置获取 embedding 服务
    from config import get_embedding_service

    embedding_service = get_embedding_service()
    embedding = await embedding_service.encode(query)
    return embedding.tolist()
```

---

## 6. 关键词管理

### 6.1 存储记忆时提取关键词

```python
async def store_memory_with_keywords(
    self,
    user_id: int,
    memory_key: str,
    content: str,
    summary: Optional[str] = None,
    memory_type: str = "command_output",
    metadata: Optional[Dict] = None
) -> str:
    """
    存储记忆并自动提取关键词
    """
    # 存储主记忆
    memory_key = await self.store_memory(
        user_id=user_id,
        memory_key=memory_key,
        content=content,
        summary=summary,
        memory_type=memory_type,
        metadata=metadata
    )

    # 提取关键词
    keywords = await self._extract_keywords(content, summary)

    # 存储关键词
    from data_layer.models.tables.memory_keyword_table import AgentMemoryKeywordsTable

    async with await self.db.get_session() as session:
        for kw, weight in keywords.items():
            keyword_entry = AgentMemoryKeywordsTable(
                memory_key=memory_key,
                user_id=user_id,
                keyword=kw.lower(),  # 统一小写
                weight=weight
            )
            session.add(keyword_entry)

        await session.commit()

    return memory_key

async def _extract_keywords(
    self,
    content: str,
    summary: Optional[str]
) -> Dict[str, float]:
    """
    从内容中提取关键词

    简单实现：基于词频和特殊规则
    后续可集成 LLM 提取
    """
    import re
    from collections import Counter

    text = f"{summary or ''} {content}".lower()

    # 提取中文词汇（2-6字）
    chinese_words = re.findall(r'[\u4e00-\u9fff]{2,6}', text)

    # 提取英文单词
    english_words = re.findall(r'[a-zA-Z_]{3,}', text)

    # 统计词频
    word_counts = Counter(chinese_words + english_words)

    # 计算权重（基于词频 + 长度因子）
    keywords = {}
    for word, count in word_counts.most_common(10):
        # 长度因子：适中长度的词权重更高
        length_factor = min(len(word) / 5, 1.0)
        keywords[word] = min(count * 0.1 + length_factor * 0.2, 1.0)

    return keywords
```

---

## 7. 索引优化

### 7.1 数据库迁移脚本

```sql
-- migrations/2026_02_10_add_memory_search_indexes.sql

-- 向量索引（pgvector）
CREATE INDEX IF NOT EXISTS idx_memories_embedding
ON agent_memories USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- 关键词表索引
CREATE INDEX IF NOT EXISTS idx_memory_keywords_lookup
ON agent_memory_keywords(user_id, keyword, memory_key);

-- 复合查询索引
CREATE INDEX IF NOT EXISTS idx_memories_search
ON agent_memories(user_id, memory_type, created_at, is_active)
WHERE is_active = true;

-- 全文搜索索引（可选）
CREATE INDEX IF NOT EXISTS idx_memories_fts
ON agent_memories USING gin(to_tsvector('chinese', summary || ' ' || content));
```

---

## 8. 使用示例

### 8.1 语义搜索

```python
results = await memory_model.search_memories_advanced(
    user_id=123,
    query="数据库配置",
    search_mode="semantic",
    limit=5
)
```

### 8.2 关键词搜索

```python
results = await memory_model.search_memories_advanced(
    user_id=123,
    query="MySQL配置",
    keywords=["MySQL", "数据库", "配置"],
    search_mode="keyword",
    limit=5
)
```

### 8.3 混合搜索（MemRecallAgent 使用）

```python
results = await memory_model.search_memories_advanced(
    user_id=123,
    query="用户之前的数据库配置",
    keywords=["数据库", "配置"],
    search_mode="hybrid",
    memory_types=["config"],
    time_range_days=30,
    min_relevance_score=0.6,
    limit=5
)
```

---

## 9. 错误处理

```python
class MemorySearchError(Exception):
    """搜索错误基类"""
    pass

class EmbeddingError(MemorySearchError):
    """向量化错误"""
    pass

class VectorSearchError(MemorySearchError):
    """向量搜索错误（pgvector 未安装等）"""
    pass
```

---

## 10. 实现检查清单

- [ ] 创建 `AgentMemoryKeywordsTable`
- [ ] 更新 `AgentMemoriesTable` 添加向量字段
- [ ] 实现 `search_memories_advanced` 方法
- [ ] 实现 `_semantic_search` 方法
- [ ] 实现 `_keyword_search` 方法
- [ ] 实现 `_hybrid_search` 方法
- [ ] 实现 `store_memory_with_keywords` 方法
- [ ] 添加数据库索引
- [ ] 编写单元测试
- [ ] 集成到 MemRecallAgent
