"""
HallucinationValidator: Validates that every claim in an article summary
has evidence in the recalled chunks.

Validation loop:
  1. Extract claims from summary via LLM
  2. For each claim: search in kept_chunks, then context_search(regex)
  3. Unsourced claims → re-OCR with focused question → re-RAG
  4. Repeat up to max_iterations until all claims are sourced

Called by the agent's system prompt logic; can also be invoked via bash.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from agents.search_agent.context_manager import ContextManager
    from agents.search_agent.rag_pipeline import RAGPipeline

logger = logging.getLogger(__name__)


class HallucinationValidator:
    def __init__(
        self,
        context_manager: ContextManager,
        rag_pipeline: RAGPipeline,
        model_client: Any | None = None,
    ) -> None:
        self.cm = context_manager
        self.rag = rag_pipeline
        self.model_client = model_client

    # ------------------------------------------------------------------

    def extract_claims(self, summary: str) -> list[str]:
        """
        Use LLM to extract verifiable factual claims from the summary.
        Returns a list of claim strings.

        Falls back to sentence-level splitting if no model_client.
        """
        if self.model_client is None:
            # Simple fallback: split on sentence boundaries
            sentences = re.split(r"(?<=[.!?])\s+", summary.strip())
            return [s.strip() for s in sentences if len(s.strip()) > 20]

        prompt = (
            "Extract the key factual claims from this academic paper summary. "
            "Output each claim on a new line prefixed with '- '.\n\n"
            f"Summary:\n{summary}"
        )
        try:
            import asyncio
            from autogen_core.models import UserMessage

            async def _extract(p: str) -> str:
                response = await self.model_client.create(
                    [UserMessage(content=p, source="user")]
                )
                return response.content

            raw = asyncio.get_event_loop().run_until_complete(_extract(prompt))
            claims = [
                line.lstrip("- ").strip()
                for line in raw.splitlines()
                if line.strip().startswith("-") and len(line.strip()) > 5
            ]
            return claims if claims else self.extract_claims.__wrapped__(self, summary)

        except Exception as e:
            logger.warning(f"LLM claim extraction failed: {e}")
            return re.split(r"(?<=[.!?])\s+", summary.strip())

    # ------------------------------------------------------------------

    def verify_claim(self, claim: str, chunks: list[dict]) -> dict:
        """
        Verify a single claim:
        1. Search in provided chunks (exact/keyword match)
        2. If not found: context_search(regex) in ContextManager
        3. Return {claim, status, evidence}
        """
        # Step 1: search in provided chunks
        keywords = _extract_keywords(claim)
        for chunk in chunks:
            content = chunk.get("content", "")
            if _any_keyword_in_text(keywords, content):
                return {
                    "claim": claim,
                    "status": "sourced",
                    "evidence": content[:300],
                    "source": chunk.get("chunk_id", ""),
                }

        # Step 2: regex search in ContextManager
        pattern = "|".join(f".*{re.escape(kw)}" for kw in keywords[:3])
        if pattern:
            matches = self.cm.search(pattern, scope="chunks", max_results=5)
            if matches and "error" not in matches[0]:
                return {
                    "claim": claim,
                    "status": "sourced",
                    "evidence": matches[0].get("matched_line", ""),
                    "source": matches[0].get("chunk_id", ""),
                    "via": "context_search",
                }

        return {"claim": claim, "status": "unsourced", "evidence": None, "source": None}

    # ------------------------------------------------------------------

    def validate_and_loop(
        self,
        article_name: str,
        topic: str,
        kept_chunks: list[dict],
        max_iterations: int = 3,
    ) -> dict:
        """
        Full validation loop.

        Returns {
          all_sourced: bool,
          claims: [{claim, status, evidence, source}],
          iterations: int
        }
        """
        summary = self.cm.get_summary(article_name) or ""
        if not summary:
            return {"all_sourced": True, "claims": [], "iterations": 0,
                    "note": "No summary to validate"}

        claims = self.extract_claims(summary)
        current_chunks = list(kept_chunks)
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            results = [self.verify_claim(c, current_chunks) for c in claims]
            unsourced = [r for r in results if r["status"] == "unsourced"]

            logger.info(
                f"Iteration {iteration}: {len(claims) - len(unsourced)}/{len(claims)} claims sourced."
            )

            if not unsourced:
                return {"all_sourced": True, "claims": results, "iterations": iteration}

            if iteration >= max_iterations:
                break

            # Re-run RAG with unsourced claim as focused query
            focused_query = "; ".join(r["claim"] for r in unsourced[:3])
            logger.info(f"Re-running RAG for unsourced claims: {focused_query!r}")
            rag_result = self.rag.execute(
                query=focused_query,
                article_name=article_name,
                topic=topic,
                model_client=self.model_client,
            )
            new_chunks = rag_result.get("kept_chunks", [])
            # Merge without duplicates
            existing_ids = {c.get("chunk_id") for c in current_chunks}
            current_chunks.extend(c for c in new_chunks if c.get("chunk_id") not in existing_ids)

        # Final pass
        final_results = [self.verify_claim(c, current_chunks) for c in claims]
        all_sourced = all(r["status"] == "sourced" for r in final_results)
        return {
            "all_sourced": all_sourced,
            "claims": final_results,
            "iterations": iteration,
        }


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _extract_keywords(text: str, max_keywords: int = 5) -> list[str]:
    """Extract significant keywords from a claim for matching."""
    # Remove stop words and short tokens
    stop = {
        "the", "a", "an", "and", "or", "in", "on", "at", "to", "for",
        "of", "is", "are", "was", "were", "that", "this", "with", "by",
        "be", "has", "have", "had", "it", "its", "as", "from", "which",
    }
    tokens = re.findall(r"\b\w{4,}\b", text.lower())
    keywords = [t for t in tokens if t not in stop]
    # Prefer longer (more specific) keywords
    keywords.sort(key=len, reverse=True)
    return keywords[:max_keywords]


def _any_keyword_in_text(keywords: list[str], text: str) -> bool:
    text_lower = text.lower()
    return any(kw in text_lower for kw in keywords)
