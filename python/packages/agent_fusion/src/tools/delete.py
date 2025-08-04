import os
import shutil
from abc import ABC, abstractmethod
from typing import List, Optional, Union
from pathlib import Path
from .utils.base import lazy_tool_loader


class BaseDeleteTool(ABC):
    """Base class for delete tools that can be extended for filesystem or vector database"""
    
    @abstractmethod
    def delete(self, identifier: str, **kwargs) -> str:
        """Abstract method for deleting content"""
        pass


class FileSystemDeleteTool(BaseDeleteTool):
    """Tool for deleting files and directories from filesystem"""
    
    def __init__(self, base_path: str = "."):
        self.base_path = Path(base_path).resolve()
    
    def delete(self, file_path: str, force: bool = False, backup: bool = False) -> str:
        """
        Delete file or directory from filesystem
        
        Args:
            file_path: Path to the file or directory to delete
            force: Whether to force delete (ignore warnings for directories)
            backup: Whether to create a backup before deletion
            
        Returns:
            Status message indicating success or failure
        """
        full_path = self.base_path / file_path
        
        if not full_path.exists():
            return f"Path not found: {file_path}"
        
        try:
            # Create backup if requested
            if backup:
                backup_path = self._create_backup(full_path)
                backup_msg = f" (backup created at {backup_path})"
            else:
                backup_msg = ""
            
            if full_path.is_file():
                # Delete file
                full_path.unlink()
                return f"Successfully deleted file: {file_path}{backup_msg}"
            
            elif full_path.is_dir():
                # Check if directory is empty or force is used
                if not force and any(full_path.iterdir()):
                    return f"Directory not empty: {file_path}. Use force=True to delete non-empty directories"
                
                # Delete directory
                shutil.rmtree(full_path)
                return f"Successfully deleted directory: {file_path}{backup_msg}"
            
            else:
                return f"Unknown path type: {file_path}"
                
        except PermissionError:
            return f"Permission denied: Cannot delete {file_path}"
        except OSError as e:
            return f"OS error deleting {file_path}: {str(e)}"
        except Exception as e:
            return f"Error deleting {file_path}: {str(e)}"
    
    def _create_backup(self, path: Path) -> str:
        """Create a backup of the file or directory"""
        import datetime
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{path.name}.bak_{timestamp}"
        backup_path = path.parent / backup_name
        
        if path.is_file():
            shutil.copy2(path, backup_path)
        else:
            shutil.copytree(path, backup_path)
        
        return str(backup_path.relative_to(self.base_path))


class VectorDatabaseDeleteTool(BaseDeleteTool):
    """Tool for deleting content from vector database (Chroma)"""
    
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
    
    def delete(self, document_ids: Union[str, List[str]], **kwargs) -> str:
        """
        Delete documents from vector database
        
        Args:
            document_ids: ID or list of IDs of documents to delete
            
        Returns:
            Status message indicating success or failure
        """
        try:
            client, collection = self._get_client()
            
            # Ensure document_ids is a list
            if isinstance(document_ids, str):
                ids_list = [document_ids]
            else:
                ids_list = document_ids
            
            # Check which documents exist
            try:
                existing = collection.get(ids=ids_list)
                existing_ids = set(existing['ids'])
                requested_ids = set(ids_list)
                
                missing_ids = requested_ids - existing_ids
                if missing_ids:
                    missing_msg = f"Documents not found: {list(missing_ids)}. "
                else:
                    missing_msg = ""
                
                # Delete existing documents
                if existing_ids:
                    collection.delete(ids=list(existing_ids))
                    success_msg = f"Successfully deleted {len(existing_ids)} document(s) from collection '{self.collection_name}'"
                else:
                    success_msg = "No documents to delete"
                
                return missing_msg + success_msg
                
            except Exception:
                # If get fails, try to delete anyway (document might exist but get failed)
                collection.delete(ids=ids_list)
                return f"Attempted to delete {len(ids_list)} document(s) from collection '{self.collection_name}'"
            
        except Exception as e:
            return f"Error deleting from vector database: {str(e)}"
    
    def delete_collection(self) -> str:
        """
        Delete the entire collection from vector database
        
        Returns:
            Status message indicating success or failure
        """
        try:
            client, collection = self._get_client()
            client.delete_collection(self.collection_name)
            return f"Successfully deleted collection '{self.collection_name}'"
            
        except Exception as e:
            return f"Error deleting collection: {str(e)}"


# Tool function implementations  
def delete_file(file_path: str, base_path: str = ".", force: bool = False, backup: bool = False) -> str:
    """Delete file or directory from filesystem"""
    tool = FileSystemDeleteTool(base_path)
    return tool.delete(file_path, force, backup)


def delete_vector_db_documents(document_ids: Union[str, List[str]], collection_name: str = "default") -> str:
    """Delete documents from vector database"""
    tool = VectorDatabaseDeleteTool(collection_name)
    return tool.delete(document_ids)


def delete_vector_db_collection(collection_name: str = "default") -> str:
    """Delete entire collection from vector database"""
    tool = VectorDatabaseDeleteTool(collection_name)
    return tool.delete_collection()


# Tool function lambdas for lazy loading
delete_file_tool = lambda: lazy_tool_loader(delete_file)
delete_vector_db_documents_tool = lambda: lazy_tool_loader(delete_vector_db_documents)
delete_vector_db_collection_tool = lambda: lazy_tool_loader(delete_vector_db_collection)