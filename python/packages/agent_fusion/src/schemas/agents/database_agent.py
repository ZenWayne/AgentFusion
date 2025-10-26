"""
Database Agent Schemas for AgentFusion

This module contains Pydantic schemas for database agent configuration,
connection parameters, and operation settings.
"""

from typing import Dict, List, Optional, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator

class DatabaseType(str, Enum):
    """Supported database types."""
    SQLITE = "sqlite"
    MYSQL = "mysql"
    POSTGRESQL = "postgresql"
    AUTO_DETECT = "auto_detect"


class QueryMode(str, Enum):
    """Query execution modes."""
    READ_ONLY = "read_only"
    READ_WRITE = "read_write"
    ANALYSIS = "analysis"
    SCHEMA_ONLY = "schema_only"


class SecurityLevel(str, Enum):
    """Security levels for query execution."""
    LOW = "low"      # All queries allowed
    MEDIUM = "medium"  # No DROP/ALTER/TRUNCATE
    HIGH = "high"     # Only SELECT queries
    STRICT = "strict"  # Pre-approved queries only


class DatabaseConnection(BaseModel):
    """Database connection configuration."""
    database_type: DatabaseType = Field(
        default=DatabaseType.AUTO_DETECT,
        description="Type of database to connect to"
    )
    host: Optional[str] = Field(
        default=None,
        description="Database host (required for MySQL/PostgreSQL)"
    )
    port: Optional[int] = Field(
        default=None,
        description="Database port (auto-detected if not specified)"
    )
    database: str = Field(
        description="Database name"
    )
    username: Optional[str] = Field(
        default=None,
        description="Database username (required for MySQL/PostgreSQL)"
    )
    password: Optional[str] = Field(
        default=None,
        description="Database password"
    )
    schema_name: Optional[str] = Field(
        default=None,
        description="Schema name (for PostgreSQL)"
    )
    connection_string: Optional[str] = Field(
        default=None,
        description="Full connection string (overrides other settings)"
    )
    connection_timeout: int = Field(
        default=30,
        description="Connection timeout in seconds"
    )
    pool_size: int = Field(
        default=5,
        description="Connection pool size"
    )

    @field_validator('port')
    def validate_port(cls, v, values):
        """Validate and set default port based on database type."""
        if v is None:
            db_type = values.get('database_type')
            if db_type == DatabaseType.MYSQL:
                return 3306
            elif db_type == DatabaseType.POSTGRESQL:
                return 5432
            elif db_type == DatabaseType.SQLITE:
                return None
        return v


class QueryConstraints(BaseModel):
    """Query execution constraints and limits."""
    max_rows: int = Field(
        default=1000,
        description="Maximum rows to return per query"
    )
    timeout: int = Field(
        default=60,
        description="Query timeout in seconds"
    )
    allowed_operations: List[str] = Field(
        default=["SELECT", "INSERT", "UPDATE", "DELETE"],
        description="Allowed SQL operations"
    )
    forbidden_operations: List[str] = Field(
        default=["DROP", "TRUNCATE", "ALTER DATABASE"],
        description="Forbidden SQL operations"
    )
    max_query_length: int = Field(
        default=10000,
        description="Maximum query character length"
    )
    require_confirmation: bool = Field(
        default=True,
        description="Require confirmation for write operations"
    )


class AnalysisSettings(BaseModel):
    """Data analysis configuration."""
    auto_analyze: bool = Field(
        default=True,
        description="Automatically analyze query results"
    )
    statistical_methods: List[str] = Field(
        default=["count", "mean", "median", "std", "min", "max"],
        description="Statistical methods to apply"
    )
    visualization: bool = Field(
        default=True,
        description="Generate data visualization suggestions"
    )
    pattern_detection: bool = Field(
        default=True,
        description="Detect patterns and anomalies"
    )
    correlation_threshold: float = Field(
        default=0.7,
        description="Threshold for correlation detection"
    )


class DatabaseAgentConfig(BaseModel):
    """Complete database agent configuration."""
    name: str = Field(
        description="Agent name"
    )
    description: str = Field(
        description="Agent description"
    )
    model_client: str = Field(
        description="Model client to use"
    )

    # Database connection settings
    connections: Dict[str, DatabaseConnection] = Field(
        description="Database connection configurations"
    )
    default_connection: str = Field(
        description="Default connection name"
    )

    # Operation settings
    query_mode: QueryMode = Field(
        default=QueryMode.READ_WRITE,
        description="Default query mode"
    )
    security_level: SecurityLevel = Field(
        default=SecurityLevel.MEDIUM,
        description="Security level for query execution"
    )

    # Constraints and analysis
    constraints: QueryConstraints = Field(
        default_factory=QueryConstraints,
        description="Query execution constraints"
    )
    analysis: AnalysisSettings = Field(
        default_factory=AnalysisSettings,
        description="Data analysis settings"
    )

    # Introspection settings
    auto_introspect: bool = Field(
        default=True,
        description="Automatically introspect database schema"
    )
    cache_schema: bool = Field(
        default=True,
        description="Cache schema information"
    )
    schema_refresh_interval: int = Field(
        default=3600,
        description="Schema refresh interval in seconds"
    )

    # Logging and monitoring
    log_queries: bool = Field(
        default=True,
        description="Log all executed queries"
    )
    audit_mode: bool = Field(
        default=False,
        description="Enable detailed audit logging"
    )

    # Error handling
    retry_on_failure: bool = Field(
        default=True,
        description="Retry failed queries"
    )
    max_retries: int = Field(
        default=3,
        description="Maximum retry attempts"
    )

    @field_validator('default_connection')
    def validate_default_connection(cls, v, values):
        """Validate that default connection exists."""
        connections = values.get('connections', {})
        if v not in connections:
            raise ValueError(f"Default connection '{v}' not found in connections")
        return v


class DatabaseSchemaInfo(BaseModel):
    """Database schema information model."""
    database_name: str = Field(description="Database name")
    tables: Dict[str, Any] = Field(description="Table information")
    relationships: List[Dict[str, Any]] = Field(description="Table relationships")
    indexes: Dict[str, List[Dict[str, Any]]] = Field(description="Table indexes")
    last_updated: str = Field(description="Last schema update timestamp")

    class TableInfo(BaseModel):
        """Table information model."""
        name: str = Field(description="Table name")
        columns: List[Dict[str, Any]] = Field(description="Column information")
        primary_keys: List[str] = Field(description="Primary key columns")
        foreign_keys: List[Dict[str, Any]] = Field(description="Foreign key relationships")
        row_count: Optional[int] = Field(description="Estimated row count")
        sample_data: Optional[List[Dict[str, Any]]] = Field(description="Sample data")


class QueryResult(BaseModel):
    """Query execution result model."""
    query: str = Field(description="Executed query")
    success: bool = Field(description="Query execution status")
    data: Optional[List[Dict[str, Any]]] = Field(description="Query results")
    columns: Optional[List[str]] = Field(description="Column names")
    row_count: int = Field(default=0, description="Number of rows returned")
    execution_time: float = Field(description="Execution time in seconds")
    error_message: Optional[str] = Field(description="Error message if failed")
    warnings: List[str] = Field(default_factory=list, description="Execution warnings")

    # Analysis results
    analysis: Optional[Dict[str, Any]] = Field(description="Data analysis results")
    visualizations: Optional[List[Dict[str, Any]]] = Field(description="Visualization suggestions")