"""
GraphRAG config builder: maps AgentFusion model labels to GraphRagConfig.

Uses the same model registry (schemas/model_info.py) as the rest of the system.
"""

from __future__ import annotations

import os

from dotenv import load_dotenv
from graphrag.config.models.graph_rag_config import GraphRagConfig
from graphrag_chunking.chunking_config import ChunkingConfig
from graphrag_llm.config.model_config import LLMProviderType, ModelConfig
from graphrag_storage.storage_config import StorageConfig
from graphrag_vectors.vector_store_config import VectorStoreConfig

from schemas.model_info import model_list
from tools.dashscope_embedding import PROVIDER_TYPE as _DASHSCOPE_PROVIDER


def _resolve_model(label: str) -> dict:
    """Lookup AgentFusion model_list entry by label string."""
    for m in model_list:
        if m["label"] == label or m["label"].value == label:
            return m
    raise KeyError(f"Model label not found: {label}")


def _build_embedding_config(emb: dict, api_key: str) -> ModelConfig:
    """Build ModelConfig for an embedding model, choosing the right provider type."""
    litellm_provider = emb.get("litellm_provider", "openai")
    if litellm_provider == "dashscope":
        # Use native DashScope SDK via custom registered provider
        return ModelConfig(
            type=_DASHSCOPE_PROVIDER,
            model_provider="dashscope",
            model=emb["model_name"],
            api_key=api_key,
            call_args={},
        )
    # OpenAI-compatible endpoint
    return ModelConfig(
        type=LLMProviderType.LiteLLM,
        model_provider="openai",
        model=emb["model_name"],
        api_base=emb.get("base_url"),
        api_key=api_key,
        call_args={"encoding_format": "float"},
    )


def build_graphrag_config(
    completion_model_label: str,
    embedding_model_label: str,
    output_dir: str = "graphrag_output",
) -> GraphRagConfig:
    """Build a GraphRagConfig from AgentFusion model labels.

    Args:
        completion_model_label: e.g. "deepseek-chat_DeepSeek"
        embedding_model_label: e.g. "text-embedding-v4_DashScope"
        output_dir: directory for Parquet + LanceDB output
    """
    load_dotenv()

    # Register custom DashScope embedding provider if needed
    from tools.dashscope_embedding import register as _register_dashscope
    _register_dashscope()

    comp = _resolve_model(completion_model_label)
    emb = _resolve_model(embedding_model_label)

    comp_api_key = os.getenv(comp["api_key_type"], "")
    emb_api_key = os.getenv(emb["api_key_type"], "")

    return GraphRagConfig(
        completion_models={
            "default_completion_model": ModelConfig(
                type=LLMProviderType.LiteLLM,
                model_provider="openai",
                model=comp['model_name'],
                api_base=comp["base_url"],
                api_key=comp_api_key,
                call_args={"temperature": 0.0},
            ),
        },
        embedding_models={
            "default_embedding_model": _build_embedding_config(emb, emb_api_key),
        },
        output_storage=StorageConfig(type="file", base_dir=output_dir),
        vector_store=VectorStoreConfig(type="lancedb", db_uri=f"{output_dir}/vectors"),
        chunking=ChunkingConfig(size=600, overlap=100),
        concurrent_requests=50,
    )
