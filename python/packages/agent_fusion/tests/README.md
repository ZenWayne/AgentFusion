# AgentFusion Tests

This directory contains pytest test cases for the AgentFusion library.

## Running Tests

To run all tests:
```bash
cd python/packages/agent_fusion
python -m pytest tests/ -v
```

To run specific test files:
```bash
python -m pytest tests/test_builders.py -v
```

To run specific test classes or methods:
```bash
python -m pytest tests/test_builders.py::TestLoadInfo -v
python -m pytest tests/test_builders.py::TestLoadInfo::test_load_info_success -v
```

## Test Structure

### `test_builders.py`
Tests for the core builder functionality:

- **TestLoadInfo**: Tests for the `load_info` function that loads configuration from JSON files
  - `test_load_info_success`: Tests successful loading of a valid configuration
  - `test_load_info_file_not_found`: Tests handling of missing config files
  - `test_load_info_invalid_json`: Tests handling of malformed JSON
  - `test_load_info_with_mcp_tools`: Tests loading agents with MCP tools

- **TestAgentBuilder**: Tests for the `AgentBuilder` class that creates agents
  - `test_agent_builder_assistant_agent`: Tests building assistant agents
  - `test_agent_builder_user_proxy_agent`: Tests building user proxy agents
  - `test_agent_builder_invalid_agent_type`: Tests error handling for invalid agent types
  - `test_agent_builder_agent_not_found`: Tests error handling for missing agents
  - `test_agent_builder_with_mcp_tools`: Tests building agents with MCP tools

- **TestIntegration**: Integration tests that combine `load_info` and `AgentBuilder`
  - `test_load_and_build_integration`: Tests the full workflow from loading config to building agents

## Test Configuration

The tests use:
- **pytest** as the test framework
- **pytest-asyncio** for async test support
- **unittest.mock** for mocking dependencies
- Temporary files for testing file operations
- Realistic filesystem MCP server configurations based on the actual config.json

## Dependencies

Make sure you have the following dependencies installed:
- pytest
- pytest-asyncio
- The AgentFusion package and its dependencies

## Notes

- Tests automatically clean up global state before and after each test
- All MCP server configurations use the real filesystem server example (`npx @modelcontextprotocol/server-filesystem`)
- Tests include comprehensive mocking of external dependencies like model clients and MCP tools 