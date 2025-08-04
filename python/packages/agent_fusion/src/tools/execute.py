import subprocess
import sys
import tempfile
import os
from pathlib import Path
from typing import Optional, Dict, Any
from .utils.base import lazy_tool_loader


class CodeExecutionTool:
    """Tool for executing Python code snippets safely"""
    
    def __init__(self, working_directory: str = None, timeout: int = 30):
        self.working_directory = Path(working_directory).resolve() if working_directory else Path.cwd()
        self.timeout = timeout
    
    def execute_python_code(self, code: str, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
        """
        Execute Python code snippet using python -c
        
        Args:
            code: Python code snippet to execute
            capture_output: Whether to capture stdout/stderr
            env_vars: Optional environment variables to set
            
        Returns:
            Execution result with stdout, stderr, and return code
        """
        try:
            # Prepare environment
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            # Execute code using python -c
            cmd = [sys.executable, "-c", code]
            
            result = subprocess.run(
                cmd,
                cwd=self.working_directory,
                capture_output=capture_output,
                text=True,
                timeout=self.timeout,
                env=env
            )
            
            # Format result
            output_parts = []
            
            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")
            
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            
            output_parts.append(f"Return Code: {result.returncode}")
            
            if result.returncode == 0:
                status = "SUCCESS"
            else:
                status = "ERROR"
            
            return f"Execution Status: {status}\n" + "\n".join(output_parts)
            
        except subprocess.TimeoutExpired:
            return f"ERROR: Code execution timed out after {self.timeout} seconds"
        except FileNotFoundError:
            return f"ERROR: Python interpreter not found at {sys.executable}"
        except Exception as e:
            return f"ERROR: Execution failed - {str(e)}"
    
    def execute_python_file(self, file_path: str, args: list = None, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
        """
        Execute a Python file
        
        Args:
            file_path: Path to Python file to execute
            args: Command line arguments to pass to the script
            capture_output: Whether to capture stdout/stderr
            env_vars: Optional environment variables to set
            
        Returns:
            Execution result with stdout, stderr, and return code
        """
        try:
            full_path = self.working_directory / file_path
            
            if not full_path.exists():
                return f"ERROR: File not found - {file_path}"
            
            if not full_path.suffix == '.py':
                return f"ERROR: Not a Python file - {file_path}"
            
            # Prepare environment
            env = os.environ.copy()
            if env_vars:
                env.update(env_vars)
            
            # Prepare command
            cmd = [sys.executable, str(full_path)]
            if args:
                cmd.extend(args)
            
            result = subprocess.run(
                cmd,
                cwd=self.working_directory,
                capture_output=capture_output,
                text=True,
                timeout=self.timeout,
                env=env
            )
            
            # Format result
            output_parts = []
            
            if result.stdout:
                output_parts.append(f"STDOUT:\n{result.stdout}")
            
            if result.stderr:
                output_parts.append(f"STDERR:\n{result.stderr}")
            
            output_parts.append(f"Return Code: {result.returncode}")
            
            if result.returncode == 0:
                status = "SUCCESS"
            else:
                status = "ERROR"
            
            return f"Execution Status: {status}\nFile: {file_path}\n" + "\n".join(output_parts)
            
        except subprocess.TimeoutExpired:
            return f"ERROR: File execution timed out after {self.timeout} seconds"
        except Exception as e:
            return f"ERROR: File execution failed - {str(e)}"
    
    def execute_with_temp_file(self, code: str, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
        """
        Execute Python code by writing to a temporary file first
        Useful for multi-line code or when python -c has limitations
        
        Args:
            code: Python code to execute
            capture_output: Whether to capture stdout/stderr
            env_vars: Optional environment variables to set
            
        Returns:
            Execution result with stdout, stderr, and return code
        """
        try:
            # Create temporary file
            with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False, encoding='utf-8') as temp_file:
                temp_file.write(code)
                temp_file_path = temp_file.name
            
            try:
                # Execute the temporary file
                result = self.execute_python_file(
                    os.path.basename(temp_file_path), 
                    capture_output=capture_output,
                    env_vars=env_vars
                )
                
                return f"Executed via temporary file:\n{result}"
                
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except OSError:
                    pass  # Ignore cleanup errors
                    
        except Exception as e:
            return f"ERROR: Temporary file execution failed - {str(e)}"


# Tool function implementations
def execute_python_code(code: str, working_directory: str = None, timeout: int = 30, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
    """Execute Python code snippet using python -c"""
    from .validation import ToolValidator
    
    return ToolValidator.safe_execute(_execute_python_code_impl, code, working_directory, timeout, capture_output, env_vars)


def execute_python_file(file_path: str, working_directory: str = None, args: list = None, timeout: int = 30, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
    """Execute a Python file"""
    from .validation import ToolValidator
    
    return ToolValidator.safe_execute(_execute_python_file_impl, file_path, working_directory, args, timeout, capture_output, env_vars)


def execute_python_multiline(code: str, working_directory: str = None, timeout: int = 30, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
    """Execute multi-line Python code using temporary file"""
    from .validation import ToolValidator
    
    return ToolValidator.safe_execute(_execute_python_multiline_impl, code, working_directory, timeout, capture_output, env_vars)


def _execute_python_code_impl(code: str, working_directory: str = None, timeout: int = 30, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
    """Internal implementation with validation"""
    from .validation import ToolValidator
    
    # Validate inputs
    ToolValidator.validate_code_snippet(code)
    
    if timeout is not None and (not isinstance(timeout, int) or timeout < 1 or timeout > 300):
        raise ValueError("Timeout must be an integer between 1 and 300 seconds")
    
    tool = CodeExecutionTool(working_directory, timeout)
    return tool.execute_python_code(code, capture_output, env_vars)


def _execute_python_file_impl(file_path: str, working_directory: str = None, args: list = None, timeout: int = 30, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
    """Internal implementation with validation"""
    from .validation import ToolValidator
    
    # Validate inputs
    if working_directory:
        ToolValidator.validate_file_path(file_path, working_directory, must_exist=True, must_be_file=True)
    
    if timeout is not None and (not isinstance(timeout, int) or timeout < 1 or timeout > 300):
        raise ValueError("Timeout must be an integer between 1 and 300 seconds")
    
    tool = CodeExecutionTool(working_directory, timeout)
    return tool.execute_python_file(file_path, args, capture_output, env_vars)


def _execute_python_multiline_impl(code: str, working_directory: str = None, timeout: int = 30, capture_output: bool = True, env_vars: Dict[str, str] = None) -> str:
    """Internal implementation with validation"""
    from .validation import ToolValidator
    
    # Validate inputs
    ToolValidator.validate_code_snippet(code)
    
    if timeout is not None and (not isinstance(timeout, int) or timeout < 1 or timeout > 300):
        raise ValueError("Timeout must be an integer between 1 and 300 seconds")
    
    tool = CodeExecutionTool(working_directory, timeout)
    return tool.execute_with_temp_file(code, capture_output, env_vars)


# Tool function lambdas for lazy loading
execute_code_tool = lambda: lazy_tool_loader(execute_python_code)
execute_file_tool = lambda: lazy_tool_loader(execute_python_file)
execute_multiline_tool = lambda: lazy_tool_loader(execute_python_multiline)