"""
Memory Model

Handles all database operations related to agent memories.
"""

from typing import Optional, Dict, Any, List, TYPE_CHECKING, Literal
from datetime import datetime, timedelta
from dataclasses import dataclass
from chainlit.logger import logger
import re
from collections import Counter
import asyncio

from data_layer.models.base_model import BaseModel
from .tables.memory_table import AgentMemoriesTable
from .tables.memory_keyword_table import AgentMemoryKeywordsTable

from sqlalchemy import select, delete, and_, or_, func, desc
from sqlalchemy.sql import func as sql_func


@dataclass
class MemoryInfo:
    id: str
    user_id: int
    memory_key: str
    memory_type: Optional[str]
    summary: Optional[str]
    content: Optional[str]
    content_metadata: Dict[str, Any]
    created_at: datetime
    is_active: bool
    agent_id: Optional[int] = None
    thread_id: Optional[str] = None


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

    def _model_to_info(self, model: AgentMemoriesTable) -> MemoryInfo:
        return MemoryInfo(
            id=str(model.id),
            user_id=model.user_id,
            agent_id=model.agent_id,
            thread_id=str(model.thread_id) if model.thread_id else None,
            memory_key=model.memory_key,
            memory_type=model.memory_type,
            summary=model.summary,
            content=model.content,
            content_metadata=model.content_metadata if model.content_metadata else {},
            created_at=model.created_at,
            is_active=model.is_active
        )

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

    async def store_memory(
        self,
        user_id: int,
        memory_key: str,
        content: str,
        summary: Optional[str] = None,
        memory_type: str = "command_output",
        agent_id: Optional[int] = None,
        thread_id: Optional[str] = None,
        metadata: Optional[Dict] = None
    ) -> str:
        """Store a new memory"""
        async with await self.db.get_session() as session:
            try:
                new_memory = AgentMemoriesTable(
                    user_id=user_id,
                    agent_id=agent_id,
                    thread_id=thread_id,
                    memory_key=memory_key,
                    memory_type=memory_type,
                    summary=summary,
                    content=content,
                    content_metadata=metadata or {}
                )
                session.add(new_memory)
                await session.commit()
                await session.refresh(new_memory)

                # Extract and store keywords
                await self._store_keywords(session, user_id, memory_key, content, summary)

                return str(new_memory.memory_key)
            except Exception as e:
                await session.rollback()
                logger.error(f"Error storing memory: {e}")
                raise

    async def _store_keywords(
        self,
        session,
        user_id: int,
        memory_key: str,
        content: str,
        summary: Optional[str]
    ) -> None:
        """Extract and store keywords for a memory"""
        keywords = self._extract_keywords(content, summary)

        for kw, weight in keywords.items():
            keyword_entry = AgentMemoryKeywordsTable(
                memory_key=memory_key,
                user_id=user_id,
                keyword=kw.lower(),
                weight=weight
            )
            session.add(keyword_entry)

        await session.commit()

    def _extract_keywords(
        self,
        content: str,
        summary: Optional[str]
    ) -> Dict[str, float]:
        """
        从内容中提取关键词

        简单实现：基于词频和特殊规则
        """
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

    async def retrieve_memory(self, memory_key: str) -> Optional[MemoryInfo]:
        """Retrieve memory by key"""
        async with await self.db.get_session() as session:
            stmt = select(AgentMemoriesTable).where(AgentMemoriesTable.memory_key == memory_key)
            result = await session.execute(stmt)
            memory = result.scalar_one_or_none()
            if memory:
                return self._model_to_info(memory)
            return None

    async def search_memories(
        self,
        query: str,
        user_id: Optional[int] = None,
        limit: int = 5
    ) -> List[MemoryInfo]:
        """Simple keyword search for memories"""
        async with await self.db.get_session() as session:
            conditions = [AgentMemoriesTable.is_active == True]
            if user_id:
                conditions.append(AgentMemoriesTable.user_id == user_id)

            search_filter = or_(
                AgentMemoriesTable.summary.ilike(f"%{query}%"),
                AgentMemoriesTable.content.ilike(f"%{query}%")
            )
            conditions.append(search_filter)

            stmt = select(AgentMemoriesTable).where(and_(*conditions)).limit(limit)
            result = await session.execute(stmt)
            memories = result.scalars().all()
            return [self._model_to_info(m) for m in memories]

    # ==========================================================================
    # 高级搜索功能
    # ==========================================================================

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

    async def _semantic_search(
        self,
        user_id: int,
        query: str,
        limit: int,
        min_score: float
    ) -> List[MemorySearchResult]:
        """
        语义搜索 - 使用向量相似度

        注意：需要 PostgreSQL pgvector 扩展
        """
        try:
            # Check if we have pgvector support
            async with await self.db.get_session() as session:
                # Try to use vector search if available
                try:
                    from pgvector.sqlalchemy import Vector
                    has_vector = True
                except ImportError:
                    has_vector = False

                if has_vector:
                    # 使用向量搜索
                    query_vector = await self._embed_query(query)
                    # Note: This requires pgvector extension
                    # For now, fallback to keyword search
                    logger.debug("Vector search requested but may not be available, falling back")

                # Fallback to basic similarity search using ILIKE
                conditions = [
                    AgentMemoriesTable.user_id == user_id,
                    AgentMemoriesTable.is_active == True
                ]

                # Use OR conditions for query matching
                search_filter = or_(
                    AgentMemoriesTable.summary.ilike(f"%{query}%"),
                    AgentMemoriesTable.content.ilike(f"%{query}%")
                )
                conditions.append(search_filter)

                stmt = select(AgentMemoriesTable).where(and_(*conditions)).limit(limit)
                result = await session.execute(stmt)
                memories = result.scalars().all()

                return [
                    self._row_to_search_result(m, 0.7, [])
                    for m in memories
                ]

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

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
        if not keywords:
            return []

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

            # 计算相关性分数
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
        # 并行执行两种搜索
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

        # 应用额外过滤器
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

    async def _apply_filters(
        self,
        results: List[MemorySearchResult],
        user_id: int,
        memory_types: Optional[List[str]],
        time_range_days: Optional[int]
    ) -> List[MemorySearchResult]:
        """对搜索结果应用额外过滤器"""
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

    def _merge_search_results(
        self,
        semantic_results: List[MemorySearchResult],
        keyword_results: List[MemorySearchResult],
        semantic_weight: float = 0.6,
        keyword_weight: float = 0.4
    ) -> List[MemorySearchResult]:
        """融合两种搜索结果"""
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
                    memory_key=semantic_result.memory_key,
                    summary=semantic_result.summary,
                    content_preview=semantic_result.content_preview,
                    memory_type=semantic_result.memory_type,
                    relevance_score=semantic_result.relevance_score * 0.7,
                    created_at=semantic_result.created_at,
                    keywords=semantic_result.keywords,
                    metadata=semantic_result.metadata
                )
            else:
                # 只有关键词搜索结果
                result = MemorySearchResult(
                    memory_key=keyword_result.memory_key,
                    summary=keyword_result.summary,
                    content_preview=keyword_result.content_preview,
                    memory_type=keyword_result.memory_type,
                    relevance_score=keyword_result.relevance_score * 0.7,
                    created_at=keyword_result.created_at,
                    keywords=keyword_result.keywords,
                    metadata=keyword_result.metadata
                )

            merged.append(result)

        return merged

    async def _embed_query(self, query: str) -> List[float]:
        """
        将查询文本转换为向量

        使用配置好的 embedding 服务
        """
        # Placeholder - actual implementation would use an embedding service
        # For now, return an empty list to indicate no embedding available
        logger.debug("Embedding not implemented, returning empty vector")
        return []
