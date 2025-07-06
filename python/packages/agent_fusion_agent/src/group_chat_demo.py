"""群聊系统OpenTelemetry演示

展示使用@trace装饰器注解的群聊系统。
"""

import asyncio
import time
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode

from .opentelemetry_config import setup_opentelemetry, cleanup_opentelemetry
from .group_chat import GroupChat, GroupChatConfig, GroupChatManager
from .agent import AgentConfig

# 获取tracer
tracer = trace.get_tracer(__name__)


class MockAgent:
    """模拟Agent用于演示"""
    
    def __init__(self, agent_id: str, name: str):
        self.config = AgentConfig(
            agent_id=agent_id,
            name=name,
            model="gpt-3.5-turbo",
            description=f"Mock agent {name}"
        )
    
    @tracer.start_as_current_span("mock_agent_process")
    async def process_message(self, message: str, **kwargs):
        """模拟处理消息"""
        span = trace.get_current_span()
        span.set_attribute("agent_id", self.config.agent_id)
        span.set_attribute("message_length", len(message))
        
        # 模拟处理时间
        await asyncio.sleep(0.1)
        
        response_content = f"{self.config.name}: 我收到了消息 '{message}'"
        
        span.set_attribute("response_length", len(response_content))
        span.add_event("response_generated")
        
        # 返回模拟响应对象
        class MockResponse:
            def __init__(self, content, model):
                self.content = content
                self.model = model
                self.usage = {"total_tokens": 25}
        
        return MockResponse(response_content, self.config.model)


class GroupChatDemo:
    """群聊演示类"""
    
    def __init__(self):
        self.setup_complete = False
        self.manager = GroupChatManager()
    
    @tracer.start_as_current_span("demo_setup")
    def setup(self):
        """设置演示环境"""
        span = trace.get_current_span()
        
        print("🔧 设置OpenTelemetry演示环境...")
        setup_opentelemetry(
            service_name="groupchat-demo",
            service_version="1.0.0",
            console_export=True
        )
        
        span.add_event("opentelemetry_configured")
        self.setup_complete = True
        print("✅ 演示环境设置完成!")
    
    @tracer.start_as_current_span("create_demo_group")
    def create_demo_group(self):
        """创建演示群聊"""
        span = trace.get_current_span()
        
        # 创建群聊配置
        config = GroupChatConfig(
            group_id="demo_group",
            name="AI专家讨论组",
            description="多个AI专家进行技术讨论",
            max_rounds=3,
            max_messages_per_round=2
        )
        
        span.set_attribute("group_id", config.group_id)
        span.set_attribute("max_rounds", config.max_rounds)
        
        # 创建群聊
        group_chat = self.manager.create_group_chat(config)
        
        # 创建模拟Agent
        agents = [
            MockAgent("expert_1", "技术专家Alice"),
            MockAgent("expert_2", "产品经理Bob"),
            MockAgent("expert_3", "设计师Carol")
        ]
        
        # 添加Agent到群聊
        for agent in agents:
            group_chat.add_agent(agent, role="专家")
        
        span.set_attribute("agent_count", len(agents))
        span.add_event("demo_group_created")
        
        print(f"📁 创建群聊: {config.name}")
        print(f"👥 添加了 {len(agents)} 个Agent")
        
        return group_chat
    
    @tracer.start_as_current_span("demo_basic_conversation")
    async def demo_basic_conversation(self, group_chat: GroupChat):
        """演示基本对话"""
        span = trace.get_current_span()
        
        print("\n💬 开始基本对话演示")
        print("=" * 40)
        
        # 开始会话
        session = group_chat.start_session()
        span.set_attribute("session_id", session.session_id)
        
        # 发送消息
        test_messages = [
            "大家好，我们来讨论一下AI技术的发展趋势",
            "请分享你们对ChatGPT的看法",
            "如何看待AI在产品设计中的应用？"
        ]
        
        span.set_attribute("message_count", len(test_messages))
        
        for i, message in enumerate(test_messages):
            print(f"\n🔹 用户消息 {i+1}: {message}")
            
            with tracer.start_as_current_span("process_test_message") as msg_span:
                msg_span.set_attribute("message_index", i)
                msg_span.set_attribute("message", message)
                
                try:
                    responses = await group_chat.process_message(message)
                    
                    msg_span.set_attribute("response_count", len(responses))
                    
                    for j, response in enumerate(responses):
                        print(f"   📤 {response['agent_name']}: {response['content'][:100]}...")
                        
                    msg_span.add_event("message_processed_successfully")
                    
                except Exception as e:
                    msg_span.set_status(Status(StatusCode.ERROR, str(e)))
                    msg_span.record_exception(e)
                    print(f"   ❌ 处理失败: {e}")
            
            # 短暂等待
            await asyncio.sleep(0.2)
        
        # 结束会话
        group_chat.end_session()
        span.add_event("conversation_completed")
        
        print("\n✅ 基本对话演示完成")
    
    @tracer.start_as_current_span("demo_error_handling")
    async def demo_error_handling(self, group_chat: GroupChat):
        """演示错误处理"""
        span = trace.get_current_span()
        
        print("\n🚨 开始错误处理演示")
        print("=" * 40)
        
        try:
            # 尝试在没有活动会话的情况下发送消息
            await group_chat.process_message("这应该会失败")
        except Exception as e:
            span.add_event("expected_error_caught", {"error": str(e)})
            print(f"✅ 成功捕获预期错误: {e}")
        
        # 尝试添加重复的Agent
        try:
            duplicate_agent = MockAgent("expert_1", "重复专家")
            group_chat.add_agent(duplicate_agent)
        except Exception as e:
            span.add_event("duplicate_agent_error", {"error": str(e)})
            print(f"✅ 成功捕获重复Agent错误: {e}")
        
        span.add_event("error_handling_completed")
        print("\n✅ 错误处理演示完成")
    
    @tracer.start_as_current_span("demo_performance_metrics")
    def demo_performance_metrics(self, group_chat: GroupChat):
        """演示性能指标"""
        span = trace.get_current_span()
        
        print("\n📊 群聊状态信息")
        print("=" * 40)
        
        status = group_chat.get_status()
        
        # 记录性能指标
        span.set_attribute("agent_count", status["agent_count"])
        span.set_attribute("has_active_session", bool(status["current_session"]))
        
        print(f"群聊ID: {status['group_id']}")
        print(f"群聊名称: {status['name']}")
        print(f"Agent数量: {status['agent_count']}")
        print(f"当前会话: {'是' if status['current_session'] else '否'}")
        
        # 管理器统计
        manager_stats = self.manager.get_manager_statistics()
        span.set_attribute("total_groups", manager_stats["total_group_chats"])
        
        print(f"总群聊数: {manager_stats['total_group_chats']}")
        print(f"活跃会话: {manager_stats['active_sessions']}")
        
        span.add_event("metrics_collected")
        print("\n✅ 性能指标演示完成")
    
    @tracer.start_as_current_span("cleanup_demo")
    def cleanup(self):
        """清理演示资源"""
        span = trace.get_current_span()
        
        print("\n🧹 清理演示资源...")
        
        # 移除所有群聊
        for group_id in self.manager.list_group_chats():
            self.manager.remove_group_chat(group_id)
            span.add_event("group_removed", {"group_id": group_id})
        
        # 清理OpenTelemetry
        cleanup_opentelemetry()
        
        span.add_event("cleanup_completed")
        print("✅ 清理完成!")
    
    @tracer.start_as_current_span("run_all_demos")
    async def run_all_demos(self):
        """运行所有演示"""
        span = trace.get_current_span()
        
        if not self.setup_complete:
            self.setup()
        
        print("\n🎬 开始GroupChat OpenTelemetry演示")
        print("=" * 60)
        
        try:
            # 创建演示群聊
            group_chat = self.create_demo_group()
            
            # 运行各种演示
            await self.demo_basic_conversation(group_chat)
            await self.demo_error_handling(group_chat)
            self.demo_performance_metrics(group_chat)
            
            span.add_event("all_demos_completed")
            print("\n🎉 所有演示完成!")
            
        except Exception as e:
            span.set_status(Status(StatusCode.ERROR, str(e)))
            span.record_exception(e)
            print(f"\n❌ 演示失败: {e}")
            raise
        finally:
            self.cleanup()


async def main():
    """主函数"""
    demo = GroupChatDemo()
    await demo.run_all_demos()


if __name__ == "__main__":
    asyncio.run(main()) 