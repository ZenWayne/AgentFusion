"""
LLM模型类

处理LLM模型相关的所有数据库操作，从model_clients表加载模型信息
"""

import json
from typing import Optional, Dict, Any, List
from datetime import datetime
from dataclasses import dataclass

from chainlit_web.data_layer.models.base_model import BaseModel


@dataclass
class LLMModelInfo:
    """LLM模型信息数据类"""
    id: int
    client_uuid: str
    label: str
    provider: str
    description: Optional[str]
    model_name: Optional[str]
    base_url: Optional[str]
    model_info: Dict[str, Any]
    config: Dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class LLMModel(BaseModel):
    """LLM模型数据模型"""
    
    async def get_all_active_models(self) -> List[LLMModelInfo]:
        """获取所有活跃的模型客户端"""
        query = """
        SELECT id, client_uuid, label, provider, description, model_name, 
               base_url, model_info, config, is_active, created_at, updated_at
        FROM model_clients 
        WHERE is_active = TRUE
        ORDER BY label
        """
        results = await self.execute_query(query)
        
        models = []
        for result in results:
            model_info = LLMModelInfo(
                id=result["id"],
                client_uuid=str(result["client_uuid"]),
                label=result["label"],
                provider=result["provider"],
                description=result["description"],
                model_name=result["model_name"],
                base_url=result["base_url"],
                model_info=result["model_info"] if result["model_info"] else {},
                config=result["config"] if result["config"] else {},
                is_active=result["is_active"],
                created_at=result["created_at"],
                updated_at=result["updated_at"]
            )
            models.append(model_info)
        
        return models
    
    async def get_model_by_label(self, label: str) -> Optional[LLMModelInfo]:
        """根据标签获取模型信息"""
        query = """
        SELECT id, client_uuid, label, provider, description, model_name, 
               base_url, model_info, config, is_active, created_at, updated_at
        FROM model_clients 
        WHERE label = $1 AND is_active = TRUE
        """
        result = await self.execute_single_query(query, [label])
        
        if not result:
            return None
        
        return LLMModelInfo(
            id=result["id"],
            client_uuid=str(result["client_uuid"]),
            label=result["label"],
            provider=result["provider"],
            description=result["description"],
            model_name=result["model_name"],
            base_url=result["base_url"],
            model_info=result["model_info"] if result["model_info"] else {},
            config=result["config"] if result["config"] else {},
            is_active=result["is_active"],
            created_at=result["created_at"],
            updated_at=result["updated_at"]
        )
    
    async def get_model_by_id(self, model_id: int) -> Optional[LLMModelInfo]:
        """根据ID获取模型信息"""
        query = """
        SELECT id, client_uuid, label, provider, description, model_name, 
               base_url, model_info, config, is_active, created_at, updated_at
        FROM model_clients 
        WHERE id = $1 AND is_active = TRUE
        """
        result = await self.execute_single_query(query, [model_id])
        
        if not result:
            return None
        
        return LLMModelInfo(
            id=result["id"],
            client_uuid=str(result["client_uuid"]),
            label=result["label"],
            provider=result["provider"],
            description=result["description"],
            model_name=result["model_name"],
            base_url=result["base_url"],
            model_info=result["model_info"] if result["model_info"] else {},
            config=result["config"] if result["config"] else {},
            is_active=result["is_active"],
            created_at=result["created_at"],
            updated_at=result["updated_at"]
        )
    
    async def get_model_labels_for_chat_settings(self) -> List[Dict[str, Any]]:
        """获取用于聊天设置的模型标签列表"""
        query = """
        SELECT label, description, model_name, model_info
        FROM model_clients 
        WHERE is_active = TRUE
        ORDER BY label
        """
        results = await self.execute_query(query)
        
        model_options = []
        for result in results:
            model_info = result["model_info"] or {}
            model_options.append({
                "label": result["label"],
                "description": result["description"] or "",
                "model_name": result["model_name"] or "",
                "capabilities": {
                    "vision": model_info.get("vision", False),
                    "function_calling": model_info.get("function_calling", False),
                    "json_output": model_info.get("json_output", False),
                    "family": model_info.get("family", "unknown")
                }
            })
        
        return model_options
    
    async def get_model_config_for_agent_builder(self, label: str) -> Optional[Dict[str, Any]]:
        """获取用于Agent Builder的模型配置"""
        model_info = await self.get_model_by_label(label)
        if not model_info:
            return None
        
        # 构建与现有ModelClient兼容的配置
        config = {
            "label": model_info.label,
            "model_name": model_info.model_name or "",
            "base_url": model_info.base_url or "",
            "provider": model_info.provider,
            "model_info": model_info.model_info,
            "config": model_info.config,
            "description": model_info.description or ""
        }
        
        return config
    
    async def create_model_client(self, 
                                label: str,
                                provider: str,
                                description: Optional[str] = None,
                                model_name: Optional[str] = None,
                                base_url: Optional[str] = None,
                                model_info: Optional[Dict[str, Any]] = None,
                                config: Optional[Dict[str, Any]] = None,
                                created_by: Optional[int] = None) -> Optional[int]:
        """创建新的模型客户端"""
        query = """
        INSERT INTO model_clients (
            label, provider, description, model_name, base_url, 
            model_info, config, created_by
        ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id
        """
        
        try:
            result = await self.execute_single_query(
                query, 
                [
                    label, provider, description, model_name, base_url,
                    json.dumps(model_info) if model_info else None,
                    json.dumps(config) if config else None,
                    created_by
                ]
            )
            return result["id"] if result else None
        except Exception as e:
            # 处理唯一约束冲突等错误
            print(f"Error creating model client: {e}")
            return None
    
    async def update_model_client(self, 
                                model_id: int,
                                **kwargs) -> bool:
        """更新模型客户端"""
        # 构建动态更新查询
        update_fields = []
        params = []
        param_count = 1
        
        for field, value in kwargs.items():
            if field in ["label", "provider", "description", "model_name", "base_url"]:
                update_fields.append(f"{field} = ${param_count}")
                params.append(value)
                param_count += 1
            elif field in ["model_info", "config"]:
                update_fields.append(f"{field} = ${param_count}")
                params.append(json.dumps(value) if value else None)
                param_count += 1
        
        if not update_fields:
            return False
        
        update_fields.append("updated_at = CURRENT_TIMESTAMP")
        params.append(model_id)
        
        query = f"""
        UPDATE model_clients 
        SET {', '.join(update_fields)}
        WHERE id = ${param_count}
        """
        
        try:
            await self.execute_command(query, params)
            return True
        except Exception as e:
            print(f"Error updating model client: {e}")
            return False
    
    async def deactivate_model_client(self, model_id: int) -> bool:
        """停用模型客户端"""
        query = """
        UPDATE model_clients 
        SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP
        WHERE id = $1
        """
        
        try:
            await self.execute_command(query, [model_id])
            return True
        except Exception as e:
            print(f"Error deactivating model client: {e}")
            return False 