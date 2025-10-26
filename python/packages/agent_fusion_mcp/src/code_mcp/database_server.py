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
from dataclasses import dataclass
from datetime import datetime, timezone
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
from mcp.server.sse import SseServerTransport
from mcp.types import (
    Tool, TextContent, CallToolResult
)
from mcp.server.fastmcp import FastMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("database-mcp-server")

mcp_tool = FastMCP("database-mcp-server")


@dataclass
class DatabaseConnectionResponse:
    """Structured response for database connection operations"""
    success: bool
    connection_name: Optional[str] = None
    database_type: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    connection_url: Optional[str] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success
        }

        if self.connection_name is not None:
            result["connection_name"] = self.connection_name
        if self.database_type is not None:
            result["database_type"] = self.database_type
        if self.message is not None:
            result["message"] = self.message
        if self.error is not None:
            result["error"] = self.error
        if self.connection_url is not None:
            result["connection_url"] = self.connection_url
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp.isoformat()

        return result


@dataclass
class DatabaseSecurityCheckResponse:
    """Structured response for database security check operations"""
    valid: bool
    query_preview: Optional[str] = None
    security_level: Optional[str] = None
    detected_patterns: Optional[List[str]] = None
    allowed_operations: Optional[List[str]] = None
    error: Optional[str] = None
    warnings: Optional[List[str]] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "valid": self.valid
        }

        if self.query_preview is not None:
            result["query_preview"] = self.query_preview
        if self.security_level is not None:
            result["security_level"] = self.security_level
        if self.detected_patterns is not None:
            result["detected_patterns"] = self.detected_patterns
        if self.allowed_operations is not None:
            result["allowed_operations"] = self.allowed_operations
        if self.error is not None:
            result["error"] = self.error
        if self.warnings is not None:
            result["warnings"] = self.warnings
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp.isoformat()

        return result


@dataclass
class DatabaseQueryResponse:
    """Structured response for database query execution operations"""
    success: bool
    connection_name: Optional[str] = None
    query_preview: Optional[str] = None
    execution_time_seconds: Optional[float] = None
    rows_returned: Optional[int] = None
    columns: Optional[List[str]] = None
    data: Optional[List[Dict[str, Any]]] = None
    row_limit_reached: Optional[bool] = None
    error: Optional[str] = None
    security_warnings: Optional[List[str]] = None
    timestamp: Optional[datetime] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        result = {
            "success": self.success
        }

        if self.connection_name is not None:
            result["connection_name"] = self.connection_name
        if self.query_preview is not None:
            result["query_preview"] = self.query_preview
        if self.execution_time_seconds is not None:
            result["execution_time_seconds"] = self.execution_time_seconds
        if self.rows_returned is not None:
            result["rows_returned"] = self.rows_returned
        if self.columns is not None:
            result["columns"] = self.columns
        if self.data is not None:
            result["data"] = self.data
        if self.row_limit_reached is not None:
            result["row_limit_reached"] = self.row_limit_reached
        if self.error is not None:
            result["error"] = self.error
        if self.security_warnings is not None:
            result["security_warnings"] = self.security_warnings
        if self.timestamp is not None:
            result["timestamp"] = self.timestamp.isoformat()

        return result


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

                # Convert response objects to dictionary
                if isinstance(result, (DatabaseConnectionResponse, DatabaseSecurityCheckResponse, DatabaseQueryResponse)):
                    result = result.to_dict()
                elif not isinstance(result, dict):
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
                              connection_string: str, pool_size: int = 5, time_out: int = 30) -> DatabaseConnectionResponse:
        """
        Establish database connection with validation.

        Test focus: Connection establishment, validation, and storage.
        """
        try:
            if not sqlalchemy:
                raise ImportError("SQLAlchemy is required. Install with: pip install sqlalchemy")

            # Create engine with safety settings
            engine_kwargs = {
                'echo': False  # Don't log queries (security)
            }

            # Add pool settings only for non-SQLite databases
            if database_type != 'sqlite':
                engine_kwargs.update({
                    'pool_size': pool_size,
                    'pool_timeout': time_out,
                    'pool_recycle': 3600,  # Recycle connections hourly
                })
            else:
                raise NotImplementedError("not supported for SQLite")

            engine = create_engine(connection_string, **engine_kwargs)

            # Test connection with simple query
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))

            # Store connection
            self.connections[connection_name] = engine

            logger.info(f"Connected to database: {connection_name}")

            return DatabaseConnectionResponse(
                success=True,
                connection_name=connection_name,
                database_type=database_type,
                message=f"Successfully connected to {database_type} database",
                connection_url=connection_string,
                timestamp=datetime.now(timezone.utc)
            )

        except ImportError as e:
            return DatabaseConnectionResponse(
                success=False,
                connection_name=connection_name,
                error=f"Missing dependency: {str(e)}",
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Connection failed: {str(e)}")
            return DatabaseConnectionResponse(
                success=False,
                connection_name=connection_name,
                error=str(e),
                timestamp=datetime.now(timezone.utc)
            )

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
                            allowed_operations: Optional[List[str]] = None) -> DatabaseSecurityCheckResponse:
        """
        Validate SQL query for security issues.

        Test focus: SQL injection detection, operation validation, security levels.
        """
        try:
            query_clean = query.strip()
            query_upper = query_clean.upper()
            query_preview = query_clean[:100] + "..." if len(query_clean) > 100 else query_clean

            # Basic SQL syntax check
            if not query_upper:
                return DatabaseSecurityCheckResponse(
                    valid=False,
                    query_preview=query_preview,
                    security_level=security_level,
                    error="Empty query",
                    timestamp=datetime.now(timezone.utc)
                )

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
                    return DatabaseSecurityCheckResponse(
                        valid=False,
                        query_preview=query_preview,
                        security_level=security_level,
                        detected_patterns=[pattern],
                        error=f"Potential SQL injection pattern detected: {pattern}",
                        timestamp=datetime.now(timezone.utc)
                    )

            # Extract operation type
            operation_match = re.match(r"^(\w+)", query_upper)
            operation = operation_match.group(1) if operation_match else "UNKNOWN"

            # Apply security level restrictions
            if security_level == "strict":
                allowed = ["SELECT"]
                if operation not in allowed:
                    return DatabaseSecurityCheckResponse(
                        valid=False,
                        query_preview=query_preview,
                        security_level=security_level,
                        allowed_operations=allowed,
                        error=f"Strict mode: only {allowed} operations allowed",
                        timestamp=datetime.now(timezone.utc)
                    )

            elif security_level == "high":
                dangerous = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
                if operation in dangerous:
                    return DatabaseSecurityCheckResponse(
                        valid=False,
                        query_preview=query_preview,
                        security_level=security_level,
                        error=f"High security: {operation} operations not allowed",
                        timestamp=datetime.now(timezone.utc)
                    )

            elif security_level == "medium":
                very_dangerous = ["DROP", "TRUNCATE", "DELETE DATABASE", "DROP DATABASE"]
                for dangerous_op in very_dangerous:
                    if dangerous_op in query_upper:
                        return DatabaseSecurityCheckResponse(
                            valid=False,
                            query_preview=query_preview,
                            security_level=security_level,
                            error=f"Medium security: {dangerous_op} operations not allowed",
                            timestamp=datetime.now(timezone.utc)
                        )

            # Custom allowed operations check
            if allowed_operations and operation not in allowed_operations:
                return DatabaseSecurityCheckResponse(
                    valid=False,
                    query_preview=query_preview,
                    security_level=security_level,
                    allowed_operations=allowed_operations,
                    error=f"Operation {operation} not in allowed operations: {allowed_operations}",
                    timestamp=datetime.now(timezone.utc)
                )

            # Query length check
            if len(query_clean) > 10000:
                return DatabaseSecurityCheckResponse(
                    valid=False,
                    query_preview=query_preview,
                    security_level=security_level,
                    error="Query too long (max 10000 characters)",
                    timestamp=datetime.now(timezone.utc)
                )

            return DatabaseSecurityCheckResponse(
                valid=True,
                query_preview=query_preview,
                security_level=security_level,
                allowed_operations=allowed_operations,
                warnings=[f"Query validation passed for {operation} operation"],
                timestamp=datetime.now(timezone.utc)
            )

        except Exception as e:
            return DatabaseSecurityCheckResponse(
                valid=False,
                query_preview=query[:100] + "..." if len(query) > 100 else query,
                security_level=security_level,
                error=f"Security check error: {str(e)}",
                timestamp=datetime.now(timezone.utc)
            )

    async def _execute_query(self, connection_name: str, query: str,
                           params: Optional[List[str]] = None, max_rows: int = 1000,
                           timeout: int = 60) -> DatabaseQueryResponse:
        """
        Execute validated SQL query safely.

        Test focus: Query execution, result processing, security validation.
        """
        start_time = datetime.now(timezone.utc)
        query_preview = query[:100] + "..." if len(query) > 100 else query

        try:
            if connection_name not in self.connections:
                return DatabaseQueryResponse(
                    success=False,
                    connection_name=connection_name,
                    query_preview=query_preview,
                    error=f"Connection '{connection_name}' not established",
                    timestamp=datetime.now(timezone.utc)
                )

            # Additional security check before execution
            security_result = await self._security_check(query)
            if not security_result.valid:
                return DatabaseQueryResponse(
                    success=False,
                    connection_name=connection_name,
                    query_preview=query_preview,
                    error=f"Security validation failed: {security_result.error}",
                    security_warnings=[security_result.error] if security_result.error else None,
                    timestamp=datetime.now(timezone.utc)
                )

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

                # Calculate execution time
                end_time = datetime.now(timezone.utc)
                execution_time = (end_time - start_time).total_seconds()

                return DatabaseQueryResponse(
                    success=True,
                    connection_name=connection_name,
                    query_preview=query_preview,
                    execution_time_seconds=execution_time,
                    rows_returned=row_count,
                    columns=columns,
                    data=data,
                    row_limit_reached=has_more,
                    security_warnings=security_result.warnings,
                    timestamp=end_time
                )

        except SQLAlchemyError as e:
            logger.error(f"Database error: {str(e)}")
            return DatabaseQueryResponse(
                success=False,
                connection_name=connection_name,
                query_preview=query_preview,
                error=f"Database error: {str(e)}",
                execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                timestamp=datetime.now(timezone.utc)
            )
        except Exception as e:
            logger.error(f"Execution error: {str(e)}")
            return DatabaseQueryResponse(
                success=False,
                connection_name=connection_name,
                query_preview=query_preview,
                error=f"Execution error: {str(e)}",
                execution_time_seconds=(datetime.now(timezone.utc) - start_time).total_seconds(),
                timestamp=datetime.now(timezone.utc)
            )


# Create server instance
database_server = DatabaseMCPServer()

@mcp_tool.tool(structured_output=True)
async def connect_database(connection_name: str, database_type: str, connection_string: str) -> DatabaseConnectionResponse:
    """
    Establish a connection to a database.

    Test focus: Database connection establishment.
    """
    return await database_server._connect_database(connection_name, database_type, connection_string)

@mcp_tool.tool(structured_output=True)
async def security_check(query: str) -> DatabaseSecurityCheckResponse:
    """
    Perform a security check on a SQL query.

    Test focus: Query security validation.
    """
    return await database_server._security_check(query)

@mcp_tool.tool(structured_output=True)
async def execute_query(connection_name: str, query: str,
                 params: Optional[List[str]] = None, max_rows: int = 1000,
                 timeout: int = 60) -> DatabaseQueryResponse:
    """
    Execute a SQL query.

    Test focus: Query execution, result processing, security validation.
    """
    return await database_server._execute_query(connection_name, query, params, max_rows, timeout)

async def main():
    """Main function to run the MCP server."""
    pass

if __name__ == "__main__":
    mcp_tool.run(transport='sse')