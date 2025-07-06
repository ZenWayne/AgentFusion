"""LLM客户端模块

实现与LLM的交互接口，使用LiteLLM提供统一的API接口。
"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, AsyncGenerator, Iterator, Union
from dataclasses import dataclass
from .exceptions import LLMClientException, TimeoutException
from .observability import get_observability_manager, InteractionStatus


@dataclass
class LLMResponse:
    """LLM响应数据类"""
    content: str
    model: str
    usage: Dict[str, Any]
    metadata: Dict[str, Any]
    raw_response: Any = None
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "content": self.content,
            "model": self.model,
            "usage": self.usage,
            "metadata": self.metadata
        }


@dataclass
class LLMStreamChunk:
    """LLM流式响应块"""
    content: str
    is_final: bool = False
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class LLMClientBase(ABC):
    """LLM客户端抽象基类"""
    
    @abstractmethod
    async def chat_completion(self, messages: List[Dict[str, Any]], 
                             model: str, **kwargs) -> LLMResponse:
        """异步聊天完成接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            **kwargs: 其他参数
            
        Returns:
            LLM响应
        """
        pass
    
    @abstractmethod
    async def stream_chat_completion(self, messages: List[Dict[str, Any]], 
                                   model: str, **kwargs) -> AsyncGenerator[LLMStreamChunk, None]:
        """异步流式聊天完成接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            **kwargs: 其他参数
            
        Returns:
            异步生成器，产生流式响应块
        """
        pass
    
    def sync_chat_completion(self, messages: List[Dict[str, Any]], 
                           model: str, **kwargs) -> LLMResponse:
        """同步聊天完成接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            **kwargs: 其他参数
            
        Returns:
            LLM响应
        """
        return asyncio.run(self.chat_completion(messages, model, **kwargs))
    
    def sync_stream_chat_completion(self, messages: List[Dict[str, Any]], 
                                  model: str, **kwargs) -> Iterator[LLMStreamChunk]:
        """同步流式聊天完成接口
        
        Args:
            messages: 消息列表
            model: 模型名称
            **kwargs: 其他参数
            
        Returns:
            迭代器，产生流式响应块
        """
        async def _async_generator():
            async for chunk in self.stream_chat_completion(messages, model, **kwargs):
                yield chunk
        
        async def _run():
            chunks = []
            async for chunk in _async_generator():
                chunks.append(chunk)
            return chunks
        
        chunks = asyncio.run(_run())
        for chunk in chunks:
            yield chunk


class LiteLLMClient(LLMClientBase):
    """LiteLLM客户端实现
    
    使用LiteLLM库与各种LLM提供商进行交互。
    """
    
    def __init__(self, default_model: Optional[str] = None, 
                 timeout: Optional[int] = None):
        """初始化LiteLLM客户端
        
        Args:
            default_model: 默认模型名称
            timeout: 请求超时时间（秒）
        """
        self.default_model = default_model
        self.timeout = timeout
        self.observability = get_observability_manager()
        
        # 尝试导入LiteLLM
        try:
            import litellm
            self.litellm = litellm
        except ImportError:
            raise LLMClientException(
                "LiteLLM not installed. Please install it with: pip install litellm",
                error_code="LITELLM_NOT_INSTALLED"
            )
    
    async def chat_completion(self, messages: List[Dict[str, Any]], 
                             model: Optional[str] = None, **kwargs) -> LLMResponse:
        """异步聊天完成"""
        model = model or self.default_model
        if not model:
            raise LLMClientException("Model not specified and no default model set")
        
        # 开始可观测性追踪
        interaction_id = self.observability.start_interaction()
        
        try:
            self.observability.record_llm_request(
                interaction_id, model, messages, **kwargs
            )
            
            # 准备参数
            completion_params = {
                "model": model,
                "messages": messages,
                **kwargs
            }
            
            # 设置超时
            if self.timeout:
                completion_params["timeout"] = self.timeout
            
            # 调用LiteLLM
            response = await self.litellm.acompletion(**completion_params)
            
            # 构造响应对象
            llm_response = self._create_response_from_litellm(response, model)
            
            # 记录响应
            self.observability.record_llm_response(
                interaction_id, llm_response.to_dict(), InteractionStatus.SUCCESS
            )
            
            return llm_response
            
        except Exception as e:
            # 记录错误
            self.observability.record_error(interaction_id, e)
            
            # 转换为框架异常
            if "timeout" in str(e).lower():
                raise TimeoutException(f"LLM request timeout: {e}")
            else:
                raise LLMClientException(f"LLM request failed: {e}")
        
        finally:
            self.observability.end_interaction(interaction_id)
    
    async def stream_chat_completion(self, messages: List[Dict[str, Any]], 
                                   model: Optional[str] = None, 
                                   **kwargs) -> AsyncGenerator[LLMStreamChunk, None]:
        """异步流式聊天完成"""
        model = model or self.default_model
        if not model:
            raise LLMClientException("Model not specified and no default model set")
        
        # 开始可观测性追踪
        interaction_id = self.observability.start_interaction()
        
        try:
            self.observability.record_llm_request(
                interaction_id, model, messages, **kwargs
            )
            
            # 准备参数
            completion_params = {
                "model": model,
                "messages": messages,
                "stream": True,
                **kwargs
            }
            
            # 设置超时
            if self.timeout:
                completion_params["timeout"] = self.timeout
            
            # 调用LiteLLM流式接口
            stream = await self.litellm.acompletion(**completion_params)
            
            accumulated_content = ""
            
            async for chunk in stream:
                try:
                    # 处理流式响应块
                    content = ""
                    if hasattr(chunk, 'choices') and chunk.choices:
                        if hasattr(chunk.choices[0], 'delta') and chunk.choices[0].delta:
                            content = chunk.choices[0].delta.content or ""
                    
                    accumulated_content += content
                    
                    # 创建流式响应块
                    stream_chunk = LLMStreamChunk(
                        content=content,
                        is_final=False,
                        metadata={"accumulated_content": accumulated_content}
                    )
                    
                    yield stream_chunk
                    
                except Exception as chunk_error:
                    # 记录块处理错误但继续处理
                    self.observability.logger.warning(
                        f"Error processing stream chunk: {chunk_error}",
                        interaction_id=interaction_id
                    )
                    continue
            
            # 发送最终块
            final_chunk = LLMStreamChunk(
                content="",
                is_final=True,
                metadata={"final_content": accumulated_content}
            )
            yield final_chunk
            
            # 记录最终响应
            self.observability.record_llm_response(
                interaction_id, 
                {"content": accumulated_content, "model": model}, 
                InteractionStatus.SUCCESS
            )
            
        except Exception as e:
            # 记录错误
            self.observability.record_error(interaction_id, e)
            
            # 转换为框架异常
            if "timeout" in str(e).lower():
                raise TimeoutException(f"LLM stream request timeout: {e}")
            else:
                raise LLMClientException(f"LLM stream request failed: {e}")
        
        finally:
            self.observability.end_interaction(interaction_id)
    
    def _create_response_from_litellm(self, response: Any, model: str) -> LLMResponse:
        """从LiteLLM响应创建LLMResponse对象
        
        Args:
            response: LiteLLM响应对象
            model: 模型名称
            
        Returns:
            LLMResponse对象
        """
        try:
            # 提取内容
            content = ""
            if hasattr(response, 'choices') and response.choices:
                if hasattr(response.choices[0], 'message'):
                    content = response.choices[0].message.content or ""
            
            # 提取使用信息
            usage = {}
            if hasattr(response, 'usage') and response.usage:
                usage = {
                    "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                    "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
                    "total_tokens": getattr(response.usage, 'total_tokens', 0)
                }
            
            # 提取元数据
            metadata = {}
            if hasattr(response, 'id'):
                metadata["id"] = response.id
            if hasattr(response, 'created'):
                metadata["created"] = response.created
            if hasattr(response, 'model'):
                metadata["response_model"] = response.model
            
            return LLMResponse(
                content=content,
                model=model,
                usage=usage,
                metadata=metadata,
                raw_response=response
            )
            
        except Exception as e:
            raise LLMClientException(f"Failed to parse LiteLLM response: {e}")
    
    def set_default_model(self, model: str) -> None:
        """设置默认模型
        
        Args:
            model: 模型名称
        """
        self.default_model = model
    
    def set_timeout(self, timeout: int) -> None:
        """设置超时时间
        
        Args:
            timeout: 超时时间（秒）
        """
        self.timeout = timeout
    
    def test_connection(self, model: Optional[str] = None) -> bool:
        """测试连接
        
        Args:
            model: 可选的模型名称
            
        Returns:
            是否连接成功
        """
        try:
            test_messages = [{"role": "user", "content": "Hello"}]
            response = self.sync_chat_completion(test_messages, model)
            return response.content is not None
        except Exception:
            return False


class MockLLMClient(LLMClientBase):
    """模拟LLM客户端
    
    用于测试和开发，不需要实际的LLM API调用。
    """
    
    def __init__(self, default_response: str = "This is a mock response.", 
                 delay: float = 0.1):
        """初始化模拟客户端
        
        Args:
            default_response: 默认响应内容
            delay: 模拟延迟时间（秒）
        """
        self.default_response = default_response
        self.delay = delay
        self.observability = get_observability_manager()
    
    async def chat_completion(self, messages: List[Dict[str, Any]], 
                             model: str, **kwargs) -> LLMResponse:
        """模拟聊天完成"""
        interaction_id = self.observability.start_interaction()
        
        try:
            self.observability.record_llm_request(
                interaction_id, model, messages, **kwargs
            )
            
            # 模拟处理延迟
            await asyncio.sleep(self.delay)
            
            # 创建模拟响应
            response = LLMResponse(
                content=self.default_response,
                model=model,
                usage={"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
                metadata={"mock": True}
            )
            
            self.observability.record_llm_response(
                interaction_id, response.to_dict(), InteractionStatus.SUCCESS
            )
            
            return response
            
        except Exception as e:
            self.observability.record_error(interaction_id, e)
            raise
        finally:
            self.observability.end_interaction(interaction_id)
    
    async def stream_chat_completion(self, messages: List[Dict[str, Any]], 
                                   model: str, **kwargs) -> AsyncGenerator[LLMStreamChunk, None]:
        """模拟流式聊天完成"""
        interaction_id = self.observability.start_interaction()
        
        try:
            self.observability.record_llm_request(
                interaction_id, model, messages, **kwargs
            )
            
            # 分块发送响应
            words = self.default_response.split()
            
            for i, word in enumerate(words):
                await asyncio.sleep(self.delay / len(words))
                
                chunk = LLMStreamChunk(
                    content=word + " ",
                    is_final=False,
                    metadata={"word_index": i}
                )
                yield chunk
            
            # 发送最终块
            final_chunk = LLMStreamChunk(
                content="",
                is_final=True,
                metadata={"final_content": self.default_response}
            )
            yield final_chunk
            
            self.observability.record_llm_response(
                interaction_id, 
                {"content": self.default_response, "model": model}, 
                InteractionStatus.SUCCESS
            )
            
        except Exception as e:
            self.observability.record_error(interaction_id, e)
            raise
        finally:
            self.observability.end_interaction(interaction_id)


class LLMClientManager:
    """LLM客户端管理器
    
    管理多个LLM客户端实例，支持不同的模型和配置。
    """
    
    def __init__(self):
        self.clients: Dict[str, LLMClientBase] = {}
        self.default_client_name: Optional[str] = None
    
    def register_client(self, name: str, client: LLMClientBase, 
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
    
    def get_client(self, name: Optional[str] = None) -> Optional[LLMClientBase]:
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
            raise LLMClientException(f"Client {name} not found")
    
    async def chat_completion(self, messages: List[Dict[str, Any]], 
                             model: str, client_name: Optional[str] = None,
                             **kwargs) -> LLMResponse:
        """使用指定客户端进行聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            client_name: 客户端名称
            **kwargs: 其他参数
            
        Returns:
            LLM响应
        """
        client = self.get_client(client_name)
        if not client:
            raise LLMClientException(f"Client {client_name or 'default'} not found")
        
        return await client.chat_completion(messages, model, **kwargs)
    
    async def stream_chat_completion(self, messages: List[Dict[str, Any]], 
                                   model: str, client_name: Optional[str] = None,
                                   **kwargs) -> AsyncGenerator[LLMStreamChunk, None]:
        """使用指定客户端进行流式聊天完成
        
        Args:
            messages: 消息列表
            model: 模型名称
            client_name: 客户端名称
            **kwargs: 其他参数
            
        Returns:
            异步生成器
        """
        client = self.get_client(client_name)
        if not client:
            raise LLMClientException(f"Client {client_name or 'default'} not found")
        
        async for chunk in client.stream_chat_completion(messages, model, **kwargs):
            yield chunk


# 全局LLM客户端管理器实例
llm_client_manager = LLMClientManager()


def get_llm_client_manager() -> LLMClientManager:
    """获取全局LLM客户端管理器实例
    
    Returns:
        LLM客户端管理器实例
    """
    return llm_client_manager 