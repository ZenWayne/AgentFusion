"""
Agent model for handling agent-related database operations.

This module provides functionality to manage agents in the database.
"""

from typing import Dict, List, Any, Optional, TYPE_CHECKING

#use mcp_tables.py and agent_table.py
from .base_model import ComponentModel
from .tables import AgentTable, ModelClientTable, PromptTable, PromptVersionTable, McpServerTable, AgentMcpServerTable
from schemas.component import ComponentInfo
from schemas.types import ComponentType
from schemas.agent import AgentType, AssistantAgentConfig, UserProxyAgentConfig
from .prompt_model import PromptModel
from .mcp_model import McpModel
from builders.agent_builder import AgentBuilder

from sqlalchemy import select, insert, update, and_, Column, Integer, String, Text, Boolean, DateTime, ForeignKey, UUID, ARRAY
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import JSONB

from data_layer.models.llm_model import LLMModel

if TYPE_CHECKING:
    from data_layer.base_data_layer import DBDataLayer



class AgentModel(ComponentModel, AgentBuilder):
    """Agent model class"""
    table_class = AgentTable
    uuid_column_name = "agent_uuid"
    name_column_name = "name"
    
    def __init__(self, db_layer: "DBDataLayer"):
        super().__init__(db_layer)
        self.prompt_model = PromptModel(db_layer)
        self.mcp_model = McpModel(db_layer)
    
    def model_client_builder(self) -> LLMModel:
        return LLMModel(self.db)
    
    async def get_all_components(self, filter_active: bool = True) -> List[ComponentInfo]:
        """
        Get agents for chat profile and return as ComponentInfo objects
        
        Returns:
            Dict[str, ComponentInfo]: Agent name to ComponentInfo mapping
        """
        async with await self.db.get_session() as session:
            # Build query with joins
            stmt = select(
                AgentTable,
                ModelClientTable.label.label('model_client_label'),
                PromptVersionTable.content.label('current_prompt')
            ).select_from(
                AgentTable.__table__.outerjoin(ModelClientTable.__table__, AgentTable.model_client_id == ModelClientTable.id)
                .outerjoin(PromptTable.__table__, AgentTable.id == PromptTable.agent_id)
                .outerjoin(PromptVersionTable.__table__, and_(
                    PromptTable.id == PromptVersionTable.prompt_id,
                    PromptVersionTable.is_current == True
                ))
            )
            
            if filter_active:
                stmt = stmt.where(AgentTable.is_active == True)
                
            stmt = stmt.order_by(AgentTable.name)
            
            result = await session.execute(stmt)
            rows = result.all()
            
            agent_info = []
            
            for row in rows:
                agent = row[0]  # AgentTable object
                component_info = await self.to_component_info(agent)
                agent_info.append(component_info)
            
            return agent_info
    
    async def to_component_info(self, table_row: AgentTable) -> ComponentInfo:
        """将组件信息转换为ComponentInfo对象"""
        async with await self.db.get_session() as session:
            # Build query with joins to get model client label
            stmt = select(
                ModelClientTable.label.label('model_client_label')
            ).select_from(
                AgentTable.__table__.outerjoin(ModelClientTable.__table__, AgentTable.model_client_id == ModelClientTable.id)
            ).where(AgentTable.id == table_row.id)
            
            result = await session.execute(stmt)
            row = result.first()
            
            model_client_label = row[0] if row else None
            
            # Get current prompt content from PromptModel
            current_prompt = await self.prompt_model.get_current_prompt_content(ComponentType.AGENT, table_row.name)
            
            # Get MCP servers from relationship table instead of config
            mcp_servers_stmt = select(
                McpServerTable.name
            ).select_from(
                AgentMcpServerTable.__table__.join(
                    McpServerTable.__table__, 
                    AgentMcpServerTable.mcp_server_id == McpServerTable.id
                )
            ).where(
                and_(
                    AgentMcpServerTable.agent_id == table_row.id,
                    AgentMcpServerTable.is_active == True,
                    McpServerTable.is_active == True
                )
            )
            
            mcp_result = await session.execute(mcp_servers_stmt)
            mcp_server_names = [row[0] for row in mcp_result.all()]
            
            # Base configuration using dedicated columns
            # Handle labels - deserialize from JSON string if needed (SQLite compatibility)
            labels = table_row.labels or []
            if isinstance(labels, str):
                import json
                try:
                    labels = json.loads(labels)
                except (json.JSONDecodeError, ValueError):
                    labels = []
            
            base_config = {
                "name": table_row.name,
                "description": table_row.description or "",
                "labels": labels
            }
            
            # Use dedicated agent_type column
            agent_type = table_row.agent_type or "assistant_agent"
            
            if agent_type in [AgentType.ASSISTANT_AGENT, AgentType.CODE_AGENT]:
                # Load MCP tools from relationship table
                mcp_tools = None
                if mcp_server_names:
                    mcp_tools = []
                    for server_name in mcp_server_names:
                        server_params = await self.mcp_model.get_mcp_server_params_by_name(server_name)
                        if server_params:
                            mcp_tools.append(server_params)
                
                # Handle handoff_tools - deserialize from JSON if needed
                handoff_tools = table_row.handoff_tools or []
                if isinstance(handoff_tools, str):
                    import json
                    try:
                        handoff_tools = json.loads(handoff_tools)
                    except (json.JSONDecodeError, ValueError):
                        handoff_tools = []
                
                # Convert dict list to HandoffTools objects if needed
                from schemas.agent import HandoffTools
                handoff_tools_objects = None
                if handoff_tools:
                    handoff_tools_objects = []
                    for tool in handoff_tools:
                        if isinstance(tool, dict):
                            handoff_tools_objects.append(HandoffTools(**tool))
                        else:
                            handoff_tools_objects.append(tool)
                
                return AssistantAgentConfig(
                    type=agent_type,
                    model_client=model_client_label or "default",
                    prompt=lambda content=current_prompt: content or "",
                    mcp_tools=mcp_tools,
                    handoff_tools=handoff_tools_objects,
                    **base_config
                )
            else:
                return UserProxyAgentConfig(
                    type=AgentType.USER_PROXY_AGENT,
                    input_func=table_row.input_func or "input",
                    **base_config
                ) 

    async def update_component_by_id(self, component_id: int, component_info: ComponentInfo) -> ComponentInfo:
        """根据组件主键ID更新组件信息"""
        async with await self.db.get_session() as session:
            try:
                # Check if agent exists first
                check_stmt = select(AgentTable.id).where(and_(
                    AgentTable.id == component_id,
                    AgentTable.is_active == True
                ))
                result = await session.execute(check_stmt)
                if not result.scalar_one_or_none():
                    raise ValueError(f"Agent with ID '{component_id}' not found")
                
                # Prepare update values using dedicated columns
                # Handle labels - serialize to JSON string if needed (SQLite compatibility)
                labels = component_info.labels
                if isinstance(labels, list):
                    import json
                    labels = json.dumps(labels)
                
                update_values = {
                    "name": component_info.name,
                    "description": component_info.description,
                    "agent_type": component_info.type,
                    "labels": labels,
                    "updated_at": func.current_timestamp()
                }
                
                # Add input_func if it exists (for UserProxyAgent)
                if hasattr(component_info, 'input_func'):
                    update_values["input_func"] = component_info.input_func
                
                # Add handoff_tools if it exists (for AssistantAgent)
                if hasattr(component_info, 'handoff_tools') and component_info.handoff_tools is not None:
                    import json
                    # Convert HandoffTools objects to dict for JSON serialization
                    handoff_tools_list = []
                    for tool in component_info.handoff_tools:
                        if hasattr(tool, 'model_dump'):  # Pydantic model
                            handoff_tools_list.append(tool.model_dump())
                        elif hasattr(tool, 'dict'):  # Pydantic v1 style
                            handoff_tools_list.append(tool.dict())
                        elif isinstance(tool, dict):
                            handoff_tools_list.append(tool)
                        else:
                            # Fallback for other objects
                            handoff_tools_list.append({"target": str(tool.target), "message": str(tool.message)})
                    update_values["handoff_tools"] = handoff_tools_list
                
                # Use UPDATE statement instead of modifying ORM object
                update_stmt = update(AgentTable).where(
                    AgentTable.id == component_id
                ).values(**update_values)
                
                await session.execute(update_stmt)
                await session.commit()
                
                # Get updated agent for return
                select_stmt = select(AgentTable).where(AgentTable.id == component_id)
                result = await session.execute(select_stmt)
                updated_agent = result.scalar_one()
                
                return await self.to_component_info(updated_agent)
                
            except Exception as e:
                await session.rollback()
                raise ValueError(f"Agent with ID '{component_id}' update failed: {e}")
    
    
    async def update_agent_prompt(self, agent_name: str, new_prompt: str, version_label: Optional[str] = None, changed_by: int = 1) -> bool:
        """
        Update agent prompt
        
        Args:
            agent_name: Agent name
            new_prompt: New prompt content
            version_label: Version label
            changed_by: User ID who made the change
            
        Returns:
            bool: Whether update was successful
        """
        return await self.prompt_model.update_agent_prompt(agent_name, new_prompt, version_label, changed_by)
    
    async def get_agent_prompt_history(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get agent prompt version history
        
        Args:
            agent_name: Agent name
            
        Returns:
            List[Dict[str, Any]]: Prompt version history
        """
        return await self.prompt_model.get_agent_prompt_history(agent_name)
    
    async def add_mcp_server_to_agent(self, agent_name: str, server_name: str, updated_by: int = 1) -> bool:
        """
        Add an MCP server to an agent via relationship table
        
        Args:
            agent_name: Agent name
            server_name: MCP server name
            updated_by: User ID who made the change
            
        Returns:
            bool: Whether the operation was successful
        """
        async with await self.db.get_session() as session:
            try:
                # Get the agent ID
                agent_stmt = select(AgentTable.id).where(and_(
                    AgentTable.name == agent_name,
                    AgentTable.is_active == True
                ))
                agent_result = await session.execute(agent_stmt)
                agent_id = agent_result.scalar_one_or_none()
                
                if not agent_id:
                    return False
                
                # Get the MCP server ID
                server_stmt = select(McpServerTable.id).where(and_(
                    McpServerTable.name == server_name,
                    McpServerTable.is_active == True
                ))
                server_result = await session.execute(server_stmt)
                server_id = server_result.scalar_one_or_none()
                
                if not server_id:
                    return False
                
                # Check if relationship already exists
                existing_stmt = select(AgentMcpServerTable.id).where(and_(
                    AgentMcpServerTable.agent_id == agent_id,
                    AgentMcpServerTable.mcp_server_id == server_id
                ))
                existing_result = await session.execute(existing_stmt)
                existing_id = existing_result.scalar_one_or_none()
                
                if existing_id:
                    # Reactivate if exists but inactive
                    update_stmt = update(AgentMcpServerTable).where(
                        AgentMcpServerTable.id == existing_id
                    ).values(is_active=True)
                    await session.execute(update_stmt)
                else:
                    # Insert new relationship
                    insert_stmt = insert(AgentMcpServerTable).values(
                        agent_id=agent_id,
                        mcp_server_id=server_id,
                        created_by=updated_by
                    )
                    await session.execute(insert_stmt)
                
                await session.commit()
                return True
                
            except Exception as e:
                await session.rollback()
                print(f"Error adding MCP server to agent: {e}")
                return False
    
    async def remove_mcp_server_from_agent(self, agent_name: str, server_name: str, updated_by: int = 1) -> bool:
        """
        Remove an MCP server from an agent via relationship table
        
        Args:
            agent_name: Agent name
            server_name: MCP server name
            updated_by: User ID who made the change
            
        Returns:
            bool: Whether the operation was successful
        """
        async with await self.db.get_session() as session:
            try:
                # Get the agent ID
                agent_stmt = select(AgentTable.id).where(and_(
                    AgentTable.name == agent_name,
                    AgentTable.is_active == True
                ))
                agent_result = await session.execute(agent_stmt)
                agent_id = agent_result.scalar_one_or_none()
                
                if not agent_id:
                    return False
                
                # Get the MCP server ID
                server_stmt = select(McpServerTable.id).where(and_(
                    McpServerTable.name == server_name,
                    McpServerTable.is_active == True
                ))
                server_result = await session.execute(server_stmt)
                server_id = server_result.scalar_one_or_none()
                
                if not server_id:
                    return False
                
                # Deactivate the relationship (soft delete)
                update_stmt = update(AgentMcpServerTable).where(and_(
                    AgentMcpServerTable.agent_id == agent_id,
                    AgentMcpServerTable.mcp_server_id == server_id
                )).values(is_active=False)
                
                result = await session.execute(update_stmt)
                await session.commit()
                
                return result.rowcount > 0
                
            except Exception as e:
                await session.rollback()
                print(f"Error removing MCP server from agent: {e}")
                return False
    
    async def get_agent_mcp_servers(self, agent_name: str) -> List[str]:
        """
        Get list of MCP server names associated with an agent from relationship table
        
        Args:
            agent_name: Agent name
            
        Returns:
            List[str]: List of MCP server names
        """
        async with await self.db.get_session() as session:
            try:
                # Get MCP server names via relationship table
                stmt = select(
                    McpServerTable.name
                ).select_from(
                    AgentTable.__table__.join(
                        AgentMcpServerTable.__table__, 
                        AgentTable.id == AgentMcpServerTable.agent_id
                    ).join(
                        McpServerTable.__table__, 
                        AgentMcpServerTable.mcp_server_id == McpServerTable.id
                    )
                ).where(
                    and_(
                        AgentTable.name == agent_name,
                        AgentTable.is_active == True,
                        AgentMcpServerTable.is_active == True,
                        McpServerTable.is_active == True
                    )
                )
                
                result = await session.execute(stmt)
                return [row[0] for row in result.all()]
                
            except Exception as e:
                print(f"Error getting agent MCP servers: {e}")
                return []