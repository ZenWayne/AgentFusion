"""
Pytest tests for AgentModel class.

This module tests all functionality of the AgentModel class using SQLite for testing.
"""

import pytest
import pytest_asyncio
import tempfile
import os
import uuid
from datetime import datetime
from typing import Dict, Any, Optional, List
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# Import the classes we need to test
from data_layer.base_data_layer import DBDataLayer
from data_layer.models.agent_model import AgentModel
from data_layer.models.tables import (
    Base, BaseComponentTable, AgentTable, ModelClientTable, PromptTable, 
    PromptVersionTable, McpServerTable, AgentMcpServerTable, UserTable,
    ElementTable, FeedbackTable, GroupChatTable, StepsTable, ThreadTable,
    UserActivityLogsTable
)
from data_layer.models.prompt_model import PromptModel
from data_layer.models.mcp_model import McpModel
from schemas.component import ComponentInfo
from schemas.agent import AgentType, AssistantAgentConfig, UserProxyAgentConfig, HandoffTools


class SQLiteDBDataLayer(DBDataLayer):
    """SQLite implementation of DBDataLayer for testing"""
    
    def __init__(self, database_url: str = None, show_logger: bool = False):
        if database_url is None:
            # Create a temporary SQLite database for testing
            self.temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
            database_url = f"sqlite+aiosqlite:///{self.temp_db.name}"
        
        # Initialize without pool since SQLite doesn't use asyncpg
        self.database_url = database_url
        self.pool = None
        self.show_logger = show_logger
        
    async def connect(self):
        """Create SQLAlchemy engine for SQLite"""
        if not hasattr(self, '_engine'):
            self._engine = create_async_engine(
                self.database_url,
                echo=self.show_logger
            )
            self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)
            
            # Replace JSONB, ARRAY and UUID columns for SQLite compatibility
            for table in Base.metadata.tables.values():
                for column in table.columns:
                    column_type_str = str(column.type)
                    if hasattr(column.type, '__visit_name__') and column.type.__visit_name__.startswith('JSON'):
                        column.type = JSON()
                    elif (hasattr(column.type, '__visit_name__') and column.type.__visit_name__.startswith('ARRAY')) or 'ARRAY' in column_type_str:
                        column.type = Text()  # Store arrays as text in SQLite
                    elif 'UUID' in column_type_str:
                        column.type = Text()  # Store UUID as text in SQLite
            
            # Create all tables
            async with self._engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
    
    async def disconnect(self):
        """Close SQLAlchemy engine"""
        if hasattr(self, '_engine'):
            await self._engine.dispose()
            
    async def get_session(self):
        """Get SQLAlchemy async session"""
        if not hasattr(self, '_engine'):
            await self.connect()
        return self._session_factory()
    
    async def cleanup(self):
        """Clean up database connections and temp files"""
        await self.disconnect()
        if hasattr(self, 'temp_db'):
            try:
                os.unlink(self.temp_db.name)
            except:
                pass

    # Mock the asyncpg-specific methods since we're using SQLAlchemy for testing
    async def execute_query(self, query: str, params=None):
        async with await self.get_session() as session:
            result = await session.execute(text(query), params or {})
            return [dict(row._mapping) for row in result.fetchall()]
    
    async def execute_single_query(self, query: str, params=None):
        results = await self.execute_query(query, params)
        return results[0] if results else None
    
    async def execute_command(self, query: str, params=None):
        async with await self.get_session() as session:
            result = await session.execute(text(query), params or {})
            await session.commit()
            return str(result.rowcount)


@pytest_asyncio.fixture
async def sqlite_db():
    """Create a SQLite database for testing"""
    db = SQLiteDBDataLayer()
    await db.connect()
    yield db
    await db.cleanup()


@pytest_asyncio.fixture
async def agent_model(sqlite_db):
    """Create AgentModel instance with test database"""
    return AgentModel(sqlite_db)


@pytest_asyncio.fixture
async def sample_model_client(sqlite_db):
    """Create a sample model client for testing"""
    async with await sqlite_db.get_session() as session:
        model_client = ModelClientTable(
            id=1,
            label="deepseek-chat_DeepSeek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            provider="deepseek",
            model_info={"family": "deepseek"},
            client_uuid=str(uuid.uuid4())
        )
        session.add(model_client)
        await session.commit()
        await session.refresh(model_client)
        return model_client


@pytest_asyncio.fixture
async def sample_agent(sqlite_db, sample_model_client):
    """Create a sample agent for testing"""
    async with await sqlite_db.get_session() as session:
        agent = AgentTable(
            id=1,
            name="test-agent",
            description="A test assistant agent",
            model_client_id=sample_model_client.id,
            agent_uuid=str(uuid.uuid4()),
            provider="test-provider",
            agent_type="assistant_agent",
            labels='["test", "assistant"]',
            handoff_tools='[]'  # Empty handoff tools by default
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return agent


@pytest_asyncio.fixture 
async def sample_prompt(sqlite_db, sample_agent):
    """Create a sample prompt for testing"""
    async with await sqlite_db.get_session() as session:
        # Create prompt
        prompt = PromptTable(
            id=1,
            prompt_id="test-agent_system",
            name="test-agent System Message", 
            category="agent",
            subcategory="system_message",
            agent_id=sample_agent.id,
            prompt_uuid=str(uuid.uuid4())
        )
        session.add(prompt)
        await session.flush()
        
        # Create prompt version
        prompt_version = PromptVersionTable(
            prompt_id=prompt.id,
            version_number=1,
            content="You are a helpful test assistant.",
            is_current=True
        )
        session.add(prompt_version)
        await session.commit()
        return prompt


@pytest_asyncio.fixture
async def sample_mcp_server(sqlite_db):
    """Create a sample MCP server for testing"""
    async with await sqlite_db.get_session() as session:
        mcp_server = McpServerTable(
            id=1,
            name="test-mcp-server",
            description="Test MCP server",
            server_uuid=str(uuid.uuid4()),
            command="test-command",
            args=[]
        )
        session.add(mcp_server)
        await session.commit()
        await session.refresh(mcp_server)
        return mcp_server


@pytest_asyncio.fixture
async def sample_agent_with_handoff_tools(sqlite_db, sample_model_client):
    """Create a sample agent with handoff_tools for testing"""
    import json
    handoff_tools_data = [
        {"target": "user", "message": "Transfer to user"},
        {"target": "admin", "message": "Escalate to admin"}
    ]
    
    async with await sqlite_db.get_session() as session:
        agent = AgentTable(
            id=2,
            name="handoff-agent",
            description="Agent with handoff tools",
            model_client_id=sample_model_client.id,
            agent_uuid=str(uuid.uuid4()),
            provider="test-provider",
            agent_type="assistant_agent",
            labels='["handoff", "test"]',
            handoff_tools=json.dumps(handoff_tools_data)
        )
        session.add(agent)
        await session.commit()
        await session.refresh(agent)
        return agent


class TestAgentModel:
    """Test cases for AgentModel class"""
    
    @pytest.mark.asyncio
    async def test_get_all_components_empty(self, agent_model: AgentModel):
        """Test get_all_components with empty database"""
        result: List[ComponentInfo] = await agent_model.get_all_components()
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio  
    async def test_get_all_components_with_data(self, agent_model, sample_agent, sample_prompt):
        """Test get_all_components with sample data"""
        result: List[ComponentInfo] = await agent_model.get_all_components()
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        agent_info: AssistantAgentConfig = result[0]
        assert isinstance(agent_info, AssistantAgentConfig)
        assert agent_info.name == "test-agent"
        assert agent_info.description == "A test assistant agent"
        assert agent_info.type == AgentType.ASSISTANT_AGENT

    @pytest.mark.asyncio
    async def test_get_all_components_filter_inactive(self, agent_model, sqlite_db, sample_model_client):
        """Test get_all_components filters inactive agents"""
        # Create an inactive agent
        async with await sqlite_db.get_session() as session:
            inactive_agent = AgentTable(
                name="inactive-agent",
                description="Inactive agent",
                model_client_id=sample_model_client.id,
                is_active=False,
                agent_uuid=str(uuid.uuid4()),
                provider="test-provider",
                agent_type="assistant_agent"
            )
            session.add(inactive_agent)
            await session.commit()
        
        # Should not include inactive agent
        result: List[ComponentInfo] = await agent_model.get_all_components(filter_active=True)
        inactive_names = [component.name for component in result]
        assert "inactive-agent" not in inactive_names
        
        # Should include inactive agent when filter is disabled
        result = await agent_model.get_all_components(filter_active=False)
        all_names = [component.name for component in result]
        assert "inactive-agent" in all_names

    @pytest.mark.asyncio
    async def test_to_component_info_assistant_agent(self, agent_model, sample_agent, sample_prompt):
        """Test to_component_info for assistant agent"""
        component_info: AssistantAgentConfig = await agent_model.to_component_info(sample_agent)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.name == "test-agent"
        assert component_info.description == "A test assistant agent"
        assert component_info.type == AgentType.ASSISTANT_AGENT
        assert component_info.model_client == "deepseek-chat_DeepSeek"
        assert component_info.labels == ["test", "assistant"]

    @pytest.mark.asyncio
    async def test_to_component_info_user_proxy_agent(self, agent_model, sqlite_db, sample_model_client):
        """Test to_component_info for user proxy agent"""
        # Create user proxy agent
        async with await sqlite_db.get_session() as session:
            user_agent = AgentTable(
                name="user-agent",
                description="User proxy agent",
                agent_uuid=str(uuid.uuid4()),
                provider="test-provider",
                agent_type="user_proxy_agent",
                input_func="input",
                labels='["user", "proxy"]'
            )
            session.add(user_agent)
            await session.commit()
            await session.refresh(user_agent)
        
        component_info: UserProxyAgentConfig = await agent_model.to_component_info(user_agent)
        
        assert isinstance(component_info, UserProxyAgentConfig)
        assert component_info.name == "user-agent"
        assert component_info.type == AgentType.USER_PROXY_AGENT
        assert component_info.input_func == "input"

    @pytest.mark.asyncio
    async def test_update_component_by_id(self, agent_model, sample_agent):
        """Test update_component_by_id"""
        # Create updated component info
        updated_info: AssistantAgentConfig = AssistantAgentConfig(
            type=AgentType.ASSISTANT_AGENT,
            name="updated-agent",
            description="Updated description",
            labels=["updated", "test"],
            model_client="deepseek-chat_DeepSeek",
            prompt=lambda: "Updated prompt content"
        )
        
        result: AssistantAgentConfig = await agent_model.update_component_by_id(sample_agent.id, updated_info)
        
        assert isinstance(result, AssistantAgentConfig)
        assert result.name == "updated-agent"
        assert result.description == "Updated description"
        assert result.labels == ["updated", "test"]

    @pytest.mark.asyncio
    async def test_update_component_by_id_not_found(self, agent_model):
        """Test update_component_by_id with non-existent ID"""
        updated_info: AssistantAgentConfig = AssistantAgentConfig(
            type=AgentType.ASSISTANT_AGENT,
            name="test",
            description="test",
            labels=[],
            model_client="deepseek-chat_DeepSeek",
            prompt=lambda: "Test prompt"
        )
        
        with pytest.raises(ValueError, match="Agent with ID '999' not found"):
            await agent_model.update_component_by_id(999, updated_info)

    @pytest.mark.asyncio
    async def test_update_agent_prompt(self, agent_model, sample_agent):
        """Test update_agent_prompt delegates to prompt_model"""
        # Mock the prompt_model method
        agent_model.prompt_model.update_agent_prompt = AsyncMock(return_value=True)
        
        result: bool = await agent_model.update_agent_prompt(
            "test-agent", 
            "New prompt content",
            "v2.0",
            1
        )
        
        assert result is True
        agent_model.prompt_model.update_agent_prompt.assert_called_once_with(
            "test-agent", "New prompt content", "v2.0", 1
        )

    @pytest.mark.asyncio
    async def test_get_agent_prompt_history(self, agent_model, sample_agent):
        """Test get_agent_prompt_history delegates to prompt_model"""
        expected_history: List[Dict[str, Any]] = [
            {"version_number": 1, "content": "Test prompt", "is_current": True}
        ]
        agent_model.prompt_model.get_agent_prompt_history = AsyncMock(return_value=expected_history)
        
        result: List[Dict[str, Any]] = await agent_model.get_agent_prompt_history("test-agent")
        
        assert result == expected_history
        agent_model.prompt_model.get_agent_prompt_history.assert_called_once_with("test-agent")

    @pytest.mark.asyncio
    async def test_add_mcp_server_to_agent(self, agent_model, sample_agent, sample_mcp_server):
        """Test add_mcp_server_to_agent"""
        # Mock mcp_model method
        agent_model.mcp_model.get_mcp_server_by_name = AsyncMock(return_value={"name": "test-mcp-server"})
        
        result: bool = await agent_model.add_mcp_server_to_agent("test-agent", "test-mcp-server", 1)
        
        assert result is True
        
        # Verify the relationship was created in agent_mcp_servers table
        async with await agent_model.db.get_session() as session:
            from sqlalchemy import select, join
            # Check that relationship exists in agent_mcp_servers table
            stmt = select(AgentMcpServerTable, McpServerTable.name).select_from(
                AgentMcpServerTable.__table__.join(
                    McpServerTable.__table__, 
                    AgentMcpServerTable.mcp_server_id == McpServerTable.id
                )
            ).where(
                AgentMcpServerTable.agent_id == sample_agent.id
            )
            result = await session.execute(stmt)
            relationships = result.all()
            
            assert len(relationships) == 1
            relationship, server_name = relationships[0]
            assert server_name == "test-mcp-server"
            assert relationship.is_active is True

    @pytest.mark.asyncio
    async def test_add_mcp_server_to_agent_nonexistent_agent(self, agent_model):
        """Test add_mcp_server_to_agent with non-existent agent"""
        agent_model.mcp_model.get_mcp_server_by_name = AsyncMock(return_value={"name": "test-server"})
        
        result: bool = await agent_model.add_mcp_server_to_agent("nonexistent-agent", "test-server", 1)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_add_mcp_server_to_agent_nonexistent_server(self, agent_model, sample_agent):
        """Test add_mcp_server_to_agent with non-existent MCP server"""
        agent_model.mcp_model.get_mcp_server_by_name = AsyncMock(return_value=None)
        
        result: bool = await agent_model.add_mcp_server_to_agent("test-agent", "nonexistent-server", 1)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_remove_mcp_server_from_agent(self, agent_model, sample_agent, sample_mcp_server):
        """Test remove_mcp_server_from_agent"""
        # First add a server
        agent_model.mcp_model.get_mcp_server_by_name = AsyncMock(return_value={"name": "test-mcp-server"})
        await agent_model.add_mcp_server_to_agent("test-agent", "test-mcp-server", 1)
        
        # Now remove it
        result: bool = await agent_model.remove_mcp_server_from_agent("test-agent", "test-mcp-server", 1)
        
        assert result is True
        
        # Verify the relationship was deactivated in agent_mcp_servers table
        async with await agent_model.db.get_session() as session:
            from sqlalchemy import select
            # Check that relationship is deactivated in agent_mcp_servers table
            stmt = select(AgentMcpServerTable, McpServerTable.name).select_from(
                AgentMcpServerTable.__table__.join(
                    McpServerTable.__table__, 
                    AgentMcpServerTable.mcp_server_id == McpServerTable.id
                )
            ).where(
                AgentMcpServerTable.agent_id == sample_agent.id
            )
            result = await session.execute(stmt)
            relationships = result.all()
            
            # Should still exist but be inactive (soft delete)
            assert len(relationships) == 1
            relationship, server_name = relationships[0]
            assert server_name == "test-mcp-server"
            assert relationship.is_active is False

    @pytest.mark.asyncio
    async def test_remove_mcp_server_from_agent_nonexistent_agent(self, agent_model):
        """Test remove_mcp_server_from_agent with non-existent agent"""
        result: bool = await agent_model.remove_mcp_server_from_agent("nonexistent-agent", "test-server", 1)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_get_agent_mcp_servers(self, agent_model, sample_agent, sample_mcp_server):
        """Test get_agent_mcp_servers"""
        # Add MCP servers to agent
        agent_model.mcp_model.get_mcp_server_by_name = AsyncMock(return_value={"name": "test-mcp-server"})
        await agent_model.add_mcp_server_to_agent("test-agent", "test-mcp-server", 1)
        
        result: List[str] = await agent_model.get_agent_mcp_servers("test-agent")
        
        assert isinstance(result, list)
        assert "test-mcp-server" in result

    @pytest.mark.asyncio
    async def test_get_agent_mcp_servers_nonexistent_agent(self, agent_model):
        """Test get_agent_mcp_servers with non-existent agent"""
        result: List[str] = await agent_model.get_agent_mcp_servers("nonexistent-agent")
        
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_to_component_info_with_mcp_tools(self, agent_model, sample_agent, sample_mcp_server, sample_prompt):
        """Test to_component_info includes MCP tools when configured via relationship table"""
        # Create relationship record in agent_mcp_servers table
        async with await agent_model.db.get_session() as session:
            relationship = AgentMcpServerTable(
                agent_id=sample_agent.id,
                mcp_server_id=sample_mcp_server.id,
                is_active=True,
                created_by=1
            )
            session.add(relationship)
            await session.commit()
        
        # Mock mcp_model method for getting server params
        agent_model.mcp_model.get_mcp_server_params_by_name = AsyncMock(return_value={"type": "StdioServerParams", "command": "test-command"})
        
        component_info: AssistantAgentConfig = await agent_model.to_component_info(sample_agent)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.mcp_tools is not None
        assert len(component_info.mcp_tools) == 1
        mcp_tool = component_info.mcp_tools[0]
        assert mcp_tool.type == "StdioServerParams"
        assert mcp_tool.command == "test-command"


class TestAgentModelHandoffTools:
    """Test cases for handoff_tools functionality in AgentModel"""
    
    @pytest.mark.asyncio
    async def test_to_component_info_with_handoff_tools(self, agent_model, sample_agent_with_handoff_tools):
        """Test to_component_info correctly deserializes handoff_tools from JSON"""
        component_info: AssistantAgentConfig = await agent_model.to_component_info(sample_agent_with_handoff_tools)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.handoff_tools is not None
        assert len(component_info.handoff_tools) == 2
        
        # Check first handoff tool
        handoff_tool_1 = component_info.handoff_tools[0]
        assert isinstance(handoff_tool_1, HandoffTools)
        assert handoff_tool_1.target == "user"
        assert handoff_tool_1.message == "Transfer to user"
        
        # Check second handoff tool
        handoff_tool_2 = component_info.handoff_tools[1]
        assert isinstance(handoff_tool_2, HandoffTools)
        assert handoff_tool_2.target == "admin"
        assert handoff_tool_2.message == "Escalate to admin"

    @pytest.mark.asyncio
    async def test_to_component_info_with_empty_handoff_tools(self, agent_model, sample_agent):
        """Test to_component_info handles empty handoff_tools correctly"""
        component_info: AssistantAgentConfig = await agent_model.to_component_info(sample_agent)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.handoff_tools is None

    @pytest.mark.asyncio
    async def test_to_component_info_with_null_handoff_tools(self, agent_model, sqlite_db, sample_model_client):
        """Test to_component_info handles NULL handoff_tools correctly"""
        # Create agent with NULL handoff_tools
        async with await sqlite_db.get_session() as session:
            agent = AgentTable(
                name="null-handoff-agent",
                description="Agent with NULL handoff tools",
                model_client_id=sample_model_client.id,
                agent_uuid=str(uuid.uuid4()),
                provider="test-provider",
                agent_type="assistant_agent",
                labels='["test"]',
                handoff_tools=None
            )
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
        
        component_info: AssistantAgentConfig = await agent_model.to_component_info(agent)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.handoff_tools is None

    @pytest.mark.asyncio
    async def test_to_component_info_with_invalid_handoff_tools_json(self, agent_model, sqlite_db, sample_model_client):
        """Test to_component_info handles invalid JSON in handoff_tools gracefully"""
        # Create agent with invalid JSON in handoff_tools
        async with await sqlite_db.get_session() as session:
            agent = AgentTable(
                name="invalid-json-agent",
                description="Agent with invalid JSON handoff tools",
                model_client_id=sample_model_client.id,
                agent_uuid=str(uuid.uuid4()),
                provider="test-provider",
                agent_type="assistant_agent",
                labels='["test"]',
                handoff_tools='{"invalid": json}'  # Invalid JSON
            )
            session.add(agent)
            await session.commit()
            await session.refresh(agent)
        
        component_info: AssistantAgentConfig = await agent_model.to_component_info(agent)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.handoff_tools is None

    @pytest.mark.asyncio
    async def test_update_component_by_id_with_handoff_tools(self, agent_model, sample_agent):
        """Test update_component_by_id correctly serializes handoff_tools to JSON"""
        # Create updated component info with handoff_tools
        handoff_tools = [
            HandoffTools(target="user", message="Complete task and return to user"),
            HandoffTools(target="supervisor", message="Request supervisor approval")
        ]
        
        updated_info: AssistantAgentConfig = AssistantAgentConfig(
            type=AgentType.ASSISTANT_AGENT,
            name="updated-handoff-agent",
            description="Updated with handoff tools",
            labels=["updated", "handoff"],
            model_client="deepseek-chat_DeepSeek",
            prompt=lambda: "Updated prompt content",
            handoff_tools=handoff_tools
        )
        
        result: AssistantAgentConfig = await agent_model.update_component_by_id(sample_agent.id, updated_info)
        
        assert isinstance(result, AssistantAgentConfig)
        assert result.name == "updated-handoff-agent"
        assert result.handoff_tools is not None
        assert len(result.handoff_tools) == 2
        
        # Verify data was persisted correctly in database
        async with await agent_model.db.get_session() as session:
            from sqlalchemy import select
            stmt = select(AgentTable).where(AgentTable.id == sample_agent.id)
            result = await session.execute(stmt)
            updated_agent = result.scalar_one()
            
            # In SQLite, the handoff_tools might be stored as a list or JSON string
            stored_handoff_tools = updated_agent.handoff_tools
            if isinstance(stored_handoff_tools, str):
                import json
                stored_handoff_tools = json.loads(stored_handoff_tools)
            
            assert len(stored_handoff_tools) == 2
            assert stored_handoff_tools[0]["target"] == "user"
            assert stored_handoff_tools[0]["message"] == "Complete task and return to user"
            assert stored_handoff_tools[1]["target"] == "supervisor"
            assert stored_handoff_tools[1]["message"] == "Request supervisor approval"

    @pytest.mark.asyncio
    async def test_update_component_by_id_with_empty_handoff_tools(self, agent_model, sample_agent_with_handoff_tools):
        """Test update_component_by_id handles empty handoff_tools correctly"""
        # Update with empty handoff_tools
        updated_info: AssistantAgentConfig = AssistantAgentConfig(
            type=AgentType.ASSISTANT_AGENT,
            name="cleared-handoff-agent",
            description="Cleared handoff tools",
            labels=["cleared"],
            model_client="deepseek-chat_DeepSeek",
            prompt=lambda: "Prompt content",
            handoff_tools=[]
        )
        
        result: AssistantAgentConfig = await agent_model.update_component_by_id(sample_agent_with_handoff_tools.id, updated_info)
        
        assert isinstance(result, AssistantAgentConfig)
        assert result.handoff_tools is None

    @pytest.mark.asyncio
    async def test_update_component_by_id_with_none_handoff_tools(self, agent_model, sample_agent_with_handoff_tools):
        """Test update_component_by_id handles None handoff_tools correctly"""
        # Update with None handoff_tools
        updated_info: AssistantAgentConfig = AssistantAgentConfig(
            type=AgentType.ASSISTANT_AGENT,
            name="none-handoff-agent",
            description="None handoff tools",
            labels=["none"],
            model_client="deepseek-chat_DeepSeek",
            prompt=lambda: "Prompt content",
            handoff_tools=None
        )
        
        result: AssistantAgentConfig = await agent_model.update_component_by_id(sample_agent_with_handoff_tools.id, updated_info)
        
        assert isinstance(result, AssistantAgentConfig)
        # The original handoff_tools should remain unchanged when None is passed
        assert result.handoff_tools is not None
        assert len(result.handoff_tools) == 2

    @pytest.mark.asyncio
    async def test_handoff_tools_serialization_with_dict_input(self, agent_model, sample_agent):
        """Test handoff_tools serialization handles dict input correctly"""
        # Create handoff_tools as dicts instead of HandoffTools objects
        handoff_tools_dicts = [
            {"target": "user", "message": "Task completed"},
            {"target": "manager", "message": "Needs approval"}
        ]
        
        # Manually create AssistantAgentConfig with dict handoff_tools
        updated_info: AssistantAgentConfig = AssistantAgentConfig(
            type=AgentType.ASSISTANT_AGENT,
            name="dict-handoff-agent",
            description="Dict handoff tools",
            labels=["dict"],
            model_client="deepseek-chat_DeepSeek",
            prompt=lambda: "Prompt content"
        )
        # Manually set handoff_tools to bypass Pydantic validation
        updated_info.handoff_tools = handoff_tools_dicts
        
        result: AssistantAgentConfig = await agent_model.update_component_by_id(sample_agent.id, updated_info)
        
        assert isinstance(result, AssistantAgentConfig)
        assert result.handoff_tools is not None
        assert len(result.handoff_tools) == 2

    @pytest.mark.asyncio
    async def test_handoff_tools_backward_compatibility(self, agent_model, sqlite_db, sample_model_client):
        """Test that existing agents without handoff_tools work correctly"""
        # Create agent without handoff_tools field (simulating legacy data)
        async with await sqlite_db.get_session() as session:
            # Insert using raw SQL to bypass ORM default values
            from sqlalchemy import text
            insert_stmt = text("""
                INSERT INTO agents (name, description, model_client_id, agent_uuid, provider, agent_type, labels)
                VALUES (:name, :description, :model_client_id, :agent_uuid, :provider, :agent_type, :labels)
            """)
            await session.execute(insert_stmt, {
                "name": "legacy-agent",
                "description": "Legacy agent without handoff_tools",
                "model_client_id": sample_model_client.id,
                "agent_uuid": str(uuid.uuid4()),
                "provider": "legacy-provider",
                "agent_type": "assistant_agent",
                "labels": '["legacy"]'
            })
            await session.commit()
            
            # Fetch the created agent
            from sqlalchemy import select
            stmt = select(AgentTable).where(AgentTable.name == "legacy-agent")
            result = await session.execute(stmt)
            legacy_agent = result.scalar_one()
        
        component_info: AssistantAgentConfig = await agent_model.to_component_info(legacy_agent)
        
        assert isinstance(component_info, AssistantAgentConfig)
        assert component_info.name == "legacy-agent"
        assert component_info.handoff_tools is None

    @pytest.mark.asyncio
    async def test_get_all_components_includes_handoff_tools(self, agent_model, sample_agent_with_handoff_tools, sample_prompt):
        """Test get_all_components includes handoff_tools in results"""
        # Create a prompt for the handoff agent
        async with await agent_model.db.get_session() as session:
            prompt = PromptTable(
                prompt_id="handoff-agent_system",
                name="handoff-agent System Message",
                category="agent",
                subcategory="system_message",
                agent_id=sample_agent_with_handoff_tools.id,
                prompt_uuid=str(uuid.uuid4())
            )
            session.add(prompt)
            await session.flush()
            
            prompt_version = PromptVersionTable(
                prompt_id=prompt.id,
                version_number=1,
                content="You are a handoff test assistant.",
                is_current=True
            )
            session.add(prompt_version)
            await session.commit()
        
        components = await agent_model.get_all_components()
        
        # Find the handoff agent in the list
        handoff_agent_info = None
        for component in components:
            if component.name == "handoff-agent":
                handoff_agent_info = component
                break
        
        assert handoff_agent_info is not None
        assert isinstance(handoff_agent_info, AssistantAgentConfig)
        assert handoff_agent_info.handoff_tools is not None
        assert len(handoff_agent_info.handoff_tools) == 2


if __name__ == "__main__":
    pytest.main([__file__])