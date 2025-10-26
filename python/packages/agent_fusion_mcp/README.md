# AgentFusion MCP

MCP (Model Context Protocol) Server implementations for AgentFusion database operations.

## Overview

This package provides MCP server implementations for various database tools and services, focusing on secure database operations:

- Connection management
- Security validation
- Safe query execution

## Installation

```bash
pip install agent_fusion_mcp
```

## Usage

### Database MCP Server

```python
from agent_fusion_mcp import DatabaseMCPServer

# Create server instance
server = DatabaseMCPServer()

# Connect to database
await server._connect_database(
    connection_name="my_db",
    database_type="postgresql",
    connection_string="postgresql://user:pass@host:port/db"
)

# Execute queries
result = await server._execute_query(
    connection_name="my_db",
    query="SELECT * FROM users"
)
```

## Security Features

- SQL injection detection
- Query validation with multiple security levels
- Row limits and timeouts
- Allowed operation restrictions

## Development

```bash
# Install in development mode
pip install -e .

# Run tests
pytest
```

## License

MIT