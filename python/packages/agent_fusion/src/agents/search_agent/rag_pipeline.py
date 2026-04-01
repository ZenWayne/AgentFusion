"""
RAGPipeline: Orchestrates vector recall → DashScope rerank → LLM-as-judge dropout.

Operates entirely on the in-memory ContextManager.
Inspirational pickup (context_search-based re-retrieval) is handled by the agent
via its prompt, not here.

Usage (called from the agent's context or bash):
  from agents.search_agent.rag_pipeline import RAGPipeline
  pipeline = RAGPipeline(context_manager)
  result = pipeline.execute(query="...", article_name="...")
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

from tools.rerank import rerank_documents_with_dashscope, DashScopeReranker

if TYPE_CHECKING:
    from agents.search_agent.context_manager import ContextManager, Chunk

logger = logging.getLogger(__name__)


class RAGPipeline:
    """
    Three-phase RAG pipeline:
    1. Vector recall  — Chroma EphemeralClient (in ContextManager)
    2. Rerank         — DashScope gte-rerank-v2
    3. LLM dropout    — LLM-as-judge: drop chunks irrelevant to summary + topic
    """

    def __init__(
        self,
        context_manager: ContextManager,
        reranker_model: str = "gte-rerank-v2",
        top_k: int = 10,
        recall_n: int = 20,
        dropout_threshold: float = 0.5,
    ) -> None:
        self.cm = context_manager
        self.reranker = DashScopeReranker(model=reranker_model, top_n=top_k)
        self.top_k = top_k
        self.recall_n = recall_n
        self.dropout_threshold = dropout_threshold

    # ------------------------------------------------------------------
    # Phase 1: Vector recall
    # ------------------------------------------------------------------

    def recall(self, query: str) -> list[dict]:
        """Semantic recall from Chroma EphemeralClient."""
        results = self.cm.vector_recall(query, n_results=self.recall_n)
        logger.info(f"Recalled {len(results)} chunks for query: {query!r}")
        return results

    # ------------------------------------------------------------------
    # Phase 2: DashScope rerank
    # ------------------------------------------------------------------

    def rerank(self, query: str, candidates: list[dict]) -> list[dict]:
        """
        Rerank candidates with DashScope gte-rerank-v2.
        Returns list of {chunk_id, content, metadata, score} sorted by score desc.
        """
        if not candidates:
            return []

        documents = [c["content"] for c in candidates]
        indices, scores = rerank_documents_with_dashscope(
            query=query,
            documents=documents,
            top_n=min(self.top_k, len(candidates)),
            model=self.reranker.model,
        )

        reranked = []
        for rank, (idx, score) in enumerate(zip(indices, scores)):
            if 0 <= idx < len(candidates):
                entry = dict(candidates[idx])
                entry["score"] = score
                entry["rank"] = rank + 1
                reranked.append(entry)

        logger.info(f"Reranked to {len(reranked)} chunks, top score: {scores[0] if scores else 'N/A'}")
        return reranked

    # ------------------------------------------------------------------
    # Phase 3: LLM-as-judge dropout
    # ------------------------------------------------------------------

    def llm_dropout(
        self,
        reranked: list[dict],
        summary: str,
        topic: str,
        model_client=None,
    ) -> tuple[list[dict], list[dict]]:
        """
        LLM-as-judge: evaluate each reranked chunk for relevance to
        the article summary and exploration topic.

        Returns (kept_chunks, dropped_chunks).

        If model_client is None, falls back to keeping all chunks
        (no dropout applied).
        """
        if model_client is None:
            logger.warning("No model_client provided for LLM dropout — keeping all chunks.")
            return reranked, []

        kept: list[dict] = []
        dropped: list[dict] = []

        judge_prompt_template = (
            "You are evaluating whether a text chunk is relevant to a research task.\n\n"
            "## Research Topic\n{topic}\n\n"
            "## Article Summary\n{summary}\n\n"
            "## Chunk to Evaluate\n{content}\n\n"
            "Is this chunk relevant to the research topic and consistent with the summary?\n"
            "Respond with exactly one word: RELEVANT or IRRELEVANT, followed by a brief reason."
        )

        for chunk in reranked:
            prompt = judge_prompt_template.format(
                topic=topic,
                summary=summary[:1000],  # truncate to avoid context overflow
                content=chunk["content"][:500],
            )
            try:
                # Use synchronous call pattern compatible with existing model clients
                import asyncio

                async def _judge(p: str):
                    from autogen_core.models import UserMessage
                    response = await model_client.create(
                        [UserMessage(content=p, source="user")]
                    )
                    return response.content

                verdict = asyncio.get_event_loop().run_until_complete(_judge(prompt))
                verdict_upper = str(verdict).strip().upper()
                chunk["llm_verdict"] = str(verdict).strip()

                if "IRRELEVANT" in verdict_upper:
                    dropped.append(chunk)
                else:
                    kept.append(chunk)

            except Exception as e:
                logger.warning(f"LLM judge failed for chunk {chunk.get('chunk_id')}: {e}")
                kept.append(chunk)  # Keep on error

        logger.info(f"LLM dropout: kept={len(kept)}, dropped={len(dropped)}")
        return kept, dropped

    # ------------------------------------------------------------------
    # Full pipeline
    # ------------------------------------------------------------------

    def execute(
        self,
        query: str,
        article_name: str,
        topic: str = "",
        model_client=None,
    ) -> dict:
        """
        Full pipeline: recall → rerank → LLM dropout.

        Returns:
          {
            "kept_chunks": [...],      # chunks to use in final context
            "dropped_chunks": [...],   # chunks dropped by LLM judge
            "query": str,
          }
        """
        summary = self.cm.get_summary(article_name) or ""
        if not topic:
            topic = query

        # 1. Recall
        candidates = self.recall(query)
        if not candidates:
            return {"kept_chunks": [], "dropped_chunks": [], "query": query}

        # 2. Rerank
        reranked = self.rerank(query, candidates)

        # 3. LLM dropout (optional)
        kept, dropped = self.llm_dropout(reranked, summary, topic, model_client)

        return {
            "kept_chunks": kept,
            "dropped_chunks": dropped,
            "query": query,
        }
