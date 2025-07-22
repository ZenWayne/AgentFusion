"""
MCP (Model Context Protocol) model for handling MCP server-related database operations.

This module provides functionality to manage MCP servers in the database using ORM.
"""

import json
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from datetime import datetime

from .base_model import BaseModel, ComponentModel, BaseComponentTable
from schemas.mcp import McpServerConfig
from schemas.types import ComponentType
from autogen_ext.tools.mcp import McpServerParams, StdioServerParams, SseServerParams
from base.mcp import parse_mcp_server
from sqlalchemy import select, insert, update, and_, UUID, Column, Integer, String, Text, Boolean, DateTime
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import JSONB
from .tables import McpServerTable

if TYPE_CHECKING:
    from data_layer.base_data_layer import DBDataLayer





class McpModel(ComponentModel):
    """MCP model class"""
    table_class = McpServerTable
    uuid_column_name = "server_uuid"
    name_column_name = "name"
    
    async def to_component_info(self, model: McpServerTable) -> McpServerConfig:
        """Convert SQLAlchemy model to McpServerConfig"""
        # Determine server type
        server_type = None
        if model.command:
            server_type = "stdio"
        elif model.url:
            server_type = "sse"
        
        return McpServerConfig(
            type=ComponentType.MCP,
            name=model.name,
            description=model.description,
            command=model.command,
            args=model.args or [],
            env=model.env or {},
            url=model.url,
            headers=model.headers or {},
            timeout=model.timeout or 30,
            sse_read_timeout=model.sse_read_timeout or 30,
            server_type=server_type,
            is_active=model.is_active,
            server_uuid=str(model.server_uuid) if model.server_uuid else None
        )
    
    async def _update_mcp_server(self, server_id: int, **kwargs) -> bool:
        """Update MCP server (internal method)"""
        async with await self.db.get_session() as session:
            try:
                stmt = select(McpServerTable).where(McpServerTable.id == server_id)
                result = await session.execute(stmt)
                model = result.scalar_one_or_none()
                
                if not model:
                    return False
                
                # Update fields
                for field, value in kwargs.items():
                    if hasattr(model, field):
                        setattr(model, field, value)
                
                # Update timestamp
                model.updated_at = func.current_timestamp()
                
                await session.commit()
                return True
            except Exception as e:
                await session.rollback()
                print(f"Error updating MCP server: {e}")
                return False
    
    async def update_component_by_id(self, component_id: int, mcp_config: McpServerConfig) -> Optional[McpServerConfig]:
        """Update MCP server by component ID"""
        # Prepare update data
        update_data = {
            "name": mcp_config.name,
            "description": mcp_config.description,
            "command": mcp_config.command,
            "args": mcp_config.args,
            "env": mcp_config.env,
            "url": mcp_config.url,
            "headers": mcp_config.headers,
            "timeout": mcp_config.timeout,
            "sse_read_timeout": mcp_config.sse_read_timeout
        }
        
        update_success = await self._update_mcp_server(component_id, **update_data)
        
        if not update_success:
            return None
        
        updated_server = await self.get_component_by_id(component_id)
        return updated_server
    
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
        async with await self.db.get_session() as session:
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
                
                # Create new MCP server
                new_server = McpServerTable(
                    name=name,
                    command=command,
                    args=args,
                    env=env,
                    url=url,
                    headers=headers,
                    timeout=timeout,
                    sse_read_timeout=sse_read_timeout,
                    description=description,
                    created_by=created_by,
                    updated_by=created_by
                )
                
                session.add(new_server)
                await session.commit()
                await session.refresh(new_server)
                
                return new_server.id
                
            except Exception as e:
                await session.rollback()
                print(f"Error creating MCP server: {e}")
                return None
    
    async def get_mcp_server(self, server_id: int) -> Optional[Dict[str, Any]]:
        """
        Get MCP server by ID (legacy method for backward compatibility)
        
        Args:
            server_id: MCP server ID
            
        Returns:
            Optional[Dict[str, Any]]: MCP server data
        """
        config = await self.get_component_by_id(server_id)
        if not config:
            return None
            
        return {
            "id": server_id,
            "server_uuid": config.server_uuid,
            "name": config.name,
            "command": config.command,
            "args": config.args,
            "env": config.env,
            "url": config.url,
            "headers": config.headers,
            "timeout": config.timeout,
            "sse_read_timeout": config.sse_read_timeout,
            "description": config.description,
            "is_active": config.is_active
        }
    
    async def get_mcp_server_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get MCP server by name (legacy method for backward compatibility)
        
        Args:
            name: MCP server name
            
        Returns:
            Optional[Dict[str, Any]]: MCP server data
        """
        config = await self.get_component_by_name(name)
        if not config:
            return None
            
        # Get server ID for legacy compatibility
        server_id = await self.get_component_id_by_uuid(config.server_uuid)
        
        return {
            "id": server_id,
            "server_uuid": config.server_uuid,
            "name": config.name,
            "command": config.command,
            "args": config.args,
            "env": config.env,
            "url": config.url,
            "headers": config.headers,
            "timeout": config.timeout,
            "sse_read_timeout": config.sse_read_timeout,
            "description": config.description,
            "is_active": config.is_active
        }
    
    async def get_all_mcp_servers(self) -> List[Dict[str, Any]]:
        """
        Get all active MCP servers (legacy method for backward compatibility)
        
        Returns:
            List[Dict[str, Any]]: List of MCP server data
        """
        configs = await self.get_all_active_components()
        results = []
        
        for config in configs:
            server_id = await self.get_component_id_by_uuid(config.server_uuid)
            results.append({
                "id": server_id,
                "server_uuid": config.server_uuid,
                "name": config.name,
                "command": config.command,
                "args": config.args,
                "env": config.env,
                "url": config.url,
                "headers": config.headers,
                "timeout": config.timeout,
                "sse_read_timeout": config.sse_read_timeout,
                "description": config.description,
                "is_active": config.is_active
            })
            
        return results
    
    async def update_mcp_server(self, server_id: int, params: McpServerParams, updated_by: int = 1) -> bool:
        """
        Update MCP server (legacy method for backward compatibility)
        
        Args:
            server_id: MCP server ID
            params: McpServerParams (StdioServerParams or SseServerParams)
            updated_by: User ID who updated the server
            
        Returns:
            bool: Whether update was successful
        """
        try:
            # Get current server config
            current_config = await self.get_component_by_id(server_id)
            if not current_config:
                return False
            
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
            
            # Create updated config
            updated_config = McpServerConfig(
                type=ComponentType.MCP,
                name=current_config.name,
                description=current_config.description,
                command=command,
                args=args,
                env=env,
                url=url,
                headers=headers,
                timeout=timeout,
                sse_read_timeout=sse_read_timeout,
                is_active=current_config.is_active,
                server_uuid=current_config.server_uuid
            )
            
            result = await self.update_component_by_id(server_id, updated_config)
            return result is not None
            
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
            return await self.deactivate_component(server_id)
        except Exception as e:
            print(f"Error deleting MCP server: {e}")
            return False
    
    async def get_mcp_servers_for_config(self) -> Dict[str, Dict[str, Any]]:
        """
        Get MCP servers formatted for configuration usage
        
        Returns:
            Dict[str, Dict[str, Any]]: MCP servers in config format
        """
        configs = await self.get_all_active_components()
        config_format = {}
        
        for config in configs:
            server_config = {}
            
            # Determine server type based on available fields
            if config.command:
                server_config["type"] = "StdioServerParams"
                server_config["command"] = config.command
                server_config["args"] = config.args
                server_config["env"] = config.env
            elif config.url:
                server_config["type"] = "SseServerParams"
                server_config["url"] = config.url
                server_config["headers"] = config.headers
                server_config["timeout"] = config.timeout
                server_config["sse_read_timeout"] = config.sse_read_timeout
            
            config_format[config.name] = server_config
                
        return config_format
    
    async def get_mcp_server_params(self, server_id: int) -> Optional[McpServerParams]:
        """
        Get McpServerParams object from database
        
        Args:
            server_id: MCP server ID
            
        Returns:
            Optional[McpServerParams]: Parsed McpServerParams object
        """
        config = await self.get_component_by_id(server_id)
        if not config:
            return None
        
        # Convert to config format and parse
        if config.command:
            server_config = {
                "type": "StdioServerParams",
                "command": config.command,
                "args": config.args,
                "env": config.env
            }
        elif config.url:
            server_config = {
                "type": "SseServerParams",
                "url": config.url,
                "headers": config.headers,
                "timeout": config.timeout,
                "sse_read_timeout": config.sse_read_timeout
            }
        else:
            return None
        
        return parse_mcp_server(server_config)
    
    async def get_mcp_server_params_by_name(self, server_name: str) -> Optional[McpServerParams]:
        """
        Get McpServerParams object from database by server name
        
        Args:
            server_name: MCP server name
            
        Returns:
            Optional[McpServerParams]: Parsed McpServerParams object
        """
        server_data = await self.get_mcp_server_by_name(server_name)
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