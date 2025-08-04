"""
Validation utilities for AgentFusion tools
Provides comprehensive error handling and input validation
"""

import re
import os
from pathlib import Path
from typing import Union, List, Optional, Any, Dict
import logging

# Set up logging for tools
logger = logging.getLogger(__name__)


class ValidationError(Exception):
    """Custom exception for validation errors"""
    def __init__(self, message: str, error_code: str = None):
        self.message = message
        self.error_code = error_code
        super().__init__(self.message)


class ToolValidator:
    """Utility class for validating tool inputs and handling errors safely"""
    
    @staticmethod
    def validate_file_path(file_path: str, base_path: str = ".", must_exist: bool = True, must_be_file: bool = True) -> Path:
        """
        Validate and resolve file path
        
        Args:
            file_path: Path to validate
            base_path: Base directory for relative paths
            must_exist: Whether the file must exist
            must_be_file: Whether the path must be a file (not directory)
            
        Returns:
            Resolved Path object
            
        Raises:
            ValidationError: If validation fails
        """
        try:
            if not file_path or not isinstance(file_path, str):
                raise ValidationError("File path must be a non-empty string", "INVALID_PATH")
            
            # Convert to Path and resolve
            base = Path(base_path).resolve()
            full_path = base / file_path
            
            # Security check - ensure path is within base directory
            try:
                full_path.resolve().relative_to(base.resolve())
            except ValueError:
                raise ValidationError(f"Path '{file_path}' is outside the allowed directory", "PATH_TRAVERSAL")
            
            if must_exist and not full_path.exists():
                raise ValidationError(f"Path does not exist: {file_path}", "PATH_NOT_FOUND")
            
            if must_exist and must_be_file and not full_path.is_file():
                raise ValidationError(f"Path is not a file: {file_path}", "NOT_A_FILE")
            
            return full_path
            
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Path validation failed: {str(e)}", "PATH_VALIDATION_ERROR")
    
    @staticmethod
    def validate_regex_pattern(pattern: str) -> str:
        """
        Validate regex pattern
        
        Args:
            pattern: Regex pattern to validate
            
        Returns:
            The validated pattern
            
        Raises:
            ValidationError: If pattern is invalid
        """
        try:
            if not pattern or not isinstance(pattern, str):
                raise ValidationError("Pattern must be a non-empty string", "INVALID_PATTERN")
            
            # Test compile the regex
            re.compile(pattern)
            return pattern
            
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern: {str(e)}", "REGEX_ERROR")
        except Exception as e:
            raise ValidationError(f"Pattern validation failed: {str(e)}", "PATTERN_VALIDATION_ERROR")
    
    @staticmethod
    def validate_code_snippet(code: str, max_length: int = 10000) -> str:
        """
        Validate Python code snippet for security and basic syntax
        
        Args:
            code: Code snippet to validate
            max_length: Maximum allowed code length
            
        Returns:
            The validated code
            
        Raises:
            ValidationError: If code is invalid or potentially dangerous
        """
        try:
            if not code or not isinstance(code, str):
                raise ValidationError("Code must be a non-empty string", "INVALID_CODE")
            
            if len(code) > max_length:
                raise ValidationError(f"Code exceeds maximum length of {max_length} characters", "CODE_TOO_LONG")
            
            # Basic security checks - block potentially dangerous imports/functions
            dangerous_patterns = [
                r'\bos\.system\b',
                r'\bsubprocess\b',  # Allow subprocess but warn
                r'\bexec\b',
                r'\beval\b',
                r'\b__import__\b',
                r'\bopen\s*\([^)]*["\'][wax]["\']',  # File operations in write/append mode
                r'\brmdir\b',
                r'\bunlink\b',
                r'\bremove\b',
            ]
            
            warnings = []
            for pattern in dangerous_patterns:
                if re.search(pattern, code, re.IGNORECASE):
                    if 'subprocess' in pattern:
                        warnings.append(f"Code contains potentially dangerous operation: {pattern}")
                    else:
                        raise ValidationError(f"Code contains prohibited operation: {pattern}", "DANGEROUS_CODE")
            
            # Try to compile the code to check basic syntax
            try:
                compile(code, '<string>', 'exec')
            except SyntaxError as e:
                raise ValidationError(f"Code has syntax error: {str(e)}", "SYNTAX_ERROR")
            
            # Log warnings if any
            if warnings:
                for warning in warnings:
                    logger.warning(warning)
            
            return code
            
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Code validation failed: {str(e)}", "CODE_VALIDATION_ERROR")
    
    @staticmethod
    def validate_document_id(document_id: Union[str, List[str]]) -> Union[str, List[str]]:
        """
        Validate document ID(s) for vector database operations
        
        Args:
            document_id: Single ID or list of IDs
            
        Returns:
            Validated ID(s)
            
        Raises:
            ValidationError: If IDs are invalid
        """
        try:
            if isinstance(document_id, str):
                if not document_id.strip():
                    raise ValidationError("Document ID cannot be empty", "EMPTY_ID")
                return document_id.strip()
            
            elif isinstance(document_id, list):
                if not document_id:
                    raise ValidationError("Document ID list cannot be empty", "EMPTY_ID_LIST")
                
                validated_ids = []
                for idx, doc_id in enumerate(document_id):
                    if not isinstance(doc_id, str) or not doc_id.strip():
                        raise ValidationError(f"Document ID at index {idx} is invalid", "INVALID_ID_IN_LIST")
                    validated_ids.append(doc_id.strip())
                
                return validated_ids
            
            else:
                raise ValidationError("Document ID must be string or list of strings", "INVALID_ID_TYPE")
                
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Document ID validation failed: {str(e)}", "ID_VALIDATION_ERROR")
    
    @staticmethod
    def safe_execute(func, *args, **kwargs) -> str:
        """
        Safely execute a function with comprehensive error handling
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result or error message
        """
        try:
            return func(*args, **kwargs)
        except ValidationError as e:
            return f"Validation Error [{e.error_code}]: {e.message}"
        except PermissionError as e:
            return f"Permission Error: {str(e)}"
        except FileNotFoundError as e:
            return f"File Not Found Error: {str(e)}"
        except OSError as e:
            return f"OS Error: {str(e)}"
        except ImportError as e:
            return f"Import Error: {str(e)}"
        except Exception as e:
            logger.exception("Unexpected error in tool execution")
            return f"Unexpected Error: {str(e)}"
    
    @staticmethod
    def validate_collection_name(collection_name: str) -> str:
        """
        Validate vector database collection name
        
        Args:
            collection_name: Collection name to validate
            
        Returns:
            Validated collection name
            
        Raises:
            ValidationError: If collection name is invalid
        """
        try:
            if not collection_name or not isinstance(collection_name, str):
                raise ValidationError("Collection name must be a non-empty string", "INVALID_COLLECTION_NAME")
            
            # Basic validation - alphanumeric, underscore, hyphen only
            if not re.match(r'^[a-zA-Z0-9_-]+$', collection_name):
                raise ValidationError("Collection name can only contain letters, numbers, underscores, and hyphens", "INVALID_COLLECTION_NAME")
            
            if len(collection_name) > 100:
                raise ValidationError("Collection name cannot exceed 100 characters", "COLLECTION_NAME_TOO_LONG")
            
            return collection_name
            
        except ValidationError:
            raise
        except Exception as e:
            raise ValidationError(f"Collection name validation failed: {str(e)}", "COLLECTION_VALIDATION_ERROR")


# Convenience decorators for tool functions
def validate_inputs(validator_func):
    """Decorator to validate inputs before function execution"""
    def decorator(func):
        def wrapper(*args, **kwargs):
            try:
                # Validate inputs using the provided validator function
                validated_args, validated_kwargs = validator_func(*args, **kwargs)
                return func(*validated_args, **validated_kwargs)
            except Exception as e:
                return f"Input validation failed: {str(e)}"
        return wrapper
    return decorator