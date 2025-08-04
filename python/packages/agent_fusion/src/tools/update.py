import re
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Union
from pathlib import Path
from .utils.base import lazy_tool_loader


class BaseUpdateTool(ABC):
    """Base class for update tools that can be extended for filesystem or vector database"""
    
    @abstractmethod
    def update(self, identifier: str, new_content: str, **kwargs) -> str:
        """Abstract method for updating content"""
        pass


class FileSystemUpdateTool(BaseUpdateTool):
    """Tool for updating content in filesystem using regex pattern matching"""
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path).resolve()
    
    def update(self, file_path: str, pattern: str, replacement: str, backup: bool = True) -> str:
        """
        Update file content by replacing regex pattern matches with new content
        
        Args:
            file_path: Path to the file to update
            pattern: Regex pattern to match content to replace
            replacement: New content to replace matches with
            backup: Whether to create a backup file before updating
            
        Returns:
            Status message indicating success or failure
        """
        full_path = self.base_path / file_path
        
        if not full_path.exists() or not full_path.is_file():
            return f"File not found: {file_path}"
        
        try:
            # Read original content
            with open(full_path, 'r', encoding='utf-8') as f:
                original_content = f.read()
            
            # Find matches to count replacements
            matches = re.findall(pattern, original_content, re.MULTILINE | re.DOTALL)
            if not matches:
                return f"No matches found for pattern '{pattern}' in {file_path}"
            
            # Create backup if requested
            if backup:
                backup_path = full_path.with_suffix(full_path.suffix + '.bak')
                with open(backup_path, 'w', encoding='utf-8') as f:
                    f.write(original_content)
            
            # Perform replacement
            updated_content = re.sub(pattern, replacement, original_content, flags=re.MULTILINE | re.DOTALL)
            
            # Write updated content
            with open(full_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            backup_msg = f" (backup created at {backup_path.name})" if backup else ""
            return f"Successfully replaced {len(matches)} occurrence(s) in {file_path}{backup_msg}"
            
        except Exception as e:
            return f"Error updating file {file_path}: {str(e)}"


class VectorDatabaseUpdateTool(BaseUpdateTool):
    """Tool for updating content in vector database (Chroma)"""
    
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
    
    def update(self, document_id: str, new_content: str, metadata: dict = None) -> str:
        """
        Update document content in vector database
        
        Args:
            document_id: ID of the document to update
            new_content: New content for the document
            metadata: Optional metadata to update
            
        Returns:
            Status message indicating success or failure
        """
        try:
            client, collection = self._get_client()
            
            # Check if document exists
            try:
                existing = collection.get(ids=[document_id])
                if not existing['ids']:
                    return f"Document with ID '{document_id}' not found in collection '{self.collection_name}'"
            except Exception:
                return f"Document with ID '{document_id}' not found in collection '{self.collection_name}'"
            
            # Update the document
            update_data = {
                'ids': [document_id],
                'documents': [new_content]
            }
            
            if metadata:
                update_data['metadatas'] = [metadata]
            
            collection.update(**update_data)
            
            return f"Successfully updated document '{document_id}' in collection '{self.collection_name}'"
            
        except Exception as e:
            return f"Error updating vector database: {str(e)}"
    
    def upsert(self, document_id: str, content: str, metadata: dict = None) -> str:
        """
        Insert or update document content in vector database
        
        Args:
            document_id: ID of the document to upsert
            content: Content for the document
            metadata: Optional metadata
            
        Returns:
            Status message indicating success or failure
        """
        try:
            client, collection = self._get_client()
            
            upsert_data = {
                'ids': [document_id],
                'documents': [content]
            }
            
            if metadata:
                upsert_data['metadatas'] = [metadata]
            
            collection.upsert(**upsert_data)
            
            return f"Successfully upserted document '{document_id}' in collection '{self.collection_name}'"
            
        except Exception as e:
            return f"Error upserting to vector database: {str(e)}"


# Tool function implementations
def update_file_content(file_path: str, pattern: str, replacement: str, base_path: str = ".", backup: bool = True) -> str:
    """Update file content by replacing regex pattern matches with new content"""
    tool = FileSystemUpdateTool(base_path)
    return tool.update(file_path, pattern, replacement, backup)


def update_vector_db_document(document_id: str, new_content: str, collection_name: str = "default", metadata: dict = None) -> str:
    """Update document content in vector database"""
    tool = VectorDatabaseUpdateTool(collection_name)
    return tool.update(document_id, new_content, metadata)


def upsert_vector_db_document(document_id: str, content: str, collection_name: str = "default", metadata: dict = None) -> str:
    """Insert or update document content in vector database"""
    tool = VectorDatabaseUpdateTool(collection_name)
    return tool.upsert(document_id, content, metadata)


# Tool function lambdas for lazy loading
update_file_tool = lambda: lazy_tool_loader(update_file_content)
update_vector_db_tool = lambda: lazy_tool_loader(update_vector_db_document)
upsert_vector_db_tool = lambda: lazy_tool_loader(upsert_vector_db_document)