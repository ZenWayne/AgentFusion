"""
MCP (Model Context Protocol) server configuration schema
"""

from typing import Optional, Dict, List, Any
from pydantic import BaseModel, Field
from .types import ComponentType


class McpServerConfig(BaseModel):
    """MCP server configuration schema"""
    type: ComponentType = Field(default=ComponentType.MCP)
    name: str = Field(..., description="MCP server name")
    description: Optional[str] = Field(None, description="Server description")

    # Stdio server parameters
    command: Optional[str] = Field(None, description="Command to run for stdio server")
    args: Optional[List[str]] = Field(None, description="Arguments for stdio server")
    env: Optional[Dict[str, str]] = Field(None, description="Environment variables for stdio server")

    # SSE server parameters
    url: Optional[str] = Field(None, description="URL for SSE server")
    headers: Optional[Dict[str, str]] = Field(None, description="Headers for SSE server")
    timeout: Optional[int] = Field(30, description="Timeout for SSE server")
    sse_read_timeout: Optional[int] = Field(30, description="SSE read timeout")
    read_timeout_seconds: Optional[int] = Field(5, description="Read timeout in seconds")

    # Server type metadata
    server_type: Optional[str] = Field(None, description="Type of server (stdio/sse)")

    # Common fields
    is_active: bool = Field(True, description="Whether the server is active")
    server_uuid: Optional[str] = Field(None, description="Server UUID")
    
    @property
    def is_stdio_server(self) -> bool:
        """Check if this is a stdio server"""
        return self.command is not None
    
    @property
    def is_sse_server(self) -> bool:
        """Check if this is an SSE server"""
        return self.url is not None