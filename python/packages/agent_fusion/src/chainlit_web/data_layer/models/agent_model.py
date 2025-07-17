"""
Agent model for handling agent-related database operations.

This module provides functionality to manage agents in the database.
"""

import json
from typing import Dict, List, Any, Optional, TYPE_CHECKING
from .base_model import BaseModel
from schemas.agent import ComponentInfo, AgentType, AssistantAgentConfig, UserProxyAgentConfig

if TYPE_CHECKING:
    from chainlit_web.data_layer.base_data_layer import DBDataLayer


class AgentModel(BaseModel):
    """Agent model class"""
    
    def __init__(self, db_layer: "DBDataLayer"):
        super().__init__(db_layer)
    
    async def get_agents_for_chat_profile(self) -> Dict[str, ComponentInfo]:
        """
        Get agents for chat profile and return as ComponentInfo objects
        
        Returns:
            Dict[str, ComponentInfo]: Agent name to ComponentInfo mapping
        """
        query = """
        SELECT 
            a.name,
            a.label,
            a.description,
            a.config,
            mc.label as model_client_label,
            mc.config as model_client_config,
            pv.content as current_prompt
        FROM agents a
        LEFT JOIN model_clients mc ON a.model_client_id = mc.id
        LEFT JOIN prompts p ON a.id = p.agent_id
        LEFT JOIN prompt_versions pv ON p.id = pv.prompt_id AND pv.is_current = true
        WHERE a.is_active = true
        ORDER BY a.name
        """
        
        results = await self.execute_query(query)
        agent_info = {}
        
        for row in results:
            agent_name = row["name"]
            agent_config = json.loads(row["config"]) if row["config"] else {}
            
            # Base configuration
            base_config = {
                "name": agent_name,
                "description": row["description"] or "",
                "labels": agent_config.get("labels", [])
            }
            
            # Determine agent type
            agent_type = agent_config.get("type", "assistant_agent")
            
            if agent_type == AgentType.ASSISTANT_AGENT:
                # AssistantAgent configuration
                component_info = AssistantAgentConfig(
                    type=AgentType.ASSISTANT_AGENT,
                    model_client=row["model_client_label"] or "default",
                    prompt=lambda content=row["current_prompt"]: content or "",
                    mcp_tools=agent_config.get("mcp_tools"),
                    **base_config
                )
            else:
                # UserProxyAgent configuration
                component_info = UserProxyAgentConfig(
                    type=AgentType.USER_PROXY_AGENT,
                    input_func=agent_config.get("input_func", "input"),
                    **base_config
                )
            
            agent_info[agent_name] = component_info
        
        return agent_info
    
    async def get_group_chats_for_chat_profile(self) -> Dict[str, Any]:
        """
        Get group chats for chat profile
        
        Returns:
            Dict[str, Any]: GroupChat configuration mapping
        """
        # TODO: Implement group chat configuration loading
        # For now, return empty dict until GroupChat implementation is ready
        return {}
    
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
        try:
            # Find agent info
            agent_query = """
            SELECT a.id, p.id as prompt_id, p.prompt_id as prompt_business_id
            FROM agents a
            LEFT JOIN prompts p ON a.id = p.agent_id
            WHERE a.name = $1 AND a.is_active = true
            """
            
            agent_result = await self.execute_single_query(agent_query, [agent_name])
            if not agent_result:
                return False
            
            agent_id = agent_result["id"]
            prompt_id = agent_result["prompt_id"]
            prompt_business_id = agent_result["prompt_business_id"]
            
            # Create prompt if it doesn't exist
            if not prompt_id:
                prompt_business_id = f"{agent_name}_system"
                create_prompt_query = """
                INSERT INTO prompts (prompt_id, name, category, subcategory, description, agent_id, created_by)
                VALUES ($1, $2, 'agent', 'system_message', $3, $4, $5)
                RETURNING id
                """
                prompt_result = await self.execute_single_query(
                    create_prompt_query, 
                    [prompt_business_id, f"{agent_name} System Message", f"System message for {agent_name} agent", agent_id, changed_by]
                )
                prompt_id = prompt_result["id"]
            
            # Create new prompt version
            create_version_query = """
            SELECT create_prompt_version($1, $2, $3, $4, $5)
            """
            
            await self.execute_single_query(
                create_version_query,
                [prompt_business_id, new_prompt, version_label, changed_by, "Updated via API"]
            )
            
            return True
            
        except Exception as e:
            print(f"Error updating agent prompt: {e}")
            return False
    
    async def get_agent_prompt_history(self, agent_name: str) -> List[Dict[str, Any]]:
        """
        Get agent prompt version history
        
        Args:
            agent_name: Agent name
            
        Returns:
            List[Dict[str, Any]]: Prompt version history
        """
        query = """
        SELECT 
            pv.version_number,
            pv.version_label,
            pv.content,
            pv.status,
            pv.created_at,
            pv.is_current,
            u.username as created_by_username
        FROM agents a
        JOIN prompts p ON a.id = p.agent_id
        JOIN prompt_versions pv ON p.id = pv.prompt_id
        LEFT JOIN "User" u ON pv.created_by = u.id
        WHERE a.name = $1 AND a.is_active = true
        ORDER BY pv.version_number DESC
        """
        
        results = await self.execute_query(query, [agent_name])
        
        # Convert to list
        history = []
        for row in results:
            history.append({
                "version_number": row["version_number"],
                "version_label": row["version_label"],
                "content": row["content"],
                "status": row["status"],
                "created_at": row["created_at"].isoformat() if row["created_at"] else None,
                "is_current": row["is_current"],
                "created_by_username": row["created_by_username"]
            })
        
        return history