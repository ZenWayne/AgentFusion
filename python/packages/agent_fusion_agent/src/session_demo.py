"""Session使用示例

演示如何使用Session类进行单Agent和群聊的会话管理。
"""

import asyncio
from datetime import datetime

from agent import (
    create_simple_agent,
    create_group_chat,
    create_session,
    get_session_manager,
    SessionConfig
)


async def demo_single_agent_session():
    """演示单Agent会话"""
    print("=== 单Agent会话示例 ===")
    
    # 创建Agent
    agent = create_simple_agent(
        name="AI助手",
        model="gpt-4",
        system_prompt="你是一个有用的AI助手，总是以友好的方式回应用户。"
    )
    
    # 创建会话
    session = create_session(agent, name="AI助手会话")
    
    print(f"创建会话: {session.config.name}")
    print(f"会话ID: {session.config.session_id}")
    print(f"会话类型: {session.session_type}")
    
    # 开始会话
    session.start()
    print("会话已启动")
    
    # 添加上下文变量
    session.add_context_variable("user_name", "张三")
    session.add_context_variable("session_start", datetime.now())
    
    # 模拟对话
    messages = [
        "你好！",
        "我的名字是什么？",
        "现在是什么时间？",
        "谢谢你的帮助！"
    ]
    
    for message in messages:
        print(f"\n用户: {message}")
        try:
            response = await session.process_message(message)
            print(f"AI助手: {response.content}")
        except Exception as e:
            print(f"错误: {e}")
    
    # 查看会话状态
    print(f"\n会话状态: {session.get_status()}")
    
    # 查看对话历史
    history = session.get_conversation_history(limit=5)
    print(f"\n最近5条消息:")
    for msg in history:
        print(f"  {msg['role']}: {msg['content'][:50]}...")
    
    # 结束会话
    session.end()
    print("会话已结束")


async def demo_group_chat_session():
    """演示群聊会话"""
    print("\n=== 群聊会话示例 ===")
    
    # 创建多个Agent
    tech_expert = create_simple_agent(
        name="技术专家Alice",
        model="gpt-4",
        system_prompt="你是Alice，一名资深技术专家。专注于技术方案设计和架构讨论。"
    )
    
    product_manager = create_simple_agent(
        name="产品经理Bob",
        model="gpt-4", 
        system_prompt="你是Bob，一名产品经理。专注于产品需求分析和用户体验。"
    )
    
    designer = create_simple_agent(
        name="设计师Carol",
        model="gpt-4",
        system_prompt="你是Carol，一名UI/UX设计师。专注于用户界面设计和交互体验。"
    )
    
    # 创建群聊
    group = create_group_chat(
        name="产品开发团队",
        selector_model="gpt-4",
        selector_prompt="根据讨论内容选择最合适的专家来回应。技术问题选择Alice，产品问题选择Bob，设计问题选择Carol。"
    )
    
    # 添加Agent到群聊
    group.add_agent(tech_expert)
    group.add_agent(product_manager)
    group.add_agent(designer)
    
    print(f"群聊成员: {[agent['name'] for agent in group.list_agents()]}")
    
    # 创建群聊会话
    session = create_session(group, name="产品开发讨论")
    
    print(f"创建群聊会话: {session.config.name}")
    print(f"会话类型: {session.session_type}")
    
    # 开始会话
    session.start()
    print("群聊会话已启动")
    
    # 模拟群聊讨论
    topics = [
        "我们需要开发一个新的移动应用，请大家讨论技术方案",
        "用户反馈说界面不够直观，需要优化设计",
        "如何提升应用的性能和响应速度？"
    ]
    
    for topic in topics:
        print(f"\n讨论话题: {topic}")
        try:
            responses = await session.process_message(topic)
            for response in responses:
                print(f"  {response.get('agent_name', 'Unknown')}: {response.get('content', '')}")
        except Exception as e:
            print(f"错误: {e}")
    
    # 查看会话状态
    status = session.get_status()
    print(f"\n群聊会话状态: {status}")
    
    # 结束会话
    session.end()
    print("群聊会话已结束")


async def demo_session_manager():
    """演示会话管理器"""
    print("\n=== 会话管理器示例 ===")
    
    # 获取会话管理器
    session_manager = get_session_manager()
    
    # 创建多个Agent
    agent1 = create_simple_agent("助手1", system_prompt="你是助手1")
    agent2 = create_simple_agent("助手2", system_prompt="你是助手2")
    
    # 创建群聊
    group = create_group_chat("测试群聊")
    group.add_agent(agent1)
    group.add_agent(agent2)
    
    # 通过管理器创建会话
    session1 = session_manager.create_session(agent1, SessionConfig(name="会话1"))
    session2 = session_manager.create_session(agent2, SessionConfig(name="会话2"))
    session3 = session_manager.create_session(group, SessionConfig(name="群聊会话"))
    
    print("创建了3个会话")
    
    # 启动会话
    session1.start()
    session2.start()
    session3.start()
    
    # 获取活跃会话
    active_sessions = session_manager.get_active_sessions()
    print(f"活跃会话数: {len(active_sessions)}")
    
    # 获取统计信息
    stats = session_manager.get_manager_statistics()
    print(f"管理器统计: {stats}")
    
    # 列出所有会话
    all_sessions = session_manager.list_sessions()
    print(f"所有会话ID: {all_sessions}")
    
    # 结束所有会话
    session_manager.end_all_sessions()
    print("所有会话已结束")


async def demo_context_manager():
    """演示上下文管理器模式"""
    print("\n=== 上下文管理器示例 ===")
    
    agent = create_simple_agent("上下文助手", system_prompt="你是一个测试助手")
    
    # 同步上下文管理器
    print("使用同步上下文管理器:")
    with create_session(agent, name="同步会话") as session:
        try:
            response = await session.process_message("Hello")
            print(f"响应: {response.content}")
        except Exception as e:
            print(f"错误: {e}")
    
    # 异步上下文管理器
    print("\n使用异步上下文管理器:")
    async with create_session(agent, name="异步会话") as session:
        try:
            response = await session.process_message("Hello again")
            print(f"响应: {response.content}")
        except Exception as e:
            print(f"错误: {e}")


async def demo_streaming():
    """演示流式输出"""
    print("\n=== 流式输出示例 ===")
    
    agent = create_simple_agent("流式助手", system_prompt="你是一个会讲故事的助手")
    
    async with create_session(agent, name="流式会话") as session:
        print("用户: 请讲一个简短的故事")
        print("AI助手: ", end="", flush=True)
        
        try:
            async for chunk in session.stream_process_message("请讲一个简短的故事"):
                print(chunk.content, end="", flush=True)
            print()  # 换行
        except Exception as e:
            print(f"\n错误: {e}")


async def main():
    """主函数"""
    print("Session类使用示例")
    print("=" * 50)
    
    try:
        await demo_single_agent_session()
        await demo_group_chat_session()
        await demo_session_manager()
        await demo_context_manager()
        await demo_streaming()
    except Exception as e:
        print(f"演示过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n演示完成！")


if __name__ == "__main__":
    asyncio.run(main()) 