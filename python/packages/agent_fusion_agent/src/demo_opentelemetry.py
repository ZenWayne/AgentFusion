"""OpenTelemetry演示文件

运行各种OpenTelemetry示例，展示追踪和监控功能。
"""

import asyncio
import time
from typing import Dict, Any

from .opentelemetry_config import setup_opentelemetry, cleanup_opentelemetry
from .opentelemetry_integration import TracedAgent, OpenTelemetryObservabilityManager


class OpenTelemetryDemo:
    """OpenTelemetry演示类"""
    
    def __init__(self):
        self.setup_complete = False
    
    def setup(self):
        """设置OpenTelemetry"""
        print("🔧 Setting up OpenTelemetry...")
        setup_opentelemetry(
            service_name="agent-fusion-demo",
            service_version="1.0.0",
            console_export=True  # 输出到控制台便于观察
        )
        self.setup_complete = True
        print("✅ OpenTelemetry setup complete!")
    
    def demo_basic_agent_interaction(self):
        """演示基本Agent交互"""
        print("\n🤖 Demo: Basic Agent Interaction")
        print("=" * 50)
        
        # 创建带追踪的Agent
        agent = TracedAgent("demo_agent", "gpt-4")
        
        # 处理几个不同的消息
        messages = [
            "Hello, how are you?",
            "What's the weather like today?",
            "Can you help me with Python programming?",
            "Tell me a joke"
        ]
        
        for i, message in enumerate(messages):
            print(f"\n💬 Processing message {i+1}: {message}")
            
            result = agent.process_message(
                user_id=f"user_{i+1}",
                message=message,
                context={
                    "session_id": f"session_{i+1}",
                    "channel": "demo",
                    "timestamp": time.time()
                }
            )
            
            print(f"✅ Response: {result['response']}")
            print(f"📊 Status: {result['status']}")
            
            # 稍微等待一下，便于观察
            time.sleep(0.1)
        
        # 获取指标摘要
        metrics = agent.observability.get_metrics_summary()
        print(f"\n📈 Metrics Summary:")
        print(f"   Total interactions: {metrics.get('total_interactions', 0)}")
        print(f"   Successful interactions: {metrics.get('successful_interactions', 0)}")
        print(f"   Success rate: {metrics.get('success_rate', 0):.2%}")
        print(f"   Average duration: {metrics.get('average_duration_ms', 0):.2f}ms")
    
    def demo_error_handling(self):
        """演示错误处理"""
        print("\n🚨 Demo: Error Handling")
        print("=" * 50)
        
        agent = TracedAgent("error_demo_agent", "gpt-4")
        
        # 模拟一个会产生错误的场景
        class ErrorAgent(TracedAgent):
            def _generate_response(self, interaction_id: str, user_id: str, message: str) -> str:
                # 模拟特定条件下的错误
                if "error" in message.lower():
                    raise ValueError("Simulated error for demonstration")
                return super()._generate_response(interaction_id, user_id, message)
        
        error_agent = ErrorAgent("error_agent", "gpt-4")
        
        # 正常消息
        print("\n✅ Processing normal message...")
        result = error_agent.process_message("user_1", "Hello there!")
        print(f"Response: {result['response']}")
        
        # 触发错误的消息
        print("\n❌ Processing message that will trigger error...")
        result = error_agent.process_message("user_2", "This will cause an error")
        print(f"Response: {result['response']}")
        print(f"Error: {result.get('error', 'No error')}")
        
        # 检查指标
        metrics = error_agent.observability.get_metrics_summary()
        print(f"\n📊 Error Handling Metrics:")
        print(f"   Total interactions: {metrics.get('total_interactions', 0)}")
        print(f"   Failed interactions: {metrics.get('failed_interactions', 0)}")
        print(f"   Success rate: {metrics.get('success_rate', 0):.2%}")
    
    def demo_distributed_tracing(self):
        """演示分布式追踪"""
        print("\n🌐 Demo: Distributed Tracing")
        print("=" * 50)
        
        # 模拟两个不同的服务
        service_a_agent = TracedAgent("service_a_agent", "gpt-4")
        service_b_agent = TracedAgent("service_b_agent", "gpt-3.5-turbo")
        
        # 服务A处理消息
        print("\n🔵 Service A processing message...")
        result_a = service_a_agent.process_message(
            "user_distributed",
            "This is a distributed request",
            {"service": "A", "step": 1}
        )
        
        # 获取追踪上下文
        trace_context = service_a_agent.get_trace_context(result_a["interaction_id"])
        print(f"📋 Trace context headers: {list(trace_context.keys())}")
        
        # 服务B继续处理（模拟接收到分布式调用）
        print("\n🟢 Service B continuing the trace...")
        
        # 创建新的可观测性管理器并继续追踪
        service_b_observability = OpenTelemetryObservabilityManager()
        interaction_id_b = service_b_observability.start_interaction(
            context={"service": "B", "step": 2, "parent_service": "A"}
        )
        
        # 继续分布式追踪
        service_b_observability.continue_trace(interaction_id_b, trace_context)
        
        # 模拟一些处理
        service_b_observability.add_span_event(
            interaction_id_b,
            "distributed_processing_started",
            {"received_from": "service_a"}
        )
        
        time.sleep(0.2)  # 模拟处理时间
        
        service_b_observability.add_span_event(
            interaction_id_b,
            "distributed_processing_completed",
            {"processing_time": 0.2}
        )
        
        # 结束分布式追踪
        service_b_observability.end_interaction(interaction_id_b)
        
        print("✅ Distributed tracing completed!")
    
    def demo_concurrent_interactions(self):
        """演示并发交互"""
        print("\n⚡ Demo: Concurrent Interactions")
        print("=" * 50)
        
        agent = TracedAgent("concurrent_agent", "gpt-4")
        
        # 并发处理多个消息
        async def process_concurrent_messages():
            tasks = []
            messages = [
                ("user_1", "What's 2+2?"),
                ("user_2", "Tell me about Python"),
                ("user_3", "How's the weather?"),
                ("user_4", "What's your favorite color?"),
                ("user_5", "Can you help me?")
            ]
            
            for user_id, message in messages:
                # 创建异步任务（虽然process_message是同步的，但我们可以用线程池）
                task = asyncio.create_task(
                    asyncio.to_thread(
                        agent.process_message,
                        user_id,
                        message,
                        {"concurrent": True, "timestamp": time.time()}
                    )
                )
                tasks.append(task)
            
            # 等待所有任务完成
            results = await asyncio.gather(*tasks)
            return results
        
        # 运行并发处理
        print("🚀 Starting concurrent processing...")
        start_time = time.time()
        
        results = asyncio.run(process_concurrent_messages())
        
        end_time = time.time()
        total_time = end_time - start_time
        
        print(f"✅ Processed {len(results)} messages concurrently in {total_time:.2f}s")
        
        # 显示结果
        for i, result in enumerate(results):
            print(f"   Message {i+1}: {result['status']}")
        
        # 获取指标
        metrics = agent.observability.get_metrics_summary()
        print(f"\n📊 Concurrent Processing Metrics:")
        print(f"   Total interactions: {metrics.get('total_interactions', 0)}")
        print(f"   Average duration: {metrics.get('average_duration_ms', 0):.2f}ms")
        print(f"   Success rate: {metrics.get('success_rate', 0):.2%}")
    
    def demo_custom_spans_and_events(self):
        """演示自定义Spans和Events"""
        print("\n🎯 Demo: Custom Spans and Events")
        print("=" * 50)
        
        agent = TracedAgent("custom_agent", "gpt-4")
        
        # 开始一个交互
        interaction_id = agent.observability.start_interaction(
            context={"demo": "custom_spans", "user_type": "premium"}
        )
        
        try:
            # 添加自定义事件
            agent.observability.add_span_event(
                interaction_id,
                "user_authentication_started",
                {"auth_method": "oauth2"}
            )
            
            time.sleep(0.05)  # 模拟认证时间
            
            agent.observability.add_span_event(
                interaction_id,
                "user_authentication_completed",
                {"auth_result": "success", "user_role": "premium"}
            )
            
            # 设置自定义属性
            agent.observability.set_span_attribute(
                interaction_id,
                "user.premium_status",
                True
            )
            
            agent.observability.set_span_attribute(
                interaction_id,
                "feature.advanced_processing",
                True
            )
            
            # 模拟复杂的处理流程
            for step in range(3):
                agent.observability.add_span_event(
                    interaction_id,
                    f"processing_step_{step + 1}",
                    {"step": step + 1, "complexity": "high"}
                )
                time.sleep(0.02)
            
            # 最终事件
            agent.observability.add_span_event(
                interaction_id,
                "custom_processing_completed",
                {"total_steps": 3, "result": "success"}
            )
            
            print("✅ Custom spans and events added successfully!")
            
        finally:
            # 结束交互
            agent.observability.end_interaction(interaction_id)
    
    def cleanup(self):
        """清理资源"""
        print("\n🧹 Cleaning up OpenTelemetry resources...")
        cleanup_opentelemetry()
        print("✅ Cleanup complete!")
    
    def run_all_demos(self):
        """运行所有演示"""
        if not self.setup_complete:
            self.setup()
        
        print("\n🎬 Starting OpenTelemetry Demos")
        print("=" * 60)
        
        try:
            # 运行各种演示
            self.demo_basic_agent_interaction()
            self.demo_error_handling()
            self.demo_distributed_tracing()
            self.demo_concurrent_interactions()
            self.demo_custom_spans_and_events()
            
            print("\n🎉 All demos completed successfully!")
            
        except Exception as e:
            print(f"\n❌ Demo failed with error: {e}")
            raise
        finally:
            self.cleanup()


def main():
    """主函数"""
    demo = OpenTelemetryDemo()
    demo.run_all_demos()


if __name__ == "__main__":
    main() 