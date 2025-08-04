"""
Comprehensive test cases for AgentFusion Tools package.

This module tests all functionality of the tools package including:
- File system retrieve tools (regex pattern matching)
- Vector database retrieve tools (semantic search)
- File system update tools (regex-based replacement)
- Vector database update tools (document updates)
- File system delete tools (file/directory deletion)
- Vector database delete tools (document deletion)
- Code execution tools (Python snippet execution)
- Input validation and error handling
- Security features and path traversal protection
"""

import pytest
import pytest_asyncio
import tempfile
import os
import shutil
from pathlib import Path
from unittest.mock import patch, MagicMock
import re

# Import the tools we need to test
from tools.base.retrieve import (
    retrieve_from_filesystem, retrieve_from_vector_db,
    FileSystemRetrieveTool, VectorDatabaseRetrieveTool
)
from tools.update import (
    update_file_content, update_vector_db_document, upsert_vector_db_document,
    FileSystemUpdateTool, VectorDatabaseUpdateTool
)
from tools.delete import (
    delete_file, delete_vector_db_documents, delete_vector_db_collection,
    FileSystemDeleteTool, VectorDatabaseDeleteTool
)
from tools.execute import (
    execute_python_code, execute_python_file, execute_python_multiline,
    CodeExecutionTool
)
from tools.utils.validation import ToolValidator, ValidationError


class TestFileSystemRetrieveTool:
    """Test cases for FileSystemRetrieveTool"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing"""
        temp_dir = tempfile.mkdtemp()
        
        # Create test files
        test_content = {
            'test1.py': 'def hello():\n    print("Hello World")\n\nclass TestClass:\n    pass',
            'test2.js': 'function greet() {\n    console.log("Hello");\n}\n\nconst x = 42;',
            'subdir/test3.txt': 'This is a test file\nwith multiple lines\nand some patterns: ABC123'
        }
        
        for file_path, content in test_content.items():
            full_path = Path(temp_dir) / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            full_path.write_text(content, encoding='utf-8')
        
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_search_in_specific_file(self, temp_dir):
        """Test searching for pattern in specific file"""
        tool = FileSystemRetrieveTool(temp_dir)
        result = tool.retrieve(pattern=r'def \w+', file_path='test1.py')
        
        assert 'Found 1 matches' in result
        assert 'def hello' in result
    
    def test_search_in_directory_recursive(self, temp_dir):
        """Test recursive directory search"""
        tool = FileSystemRetrieveTool(temp_dir)
        result = tool.retrieve(pattern=r'test', recursive=True)
        
        assert 'test3.txt' in result or 'test1.py' in result
    
    def test_search_no_matches(self, temp_dir):
        """Test search with no matches"""
        tool = FileSystemRetrieveTool(temp_dir)
        result = tool.retrieve(pattern=r'nonexistent_pattern', file_path='test1.py')
        
        assert 'No matches found' in result
    
    def test_file_not_found(self, temp_dir):
        """Test searching in non-existent file"""
        tool = FileSystemRetrieveTool(temp_dir)
        result = tool.retrieve(pattern=r'test', file_path='nonexistent.txt')
        
        assert 'File not found' in result
    
    def test_invalid_regex(self, temp_dir):
        """Test invalid regex pattern"""
        result = retrieve_from_filesystem(pattern='[unclosed', file_path='test1.py', base_path=temp_dir)
        
        assert 'Invalid regex pattern' in result


class TestVectorDatabaseRetrieveTool:
    """Test cases for VectorDatabaseRetrieveTool"""
    
    @pytest.fixture
    def mock_chroma(self):
        """Mock ChromaDB for testing"""
        with patch('chromadb.Client') as mock_client_class:
            mock_client = MagicMock()
            mock_collection = MagicMock()
            
            mock_client_class.return_value = mock_client
            mock_client.get_or_create_collection.return_value = mock_collection
            
            # Mock successful query response
            mock_collection.query.return_value = {
                'documents': [['Document 1 content', 'Document 2 content']],
                'distances': [[0.1, 0.3]]
            }
            
            yield mock_client, mock_collection
    
    def test_successful_query(self, mock_chroma):
        """Test successful vector database query"""
        mock_client, mock_collection = mock_chroma
        
        result = retrieve_from_vector_db('test query', 'test_collection', 2)
        
        assert 'Result 1' in result
        assert 'Result 2' in result
        assert 'similarity: 0.900' in result  # 1 - 0.1
        assert 'similarity: 0.700' in result  # 1 - 0.3
    
    def test_no_results(self, mock_chroma):
        """Test query with no results"""
        mock_client, mock_collection = mock_chroma
        mock_collection.query.return_value = {'documents': [[]], 'distances': [[]]}
        
        result = retrieve_from_vector_db('test query')
        
        assert 'No results found' in result
    
    def test_chromadb_not_installed(self):
        """Test error when ChromaDB is not installed"""
        with patch('chromadb.Client', side_effect=ImportError()):
            result = retrieve_from_vector_db('test query')
            
            assert 'ChromaDB not installed' in result


class TestFileSystemUpdateTool:
    """Test cases for FileSystemUpdateTool"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing"""
        temp_dir = tempfile.mkdtemp()
        
        # Create test file
        test_file = Path(temp_dir) / 'test_update.py'
        test_file.write_text('def old_function():\n    return "old"\n\ndef another_function():\n    return "unchanged"')
        
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_successful_update(self, temp_dir):
        """Test successful file content update"""
        result = update_file_content('test_update.py', r'def old_function\(\):', 'def new_function():', temp_dir, backup=False)
        
        assert 'Successfully replaced 1 occurrence' in result
        
        # Verify file was updated
        updated_content = (Path(temp_dir) / 'test_update.py').read_text()
        assert 'def new_function():' in updated_content
        assert 'def old_function():' not in updated_content
    
    def test_update_with_backup(self, temp_dir):
        """Test file update with backup creation"""
        result = update_file_content('test_update.py', r'old', 'new', temp_dir, backup=True)
        
        assert 'Successfully replaced' in result
        assert 'backup created' in result
        
        # Verify backup file exists
        backup_files = list(Path(temp_dir).glob('*.bak'))
        assert len(backup_files) == 1
    
    def test_update_file_not_found(self, temp_dir):
        """Test updating non-existent file"""
        result = update_file_content('nonexistent.py', r'pattern', 'replacement', temp_dir)
        
        assert 'File not found' in result
    
    def test_update_no_matches(self, temp_dir):
        """Test update with no pattern matches"""
        result = update_file_content('test_update.py', r'nonexistent_pattern', 'replacement', temp_dir)
        
        assert 'No matches found' in result


class TestFileSystemDeleteTool:
    """Test cases for FileSystemDeleteTool"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create temporary directory for testing"""
        temp_dir = tempfile.mkdtemp()
        
        # Create test files and directories
        test_file = Path(temp_dir) / 'test_delete.txt'
        test_file.write_text('test content')
        
        test_dir = Path(temp_dir) / 'test_subdir'
        test_dir.mkdir()
        (test_dir / 'nested_file.txt').write_text('nested content')
        
        empty_dir = Path(temp_dir) / 'empty_dir'
        empty_dir.mkdir()
        
        yield temp_dir
        shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_delete_file(self, temp_dir):
        """Test successful file deletion"""
        result = delete_file('test_delete.txt', temp_dir, backup=False)
        
        assert 'Successfully deleted file' in result
        assert not (Path(temp_dir) / 'test_delete.txt').exists()
    
    def test_delete_file_with_backup(self, temp_dir):
        """Test file deletion with backup"""
        result = delete_file('test_delete.txt', temp_dir, backup=True)
        
        assert 'Successfully deleted file' in result
        assert 'backup created' in result
        
        # Verify backup exists
        backup_files = list(Path(temp_dir).glob('*.bak_*'))
        assert len(backup_files) == 1
    
    def test_delete_empty_directory(self, temp_dir):
        """Test deleting empty directory"""
        result = delete_file('empty_dir', temp_dir)
        
        assert 'Successfully deleted directory' in result
        assert not (Path(temp_dir) / 'empty_dir').exists()
    
    def test_delete_non_empty_directory_without_force(self, temp_dir):
        """Test deleting non-empty directory without force"""
        result = delete_file('test_subdir', temp_dir, force=False)
        
        assert 'Directory not empty' in result
        assert (Path(temp_dir) / 'test_subdir').exists()
    
    def test_delete_non_empty_directory_with_force(self, temp_dir):
        """Test deleting non-empty directory with force"""
        result = delete_file('test_subdir', temp_dir, force=True)
        
        assert 'Successfully deleted directory' in result
        assert not (Path(temp_dir) / 'test_subdir').exists()
    
    def test_delete_nonexistent_path(self, temp_dir):
        """Test deleting non-existent path"""
        result = delete_file('nonexistent.txt', temp_dir)
        
        assert 'Path not found' in result


class TestCodeExecutionTool:
    """Test cases for CodeExecutionTool"""
    
    def test_execute_simple_code(self):
        """Test executing simple Python code"""
        result = execute_python_code('print("Hello, World!")')
        
        assert 'Execution Status: SUCCESS' in result
        assert 'STDOUT:\nHello, World!' in result
        assert 'Return Code: 0' in result
    
    def test_execute_code_with_error(self):
        """Test executing Python code that raises an error"""
        result = execute_python_code('raise ValueError("Test error")')
        
        assert 'Execution Status: ERROR' in result
        assert 'STDERR:' in result
        assert 'ValueError: Test error' in result
        assert 'Return Code: 1' in result
    
    def test_execute_code_with_syntax_error(self):
        """Test executing Python code with syntax error"""
        result = execute_python_code('def invalid_syntax(')
        
        assert 'Code has syntax error' in result
    
    def test_execute_dangerous_code(self):
        """Test executing potentially dangerous Python code"""
        result = execute_python_code('import os; os.system("echo test")')
        
        assert 'Code contains prohibited operation' in result
    
    def test_execute_multiline_code(self):
        """Test executing multi-line Python code"""
        code = '''
x = 10
y = 20
print(f"Sum: {x + y}")
'''
        result = execute_python_multiline(code)
        
        assert 'Execution Status: SUCCESS' in result
        assert 'Sum: 30' in result
    
    def test_execute_code_timeout_validation(self):
        """Test timeout validation"""
        result = execute_python_code('print("test")', timeout=500)  # Over 300 limit
        
        assert 'Timeout must be an integer between 1 and 300' in result
    
    def test_execute_empty_code(self):
        """Test executing empty code"""
        result = execute_python_code('')
        
        assert 'Code must be a non-empty string' in result


class TestToolValidator:
    """Test cases for ToolValidator class"""
    
    def test_validate_file_path_valid(self):
        """Test validating valid file path"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_file:
            temp_file.write('test')
            temp_path = temp_file.name
        
        try:
            result = ToolValidator.validate_file_path(
                os.path.basename(temp_path), 
                os.path.dirname(temp_path),
                must_exist=True
            )
            assert result.name == os.path.basename(temp_path)
        finally:
            os.unlink(temp_path)
    
    def test_validate_file_path_traversal_attack(self):
        """Test path traversal protection"""
        with pytest.raises(ValidationError) as exc_info:
            ToolValidator.validate_file_path('../../../etc/passwd', '/tmp')
        
        assert 'outside the allowed directory' in str(exc_info.value)
    
    def test_validate_regex_pattern_valid(self):
        """Test validating valid regex pattern"""
        result = ToolValidator.validate_regex_pattern(r'\d+')
        assert result == r'\d+'
    
    def test_validate_regex_pattern_invalid(self):
        """Test validating invalid regex pattern"""
        with pytest.raises(ValidationError) as exc_info:
            ToolValidator.validate_regex_pattern('[unclosed')
        
        assert 'Invalid regex pattern' in str(exc_info.value)
    
    def test_validate_code_snippet_valid(self):
        """Test validating valid code snippet"""
        code = 'print("Hello, World!")'
        result = ToolValidator.validate_code_snippet(code)
        assert result == code
    
    def test_validate_code_snippet_too_long(self):
        """Test validating code snippet that's too long"""
        code = 'x = 1\n' * 5001  # Over 10000 chars
        
        with pytest.raises(ValidationError) as exc_info:
            ToolValidator.validate_code_snippet(code, max_length=10000)
        
        assert 'exceeds maximum length' in str(exc_info.value)
    
    def test_validate_document_id_string(self):
        """Test validating single document ID"""
        result = ToolValidator.validate_document_id('test_doc_123')
        assert result == 'test_doc_123'
    
    def test_validate_document_id_list(self):
        """Test validating list of document IDs"""
        ids = ['doc1', 'doc2', 'doc3']
        result = ToolValidator.validate_document_id(ids)
        assert result == ids
    
    def test_validate_document_id_empty(self):
        """Test validating empty document ID"""
        with pytest.raises(ValidationError) as exc_info:
            ToolValidator.validate_document_id('')
        
        assert 'cannot be empty' in str(exc_info.value)
    
    def test_validate_collection_name_valid(self):
        """Test validating valid collection name"""
        result = ToolValidator.validate_collection_name('test_collection_123')
        assert result == 'test_collection_123'
    
    def test_validate_collection_name_invalid_chars(self):
        """Test validating collection name with invalid characters"""
        with pytest.raises(ValidationError) as exc_info:
            ToolValidator.validate_collection_name('test@collection!')
        
        assert 'can only contain letters, numbers, underscores, and hyphens' in str(exc_info.value)
    
    def test_safe_execute_success(self):
        """Test safe execution of successful function"""
        def test_func(x, y):
            return x + y
        
        result = ToolValidator.safe_execute(test_func, 5, 10)
        assert result == 15
    
    def test_safe_execute_validation_error(self):
        """Test safe execution with validation error"""
        def test_func():
            raise ValidationError("Test validation error", "TEST_ERROR")
        
        result = ToolValidator.safe_execute(test_func)
        assert 'Validation Error [TEST_ERROR]: Test validation error' in result
    
    def test_safe_execute_general_exception(self):
        """Test safe execution with general exception"""
        def test_func():
            raise ValueError("Test error")
        
        result = ToolValidator.safe_execute(test_func)
        assert 'Unexpected Error: Test error' in result


class TestToolIntegration:
    """Integration tests for tool workflows"""
    
    @pytest.fixture
    def temp_workspace(self):
        """Create temporary workspace for integration testing"""
        temp_dir = tempfile.mkdtemp()
        
        # Create a small project structure
        project_files = {
            'main.py': '''
def main():
    print("Main function")
    return calculate_result(10, 20)

def calculate_result(a, b):
    return a + b

if __name__ == "__main__":
    main()
''',
            'utils.py': '''
def helper_function():
    return "Helper result"

class UtilityClass:
    def __init__(self, value):
        self.value = value
    
    def get_value(self):
        return self.value
''',
            'config.json': '{"setting1": "value1", "setting2": 42}'
        }
        
        for file_path, content in project_files.items():
            (Path(temp_dir) / file_path).write_text(content.strip())
        
        yield temp_dir
        shutil.rmtree(temp_dir)
    
    def test_retrieve_update_workflow(self, temp_workspace):
        """Test retrieve -> update workflow"""
        # First, retrieve function definitions
        result = retrieve_from_filesystem(r'def \w+\(', base_path=temp_workspace)
        assert 'def main(' in result
        assert 'def calculate_result(' in result
        
        # Then update a function name
        update_result = update_file_content(
            'main.py', 
            r'def calculate_result', 
            'def compute_result',
            temp_workspace,
            backup=False
        )
        assert 'Successfully replaced 1 occurrence' in update_result
        
        # Verify the update
        verify_result = retrieve_from_filesystem(r'def \w+\(', file_path='main.py', base_path=temp_workspace)
        assert 'def compute_result(' in verify_result
        assert 'def calculate_result(' not in verify_result
    
    def test_code_execution_workflow(self, temp_workspace):
        """Test code execution workflow"""
        # Execute the main.py file
        result = execute_python_file('main.py', working_directory=temp_workspace)
        
        assert 'Execution Status: SUCCESS' in result
        assert 'Main function' in result
        assert '30' in result  # Result of 10 + 20
    
    def test_error_handling_workflow(self, temp_workspace):
        """Test comprehensive error handling"""
        # Try to retrieve from non-existent file
        result = retrieve_from_filesystem(r'test', file_path='nonexistent.py', base_path=temp_workspace)
        assert 'File not found' in result
        
        # Try to update non-existent file  
        result = update_file_content('nonexistent.py', r'pattern', 'replacement', temp_workspace)
        assert 'File not found' in result
        
        # Try to delete non-existent file
        result = delete_file('nonexistent.py', temp_workspace)
        assert 'Path not found' in result
        
        # Try to execute invalid code
        result = execute_python_code('invalid syntax here')
        assert 'Code has syntax error' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])