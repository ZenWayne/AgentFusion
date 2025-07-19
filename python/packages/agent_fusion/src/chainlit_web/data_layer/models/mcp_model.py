"""
MCP (Model Context Protocol) model for handling MCP server-related database operations.

This module provides functionality to manage MCP servers in the database.
"""

import json
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from .base_model import BaseModel
from autogen_ext.tools.mcp import McpServerParams, StdioServerParams, SseServerParams
from base.mcp import parse_mcp_server

if TYPE_CHECKING:
    from chainlit_web.data_layer.base_data_layer import DBDataLayer


class McpModel(BaseModel):
    """MCP model class"""
    
    def __init__(self, db_layer: "DBDataLayer"):
        super().__init__(db_layer)
    
    async def create_mcp_server(self, name: str, params: McpServerParams, description: Optional[str] = None, created_by: int = 1) -> Optional[int]:
        """
        Create a new MCP server
        
        Args:
            name: MCP server name
            params: McpServerParams (StdioServerParams or SseServerParams)
            description: Server description
            created_by: User ID who created the server
            
        Returns:
            Optional[int]: MCP server ID if successful, None otherwise
        """
        try:
            # Extract common fields
            command = None
            args = []
            env = {}
            url = None
            headers = {}
            timeout = 30
            sse_read_timeout = 30
            
            if isinstance(params, StdioServerParams):
                command = params.command
                args = params.args or []
                env = params.env or {}
            elif isinstance(params, SseServerParams):
                url = params.url
                headers = params.headers or {}
                timeout = getattr(params, 'timeout', 30)
                sse_read_timeout = getattr(params, 'sse_read_timeout', 30)
            
            query = """
            INSERT INTO mcp_servers (
                name, command, args, env, url, headers, timeout, sse_read_timeout, 
                description, created_by, updated_by
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING id
            """
            
            result = await self.execute_single_query(query, [
                name,
                command,
                json.dumps(args),
                json.dumps(env),
                url,
                json.dumps(headers),
                timeout,
                sse_read_timeout,
                description,
                created_by,
                created_by
            ])
            
            return result["id"] if result else None
            
        except Exception as e:
            print(f"Error creating MCP server: {e}")
            return None
    
    async def get_mcp_server(self, server_id: int) -> Optional[Dict[str, Any]]:
        """
        Get MCP server by ID
        
        Args:
            server_id: MCP server ID
            
        Returns:
            Optional[Dict[str, Any]]: MCP server data
        """
        query = """
        SELECT 
            id, server_uuid, name, command, args, env, url, headers, 
            timeout, sse_read_timeout, description, is_active, 
            created_at, updated_at, created_by, updated_by
        FROM mcp_servers
        WHERE id = $1 AND is_active = true
        """
        
        result = await self.execute_single_query(query, [server_id])
        if result:
            # Parse JSON fields
            result["args"] = json.loads(result["args"]) if result["args"] else []
            result["env"] = json.loads(result["env"]) if result["env"] else {}
            result["headers"] = json.loads(result["headers"]) if result["headers"] else {}
            
        return result
    
    async def get_mcp_server_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get MCP server by name
        
        Args:
            name: MCP server name
            
        Returns:
            Optional[Dict[str, Any]]: MCP server data
        """
        query = """
        SELECT 
            id, server_uuid, name, command, args, env, url, headers, 
            timeout, sse_read_timeout, description, is_active, 
            created_at, updated_at, created_by, updated_by
        FROM mcp_servers
        WHERE name = $1 AND is_active = true
        """
        
        result = await self.execute_single_query(query, [name])
        if result:
            # Parse JSON fields
            result["args"] = json.loads(result["args"]) if result["args"] else []
            result["env"] = json.loads(result["env"]) if result["env"] else {}
            result["headers"] = json.loads(result["headers"]) if result["headers"] else {}
            
        return result
    
    async def get_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """
        Get all active MCP servers
        
        Returns:
            List[Dict[str, Any]]: List of MCP server data
        """
        query = """
        SELECT 
            id, server_uuid, name, command, args, env, url, headers, 
            timeout, sse_read_timeout, description, is_active, 
            created_at, updated_at, created_by, updated_by
        FROM mcp_servers
        WHERE is_active = true
        ORDER BY name
        """
        
        results = await self.execute_query(query)
        
        # Parse JSON fields for all results
        for result in results:
            result["args"] = json.loads(result["args"]) if result["args"] else []
            result["env"] = json.loads(result["env"]) if result["env"] else {}
            result["headers"] = json.loads(result["headers"]) if result["headers"] else {}
            
        return results
    
    async def update_mcp_server(self, server_id: int, params: McpServerParams, updated_by: int = 1) -> bool:
        """
        Update MCP server
        
        Args:
            server_id: MCP server ID
            params: McpServerParams (StdioServerParams or SseServerParams)
            updated_by: User ID who updated the server
            
        Returns:
            bool: Whether update was successful
        """
        try:
            # Extract fields from McpServerParams
            command = None
            args = []
            env = {}
            url = None
            headers = {}
            timeout = 30
            sse_read_timeout = 30
            
            if isinstance(params, StdioServerParams):
                command = params.command
                args = params.args or []
                env = params.env or {}
            elif isinstance(params, SseServerParams):
                url = params.url
                headers = params.headers or {}
                timeout = getattr(params, 'timeout', 30)
                sse_read_timeout = getattr(params, 'sse_read_timeout', 30)
            
            query = """
            UPDATE mcp_servers 
            SET command = $2, args = $3, env = $4, url = $5, headers = $6, 
                timeout = $7, sse_read_timeout = $8, updated_by = $9
            WHERE id = $1 AND is_active = true
            """
            
            await self.execute_command(query, [
                server_id,
                command,
                json.dumps(args),
                json.dumps(env),
                url,
                json.dumps(headers),
                timeout,
                sse_read_timeout,
                updated_by
            ])
            
            return True
            
        except Exception as e:
            print(f"Error updating MCP server: {e}")
            return False
    
    async def delete_mcp_server(self, server_id: int, updated_by: int = 1) -> bool:
        """
        Delete MCP server (soft delete by setting is_active = false)
        
        Args:
            server_id: MCP server ID
            updated_by: User ID who deleted the server
            
        Returns:
            bool: Whether deletion was successful
        """
        try:
            query = """
            UPDATE mcp_servers 
            SET is_active = false, updated_by = $2
            WHERE id = $1
            """
            
            await self.execute_command(query, [server_id, updated_by])
            return True
            
        except Exception as e:
            print(f"Error deleting MCP server: {e}")
            return False
    
    async def get_mcp_servers_for_config(self) -> Dict[str, Dict[str, Any]]:
        """
        Get MCP servers formatted for configuration usage
        
        Returns:
            Dict[str, Dict[str, Any]]: MCP servers in config format
        """
        servers = await self.get_all_mcp_servers()
        config_format = {}
        
        for server in servers:
            server_config = {}
            
            # Determine server type based on available fields
            if server["command"]:
                server_config["type"] = "StdioServerParams"
                server_config["command"] = server["command"]
                server_config["args"] = server["args"]
                server_config["env"] = server["env"]
            elif server["url"]:
                server_config["type"] = "SseServerParams"
                server_config["url"] = server["url"]
                server_config["headers"] = server["headers"]
                server_config["timeout"] = server["timeout"]
                server_config["sse_read_timeout"] = server["sse_read_timeout"]
            
            config_format[server["name"]] = server_config
                
        return config_format
    
    async def get_mcp_server_params(self, server_id: int) -> Optional[McpServerParams]:
        """
        Get McpServerParams object from database
        
        Args:
            server_id: MCP server ID
            
        Returns:
            Optional[McpServerParams]: Parsed McpServerParams object
        """
        server_data = await self.get_mcp_server(server_id)
        if not server_data:
            return None
        
        # Convert to config format and parse
        if server_data["command"]:
            config = {
                "type": "StdioServerParams",
                "command": server_data["command"],
                "args": server_data["args"],
                "env": server_data["env"]
            }
        elif server_data["url"]:
            config = {
                "type": "SseServerParams",
                "url": server_data["url"],
                "headers": server_data["headers"],
                "timeout": server_data["timeout"],
                "sse_read_timeout": server_data["sse_read_timeout"]
            }
        else:
            return None
        
        return parse_mcp_server(config)