"""
ArticleStore: Stores full OCR Markdown documents for GraphRAG indexing.

Replaces ContextManager's chunk-based storage. Whole documents are passed
to GraphRAG's build_index(), which handles chunking internally.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pandas as pd


@dataclass
class ArticleEntry:
    article_name: str
    source_url: str
    full_markdown: str


class ArticleStore:
    """Stores complete Markdown documents, exports DataFrame for GraphRAG."""

    def __init__(self) -> None:
        self.articles: dict[str, ArticleEntry] = {}

    def add_article(self, name: str, url: str, markdown: str) -> None:
        self.articles[name] = ArticleEntry(name, url, markdown)

    def get_article(self, name: str) -> ArticleEntry | None:
        return self.articles.get(name)

    def list_articles(self) -> list[str]:
        return list(self.articles.keys())

    def to_dataframe(self) -> pd.DataFrame:
        """Export as DataFrame consumable by graphrag.api.build_index()."""
        rows = []
        for entry in self.articles.values():
            rows.append({
                "id": entry.article_name,
                "text": f"[Article: {entry.article_name} | URL: {entry.source_url}]\n{entry.full_markdown}",
                "title": entry.article_name,
            })
        return pd.DataFrame(rows)

    def get_metadata_map(self) -> dict[str, dict[str, str]]:
        """Return article_name -> {source_url} mapping for provenance."""
        return {
            name: {"source_url": entry.source_url}
            for name, entry in self.articles.items()
        }

    # ---- Persistence (shared across agents via filesystem) ----

    def save_metadata(self, output_dir: str) -> None:
        """Write metadata JSON so other agents can resolve document_id -> source_url."""
        metadata = {
            "articles": {
                name: {"source_url": entry.source_url}
                for name, entry in self.articles.items()
            },
            "index_built_at": datetime.now().isoformat(),
            "document_count": len(self.articles),
        }
        path = Path(output_dir) / "article_metadata.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    @staticmethod
    def load_metadata(output_dir: str) -> dict[str, dict[str, str]]:
        """Load metadata from disk (used by graphrag_trace in non-explorer agents)."""
        path = Path(output_dir) / "article_metadata.json"
        if not path.exists():
            return {}
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("articles", {})
