"""MCP集成使用示例

展示如何使用新的MCP集成功能和handle_response机制。
"""

import asyncio
from mcp import StdioServerParameters
from agent import create_simple_agent, create_mcp_agent, AgentConfig, SimpleAgent, MCPMixin
from llm_client import MockLLMClient, get_llm_client_manager
from observability import get_observability_manager


async def example_simple_agent_with_mcp():
    """示例：创建带有MCP工具的SimpleAgent"""
    print("=== 示例：SimpleAgent with MCP工具 ===")
    
    # 创建MCP工具配置
    mcp_tools = [
        StdioServerParameters(
            command="python",
            args=["-c", "import sys; print('Hello from Python tool!')"],
            env={"PYTHONPATH": "."}
        )
    ]
    
    # 设置LLM客户端
    llm_manager = get_llm_client_manager()
    mock_client = MockLLMClient()
    llm_manager.register_client("example_client", mock_client)
    
    # 创建Agent - 方式1：使用便利函数
    agent1 = create_simple_agent(
        name="MCP助手",
        model="gpt-3.5-turbo",
        system_prompt="你是一个拥有工具能力的AI助手。",
        mcp_tools=mcp_tools,
        llm_client_name="example_client"
    )
    
    # 验证Agent是MCPMixin的实例
    print(f"Agent是MCPMixin实例: {isinstance(agent1, MCPMixin)}")
    
    # 测试Agent状态
    status = agent1.get_status()
    print(f"Agent1 状态: {status}")
    
    # 测试消息处理（会触发handle_response）
    try:
        print("\n测试消息处理...")
        response = await agent1.process_message("你好，你能帮我做什么？")
        print(f"响应: {response.content}")
        print("✓ handle_response已自动调用")
    except Exception as e:
        print(f"消息处理失败: {e}")
    
    # 测试流式处理（会触发handle_response）
    try:
        print("\n测试流式处理...")
        async for chunk in agent1.stream_process_message("告诉我你的能力"):
            print(f"流式块: {chunk.content}")
        print("✓ handle_response已自动调用")
    except Exception as e:
        print(f"流式处理失败: {e}")


async def example_mcp_mixin_functionality():
    """示例：MCPMixin功能演示"""
    print("\n=== 示例：MCPMixin功能演示 ===")
    
    # 创建MCP工具配置
    mcp_tools = [
        StdioServerParameters(
            command="echo",
            args=["Hello from MCP mixin"],
            env={}
        )
    ]
    
    # 设置LLM客户端
    llm_manager = get_llm_client_manager()
    mock_client = MockLLMClient()
    llm_manager.register_client("mixin_client", mock_client)
    
    # 创建Agent
    config = AgentConfig(
        name="MCP Mixin示例",
        model="gpt-3.5-turbo",
        system_prompt="你是一个展示MCP mixin功能的AI助手。",
        mcp_tools=mcp_tools,
        llm_client_name="mixin_client"
    )
    agent = SimpleAgent(config)
    
    # 测试MCP状态
    mcp_status = agent.get_mcp_status()
    print(f"MCP状态: {mcp_status}")
    
    # 测试MCP工具初始化
    print("\n手动初始化MCP工具...")
    try:
        await agent._ensure_mcp_initialized()
        print("✓ MCP工具初始化成功")
        print(f"工具数量: {len(agent.mcp_tools)}")
        print(f"工具包数量: {len(agent.mcp_toolkits)}")
    except Exception as e:
        print(f"MCP工具初始化失败: {e}")


async def example_handle_response_mechanism():
    """示例：handle_response机制演示"""
    print("\n=== 示例：handle_response机制演示 ===")
    
    # 创建自定义Agent类来展示handle_response机制
    class CustomAgent(SimpleAgent):
        def __init__(self, config):
            super().__init__(config)
            self.response_count = 0
            self.handled_responses = []
        
        async def handle_response(self, response, **context):
            """重写handle_response以展示机制"""
            self.response_count += 1
            self.handled_responses.append({
                "content": response.content,
                "context": context,
                "timestamp": "now"
            })
            print(f"🎯 CustomAgent.handle_response被调用 (第{self.response_count}次)")
            print(f"   响应内容: {response.content[:50]}...")
            print(f"   上下文: {list(context.keys())}")
            
            # 调用父类的handle_response
            await super().handle_response(response, **context)
    
    # 设置LLM客户端
    llm_manager = get_llm_client_manager()
    mock_client = MockLLMClient()
    llm_manager.register_client("custom_client", mock_client)
    
    # 创建自定义Agent
    config = AgentConfig(
        name="自定义响应处理Agent",
        model="gpt-3.5-turbo",
        system_prompt="你是一个展示响应处理机制的AI助手。",
        llm_client_name="custom_client"
    )
    agent = CustomAgent(config)
    
    # 测试响应处理
    print("\n发送消息...")
    response = await agent.process_message("展示handle_response机制")
    
    print(f"\n响应处理统计:")
    print(f"  响应处理次数: {agent.response_count}")
    print(f"  处理的响应数量: {len(agent.handled_responses)}")
    
    # 测试流式处理的响应处理
    print("\n测试流式处理的响应处理...")
    async for chunk in agent.stream_process_message("流式响应处理"):
        pass  # 只是为了触发handle_response
    
    print(f"\n流式处理后的统计:")
    print(f"  响应处理次数: {agent.response_count}")


async def example_component_handle_response():
    """示例：组件handle_response调用"""
    print("\n=== 示例：组件handle_response调用 ===")
    
    # 创建带有模拟组件的Agent
    class MockComponent:
        def __init__(self, name):
            self.name = name
            self.handled_responses = []
        
        async def handle_response(self, response, **context):
            self.handled_responses.append({
                "content": response.content,
                "context": context
            })
            print(f"📦 {self.name}.handle_response被调用")
    
    class ComponentAwareAgent(SimpleAgent):
        def __init__(self, config):
            super().__init__(config)
            # 添加模拟组件
            self.mock_context_engine = MockComponent("MockContextEngine")
            self.mock_llm_client = MockComponent("MockLLMClient")
        
        async def handle_response(self, response, **context):
            """演示组件handle_response调用"""
            print(f"🚀 开始调用组件handle_response方法...")
            
            # 调用模拟组件的handle_response
            await self.mock_context_engine.handle_response(response, **context)
            await self.mock_llm_client.handle_response(response, **context)
            
            # 调用父类的handle_response
            await super().handle_response(response, **context)
            
            print(f"✅ 所有组件handle_response调用完成")
    
    # 设置LLM客户端
    llm_manager = get_llm_client_manager()
    mock_client = MockLLMClient()
    llm_manager.register_client("component_client", mock_client)
    
    # 创建Agent
    config = AgentConfig(
        name="组件感知Agent",
        model="gpt-3.5-turbo",
        system_prompt="你是一个展示组件响应处理的AI助手。",
        llm_client_name="component_client"
    )
    agent = ComponentAwareAgent(config)
    
    # 测试组件响应处理
    print("\n发送消息以触发组件响应处理...")
    response = await agent.process_message("测试组件响应处理")
    
    print(f"\n组件响应处理统计:")
    print(f"  MockContextEngine处理次数: {len(agent.mock_context_engine.handled_responses)}")
    print(f"  MockLLMClient处理次数: {len(agent.mock_llm_client.handled_responses)}")


async def example_inheritance_hierarchy():
    """示例：继承层次结构演示"""
    print("\n=== 示例：继承层次结构 ===")
    
    # 设置LLM客户端
    llm_manager = get_llm_client_manager()
    mock_client = MockLLMClient()
    llm_manager.register_client("hierarchy_client", mock_client)
    
    # 创建Agent
    config = AgentConfig(
        name="继承层次示例",
        model="gpt-3.5-turbo",
        mcp_tools=[
            StdioServerParameters(
                command="echo",
                args=["Inheritance demo"],
                env={}
            )
        ],
        llm_client_name="hierarchy_client"
    )
    agent = SimpleAgent(config)
    
    # 展示继承层次
    print(f"Agent类: {agent.__class__.__name__}")
    print(f"继承自: {[cls.__name__ for cls in agent.__class__.__bases__]}")
    print(f"方法解析顺序: {[cls.__name__ for cls in agent.__class__.__mro__]}")
    
    # 测试各种功能
    print(f"\n功能测试:")
    print(f"  是否为AgentBase实例: {hasattr(agent, 'process_message')}")
    print(f"  是否为MCPMixin实例: {hasattr(agent, 'mcp_tools')}")
    print(f"  是否有handle_response: {hasattr(agent, 'handle_response')}")
    print(f"  是否有MCP初始化: {hasattr(agent, '_ensure_mcp_initialized')}")


async def main():
    """主函数"""
    print("MCP集成与handle_response机制演示")
    print("=" * 60)
    
    # 设置日志
    observability = get_observability_manager()
    observability.logger.info("开始MCP集成与响应处理示例")
    
    # 运行示例
    await example_simple_agent_with_mcp()
    await example_mcp_mixin_functionality()
    await example_handle_response_mechanism()
    await example_component_handle_response()
    await example_inheritance_hierarchy()
    
    print("\n" + "=" * 60)
    print("所有示例完成")


if __name__ == "__main__":
    asyncio.run(main()) 