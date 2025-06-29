"""
Pytest configuration and shared fixtures for AgentFusion tests.
"""

import pytest
import pytest_asyncio
import sys
import os
from pathlib import Path

# Configure pytest-asyncio to handle async tests properly
pytest_asyncio.plugin.DEFAULT_LOOP_SCOPE = "function"

# Add the src directory to the Python path for imports
test_dir = Path(__file__).parent
src_dir = test_dir.parent / "src"
sys.path.insert(0, str(src_dir))

@pytest.fixture(scope="session")
def test_data_dir():
    """Get the test data directory path."""
    return test_dir / "data"

@pytest.fixture(autouse=True)
def clean_global_state():
    """Clean global state before and after each test."""
    # Import here to avoid circular imports
    try:
        from builders.utils import McpInfo, AgentInfo, GraphFlowInfo, GroupChatInfo
        
        # Clear before test
        McpInfo.clear()
        AgentInfo.clear()
        GraphFlowInfo.clear()
        GroupChatInfo.clear()
        
        yield
        
        # Clear after test
        McpInfo.clear()
        AgentInfo.clear()
        GraphFlowInfo.clear()
        GroupChatInfo.clear()
    except ImportError:
        # If modules are not available, just yield
        yield

@pytest.fixture
def sample_prompt_content():
    """Sample prompt content for testing."""
    return "You are a helpful AI assistant. Please respond to user queries accurately and helpfully." 