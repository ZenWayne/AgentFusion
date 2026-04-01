"""
DashScope native embedding using dashscope SDK.

Implements graphrag_llm LLMEmbedding for models not available
in DashScope's OpenAI-compatible endpoint (e.g. qwen3-vl-embedding).
"""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING, Any, Unpack

import dashscope
from openai.types import Embedding as OpenAIEmbedding
from openai.types.create_embedding_response import Usage

from graphrag_llm.embedding.embedding import LLMEmbedding
from graphrag_llm.types import LLMEmbeddingResponse

if TYPE_CHECKING:
    from graphrag_cache import Cache, CacheKeyCreator
    from graphrag_llm.config import ModelConfig
    from graphrag_llm.metrics import MetricsProcessor, MetricsStore
    from graphrag_llm.rate_limit import RateLimiter
    from graphrag_llm.retry import Retry
    from graphrag_llm.tokenizer import Tokenizer
    from graphrag_llm.types import LLMEmbeddingArgs

PROVIDER_TYPE = "dashscope_native"


class DashScopeEmbedding(LLMEmbedding):
    """Embedding via DashScope SDK for models not in OpenAI-compat endpoint.

    Uses MultiModalEmbedding API (one call per text) to support models like
    qwen3-vl-embedding that aren't available on the OpenAI-compatible endpoint.
    """

    def __init__(
        self,
        *,
        model_id: str,
        model_config: "ModelConfig",
        tokenizer: "Tokenizer",
        metrics_store: "MetricsStore",
        metrics_processor: "MetricsProcessor | None" = None,
        rate_limiter: "RateLimiter | None" = None,
        retrier: "Retry | None" = None,
        cache: "Cache | None" = None,
        cache_key_creator: "CacheKeyCreator",
        **kwargs: Any,
    ):
        self._model_name = model_config.model
        self._api_key = model_config.api_key or os.getenv("DASHSCOPE_API_KEY", "")
        self._tokenizer = tokenizer
        self._metrics_store = metrics_store

    def _call_one(self, text: str) -> list[float]:
        resp = dashscope.MultiModalEmbedding.call(
            model=self._model_name,
            input=[dashscope.MultiModalEmbeddingItemText(text=text, factor=1.0)],
            api_key=self._api_key,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"DashScope embedding failed: {resp.status_code} {resp.message}"
            )
        return resp.output["embeddings"][0]["embedding"]

    def embedding(self, /, **kwargs: Unpack["LLMEmbeddingArgs"]) -> LLMEmbeddingResponse:
        input_texts: list[str] = kwargs.get("input", [])
        embeddings = [self._call_one(t) for t in input_texts]
        return self._build_response(embeddings)

    async def embedding_async(self, /, **kwargs: Unpack["LLMEmbeddingArgs"]) -> LLMEmbeddingResponse:
        input_texts: list[str] = kwargs.get("input", [])
        loop = asyncio.get_event_loop()
        embeddings = await asyncio.gather(
            *[loop.run_in_executor(None, self._call_one, t) for t in input_texts]
        )
        return self._build_response(list(embeddings))

    def _build_response(self, embeddings: list[list[float]]) -> LLMEmbeddingResponse:
        data = [
            OpenAIEmbedding(object="embedding", embedding=emb, index=i)
            for i, emb in enumerate(embeddings)
        ]
        return LLMEmbeddingResponse(
            object="list",
            data=data,
            model=self._model_name,
            usage=Usage(prompt_tokens=0, total_tokens=0),
        )

    @property
    def metrics_store(self) -> "MetricsStore":
        return self._metrics_store

    @property
    def tokenizer(self) -> "Tokenizer":
        return self._tokenizer


def register() -> None:
    """Register DashScopeEmbedding into graphrag_llm embedding factory."""
    from graphrag_llm.embedding.embedding_factory import (
        embedding_factory,
        register_embedding,
    )

    if PROVIDER_TYPE not in embedding_factory:
        register_embedding(
            embedding_type=PROVIDER_TYPE,
            embedding_initializer=DashScopeEmbedding,
            scope="singleton",
        )
