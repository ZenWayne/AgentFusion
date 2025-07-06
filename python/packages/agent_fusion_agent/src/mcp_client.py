"""MCP客户端模块

实现MCP(Model Context Protocol)协议支持，扩展Agent的能力边界。
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass
from .exceptions import MCPClientException


@dataclass
class MCPTool:
    """MCP工具定义"""
    name: str
    description: str
    parameters: Dict[str, Any]
    handler: Callable
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters
        }


@dataclass
class MCPResource:
    """MCP资源定义"""
    name: str
    description: str
    mime_type: str
    data: Any
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
            "data": str(self.data)
        }


@dataclass
class MCPPrompt:
    """MCP提示定义"""
    name: str
    description: str
    template: str
    parameters: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "name": self.name,
            "description": self.description,
            "template": self.template,
            "parameters": self.parameters
        }


class MCPClientBase(ABC):
    """MCP客户端抽象基类"""
    
    @abstractmethod
    def register_tool(self, tool: MCPTool) -> None:
        """注册工具
        
        Args:
            tool: MCP工具
        """
        pass
    
    @abstractmethod
    def register_resource(self, resource: MCPResource) -> None:
        """注册资源
        
        Args:
            resource: MCP资源
        """
        pass
    
    @abstractmethod
    def register_prompt(self, prompt: MCPPrompt) -> None:
        """注册提示
        
        Args:
            prompt: MCP提示
        """
        pass
    
    @abstractmethod
    def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """调用工具
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            
        Returns:
            工具执行结果
        """
        pass
    
    @abstractmethod
    def get_resource(self, resource_name: str) -> Optional[MCPResource]:
        """获取资源
        
        Args:
            resource_name: 资源名称
            
        Returns:
            资源对象，如果不存在则返回None
        """
        pass
    
    @abstractmethod
    def get_prompt(self, prompt_name: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """获取提示
        
        Args:
            prompt_name: 提示名称
            parameters: 提示参数
            
        Returns:
            渲染后的提示字符串，如果不存在则返回None
        """
        pass


class InMemoryMCPClient(MCPClientBase):
    """内存MCP客户端
    
    在内存中管理MCP工具、资源和提示，适用于简单场景。
    """
    
    def __init__(self):
        """初始化内存MCP客户端"""
        self.tools: Dict[str, MCPTool] = {}
        self.resources: Dict[str, MCPResource] = {}
        self.prompts: Dict[str, MCPPrompt] = {}
        self._observers: List[Callable[[str, Any], None]] = []
    
    def register_tool(self, tool: MCPTool) -> None:
        """注册工具"""
        self.tools[tool.name] = tool
        self._notify_observers("tool_registered", tool)
    
    def register_resource(self, resource: MCPResource) -> None:
        """注册资源"""
        self.resources[resource.name] = resource
        self._notify_observers("resource_registered", resource)
    
    def register_prompt(self, prompt: MCPPrompt) -> None:
        """注册提示"""
        self.prompts[prompt.name] = prompt
        self._notify_observers("prompt_registered", prompt)
    
    def call_tool(self, tool_name: str, parameters: Dict[str, Any]) -> Any:
        """调用工具"""
        if tool_name not in self.tools:
            raise MCPClientException(f"Tool {tool_name} not found")
        
        tool = self.tools[tool_name]
        
        try:
            # 验证参数
            self._validate_parameters(parameters, tool.parameters)
            
            # 调用工具处理函数
            result = tool.handler(parameters)
            
            self._notify_observers("tool_called", {
                "tool_name": tool_name,
                "parameters": parameters,
                "result": result
            })
            
            return result
            
        except Exception as e:
            error_msg = f"Tool {tool_name} execution failed: {e}"
            self._notify_observers("tool_error", {
                "tool_name": tool_name,
                "error": error_msg
            })
            raise MCPClientException(error_msg)
    
    def get_resource(self, resource_name: str) -> Optional[MCPResource]:
        """获取资源"""
        resource = self.resources.get(resource_name)
        if resource:
            self._notify_observers("resource_accessed", resource)
        return resource
    
    def get_prompt(self, prompt_name: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """获取提示"""
        if prompt_name not in self.prompts:
            return None
        
        prompt = self.prompts[prompt_name]
        
        try:
            # 渲染提示模板
            rendered = self._render_prompt_template(prompt.template, parameters or {})
            
            self._notify_observers("prompt_accessed", {
                "prompt_name": prompt_name,
                "parameters": parameters,
                "rendered": rendered
            })
            
            return rendered
            
        except Exception as e:
            error_msg = f"Prompt {prompt_name} rendering failed: {e}"
            self._notify_observers("prompt_error", {
                "prompt_name": prompt_name,
                "error": error_msg
            })
            raise MCPClientException(error_msg)
    
    def list_tools(self) -> List[MCPTool]:
        """列出所有工具
        
        Returns:
            工具列表
        """
        return list(self.tools.values())
    
    def list_resources(self) -> List[MCPResource]:
        """列出所有资源
        
        Returns:
            资源列表
        """
        return list(self.resources.values())
    
    def list_prompts(self) -> List[MCPPrompt]:
        """列出所有提示
        
        Returns:
            提示列表
        """
        return list(self.prompts.values())
    
    def remove_tool(self, tool_name: str) -> None:
        """移除工具
        
        Args:
            tool_name: 工具名称
        """
        if tool_name in self.tools:
            del self.tools[tool_name]
            self._notify_observers("tool_removed", tool_name)
    
    def remove_resource(self, resource_name: str) -> None:
        """移除资源
        
        Args:
            resource_name: 资源名称
        """
        if resource_name in self.resources:
            del self.resources[resource_name]
            self._notify_observers("resource_removed", resource_name)
    
    def remove_prompt(self, prompt_name: str) -> None:
        """移除提示
        
        Args:
            prompt_name: 提示名称
        """
        if prompt_name in self.prompts:
            del self.prompts[prompt_name]
            self._notify_observers("prompt_removed", prompt_name)
    
    def add_observer(self, observer: Callable[[str, Any], None]) -> None:
        """添加观察者
        
        Args:
            observer: 观察者函数
        """
        self._observers.append(observer)
    
    def remove_observer(self, observer: Callable[[str, Any], None]) -> None:
        """移除观察者
        
        Args:
            observer: 观察者函数
        """
        if observer in self._observers:
            self._observers.remove(observer)
    
    def _validate_parameters(self, parameters: Dict[str, Any], 
                           schema: Dict[str, Any]) -> None:
        """验证参数
        
        Args:
            parameters: 实际参数
            schema: 参数模式
            
        Raises:
            MCPClientException: 参数验证失败
        """
        # 简单的参数验证
        if "required" in schema:
            for required_param in schema["required"]:
                if required_param not in parameters:
                    raise MCPClientException(f"Required parameter {required_param} missing")
        
        # 可以添加更复杂的类型验证
        if "properties" in schema:
            for param_name, param_value in parameters.items():
                if param_name in schema["properties"]:
                    param_schema = schema["properties"][param_name]
                    if "type" in param_schema:
                        expected_type = param_schema["type"]
                        if not self._check_type(param_value, expected_type):
                            raise MCPClientException(
                                f"Parameter {param_name} type mismatch. Expected {expected_type}"
                            )
    
    def _check_type(self, value: Any, expected_type: str) -> bool:
        """检查类型
        
        Args:
            value: 值
            expected_type: 期望类型
            
        Returns:
            是否匹配
        """
        type_mapping = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "array": list,
            "object": dict
        }
        
        if expected_type in type_mapping:
            return isinstance(value, type_mapping[expected_type])
        
        return True  # 未知类型，暂时通过
    
    def _render_prompt_template(self, template: str, parameters: Dict[str, Any]) -> str:
        """渲染提示模板
        
        Args:
            template: 模板字符串
            parameters: 参数字典
            
        Returns:
            渲染后的字符串
        """
        import re
        
        # 简单的模板渲染，支持 {{variable}} 格式
        pattern = r'\{\{([^}]+)\}\}'
        
        def replace_func(match):
            var_name = match.group(1).strip()
            if var_name in parameters:
                return str(parameters[var_name])
            else:
                return match.group(0)  # 保持原样
        
        return re.sub(pattern, replace_func, template)
    
    def _notify_observers(self, event: str, data: Any) -> None:
        """通知观察者
        
        Args:
            event: 事件类型
            data: 事件数据
        """
        for observer in self._observers:
            try:
                observer(event, data)
            except Exception as e:
                # 观察者异常不应该影响主流程
                pass
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "tools_count": len(self.tools),
            "resources_count": len(self.resources),
            "prompts_count": len(self.prompts),
            "observers_count": len(self._observers)
        }


class MCPClientManager:
    """MCP客户端管理器
    
    管理多个MCP客户端实例，支持不同的配置和用途。
    """
    
    def __init__(self):
        self.clients: Dict[str, MCPClientBase] = {}
        self.default_client_name: Optional[str] = None
        self._global_observers: List[Callable[[str, str, Any], None]] = []
    
    def register_client(self, name: str, client: MCPClientBase, 
                       is_default: bool = False) -> None:
        """注册客户端
        
        Args:
            name: 客户端名称
            client: 客户端实例
            is_default: 是否设为默认客户端
        """
        self.clients[name] = client
        
        if is_default or not self.default_client_name:
            self.default_client_name = name
        
        # 添加全局观察者
        if hasattr(client, 'add_observer'):
            client.add_observer(lambda event, data: self._notify_global_observers(name, event, data))
    
    def get_client(self, name: Optional[str] = None) -> Optional[MCPClientBase]:
        """获取客户端
        
        Args:
            name: 客户端名称，如果为None则返回默认客户端
            
        Returns:
            客户端实例，如果不存在则返回None
        """
        if name:
            return self.clients.get(name)
        elif self.default_client_name:
            return self.clients.get(self.default_client_name)
        else:
            return None
    
    def remove_client(self, name: str) -> None:
        """移除客户端
        
        Args:
            name: 客户端名称
        """
        if name in self.clients:
            del self.clients[name]
            
            # 如果删除的是默认客户端，重新设置默认客户端
            if name == self.default_client_name:
                self.default_client_name = next(iter(self.clients.keys()), None)
    
    def list_clients(self) -> List[str]:
        """列出所有客户端名称
        
        Returns:
            客户端名称列表
        """
        return list(self.clients.keys())
    
    def set_default_client(self, name: str) -> None:
        """设置默认客户端
        
        Args:
            name: 客户端名称
        """
        if name in self.clients:
            self.default_client_name = name
        else:
            raise MCPClientException(f"Client {name} not found")
    
    def register_tool(self, tool: MCPTool, client_name: Optional[str] = None) -> None:
        """注册工具到指定客户端
        
        Args:
            tool: MCP工具
            client_name: 客户端名称
        """
        client = self.get_client(client_name)
        if not client:
            raise MCPClientException(f"Client {client_name or 'default'} not found")
        
        client.register_tool(tool)
    
    def register_resource(self, resource: MCPResource, client_name: Optional[str] = None) -> None:
        """注册资源到指定客户端
        
        Args:
            resource: MCP资源
            client_name: 客户端名称
        """
        client = self.get_client(client_name)
        if not client:
            raise MCPClientException(f"Client {client_name or 'default'} not found")
        
        client.register_resource(resource)
    
    def register_prompt(self, prompt: MCPPrompt, client_name: Optional[str] = None) -> None:
        """注册提示到指定客户端
        
        Args:
            prompt: MCP提示
            client_name: 客户端名称
        """
        client = self.get_client(client_name)
        if not client:
            raise MCPClientException(f"Client {client_name or 'default'} not found")
        
        client.register_prompt(prompt)
    
    def call_tool(self, tool_name: str, parameters: Dict[str, Any], 
                 client_name: Optional[str] = None) -> Any:
        """调用工具
        
        Args:
            tool_name: 工具名称
            parameters: 工具参数
            client_name: 客户端名称
            
        Returns:
            工具执行结果
        """
        client = self.get_client(client_name)
        if not client:
            raise MCPClientException(f"Client {client_name or 'default'} not found")
        
        return client.call_tool(tool_name, parameters)
    
    def get_all_tools(self) -> Dict[str, List[MCPTool]]:
        """获取所有客户端的工具
        
        Returns:
            客户端名称到工具列表的映射
        """
        all_tools = {}
        for client_name, client in self.clients.items():
            if hasattr(client, 'list_tools'):
                all_tools[client_name] = client.list_tools()
        return all_tools
    
    def get_all_resources(self) -> Dict[str, List[MCPResource]]:
        """获取所有客户端的资源
        
        Returns:
            客户端名称到资源列表的映射
        """
        all_resources = {}
        for client_name, client in self.clients.items():
            if hasattr(client, 'list_resources'):
                all_resources[client_name] = client.list_resources()
        return all_resources
    
    def get_all_prompts(self) -> Dict[str, List[MCPPrompt]]:
        """获取所有客户端的提示
        
        Returns:
            客户端名称到提示列表的映射
        """
        all_prompts = {}
        for client_name, client in self.clients.items():
            if hasattr(client, 'list_prompts'):
                all_prompts[client_name] = client.list_prompts()
        return all_prompts
    
    def add_global_observer(self, observer: Callable[[str, str, Any], None]) -> None:
        """添加全局观察者
        
        Args:
            observer: 观察者函数，接收客户端名称、事件类型和数据
        """
        self._global_observers.append(observer)
    
    def remove_global_observer(self, observer: Callable[[str, str, Any], None]) -> None:
        """移除全局观察者
        
        Args:
            observer: 观察者函数
        """
        if observer in self._global_observers:
            self._global_observers.remove(observer)
    
    def _notify_global_observers(self, client_name: str, event: str, data: Any) -> None:
        """通知全局观察者
        
        Args:
            client_name: 客户端名称
            event: 事件类型
            data: 事件数据
        """
        for observer in self._global_observers:
            try:
                observer(client_name, event, data)
            except Exception as e:
                pass
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """获取管理器统计信息
        
        Returns:
            统计信息字典
        """
        client_stats = {}
        for client_name, client in self.clients.items():
            if hasattr(client, 'get_statistics'):
                client_stats[client_name] = client.get_statistics()
        
        return {
            "total_clients": len(self.clients),
            "default_client": self.default_client_name,
            "global_observers": len(self._global_observers),
            "client_statistics": client_stats
        }


# 全局MCP客户端管理器实例
mcp_client_manager = MCPClientManager()


def get_mcp_client_manager() -> MCPClientManager:
    """获取全局MCP客户端管理器实例
    
    Returns:
        MCP客户端管理器实例
    """
    return mcp_client_manager 