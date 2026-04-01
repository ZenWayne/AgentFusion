"""
search_agent: AI Science Search Agent module.

Core components:
- ContextManager: In-memory context store (chunks + summaries + vector index)
- RAGPipeline: vector recall → rerank → LLM-as-judge dropout
- HallucinationValidator: claim verification loop
- scholar.py: Google Scholar scraping via Playwright
- ocr.py: DashScope multimodal OCR (PDF → markdown)
- todo_tracker.py: ToDoList.md progress management
"""

from agents.search_agent.context_manager import ContextManager, Chunk, ArticleContext
from agents.search_agent.rag_pipeline import RAGPipeline
from agents.search_agent.validator import HallucinationValidator
__all__ = [
    "ContextManager",
    "Chunk",
    "ArticleContext",
    "RAGPipeline",
    "HallucinationValidator",
]
