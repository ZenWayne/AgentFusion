"""Session类测试

测试Session类的各种功能，包括单Agent会话、群聊会话、会话管理器等。
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent import (
    create_simple_agent,
    create_group_chat,
    create_session,
    get_session_manager,
    SessionConfig,
    Session,
    SessionManager,
    MockLLMClient,
    get_llm_client_manager,
    LLMResponse
)


class TestSessionConfig:
    """测试SessionConfig类"""
    
    def test_default_config(self):
        """测试默认配置"""
        config = SessionConfig()
        
        assert config.name == "Session"
        assert config.description == ""
        assert config.auto_create_components == True
        assert config.context_variables == {}
        assert config.metadata == {}
        assert config.session_id is not None
    
    def test_custom_config(self):
        """测试自定义配置"""
        config = SessionConfig(
            name="Test Session",
            description="Test description",
            auto_create_components=False,
            context_variables={"test": "value"},
            metadata={"version": "1.0"}
        )
        
        assert config.name == "Test Session"
        assert config.description == "Test description"
        assert config.auto_create_components == False
        assert config.context_variables == {"test": "value"}
        assert config.metadata == {"version": "1.0"}
    
    def test_to_dict(self):
        """测试转换为字典"""
        config = SessionConfig(name="Test")
        config_dict = config.to_dict()
        
        assert isinstance(config_dict, dict)
        assert config_dict["name"] == "Test"
        assert "session_id" in config_dict


class TestSession:
    """测试Session类"""
    
    def setup_method(self):
        """设置测试环境"""
        # 设置Mock LLM客户端
        llm_manager = get_llm_client_manager()
        mock_client = MockLLMClient(default_response="Test response")
        llm_manager.register_client("test", mock_client, is_default=True)
    
    def test_init_with_agent(self):
        """测试使用Agent初始化Session"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        assert session.session_type == "single_agent"
        assert session.agent == agent
        assert session.group_chat is None
        assert session.context_engine is not None
        assert session.message_queue is not None
    
    def test_init_with_group_chat(self):
        """测试使用GroupChat初始化Session"""
        group = create_group_chat("Test Group")
        session = Session(group)
        
        assert session.session_type == "group_chat"
        assert session.agent is None
        assert session.group_chat == group
        assert session.context_engine is not None
        assert session.message_queue is not None
    
    def test_init_with_invalid_input(self):
        """测试使用无效输入初始化Session"""
        with pytest.raises(Exception):
            Session("invalid_input")
    
    def test_session_lifecycle(self):
        """测试会话生命周期"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        # 初始状态
        assert session.is_active == False
        assert session.start_time is None
        assert session.end_time is None
        
        # 启动会话
        session.start()
        assert session.is_active == True
        assert session.start_time is not None
        
        # 结束会话
        session.end()
        assert session.is_active == False
        assert session.end_time is not None
    
    def test_start_already_active_session(self):
        """测试启动已激活的会话"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        session.start()
        with pytest.raises(Exception):
            session.start()
    
    @pytest.mark.asyncio
    async def test_process_message_single_agent(self):
        """测试单Agent消息处理"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        session.start()
        
        response = await session.process_message("Hello")
        assert isinstance(response, LLMResponse)
        assert response.content == "Test response"
        
        session.end()
    
    @pytest.mark.asyncio
    async def test_process_message_group_chat(self):
        """测试群聊消息处理"""
        agent1 = create_simple_agent("Agent1")
        agent2 = create_simple_agent("Agent2")
        
        group = create_group_chat("Test Group")
        group.add_agent(agent1)
        group.add_agent(agent2)
        
        session = Session(group)
        session.start()
        
        # Mock群聊响应
        group.process_message = AsyncMock(return_value=[
            {"agent_name": "Agent1", "content": "Response 1", "agent_id": "agent1"},
            {"agent_name": "Agent2", "content": "Response 2", "agent_id": "agent2"}
        ])
        
        responses = await session.process_message("Hello")
        assert isinstance(responses, list)
        assert len(responses) == 2
        
        session.end()
    
    @pytest.mark.asyncio
    async def test_process_message_inactive_session(self):
        """测试在未激活会话上处理消息"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        with pytest.raises(Exception):
            await session.process_message("Hello")
    
    @pytest.mark.asyncio
    async def test_stream_process_message(self):
        """测试流式消息处理"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        session.start()
        
        # Mock流式响应
        async def mock_stream():
            from agent import LLMStreamChunk
            yield LLMStreamChunk(content="Hello", is_final=False)
            yield LLMStreamChunk(content=" World", is_final=True)
        
        agent.stream_process_message = AsyncMock(return_value=mock_stream())
        
        chunks = []
        async for chunk in session.stream_process_message("Hello"):
            chunks.append(chunk)
        
        assert len(chunks) == 2
        session.end()
    
    def test_conversation_history(self):
        """测试会话历史"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        # 添加测试消息
        session._add_message_to_history("user", "Hello")
        session._add_message_to_history("assistant", "Hi there")
        
        history = session.get_conversation_history()
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[1]["role"] == "assistant"
    
    def test_clear_history(self):
        """测试清空历史"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        session._add_message_to_history("user", "Hello")
        assert len(session.get_conversation_history()) == 1
        
        session.clear_history()
        assert len(session.get_conversation_history()) == 0
    
    def test_context_variables(self):
        """测试上下文变量管理"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        # 添加变量
        session.add_context_variable("test_var", "test_value")
        variables = session.get_context_variables()
        assert "test_var" in variables
        
        # 移除变量
        session.remove_context_variable("test_var")
        variables = session.get_context_variables()
        assert "test_var" not in variables
    
    def test_get_status(self):
        """测试获取会话状态"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        status = session.get_status()
        assert isinstance(status, dict)
        assert "session_id" in status
        assert "session_type" in status
        assert "is_active" in status
        assert status["session_type"] == "single_agent"
    
    def test_context_manager_sync(self):
        """测试同步上下文管理器"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        with session:
            assert session.is_active == True
        
        assert session.is_active == False
    
    @pytest.mark.asyncio
    async def test_context_manager_async(self):
        """测试异步上下文管理器"""
        agent = create_simple_agent("Test Agent")
        session = Session(agent)
        
        async with session:
            assert session.is_active == True
        
        assert session.is_active == False


class TestSessionManager:
    """测试SessionManager类"""
    
    def setup_method(self):
        """设置测试环境"""
        # 设置Mock LLM客户端
        llm_manager = get_llm_client_manager()
        mock_client = MockLLMClient(default_response="Test response")
        llm_manager.register_client("test", mock_client, is_default=True)
    
    def test_init(self):
        """测试初始化"""
        manager = SessionManager()
        assert isinstance(manager.sessions, dict)
        assert len(manager.sessions) == 0
    
    def test_create_session(self):
        """测试创建会话"""
        manager = SessionManager()
        agent = create_simple_agent("Test Agent")
        
        session = manager.create_session(agent)
        assert isinstance(session, Session)
        assert session.config.session_id in manager.sessions
    
    def test_get_session(self):
        """测试获取会话"""
        manager = SessionManager()
        agent = create_simple_agent("Test Agent")
        
        session = manager.create_session(agent)
        session_id = session.config.session_id
        
        retrieved_session = manager.get_session(session_id)
        assert retrieved_session == session
    
    def test_get_nonexistent_session(self):
        """测试获取不存在的会话"""
        manager = SessionManager()
        
        session = manager.get_session("nonexistent_id")
        assert session is None
    
    def test_remove_session(self):
        """测试移除会话"""
        manager = SessionManager()
        agent = create_simple_agent("Test Agent")
        
        session = manager.create_session(agent)
        session_id = session.config.session_id
        
        manager.remove_session(session_id)
        assert session_id not in manager.sessions
    
    def test_list_sessions(self):
        """测试列出会话"""
        manager = SessionManager()
        agent1 = create_simple_agent("Agent1")
        agent2 = create_simple_agent("Agent2")
        
        session1 = manager.create_session(agent1)
        session2 = manager.create_session(agent2)
        
        session_ids = manager.list_sessions()
        assert len(session_ids) == 2
        assert session1.config.session_id in session_ids
        assert session2.config.session_id in session_ids
    
    def test_get_active_sessions(self):
        """测试获取活跃会话"""
        manager = SessionManager()
        agent1 = create_simple_agent("Agent1")
        agent2 = create_simple_agent("Agent2")
        
        session1 = manager.create_session(agent1)
        session2 = manager.create_session(agent2)
        
        # 启动一个会话
        session1.start()
        
        active_sessions = manager.get_active_sessions()
        assert len(active_sessions) == 1
        assert active_sessions[0] == session1
    
    def test_end_all_sessions(self):
        """测试结束所有会话"""
        manager = SessionManager()
        agent1 = create_simple_agent("Agent1")
        agent2 = create_simple_agent("Agent2")
        
        session1 = manager.create_session(agent1)
        session2 = manager.create_session(agent2)
        
        session1.start()
        session2.start()
        
        manager.end_all_sessions()
        
        active_sessions = manager.get_active_sessions()
        assert len(active_sessions) == 0
    
    def test_get_manager_statistics(self):
        """测试获取管理器统计信息"""
        manager = SessionManager()
        agent = create_simple_agent("Test Agent")
        group = create_group_chat("Test Group")
        
        session1 = manager.create_session(agent)
        session2 = manager.create_session(group)
        
        stats = manager.get_manager_statistics()
        assert isinstance(stats, dict)
        assert stats["total_sessions"] == 2
        assert stats["session_types"]["single_agent"] == 1
        assert stats["session_types"]["group_chat"] == 1


class TestConvenienceFunctions:
    """测试便捷函数"""
    
    def setup_method(self):
        """设置测试环境"""
        # 设置Mock LLM客户端
        llm_manager = get_llm_client_manager()
        mock_client = MockLLMClient(default_response="Test response")
        llm_manager.register_client("test", mock_client, is_default=True)
    
    def test_create_session_function(self):
        """测试create_session函数"""
        agent = create_simple_agent("Test Agent")
        
        session = create_session(agent, name="Test Session")
        assert isinstance(session, Session)
        assert session.config.name == "Test Session"
    
    def test_get_session_manager_function(self):
        """测试get_session_manager函数"""
        manager1 = get_session_manager()
        manager2 = get_session_manager()
        
        # 应该返回同一个实例
        assert manager1 is manager2


class TestIntegration:
    """集成测试"""
    
    def setup_method(self):
        """设置测试环境"""
        # 设置Mock LLM客户端
        llm_manager = get_llm_client_manager()
        mock_client = MockLLMClient(default_response="Test response")
        llm_manager.register_client("test", mock_client, is_default=True)
    
    @pytest.mark.asyncio
    async def test_full_single_agent_workflow(self):
        """测试完整的单Agent工作流程"""
        # 创建Agent
        agent = create_simple_agent("Test Agent")
        
        # 创建会话
        session = create_session(agent, name="Integration Test")
        
        # 添加上下文变量
        session.add_context_variable("test_var", "test_value")
        
        # 启动会话
        session.start()
        
        # 处理消息
        response = await session.process_message("Hello")
        assert response.content == "Test response"
        
        # 检查历史
        history = session.get_conversation_history()
        assert len(history) >= 2  # 用户消息和助手响应
        
        # 检查状态
        status = session.get_status()
        assert status["is_active"] == True
        assert status["session_type"] == "single_agent"
        
        # 结束会话
        session.end()
        assert session.is_active == False
    
    @pytest.mark.asyncio
    async def test_full_group_chat_workflow(self):
        """测试完整的群聊工作流程"""
        # 创建Agent
        agent1 = create_simple_agent("Agent1")
        agent2 = create_simple_agent("Agent2")
        
        # 创建群聊
        group = create_group_chat("Test Group")
        group.add_agent(agent1)
        group.add_agent(agent2)
        
        # 创建会话
        session = create_session(group, name="Group Chat Test")
        
        # 启动会话
        session.start()
        
        # Mock群聊响应
        group.process_message = AsyncMock(return_value=[
            {"agent_name": "Agent1", "content": "Response 1", "agent_id": "agent1"}
        ])
        
        # 处理消息
        responses = await session.process_message("Hello")
        assert isinstance(responses, list)
        assert len(responses) == 1
        
        # 检查状态
        status = session.get_status()
        assert status["session_type"] == "group_chat"
        
        # 结束会话
        session.end()
        assert session.is_active == False
    
    def test_session_manager_integration(self):
        """测试会话管理器集成"""
        # 获取管理器
        manager = get_session_manager()
        
        # 创建不同类型的会话
        agent = create_simple_agent("Test Agent")
        group = create_group_chat("Test Group")
        
        session1 = manager.create_session(agent)
        session2 = manager.create_session(group)
        
        # 启动会话
        session1.start()
        session2.start()
        
        # 检查统计信息
        stats = manager.get_manager_statistics()
        assert stats["total_sessions"] == 2
        assert stats["active_sessions"] == 2
        
        # 结束所有会话
        manager.end_all_sessions()
        
        final_stats = manager.get_manager_statistics()
        assert final_stats["active_sessions"] == 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 