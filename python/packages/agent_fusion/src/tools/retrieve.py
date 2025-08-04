import re
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Union
from pathlib import Path
from tools.utils.base import lazy_tool_loader


class BaseRetrieveTool(ABC):
    """Base class for retrieve tools that can be extended for filesystem or vector database"""
    
    @abstractmethod
    def retrieve(self, query: str, **kwargs) -> str:
        """Abstract method for retrieving content based on query"""
        pass


class FileSystemRetrieveTool(BaseRetrieveTool):
    """Tool for retrieving content from filesystem using regex patterns"""
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path).resolve()
    
    def retrieve(self, pattern: str, file_path: str = None, recursive: bool = True) -> str:
        """
        Retrieve file content based on regex pattern from filesystem
        
        Args:
            pattern: Regex pattern to match content
            file_path: Specific file path to search (optional)
            recursive: Whether to search recursively in directories
            
        Returns:
            Matched content as string
        """
        if file_path:
            return self._search_in_file(pattern, file_path)
        else:
            return self._search_in_directory(pattern, recursive)
    
    def _search_in_file(self, pattern: str, file_path: str) -> str:
        """Search for pattern in a specific file"""
        full_path = self.base_path / file_path
        if not full_path.exists() or not full_path.is_file():
            return f"File not found: {file_path}"
        
        try:
            with open(full_path, 'r', encoding='utf-8') as f:
                content = f.read()
                matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
                if matches:
                    return f"Found {len(matches)} matches in {file_path}:\n" + "\n---\n".join(matches)
                else:
                    return f"No matches found for pattern '{pattern}' in {file_path}"
        except Exception as e:
            return f"Error reading file {file_path}: {str(e)}"
    
    def _search_in_directory(self, pattern: str, recursive: bool) -> str:
        """Search for pattern in directory"""
        results = []
        search_pattern = "**/*" if recursive else "*"
        
        for file_path in self.base_path.glob(search_pattern):
            if file_path.is_file() and self._is_text_file(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                        matches = re.findall(pattern, content, re.MULTILINE | re.DOTALL)
                        if matches:
                            rel_path = file_path.relative_to(self.base_path)
                            results.append(f"File: {rel_path}\nMatches: {len(matches)}\n" + "\n---\n".join(matches))
                except Exception:
                    continue  # Skip files that can't be read
        
        if results:
            return "\n\n=== FILE SEPARATOR ===\n\n".join(results)
        else:
            return f"No matches found for pattern '{pattern}' in directory tree"
    
    def _is_text_file(self, file_path: Path) -> bool:
        """Check if file is likely a text file"""
        text_extensions = {'.txt', '.py', '.js', '.html', '.css', '.json', '.xml', '.md', '.yml', '.yaml', '.ini', '.cfg', '.conf'}
        return file_path.suffix.lower() in text_extensions


class VectorDatabaseRetrieveTool(BaseRetrieveTool):
    """Tool for retrieving content from vector database (Chroma)"""
    
    def __init__(self, collection_name: str = "default"):
        self.collection_name = collection_name
        self._client = None
        self._collection = None
    
    def _get_client(self):
        """Lazy initialization of Chroma client"""
        if self._client is None:
            try:
                import chromadb
                self._client = chromadb.Client()
                self._collection = self._client.get_or_create_collection(self.collection_name)
            except ImportError:
                raise ImportError("ChromaDB not installed. Please install with: pip install chromadb")
        return self._client, self._collection
    
    def retrieve(self, query_text: str, n_results: int = 5, **kwargs) -> str:
        """
        Retrieve text based on query text from vector database
        
        Args:
            query_text: Query text for semantic search
            n_results: Number of results to return
            
        Returns:
            Retrieved content as string
        """
        try:
            client, collection = self._get_client()
            
            results = collection.query(
                query_texts=[query_text],
                n_results=n_results
            )
            
            if results['documents'] and results['documents'][0]:
                documents = results['documents'][0]
                distances = results['distances'][0] if results['distances'] else [0] * len(documents)
                
                formatted_results = []
                for i, (doc, distance) in enumerate(zip(documents, distances)):
                    formatted_results.append(f"Result {i+1} (similarity: {1-distance:.3f}):\n{doc}")
                
                return "\n\n---\n\n".join(formatted_results)
            else:
                return f"No results found for query: '{query_text}'"
                
        except Exception as e:
            return f"Error querying vector database: {str(e)}"


# Tool function implementations
def retrieve_from_filesystem(pattern: str, file_path: str = None, base_path: str = ".", recursive: bool = True) -> str:
    """Retrieve file content based on regex pattern from filesystem"""
    from .utils.validation import ToolValidator
    
    return ToolValidator.safe_execute(_retrieve_from_filesystem_impl, pattern, file_path, base_path, recursive)


def retrieve_from_vector_db(query_text: str, collection_name: str = "default", n_results: int = 5) -> str:
    """Retrieve text based on query text from vector database (Chroma)"""
    from .utils.validation import ToolValidator
    
    return ToolValidator.safe_execute(_retrieve_from_vector_db_impl, query_text, collection_name, n_results)


def _retrieve_from_filesystem_impl(pattern: str, file_path: str = None, base_path: str = ".", recursive: bool = True) -> str:
    """Internal implementation with validation"""
    from .utils.validation import ToolValidator
    
    # Validate inputs
    ToolValidator.validate_regex_pattern(pattern)
    if file_path:
        ToolValidator.validate_file_path(file_path, base_path, must_exist=True, must_be_file=True)
    
    tool = FileSystemRetrieveTool(base_path)
    return tool.retrieve(pattern, file_path, recursive)


def _retrieve_from_vector_db_impl(query_text: str, collection_name: str = "default", n_results: int = 5) -> str:
    """Internal implementation with validation"""
    from .utils.validation import ToolValidator
    
    # Validate inputs
    if not query_text or not isinstance(query_text, str):
        raise ValueError("Query text must be a non-empty string")
    
    ToolValidator.validate_collection_name(collection_name)
    
    if not isinstance(n_results, int) or n_results < 1 or n_results > 100:
        raise ValueError("n_results must be an integer between 1 and 100")
    
    tool = VectorDatabaseRetrieveTool(collection_name)
    return tool.retrieve(query_text, n_results)


# Tool function lambdas for lazy loading
retrieve_filesystem_tool = lambda: lazy_tool_loader(retrieve_from_filesystem)()
retrieve_vector_db_tool = lambda: lazy_tool_loader(retrieve_from_vector_db)()