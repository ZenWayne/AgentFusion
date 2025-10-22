"""
Database MCP Server for AgentFusion

Focused MCP server that provides only secure database operations:
- Connection management
- Security validation
- Safe query execution

Tests four core methods: _connect_database, _security_check, _execute_query, and call_tool
"""

import asyncio
import json
import logging
import re
from typing import Dict, List, Optional, Any

try:
    import sqlalchemy
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import Engine
    from sqlalchemy.exc import SQLAlchemyError
except ImportError:
    sqlalchemy = None

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import (
    Tool, TextContent, CallToolResult
)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("database-mcp-server")


class DatabaseMCPServer:
    """Lightweight Database MCP Server - secure operations only."""

    def __init__(self):
        self.server = Server("database-mcp-server")
        self.connections: Dict[str, Engine] = {}

        # Register MCP handlers
        self._register_handlers()

    def _register_handlers(self):
        """Register MCP protocol handlers."""

        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available database tools - focused and minimal."""
            return [
                Tool(
                    name="connect_database",
                    description="Establish database connection with validation",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "Unique name for this connection"
                            },
                            "database_type": {
                                "type": "string",
                                "enum": ["sqlite", "mysql", "postgresql"],
                                "description": "Database type"
                            },
                            "connection_string": {
                                "type": "string",
                                "description": "Full connection string (overrides other params)"
                            },
                            "host": {"type": "string", "description": "Database host"},
                            "port": {"type": "integer", "description": "Database port"},
                            "database": {"type": "string", "description": "Database name"},
                            "username": {"type": "string", "description": "Database username"},
                            "password": {"type": "string", "description": "Database password"},
                            "pool_size": {"type": "integer", "default": 5, "description": "Connection pool size"},
                            "timeout": {"type": "integer", "default": 30, "description": "Connection timeout"}
                        },
                        "required": ["connection_name", "database_type"]
                    }
                ),
                Tool(
                    name="security_check",
                    description="Validate SQL query for security issues",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "SQL query to validate"
                            },
                            "security_level": {
                                "type": "string",
                                "enum": ["low", "medium", "high", "strict"],
                                "default": "medium",
                                "description": "Security validation level"
                            },
                            "allowed_operations": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Explicitly allowed SQL operations"
                            }
                        },
                        "required": ["query"]
                    }
                ),
                Tool(
                    name="execute_query",
                    description="Execute validated SQL query safely",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "connection_name": {
                                "type": "string",
                                "description": "Name of established connection"
                            },
                            "query": {
                                "type": "string",
                                "description": "SQL query to execute"
                            },
                            "params": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Query parameters for prepared statements"
                            },
                            "max_rows": {
                                "type": "integer",
                                "default": 1000,
                                "description": "Maximum rows to return"
                            },
                            "timeout": {
                                "type": "integer",
                                "default": 60,
                                "description": "Query timeout in seconds"
                            }
                        },
                        "required": ["connection_name", "query"]
                    }
                )
            ]

        @self.server.call_tool()
        async def call_tool(name: str, arguments: Dict[str, Any]) -> CallToolResult:
            """Handle tool calls - main dispatcher for testing."""
            try:
                if name == "connect_database":
                    result = await self._connect_database(**arguments)
                elif name == "security_check":
                    result = await self._security_check(**arguments)
                elif name == "execute_query":
                    result = await self._execute_query(**arguments)
                else:
                    result = {"error": f"Unknown tool: {name}"}

                # Ensure result is a proper dictionary
                if not isinstance(result, dict):
                    logger.warning(f"Result is not a dict: {type(result)} - converting to dict")
                    result = {"data": result}

                logger.info(f"Tool {name} result: {json.dumps(result, indent=2)}")

                # Create CallToolResult with proper structure
                return result

            except Exception as e:
                logger.error(f"Error executing tool {name}: {str(e)}")
                error_result = {
                    "success": False,
                    "error": str(e),
                    "tool": name
                }
                return error_result

    async def _connect_database(self, connection_name: str, database_type: str,
                              **kwargs) -> Dict[str, Any]:
        """
        Establish database connection with validation.

        Test focus: Connection establishment, validation, and storage.
        """
        try:
            if not sqlalchemy:
                raise ImportError("SQLAlchemy is required. Install with: pip install sqlalchemy")

            # Build connection string
            if kwargs.get('connection_string'):
                connection_string = kwargs['connection_string']
            else:
                connection_string = self._build_connection_string(database_type, kwargs)

            # Create engine with safety settings
            engine_kwargs = {
                'echo': False  # Don't log queries (security)
            }

            # Add pool settings only for non-SQLite databases
            if database_type != 'sqlite':
                engine_kwargs.update({
                    'pool_size': kwargs.get('pool_size', 5),
                    'pool_timeout': kwargs.get('timeout', 30),
                    'pool_recycle': 3600,  # Recycle connections hourly
                })

            engine = create_engine(connection_string, **engine_kwargs)

            # Test connection with simple query
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            # Store connection
            self.connections[connection_name] = engine

            logger.info(f"Connected to database: {connection_name}")

            return {
                "success": True,
                "connection_name": connection_name,
                "database_type": database_type,
                "message": f"Successfully connected to {database_type} database"
            }

        except ImportError as e:
            return {
                "success": False,
                "error": f"Missing dependency: {str(e)}",
                "suggestion": "Install with: pip install sqlalchemy pymysql psycopg2-binary"
            }
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return {
                "success": False,
                "error": str(e),
                "connection_name": connection_name
            }

    def _build_connection_string(self, db_type: str, params: Dict[str, Any]) -> str:
        """Build database connection string."""
        if db_type == "sqlite":
            database = params.get('database', '')
            return f"sqlite:///{database}"

        elif db_type == "mysql":
            host = params.get('host', 'localhost')
            port = params.get('port', 3306)
            database = params.get('database')
            username = params.get('username')
            password = params.get('password', '')
            return f"mysql+pymysql://{username}:{password}@{host}:{port}/{database}"

        elif db_type == "postgresql":
            host = params.get('host', 'localhost')
            port = params.get('port', 5432)
            database = params.get('database')
            username = params.get('username')
            password = params.get('password', '')
            return f"postgresql://{username}:{password}@{host}:{port}/{database}"

        else:
            raise ValueError(f"Unsupported database type: {db_type}")

    async def _security_check(self, query: str, security_level: str = "medium",
                            allowed_operations: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Validate SQL query for security issues.

        Test focus: SQL injection detection, operation validation, security levels.
        """
        try:
            query_clean = query.strip()
            query_upper = query_clean.upper()

            # Basic SQL syntax check
            if not query_upper:
                return {"valid": False, "error": "Empty query"}

            # Check for SQL injection patterns
            injection_patterns = [
                r"(--|#)",  # SQL comments
                r"/\*.*?\*/",  # Multi-line comments
                r"(;)\s*(\w+)",  # Multiple statements
                r"(xp_|sp_)",  # SQL Server extended procedures
                r"(union\s+select)",  # UNION injection
                r"(exec\s*\(|execute\s*\()",  # Execute commands
            ]

            for pattern in injection_patterns:
                if re.search(pattern, query_clean, re.IGNORECASE | re.DOTALL):
                    return {
                        "valid": False,
                        "error": f"Potential SQL injection pattern detected: {pattern}"
                    }

            # Extract operation type
            operation_match = re.match(r"^(\w+)", query_upper)
            operation = operation_match.group(1) if operation_match else "UNKNOWN"

            # Apply security level restrictions
            if security_level == "strict":
                allowed = ["SELECT"]
                if operation not in allowed:
                    return {
                        "valid": False,
                        "error": f"Strict mode: only {allowed} operations allowed"
                    }

            elif security_level == "high":
                dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
                if operation in dangerous:
                    return {
                        "valid": False,
                        "error": f"High security: {operation} operations not allowed"
                    }

            elif security_level == "medium":
                very_dangerous = ["DROP", "TRUNCATE", "DELETE DATABASE", "DROP DATABASE"]
                for dangerous_op in very_dangerous:
                    if dangerous_op in query_upper:
                        return {
                            "valid": False,
                            "error": f"Medium security: {dangerous_op} operations not allowed"
                        }

            # Custom allowed operations check
            if allowed_operations and operation not in allowed_operations:
                return {
                    "valid": False,
                    "error": f"Operation {operation} not in allowed operations: {allowed_operations}"
                }

            # Query length check
            if len(query_clean) > 10000:
                return {
                    "valid": False,
                    "error": "Query too long (max 10000 characters)"
                }

            return {
                "valid": True,
                "operation": operation,
                "security_level": security_level,
                "message": f"Query validation passed for {operation} operation"
            }

        except Exception as e:
            return {
                "valid": False,
                "error": f"Security check error: {str(e)}"
            }

    async def _execute_query(self, connection_name: str, query: str,
                           params: Optional[List[str]] = None, max_rows: int = 1000,
                           timeout: int = 60) -> Dict[str, Any]:
        """
        Execute validated SQL query safely.

        Test focus: Query execution, result processing, security validation.
        """
        try:
            if connection_name not in self.connections:
                return {
                    "success": False,
                    "error": f"Connection '{connection_name}' not established"
                }

            # Additional security check before execution
            security_result = await self._security_check(query)
            if not security_result["valid"]:
                return {
                    "success": False,
                    "error": f"Security validation failed: {security_result['error']}"
                }

            engine = self.connections[connection_name]

            # Execute with timeout and row limits
            with engine.connect() as conn:
                # Set statement timeout for PostgreSQL
                if engine.dialect.name == 'postgresql':
                    conn.execute(text(f"SET statement_timeout = {timeout * 1000}"))

                # Execute query
                if params:
                    result = conn.execute(text(query), params)
                else:
                    result = conn.execute(text(query))

                # Handle results
                if result.returns_rows:
                    rows = result.fetchmany(max_rows)
                    columns = list(result.keys())
                    data = [dict(zip(columns, row)) for row in rows]
                    row_count = len(data)
                    has_more = result.rowcount > max_rows if hasattr(result, 'rowcount') else False
                else:
                    data = []
                    columns = []
                    row_count = result.rowcount if hasattr(result, 'rowcount') else 0
                    has_more = False

                # Commit for write operations
                if not query.strip().upper().startswith('SELECT'):
                    conn.commit()

                # Return minimal, secure result
                return {
                    "success": True,
                    "operation": security_result["operation"],
                    "row_count": row_count,
                    "has_more": has_more,
                    "columns": columns,
                    "data": data,
                    "message": f"Query executed successfully ({row_count} rows)"
                }

        except SQLAlchemyError as e:
            logger.error(f"Database error: {str(e)}")
            return {
                "success": False,
                "error": f"Database error: {str(e)}",
                "query_preview": query[:100] + "..." if len(query) > 100 else query
            }
        except Exception as e:
            logger.error(f"Execution error: {str(e)}")
            return {
                "success": False,
                "error": f"Execution error: {str(e)}",
                "query_preview": query[:100] + "..." if len(query) > 100 else query
            }


# Create server instance
database_server = DatabaseMCPServer()


async def main():
    """Main function to run the MCP server."""
    async with stdio_server() as (read_stream, write_stream):
        await database_server.server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="database-mcp-server",
                server_version="1.0.0",
                capabilities=database_server.server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    asyncio.run(main())