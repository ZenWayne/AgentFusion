"""OpenTelemetry与现有Observability模块集成

将OpenTelemetry集成到现有的observability.py中，提供更强大的分布式追踪能力。
"""

import time
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Any
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.propagate import inject, extract

from .observability import (
    ObservabilityManager, 
    InteractionStatus, 
    InteractionMetrics,
    LogLevel
)
from .opentelemetry_config import get_tracer


class OpenTelemetryObservabilityManager(ObservabilityManager):
    """集成OpenTelemetry的可观测性管理器
    
    扩展现有的ObservabilityManager，添加OpenTelemetry分布式追踪能力。
    """
    
    def __init__(self):
        super().__init__()
        self.tracer = get_tracer(__name__)
        self._active_spans: Dict[str, Any] = {}
    
    def start_interaction(self, interaction_id: Optional[str] = None,
                         context: Optional[Dict[str, Any]] = None) -> str:
        """开始一次交互，创建OpenTelemetry span
        
        Args:
            interaction_id: 可选的交互ID
            context: 可选的上下文信息
            
        Returns:
            交互ID
        """
        # 调用父类方法
        interaction_id = super().start_interaction(interaction_id, context)
        
        # 创建OpenTelemetry span
        span = self.tracer.start_span(f"interaction_{interaction_id}")
        span.set_attribute("interaction.id", interaction_id)
        
        if context:
            for key, value in context.items():
                if isinstance(value, (str, int, float, bool)):
                    span.set_attribute(f"context.{key}", value)
        
        # 保存span引用
        self._active_spans[interaction_id] = span
        
        # 添加事件
        span.add_event("Interaction started")
        
        return interaction_id
    
    def record_llm_request(self, interaction_id: str, model_name: str,
                          messages: List[Dict[str, Any]], 
                          agent_id: Optional[str] = None,
                          **kwargs) -> None:
        """记录LLM请求，添加OpenTelemetry追踪
        
        Args:
            interaction_id: 交互ID
            model_name: 模型名称
            messages: 消息列表
            agent_id: Agent ID
            **kwargs: 其他请求参数
        """
        # 调用父类方法
        super().record_llm_request(interaction_id, model_name, messages, agent_id, **kwargs)
        
        # 获取对应的span
        span = self._active_spans.get(interaction_id)
        if span:
            # 创建LLM请求子span
            with self.tracer.start_as_current_span("llm_request", context=trace.set_span_in_context(span)) as llm_span:
                llm_span.set_attribute("llm.model", model_name)
                llm_span.set_attribute("llm.message_count", len(messages))
                
                if agent_id:
                    llm_span.set_attribute("agent.id", agent_id)
                
                # 添加其他属性
                for key, value in kwargs.items():
                    if isinstance(value, (str, int, float, bool)):
                        llm_span.set_attribute(f"llm.{key}", value)
                
                # 计算消息总长度
                total_length = sum(len(str(msg)) for msg in messages)
                llm_span.set_attribute("llm.total_message_length", total_length)
                
                llm_span.add_event("LLM request initiated")
    
    def record_llm_response(self, interaction_id: str, response: Dict[str, Any],
                           status: InteractionStatus = InteractionStatus.SUCCESS) -> None:
        """记录LLM响应，添加OpenTelemetry追踪
        
        Args:
            interaction_id: 交互ID
            response: 响应数据
            status: 响应状态
        """
        # 调用父类方法
        super().record_llm_response(interaction_id, response, status)
        
        # 获取对应的span
        span = self._active_spans.get(interaction_id)
        if span:
            # 设置响应属性
            span.set_attribute("llm.response_status", status.value)
            
            if isinstance(response, dict):
                if "content" in response:
                    span.set_attribute("llm.response_length", len(str(response["content"])))
                if "usage" in response:
                    usage = response["usage"]
                    if "total_tokens" in usage:
                        span.set_attribute("llm.tokens_used", usage["total_tokens"])
                    if "prompt_tokens" in usage:
                        span.set_attribute("llm.prompt_tokens", usage["prompt_tokens"])
                    if "completion_tokens" in usage:
                        span.set_attribute("llm.completion_tokens", usage["completion_tokens"])
            
            # 设置span状态
            if status == InteractionStatus.SUCCESS:
                span.set_status(Status(StatusCode.OK))
                span.add_event("LLM response received successfully")
            else:
                span.set_status(Status(StatusCode.ERROR, f"LLM response failed: {status.value}"))
                span.add_event("LLM response failed")
    
    def record_error(self, interaction_id: str, error: Exception) -> None:
        """记录错误，添加OpenTelemetry追踪
        
        Args:
            interaction_id: 交互ID
            error: 异常对象
        """
        # 调用父类方法
        super().record_error(interaction_id, error)
        
        # 获取对应的span
        span = self._active_spans.get(interaction_id)
        if span:
            # 记录异常
            span.set_status(Status(StatusCode.ERROR, str(error)))
            span.record_exception(error)
            span.add_event("Error occurred", {"error.type": type(error).__name__})
    
    def end_interaction(self, interaction_id: Optional[str] = None) -> None:
        """结束交互，关闭OpenTelemetry span
        
        Args:
            interaction_id: 可选的交互ID
        """
        # 调用父类方法
        super().end_interaction(interaction_id)
        
        # 获取实际的交互ID
        if not interaction_id and self._interaction_stack:
            interaction_id = self._interaction_stack[-1]
        
        # 关闭对应的span
        if interaction_id and interaction_id in self._active_spans:
            span = self._active_spans[interaction_id]
            span.add_event("Interaction ended")
            span.end()
            del self._active_spans[interaction_id]
    
    def add_span_event(self, interaction_id: str, event_name: str, attributes: Optional[Dict[str, Any]] = None) -> None:
        """为指定交互的span添加事件
        
        Args:
            interaction_id: 交互ID
            event_name: 事件名称
            attributes: 事件属性
        """
        span = self._active_spans.get(interaction_id)
        if span:
            span.add_event(event_name, attributes or {})
    
    def set_span_attribute(self, interaction_id: str, key: str, value: Any) -> None:
        """为指定交互的span设置属性
        
        Args:
            interaction_id: 交互ID
            key: 属性键
            value: 属性值
        """
        span = self._active_spans.get(interaction_id)
        if span and isinstance(value, (str, int, float, bool)):
            span.set_attribute(key, value)
    
    def get_trace_context(self, interaction_id: str) -> Dict[str, str]:
        """获取追踪上下文，用于分布式追踪
        
        Args:
            interaction_id: 交互ID
            
        Returns:
            追踪上下文字典
        """
        span = self._active_spans.get(interaction_id)
        if span:
            headers = {}
            # 将当前span设置为活动span，然后注入上下文
            with trace.use_span(span):
                inject(headers)
            return headers
        return {}
    
    def continue_trace(self, interaction_id: str, trace_context: Dict[str, str]) -> None:
        """继续分布式追踪
        
        Args:
            interaction_id: 交互ID
            trace_context: 追踪上下文
        """
        # 从上下文中提取追踪信息
        parent_context = extract(trace_context)
        
        # 在父上下文中创建新的span
        span = self.tracer.start_span(f"continued_interaction_{interaction_id}", context=parent_context)
        span.set_attribute("interaction.id", interaction_id)
        span.set_attribute("interaction.type", "continued")
        
        # 更新active spans
        self._active_spans[interaction_id] = span
        
        span.add_event("Trace continued from distributed context")
    
    def clear_all_data(self) -> None:
        """清除所有数据，包括OpenTelemetry spans"""
        # 结束所有活动的spans
        for interaction_id, span in self._active_spans.items():
            span.add_event("Span ended during cleanup")
            span.end()
        
        self._active_spans.clear()
        
        # 调用父类方法
        super().clear_all_data()


class TracedAgent:
    """带追踪的Agent示例
    
    展示如何在Agent中使用OpenTelemetry追踪。
    """
    
    def __init__(self, agent_id: str, model_name: str = "gpt-4"):
        self.agent_id = agent_id
        self.model_name = model_name
        self.observability = OpenTelemetryObservabilityManager()
        self.tracer = get_tracer(__name__)
    
    def process_message(self, user_id: str, message: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """处理用户消息的完整流程"""
        # 开始交互追踪
        interaction_id = self.observability.start_interaction(
            context={
                "agent_id": self.agent_id,
                "user_id": user_id,
                "message_length": len(message),
                **(context or {})
            }
        )
        
        try:
            # 1. 预处理
            processed_message = self._preprocess_message(interaction_id, message)
            
            # 2. 生成响应
            response = self._generate_response(interaction_id, user_id, processed_message)
            
            # 3. 后处理
            final_response = self._postprocess_response(interaction_id, response)
            
            # 4. 记录成功结果
            self.observability.add_span_event(
                interaction_id, 
                "message_processed_successfully",
                {"response_length": len(final_response)}
            )
            
            return {
                "interaction_id": interaction_id,
                "response": final_response,
                "status": "success"
            }
            
        except Exception as e:
            # 记录错误
            self.observability.record_error(interaction_id, e)
            return {
                "interaction_id": interaction_id,
                "response": "Sorry, I encountered an error processing your message.",
                "status": "error",
                "error": str(e)
            }
        finally:
            # 结束交互
            self.observability.end_interaction(interaction_id)
    
    def _preprocess_message(self, interaction_id: str, message: str) -> str:
        """预处理消息"""
        with self.tracer.start_as_current_span("preprocess_message") as span:
            span.set_attribute("message.original_length", len(message))
            
            # 模拟预处理
            time.sleep(0.01)
            processed = message.strip()
            
            span.set_attribute("message.processed_length", len(processed))
            span.add_event("Message preprocessed")
            
            # 添加到主span
            self.observability.add_span_event(
                interaction_id,
                "preprocessing_completed",
                {"length_change": len(processed) - len(message)}
            )
            
            return processed
    
    def _generate_response(self, interaction_id: str, user_id: str, message: str) -> str:
        """生成响应"""
        with self.tracer.start_as_current_span("generate_response") as span:
            span.set_attribute("user.id", user_id)
            span.set_attribute("message.length", len(message))
            
            # 模拟LLM调用
            llm_messages = [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": message}
            ]
            
            # 记录LLM请求
            self.observability.record_llm_request(
                interaction_id,
                self.model_name,
                llm_messages,
                self.agent_id,
                temperature=0.7,
                max_tokens=1000
            )
            
            try:
                # 模拟LLM调用延迟
                time.sleep(0.5)
                
                # 模拟响应
                response = f"I understand you said: {message}. How can I help you further?"
                
                # 记录LLM响应
                self.observability.record_llm_response(
                    interaction_id,
                    {
                        "content": response,
                        "usage": {
                            "total_tokens": 50,
                            "prompt_tokens": 30,
                            "completion_tokens": 20
                        }
                    },
                    InteractionStatus.SUCCESS
                )
                
                span.set_attribute("response.length", len(response))
                span.add_event("Response generated successfully")
                
                return response
                
            except Exception as e:
                # 记录LLM错误
                self.observability.record_llm_response(
                    interaction_id,
                    {"error": str(e)},
                    InteractionStatus.FAILED
                )
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def _postprocess_response(self, interaction_id: str, response: str) -> str:
        """后处理响应"""
        with self.tracer.start_as_current_span("postprocess_response") as span:
            span.set_attribute("response.original_length", len(response))
            
            # 模拟后处理
            time.sleep(0.01)
            processed = response.capitalize()
            
            span.set_attribute("response.processed_length", len(processed))
            span.add_event("Response postprocessed")
            
            # 添加到主span
            self.observability.add_span_event(
                interaction_id,
                "postprocessing_completed",
                {"final_length": len(processed)}
            )
            
            return processed
    
    def get_trace_context(self, interaction_id: str) -> Dict[str, str]:
        """获取追踪上下文，用于分布式调用"""
        return self.observability.get_trace_context(interaction_id)


# 使用示例
def example_usage():
    """使用示例"""
    # 创建带追踪的Agent
    agent = TracedAgent("agent_001", "gpt-4")
    
    # 处理消息
    result = agent.process_message(
        "user_123",
        "Hello, how are you today?",
        {"session_id": "sess_456", "channel": "web"}
    )
    
    print(f"Result: {result}")
    
    # 获取指标摘要
    metrics = agent.observability.get_metrics_summary()
    print(f"Metrics: {metrics}")


if __name__ == "__main__":
    example_usage() 