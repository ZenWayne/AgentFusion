"""Agent基类模块

实现智能体的核心功能，支持上下文管理、LLM交互、MCP集成和流式输出。
"""

import uuid
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator, Union
from dataclasses import dataclass, field
from contextlib import asynccontextmanager

# MCP相关导入
from mcp import StdioServerParameters, ClientSession, stdio_client
from autogen.mcp import create_toolkit

from context_engine import ContextEngine
from llm_client import LLMClientBase, LLMResponse, LLMStreamChunk, get_llm_client_manager
from mcp_client import MCPClientBase, get_mcp_client_manager
from message_queue import MessageQueueBase, Message, get_message_queue_manager
from observability import get_observability_manager
from exceptions import AgentException, ValidationException


@dataclass
class AgentConfig:
    """Agent配置数据类"""
    agent_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Agent"
    description: str = ""
    model: str = "gpt-3.5-turbo"
    system_prompt: str = ""
    max_tokens: Optional[int] = None
    temperature: Optional[float] = None
    llm_client_name: Optional[str] = None
    mcp_client_name: Optional[str] = None
    message_queue_id: Optional[str] = None
    context_variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    # 添加MCP工具配置
    mcp_tools: List[StdioServerParameters] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "model": self.model,
            "system_prompt": self.system_prompt,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "llm_client_name": self.llm_client_name,
            "mcp_client_name": self.mcp_client_name,
            "message_queue_id": self.message_queue_id,
            "context_variables": self.context_variables,
            "metadata": self.metadata,
            "mcp_tools": [tool.model_dump() if hasattr(tool, 'model_dump') else str(tool) for tool in self.mcp_tools]
        }


class AgentBase(ABC, AgentConfig):
    """Agent抽象基类
    
    定义智能体的基本接口和行为规范。
    """
    
    def __init__(self, config: AgentConfig):
        """初始化Agent
        
        Args:
            config: Agent配置
        """
        super().__init__(config)
        self.context_engine = ContextEngine()
        self.observability = get_observability_manager()
        
        # 初始化组件管理器
        self.llm_manager = get_llm_client_manager()
        self.mcp_manager = get_mcp_client_manager()
        self.message_manager = get_message_queue_manager()
        
        # 初始化LLM客户端
        self.llm_client = None
        
        # 初始化组件
        self._initialize_components()
    
    @abstractmethod
    async def process_message(self, message: str, **kwargs) -> LLMResponse:
        """处理消息的抽象方法
        
        Args:
            message: 输入消息
            **kwargs: 其他参数
            
        Returns:
            LLM响应
        """
        pass
    
    @abstractmethod
    async def stream_process_message(self, message: str, **kwargs) -> AsyncGenerator[LLMStreamChunk, None]:
        """流式处理消息的抽象方法
        
        Args:
            message: 输入消息
            **kwargs: 其他参数
            
        Returns:
            异步生成器，产生流式响应块
        """
        pass
    
    def _initialize_components(self) -> None:
        """初始化组件"""
        # 初始化上下文变量
        for var_name, var_value in self.config.context_variables.items():
            self.context_engine.register_variable(var_name, var_value)
        
        # 初始化LLM客户端
        self.llm_client = self.get_llm_client()
        
        # 确保消息队列存在
        if self.config.message_queue_id:
            self.message_manager.get_or_create_queue(
                self.config.message_queue_id, 
                queue_type="memory"
            )
    
    async def handle_response(self, response: LLMResponse, **context) -> None:
        """处理响应，调用所有底层组件的handle_response方法
        
        Args:
            response: LLM响应
            **context: 上下文信息
        """
        # 调用上下文引擎的handle_response
        if hasattr(self.context_engine, 'handle_response'):
            try:
                await self.context_engine.handle_response(response, **context)
            except Exception as e:
                self.observability.logger.warning(f"Context engine handle_response failed: {e}")
        
        # 调用LLM客户端的handle_response
        if self.llm_client and hasattr(self.llm_client, 'handle_response'):
            try:
                await self.llm_client.handle_response(response, **context)
            except Exception as e:
                self.observability.logger.warning(f"LLM client handle_response failed: {e}")
        
        #CR: 这里不能呢用mcp_client相关，移到MCPMixin中处理
        # 调用MCP客户端的handle_response
        mcp_client = self.get_mcp_client()
        if mcp_client and hasattr(mcp_client, 'handle_response'):
            try:
                await mcp_client.handle_response(response, **context)
            except Exception as e:
                self.observability.logger.warning(f"MCP client handle_response failed: {e}")
        
        # 调用消息队列的handle_response
        message_queue = self.get_message_queue()
        if message_queue and hasattr(message_queue, 'handle_response'):
            try:
                await message_queue.handle_response(response, **context)
            except Exception as e:
                self.observability.logger.warning(f"Message queue handle_response failed: {e}")
        
        # 调用可观测性的handle_response
        if hasattr(self.observability, 'handle_response'):
            try:
                await self.observability.handle_response(response, **context)
            except Exception as e:
                self.observability.logger.warning(f"Observability handle_response failed: {e}")
    
    def get_llm_client(self) -> Optional[LLMClientBase]:
        """获取LLM客户端
        
        Returns:
            LLM客户端实例
        """
        return self.llm_manager.get_client(self.config.llm_client_name)
    
    #CR:不要get_mcp_client，会误导开发者
    def get_mcp_client(self) -> Optional[MCPClientBase]:
        """获取MCP客户端
        
        Returns:
            MCP客户端实例
        """
        return self.mcp_manager.get_client(self.config.mcp_client_name)
    
    def get_message_queue(self) -> Optional[MessageQueueBase]:
        """获取消息队列
        
        Returns:
            消息队列实例
        """
        if self.config.message_queue_id:
            return self.message_manager.get_queue(self.config.message_queue_id)
        return None
    
    def add_message_to_history(self, role: str, content: str, **metadata) -> None:
        """添加消息到历史记录
        
        Args:
            role: 消息角色
            content: 消息内容
            **metadata: 额外元数据
        """
        queue = self.get_message_queue()
        if queue:
            message = Message(
                role=role,
                content=content,
                agent_id=self.config.agent_id,
                metadata=metadata
            )
            queue.update(message)
    
    def get_conversation_history(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """获取对话历史
        
        Args:
            limit: 限制返回的消息数量
            
        Returns:
            消息字典列表
        """
        queue = self.get_message_queue()
        if queue:
            messages = queue.get_messages(limit=limit)
            return [
                {
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "agent_id": msg.agent_id,
                    "metadata": msg.metadata
                }
                for msg in messages
            ]
        return []
    
    def prepare_system_prompt(self) -> str:
        """准备系统提示词
        
        Returns:
            处理后的系统提示词
        """
        if not self.config.system_prompt:
            return ""
        
        return self.context_engine.prepare_for_llm_interaction(
            self.config.system_prompt,
            agent_id=self.config.agent_id
        )
    
    def prepare_messages(self, user_message: str) -> List[Dict[str, Any]]:
        """准备消息列表
        
        Args:
            user_message: 用户消息
            
        Returns:
            消息列表
        """
        messages = []
        
        # 添加系统提示
        system_prompt = self.prepare_system_prompt()
        if system_prompt:
            messages.append({
                "role": "system",
                "content": system_prompt
            })
        
        # 添加历史记录
        history = self.get_conversation_history(limit=10)  # 限制历史记录数量
        for msg in history:
            if msg["role"] in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"],
                    "content": msg["content"]
                })
        
        # 添加当前用户消息
        messages.append({
            "role": "user",
            "content": user_message
        })
        
        return messages
    
    def update_config(self, **kwargs) -> None:
        """更新配置
        
        Args:
            **kwargs: 配置参数
        """
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
    
    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态
        
        Returns:
            状态字典
        """
        return {
            "agent_id": self.config.agent_id,
            "name": self.config.name,
            "model": self.config.model,
            "llm_client_available": self.get_llm_client() is not None,
            "mcp_client_available": self.get_mcp_client() is not None,
            "message_queue_available": self.get_message_queue() is not None,
            "context_variables_count": len(self.context_engine.variables),
            "conversation_history_count": len(self.get_conversation_history())
        }


class MCPMixin:
    """MCP功能混入类
    
    提供MCP工具集成的核心功能。
    """
    
    def __init__(self, config: AgentConfig):
        """初始化MCP相关功能
        
        Args:
            config: Agent配置
        """
        # MCP工具相关
        self.mcp_toolkits: List[Any] = []
        self.mcp_tools: List[Any] = []
        self._mcp_initialized = False
        
        # 确保config存在
        if not hasattr(self, 'config'):
            self.config = config
        if not hasattr(self, 'observability'):
            self.observability = get_observability_manager()
    
    async def initialize_mcp_tools(self) -> None:
        """初始化MCP工具"""
        if not self.config.mcp_tools:
            return
            
        try:
            for mcp_server in self.config.mcp_tools:
                async with stdio_client(mcp_server) as (read, write), ClientSession(read, write) as session:
                    # Initialize the connection
                    await session.initialize()
                    toolkit = await create_toolkit(session=session, use_mcp_resources=False)
                    self.mcp_toolkits.append(toolkit)
                    
                    # 收集工具
                    if hasattr(toolkit, 'tools'):
                        self.mcp_tools.extend(toolkit.tools)
                    
            self.observability.logger.info(
                f"Initialized {len(self.mcp_toolkits)} MCP toolkits with {len(self.mcp_tools)} tools"
            )
        except Exception as e:
            self.observability.logger.error(f"Failed to initialize MCP tools: {e}")
            raise AgentException(f"MCP tools initialization failed: {e}")
    
    async def _ensure_mcp_initialized(self) -> None:
        """确保MCP工具已初始化"""
        if not self._mcp_initialized and self.config.mcp_tools:
            await self.initialize_mcp_tools()
            self._mcp_initialized = True
    
    async def _execute_tool_call(self, tool_call: Any) -> Any:
        """执行工具调用
        
        Args:
            tool_call: 工具调用对象
            
        Returns:
            工具执行结果
        """
        # 这里需要根据具体的工具调用格式来实现
        # 目前返回一个模拟结果
        tool_name = getattr(tool_call, 'function', {}).get('name', 'unknown')
        tool_args = getattr(tool_call, 'function', {}).get('arguments', '{}')
        
        self.observability.logger.info(f"Executing tool: {tool_name} with args: {tool_args}")
        
        # 在实际实现中，这里应该调用对应的MCP工具
        # 目前返回一个模拟结果
        return f"Tool {tool_name} executed with result: success"
    
    async def _handle_tool_calls(self, response: LLMResponse, messages: List[Dict[str, Any]], llm_params: Dict[str, Any]) -> Optional[LLMResponse]:
        """处理工具调用
        
        Args:
            response: LLM响应
            messages: 消息列表
            llm_params: LLM参数
            
        Returns:
            处理工具调用后的最终响应，如果没有工具调用则返回None
        """
        if not (hasattr(response, 'tool_calls') and response.tool_calls):
            return None
        
        tool_results = []
        for tool_call in response.tool_calls:
            try:
                # 执行工具调用
                tool_result = await self._execute_tool_call(tool_call)
                tool_results.append(tool_result)
            except Exception as e:
                self.observability.logger.error(f"Tool call execution failed: {e}")
                tool_results.append(f"Tool call failed: {e}")
        
        # 如果有工具调用结果，再次调用LLM处理结果
        if tool_results:
            # 添加工具调用结果到消息历史
            messages.append({
                "role": "assistant",
                "content": response.content,
                "tool_calls": response.tool_calls
            })
            
            for i, tool_result in enumerate(tool_results):
                messages.append({
                    "role": "tool",
                    "content": str(tool_result),
                    "tool_call_id": response.tool_calls[i].id if hasattr(response.tool_calls[i], 'id') else f"call_{i}"
                })
            
            # 重新调用LLM处理工具结果
            llm_client = self.get_llm_client()
            final_params = llm_params.copy()
            final_params["messages"] = messages
            final_response = await llm_client.chat_completion(**final_params)
            
            return final_response
        
        return None
    
    def get_mcp_status(self) -> Dict[str, Any]:
        """获取MCP状态
        
        Returns:
            MCP状态字典
        """
        return {
            "mcp_tools_count": len(self.mcp_tools),
            "mcp_toolkits_count": len(self.mcp_toolkits),
            "mcp_initialized": self._mcp_initialized
        }


class SimpleAgent(AgentBase, MCPMixin):
    """简单Agent实现
    
    提供基本的对话功能，支持LLM交互、上下文管理和MCP工具调用。
    """
    
    def __init__(self, config: AgentConfig):
        """初始化SimpleAgent
        
        Args:
            config: Agent配置
        """
        AgentBase.__init__(self, config)
        MCPMixin.__init__(self, config)
    
    async def process_message(self, message: str, **kwargs) -> LLMResponse:
        """处理消息，支持MCP工具调用"""
        # 验证组件
        llm_client = self.get_llm_client()
        if not llm_client:
            raise AgentException("LLM client not available")
        
        try:
            #CR: 这里使用放进MCPMixin.prepare_messages中，然后下面的prepare_messages再调用底层的prepare_system_prompt
            # 确保MCP工具已初始化
            await self._ensure_mcp_initialized()
            
            # 准备消息
            messages = self.prepare_messages(message)
            
            #CR:这里交给llm_client处理,组装消息,调用LLM,处理工具调用
            # 准备LLM参数
            llm_params = {
                "model": self.config.model,
                "messages": messages
            }
            
            if self.config.max_tokens:
                llm_params["max_tokens"] = self.config.max_tokens
            if self.config.temperature is not None:
                llm_params["temperature"] = self.config.temperature
            
            # 添加MCP工具到参数中
            if self.mcp_tools:
                llm_params["tools"] = self.mcp_tools
            
            # 合并额外参数
            llm_params.update(kwargs)
            
            # 调用LLM
            response = await llm_client.chat_completion(**llm_params)
            
            # 处理工具调用
            final_response = await self._handle_tool_calls(response, messages, llm_params)
            if final_response:
                #这些Context相关的需要新建一个Agent来集成message_queue,context_engine这些，参考README.md
                # 添加最终响应到历史记录
                self.add_message_to_history("user", message)
                self.add_message_to_history("assistant", final_response.content, 
                                           model=final_response.model, usage=final_response.usage,
                                           tool_calls=len(response.tool_calls) if hasattr(response, 'tool_calls') else 0)
                
                # 更新上下文
                self.context_engine.post_llm_interaction(final_response)
                
                # 调用handle_response处理响应
                await self.handle_response(final_response, 
                                         user_message=message, 
                                         tool_calls=True,
                                         original_response=response)
                
                return final_response
            
            #CR 这里也和上面一样，放ContextEngine中处理
            # 没有工具调用，处理普通响应
            # 添加消息到历史记录
            self.add_message_to_history("user", message)
            self.add_message_to_history("assistant", response.content, 
                                       model=response.model, usage=response.usage)
            
            # 更新上下文
            self.context_engine.post_llm_interaction(response)
            
            # 调用handle_response处理响应
            await self.handle_response(response, 
                                     user_message=message, 
                                     tool_calls=False)
            
            return response
            
        except Exception as e:
            raise AgentException(f"Message processing failed: {e}")
    
    async def stream_process_message(self, message: str, **kwargs) -> AsyncGenerator[LLMStreamChunk, None]:
        """流式处理消息，支持MCP工具调用"""
        # 验证组件
        llm_client = self.get_llm_client()
        if not llm_client:
            raise AgentException("LLM client not available")
        
        try:
            # 确保MCP工具已初始化
            await self._ensure_mcp_initialized()
            
            # 准备消息
            messages = self.prepare_messages(message)
            
            # 准备LLM参数
            llm_params = {
                "model": self.config.model,
                "messages": messages
            }
            
            if self.config.max_tokens:
                llm_params["max_tokens"] = self.config.max_tokens
            if self.config.temperature is not None:
                llm_params["temperature"] = self.config.temperature
            
            # 添加MCP工具到参数中
            if self.mcp_tools:
                llm_params["tools"] = self.mcp_tools
            
            # 合并额外参数
            llm_params.update(kwargs)
            
            # 流式调用LLM
            accumulated_content = ""
            tool_calls = []
            
            async for chunk in llm_client.stream_chat_completion(**llm_params):
                accumulated_content += chunk.content
                
                # 收集工具调用
                if hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                    tool_calls.extend(chunk.tool_calls)
                
                yield chunk
                
                # 如果是最终块，处理工具调用
                if chunk.is_final:
                    if tool_calls:
                        # 处理工具调用（在流式场景中，工具调用结果可能需要特殊处理）
                        try:
                            tool_results = []
                            for tool_call in tool_calls:
                                tool_result = await self._execute_tool_call(tool_call)
                                tool_results.append(tool_result)
                            
                            # 添加工具调用结果作为额外的流式响应
                            tool_result_content = "Tool results: " + "; ".join(str(r) for r in tool_results)
                            tool_chunk = LLMStreamChunk(
                                content=tool_result_content,
                                is_final=True
                            )
                            yield tool_chunk
                            
                            accumulated_content += tool_result_content
                        except Exception as e:
                            self.observability.logger.error(f"Tool call execution failed during streaming: {e}")
                    
                    # 添加到历史记录
                    self.add_message_to_history("user", message)
                    self.add_message_to_history("assistant", accumulated_content,
                                               tool_calls=len(tool_calls))
                    
                    # 创建模拟响应对象用于上下文更新和handle_response
                    mock_response = LLMResponse(
                        content=accumulated_content,
                        model=self.config.model,
                        usage={}
                    )
                    
                    self.context_engine.post_llm_interaction(mock_response)
                    
                    # 调用handle_response处理响应
                    await self.handle_response(mock_response, 
                                             user_message=message, 
                                             tool_calls=len(tool_calls) > 0,
                                             streaming=True)
            
        except Exception as e:
            raise AgentException(f"Stream message processing failed: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """获取Agent状态
        
        Returns:
            状态字典
        """
        status = super().get_status()
        status.update(self.get_mcp_status())
        return status


class MCPAgent(SimpleAgent):
    """支持MCP的Agent（保留向后兼容性）
    
    现在SimpleAgent已经集成了MCP功能，MCPAgent保留作为别名。
    """
    
    def __init__(self, config: AgentConfig):
        """初始化MCPAgent
        
        Args:
            config: Agent配置
        """
        super().__init__(config)
        self.observability.logger.info("MCPAgent is now equivalent to SimpleAgent with MCP support")


class AgentManager:
    """Agent管理器
    
    管理多个Agent实例，支持创建、配置和生命周期管理。
    """
    
    def __init__(self):
        self.agents: Dict[str, AgentBase] = {}
        self.observability = get_observability_manager()
    
    def create_agent(self, config: AgentConfig, agent_type: str = "simple") -> AgentBase:
        """创建Agent
        
        Args:
            config: Agent配置
            agent_type: Agent类型 ("simple" 或 "mcp")
            
        Returns:
            Agent实例
        """
        if config.agent_id in self.agents:
            raise AgentException(f"Agent {config.agent_id} already exists")
        
        # 验证配置
        self._validate_config(config)
        
        # 创建Agent实例
        if agent_type == "simple":
            agent = SimpleAgent(config)
        elif agent_type == "mcp":
            agent = MCPAgent(config)
        else:
            raise AgentException(f"Unsupported agent type: {agent_type}")
        
        self.agents[config.agent_id] = agent
        
        self.observability.logger.info(
            f"Agent {config.agent_id} created",
            context={"agent_type": agent_type, "agent_name": config.name}
        )
        
        return agent
    
    def get_agent(self, agent_id: str) -> Optional[AgentBase]:
        """获取Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent实例，如果不存在则返回None
        """
        return self.agents.get(agent_id)
    
    def remove_agent(self, agent_id: str) -> None:
        """移除Agent
        
        Args:
            agent_id: Agent ID
        """
        if agent_id in self.agents:
            del self.agents[agent_id]
            self.observability.logger.info(f"Agent {agent_id} removed")
    
    def list_agents(self) -> List[str]:
        """列出所有Agent ID
        
        Returns:
            Agent ID列表
        """
        return list(self.agents.keys())
    
    def get_agent_status(self, agent_id: str) -> Optional[Dict[str, Any]]:
        """获取Agent状态
        
        Args:
            agent_id: Agent ID
            
        Returns:
            状态字典，如果Agent不存在则返回None
        """
        agent = self.get_agent(agent_id)
        if agent:
            return agent.get_status()
        return None
    
    def get_all_agent_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有Agent状态
        
        Returns:
            Agent ID到状态字典的映射
        """
        status = {}
        for agent_id, agent in self.agents.items():
            status[agent_id] = agent.get_status()
        return status
    
    def update_agent_config(self, agent_id: str, **kwargs) -> None:
        """更新Agent配置
        
        Args:
            agent_id: Agent ID
            **kwargs: 配置参数
        """
        agent = self.get_agent(agent_id)
        if not agent:
            raise AgentException(f"Agent {agent_id} not found")
        
        agent.update_config(**kwargs)
        
        self.observability.logger.info(
            f"Agent {agent_id} config updated",
            context={"updated_fields": list(kwargs.keys())}
        )
    
    def _validate_config(self, config: AgentConfig) -> None:
        """验证Agent配置
        
        Args:
            config: Agent配置
            
        Raises:
            ValidationException: 配置验证失败
        """
        if not config.agent_id:
            raise ValidationException("Agent ID is required")
        
        if not config.name:
            raise ValidationException("Agent name is required")
        
        if not config.model:
            raise ValidationException("Model is required")
        
        # 可以添加更多验证逻辑
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """获取管理器统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "total_agents": len(self.agents),
            "agent_types": {
                agent_id: agent.__class__.__name__ 
                for agent_id, agent in self.agents.items()
            }
        }


# 全局Agent管理器实例
agent_manager = AgentManager()


def get_agent_manager() -> AgentManager:
    """获取全局Agent管理器实例
    
    Returns:
        Agent管理器实例
    """
    return agent_manager 