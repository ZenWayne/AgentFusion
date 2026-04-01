"""
ContextManager: In-memory context data structure for the search agent RAG pipeline.

All chunks, summaries, and metadata live here until the final output phase.
Uses Chroma EphemeralClient for in-process vector indexing.
"""

from __future__ import annotations

import re
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from datetime import datetime


@dataclass
class Chunk:
    chunk_id: str           # "{article_name}/{section_name}"
    article_name: str
    section_name: str
    content: str
    metadata: dict = field(default_factory=dict)  # source_url, page_num, etc.


@dataclass
class ArticleContext:
    article_name: str
    source_url: str
    full_markdown: str              # Full OCR-extracted markdown
    chunks: list[Chunk] = field(default_factory=list)
    summary: str | None = None      # Task-relevance summary
    rag_results: list[Chunk] | None = None  # Last RAG recall results


class ContextManager:
    """
    In-process Context manager for the search agent RAG pipeline.

    All slice_to_chunk and context_search operations work on this in-memory
    structure. Only flush_to_disk() writes to the filesystem.
    """

    def __init__(self) -> None:
        self.articles: dict[str, ArticleContext] = {}
        self._chroma_client = None
        self._collection = None
        self._init_chroma()

    def _init_chroma(self) -> None:
        try:
            import chromadb
            self._chroma_client = chromadb.EphemeralClient()
            self._collection = self._chroma_client.get_or_create_collection(
                name="search_agent_chunks",
                metadata={"hnsw:space": "cosine"},
            )
        except ImportError:
            self._chroma_client = None
            self._collection = None

    # ------------------------------------------------------------------
    # Article management
    # ------------------------------------------------------------------

    def add_article(self, name: str, url: str, markdown: str) -> ArticleContext:
        """Register an article with its full OCR markdown content."""
        ctx = ArticleContext(
            article_name=name,
            source_url=url,
            full_markdown=markdown,
        )
        self.articles[name] = ctx
        return ctx

    def get_article(self, name: str) -> ArticleContext | None:
        return self.articles.get(name)

    # ------------------------------------------------------------------
    # Chunk management (in-memory + Chroma vector index)
    # ------------------------------------------------------------------

    def add_chunks(self, article_name: str, chunks: list[Chunk]) -> None:
        """
        Store chunks in memory and upsert into Chroma EphemeralClient.
        If article doesn't exist yet, creates a placeholder.
        """
        if article_name not in self.articles:
            self.articles[article_name] = ArticleContext(
                article_name=article_name,
                source_url="",
                full_markdown="",
            )
        self.articles[article_name].chunks = chunks

        if self._collection is None:
            return  # chromadb not available, skip vector indexing

        if not chunks:
            return

        ids = [c.chunk_id for c in chunks]
        documents = [c.content for c in chunks]
        metadatas = [
            {
                "article_name": c.article_name,
                "section_name": c.section_name,
                **{k: str(v) for k, v in c.metadata.items()},
            }
            for c in chunks
        ]

        self._collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas,
        )

    def get_chunks(self, article_name: str) -> list[Chunk]:
        ctx = self.articles.get(article_name)
        return ctx.chunks if ctx else []

    def all_chunks(self) -> list[Chunk]:
        return [c for ctx in self.articles.values() for c in ctx.chunks]

    # ------------------------------------------------------------------
    # Vector recall (Chroma EphemeralClient)
    # ------------------------------------------------------------------

    def vector_recall(self, query: str, n_results: int = 20) -> list[dict]:
        """
        Semantic vector recall from Chroma EphemeralClient.

        Returns list of dicts: {chunk_id, content, distance, metadata}
        Falls back to full-text scan if Chroma is unavailable.
        """
        if self._collection is not None:
            total = self._collection.count()
            if total == 0:
                return []
            actual_n = min(n_results, total)
            results = self._collection.query(
                query_texts=[query],
                n_results=actual_n,
            )
            if not results["documents"] or not results["documents"][0]:
                return []
            docs = results["documents"][0]
            distances = results["distances"][0] if results.get("distances") else [0.0] * len(docs)
            ids = results["ids"][0]
            metas = results["metadatas"][0] if results.get("metadatas") else [{}] * len(docs)
            return [
                {
                    "chunk_id": ids[i],
                    "content": docs[i],
                    "distance": distances[i],
                    "metadata": metas[i],
                }
                for i in range(len(docs))
            ]

        # Fallback: return all chunks (no ranking)
        all_c = self.all_chunks()
        return [
            {
                "chunk_id": c.chunk_id,
                "content": c.content,
                "distance": 0.0,
                "metadata": c.metadata,
            }
            for c in all_c[:n_results]
        ]

    # ------------------------------------------------------------------
    # Regex search (for ContextSearchTool)
    # ------------------------------------------------------------------

    def search(
        self,
        pattern: str,
        scope: str = "all",
        max_results: int = 50,
    ) -> list[dict]:
        """
        Regex multi-keyword search across in-memory chunks and summaries.

        pattern: regex string, e.g. '.*word_a|.*word_b'
        scope: 'all', 'chunks', 'summaries'
        Returns list of {source, chunk_id, line_number, matched_line}
        """
        try:
            compiled = re.compile(pattern, re.MULTILINE | re.IGNORECASE)
        except re.error as e:
            return [{"error": f"Invalid regex pattern: {e}"}]

        results: list[dict] = []

        if scope in ("all", "chunks"):
            for chunk in self.all_chunks():
                for lineno, line in enumerate(chunk.content.splitlines(), 1):
                    if compiled.search(line):
                        results.append({
                            "source": "chunk",
                            "chunk_id": chunk.chunk_id,
                            "article_name": chunk.article_name,
                            "section_name": chunk.section_name,
                            "line_number": lineno,
                            "matched_line": line.strip(),
                        })
                        if len(results) >= max_results:
                            return results

        if scope in ("all", "summaries"):
            for name, ctx in self.articles.items():
                if not ctx.summary:
                    continue
                for lineno, line in enumerate(ctx.summary.splitlines(), 1):
                    if compiled.search(line):
                        results.append({
                            "source": "summary",
                            "chunk_id": f"{name}/__summary__",
                            "article_name": name,
                            "section_name": "__summary__",
                            "line_number": lineno,
                            "matched_line": line.strip(),
                        })
                        if len(results) >= max_results:
                            return results

        return results

    # ------------------------------------------------------------------
    # Summary management
    # ------------------------------------------------------------------

    def set_summary(self, article_name: str, summary: str) -> None:
        if article_name in self.articles:
            self.articles[article_name].summary = summary
        else:
            self.articles[article_name] = ArticleContext(
                article_name=article_name,
                source_url="",
                full_markdown="",
                summary=summary,
            )

    def get_summary(self, article_name: str) -> str | None:
        ctx = self.articles.get(article_name)
        return ctx.summary if ctx else None

    def set_rag_results(self, article_name: str, chunks: list[Chunk]) -> None:
        if article_name in self.articles:
            self.articles[article_name].rag_results = chunks

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def get_global_context(self) -> dict:
        """Return {article_name: {url, summary_excerpt}} mapping."""
        return {
            name: {
                "url": ctx.source_url,
                "summary_excerpt": (ctx.summary or "")[:300],
                "chunk_count": len(ctx.chunks),
            }
            for name, ctx in self.articles.items()
        }

    # ------------------------------------------------------------------
    # Final output (flush to disk)
    # ------------------------------------------------------------------

    def flush_to_disk(self, output_dir: str = "search_agent/output") -> list[str]:
        """
        Write all context to disk. Called only in the final phase.

        Writes:
          - output/context/<article_name>_context.md  (RAG results + summary)
          - output/<article_name>_summary              (OCR markdown)

        Returns list of written file paths.
        """
        written: list[str] = []
        base = Path(output_dir)
        context_dir = base / "context"
        context_dir.mkdir(parents=True, exist_ok=True)

        for name, ctx in self.articles.items():
            safe_name = _safe_filename(name)

            # OCR result / full article
            summary_path = base / f"{safe_name}_summary"
            summary_path.write_text(ctx.full_markdown or "", encoding="utf-8")
            written.append(str(summary_path))

            # Final context: summary + RAG chunks
            context_lines: list[str] = [
                f"# {name}\n",
                f"**Source**: {ctx.source_url}\n",
                f"**Generated**: {datetime.now().isoformat()}\n\n",
            ]
            if ctx.summary:
                context_lines += ["## Summary\n\n", ctx.summary, "\n\n"]
            if ctx.rag_results:
                context_lines.append("## Key Evidence Chunks\n\n")
                for chunk in ctx.rag_results:
                    context_lines += [
                        f"### {chunk.section_name}\n\n",
                        chunk.content,
                        "\n\n---\n\n",
                    ]
            context_path = context_dir / f"{safe_name}_context.md"
            context_path.write_text("".join(context_lines), encoding="utf-8")
            written.append(str(context_path))

        return written


def _safe_filename(name: str) -> str:
    """Convert article name to a filesystem-safe filename."""
    return re.sub(r"[^\w\-_.]", "_", name)[:100]
