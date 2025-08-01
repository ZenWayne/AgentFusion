"""
Pytest tests for GroupChatModel class.

This module tests all functionality of the GroupChatModel class using SQLite for testing.
"""

import pytest
import pytest_asyncio
import tempfile
import os
import uuid
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# Import the classes we need to test
from data_layer.base_data_layer import DBDataLayer
from data_layer.models.group_chat_model import GroupChatModel
from data_layer.models.tables import (
    Base, BaseComponentTable, GroupChatTable, AgentTable, GroupChatParticipantsTable
)
from schemas.component import ComponentInfo
from schemas.group_chat import SelectorGroupChatConfig, RoundRobinGroupChatConfig, GroupChatType
from schemas.model_info import model_client


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
                        column.default = None  # Remove list defaults for SQLite
                    elif 'UUID' in column_type_str:
                        column.type = Text()  # Store UUID as text in SQLite
                        # Remove gen_random_uuid() default for SQLite
                        if hasattr(column, 'server_default') and column.server_default:
                            column.server_default = None
            
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
async def group_chat_model(sqlite_db):
    """Create GroupChatModel instance with test database"""
    return GroupChatModel(sqlite_db)


@pytest_asyncio.fixture
async def sample_agents(sqlite_db):
    """Create sample agents for testing"""
    async with await sqlite_db.get_session() as session:
        agents = [
            AgentTable(
                id=1,
                name="agent1",
                label="Agent 1",
                provider="test_provider",
                agent_uuid=str(uuid.uuid4())
            ),
            AgentTable(
                id=2,
                name="agent2",
                label="Agent 2", 
                provider="test_provider",
                agent_uuid=str(uuid.uuid4())
            ),
            AgentTable(
                id=3,
                name="agent3",
                label="Agent 3",
                provider="test_provider",
                agent_uuid=str(uuid.uuid4())
            )
        ]
        for agent in agents:
            session.add(agent)
        await session.commit()
        return agents


@pytest_asyncio.fixture
async def sample_selector_group_chat(sqlite_db, sample_agents):
    """Create a sample selector group chat for testing"""
    async with await sqlite_db.get_session() as session:
        # Create group chat without participants field
        group_chat = GroupChatTable(
            id=1,
            name="test-selector-chat",
            type="selector_group_chat",
            description="A test selector group chat",
            labels="test,selector",  # Store as comma-separated string for SQLite
            selector_prompt="Select the best participant for this task",
            model_client=model_client.deepseek_chat_DeepSeek.value,
            group_chat_uuid=str(uuid.uuid4())
        )
        session.add(group_chat)
        await session.commit()
        await session.refresh(group_chat)
        
        # Add participants via relationship table
        participants = [
            GroupChatParticipantsTable(
                group_chat_id=group_chat.id,
                agent_id=1,
                join_order=0
            ),
            GroupChatParticipantsTable(
                group_chat_id=group_chat.id,
                agent_id=2,
                join_order=1
            ),
            GroupChatParticipantsTable(
                group_chat_id=group_chat.id,
                agent_id=3,
                join_order=2
            )
        ]
        for participant in participants:
            session.add(participant)
        await session.commit()
        
        return group_chat


@pytest_asyncio.fixture
async def sample_round_robin_group_chat(sqlite_db, sample_agents):
    """Create a sample round robin group chat for testing"""
    async with await sqlite_db.get_session() as session:
        group_chat = GroupChatTable(
            id=2,
            name="test-round-robin-chat",
            type="round_robin_group_chat",
            description="A test round robin group chat",
            labels="test,round_robin",  # Store as comma-separated string for SQLite
            handoff_target="user",
            termination_condition="handoff",
            group_chat_uuid=str(uuid.uuid4())
        )
        session.add(group_chat)
        await session.commit()
        await session.refresh(group_chat)
        
        # Add participants via relationship table
        participants = [
            GroupChatParticipantsTable(
                group_chat_id=group_chat.id,
                agent_id=1,
                join_order=0
            ),
            GroupChatParticipantsTable(
                group_chat_id=group_chat.id,
                agent_id=2,
                join_order=1
            )
        ]
        for participant in participants:
            session.add(participant)
        await session.commit()
        
        return group_chat


class TestGroupChatModel:
    """Test cases for GroupChatModel class"""
    
    @pytest.mark.asyncio
    async def test_get_all_components_empty(self, group_chat_model: GroupChatModel):
        """Test get_all_components with empty database"""
        result: List[ComponentInfo] = await group_chat_model.get_all_components()
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio  
    async def test_get_all_components_with_selector_data(self, group_chat_model, sample_selector_group_chat):
        """Test get_all_components with selector group chat data"""
        result: List[ComponentInfo] = await group_chat_model.get_all_components()
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        group_chat_info: SelectorGroupChatConfig = result[0]
        assert isinstance(group_chat_info, SelectorGroupChatConfig)
        assert group_chat_info.name == "test-selector-chat"
        assert group_chat_info.description == "A test selector group chat"
        assert group_chat_info.type == GroupChatType.SELECTOR_GROUP_CHAT
        assert group_chat_info.selector_prompt == "Select the best participant for this task"
        assert group_chat_info.participants == ["agent1", "agent2", "agent3"]
        assert group_chat_info.model_client == model_client.deepseek_chat_DeepSeek

    @pytest.mark.asyncio
    async def test_get_all_components_filter_inactive(self, group_chat_model, sqlite_db):
        """Test get_all_components filters inactive group chats"""
        # Create an inactive group chat
        async with await sqlite_db.get_session() as session:
            inactive_chat = GroupChatTable(
                name="inactive-chat",
                type="selector_group_chat",
                description="Inactive group chat",
                is_active=False,
                group_chat_uuid=str(uuid.uuid4()),
                selector_prompt="Test prompt",
                model_client=model_client.deepseek_chat_DeepSeek.value,
                labels="inactive"  # Use string instead of empty list
            )
            session.add(inactive_chat)
            await session.commit()
        
        # Should not include inactive group chat
        result: List[ComponentInfo] = await group_chat_model.get_all_components(filter_active=True)
        inactive_names = [comp.name for comp in result]
        assert "inactive-chat" not in inactive_names
        
        # Should include inactive group chat when filter is disabled
        result = await group_chat_model.get_all_components(filter_active=False)
        all_names = [comp.name for comp in result]
        assert "inactive-chat" in all_names

    @pytest.mark.asyncio
    async def test_to_component_info_selector_group_chat(self, group_chat_model, sample_selector_group_chat):
        """Test to_component_info for selector group chat"""
        component_info: SelectorGroupChatConfig = await group_chat_model.to_component_info(sample_selector_group_chat)
        
        assert isinstance(component_info, SelectorGroupChatConfig)
        assert component_info.name == "test-selector-chat"
        assert component_info.description == "A test selector group chat"
        assert component_info.type == GroupChatType.SELECTOR_GROUP_CHAT
        assert component_info.selector_prompt == "Select the best participant for this task"
        assert component_info.participants == ["agent1", "agent2", "agent3"]
        assert component_info.model_client == model_client.deepseek_chat_DeepSeek
        assert component_info.labels == ["test", "selector"]

    @pytest.mark.asyncio
    async def test_to_component_info_unknown_type(self, group_chat_model, sqlite_db):
        """Test to_component_info for unknown group chat type falls back to basic ComponentInfo"""
        # Create group chat with unknown type
        async with await sqlite_db.get_session() as session:
            unknown_chat = GroupChatTable(
                name="unknown-chat",
                type="unknown_type",
                description="Unknown type group chat",
                group_chat_uuid=str(uuid.uuid4()),
                labels="unknown",
                model_client=model_client.deepseek_chat_DeepSeek.value
            )
            session.add(unknown_chat)
            await session.commit()
            await session.refresh(unknown_chat)
        
        component_info: SelectorGroupChatConfig = await group_chat_model.to_component_info(unknown_chat)
        
        assert isinstance(component_info, SelectorGroupChatConfig)
        assert component_info.name == "unknown-chat"
        assert component_info.type == GroupChatType.SELECTOR_GROUP_CHAT  # Falls back to selector type
        assert component_info.description == "Unknown type group chat"
        assert component_info.labels == ["unknown"]
        assert component_info.model_client == model_client.deepseek_chat_DeepSeek.value

    @pytest.mark.asyncio
    async def test_create_group_chat_selector(self, group_chat_model, sample_agents):
        """Test create_group_chat for selector type"""
        result: Optional[int] = await group_chat_model.create_group_chat(
            name="new-selector-chat",
            type="selector_group_chat",
            description="New selector chat",
            labels=["new", "selector"],
            selector_prompt="Choose the best agent",
            participants=["agent1", "agent2"],
            model_client=model_client.deepseek_chat_DeepSeek.value,
            created_by=1
        )
        
        assert result is not None
        assert isinstance(result, int)
        
        # Verify the group chat was created
        async with await group_chat_model.db.get_session() as session:
            from sqlalchemy import select
            stmt = select(GroupChatTable).where(GroupChatTable.id == result)
            db_result = await session.execute(stmt)
            created_chat = db_result.scalar_one_or_none()
            
            assert created_chat is not None
            assert created_chat.name == "new-selector-chat"
            assert created_chat.type == "selector_group_chat"
            assert created_chat.description == "New selector chat"
            assert created_chat.selector_prompt == "Choose the best agent"
            assert created_chat.model_client == model_client.deepseek_chat_DeepSeek.value
            assert created_chat.created_by == 1

    @pytest.mark.asyncio
    async def test_create_group_chat_minimal(self, group_chat_model):
        """Test create_group_chat with minimal parameters"""
        result: Optional[int] = await group_chat_model.create_group_chat(
            name="minimal-chat",
            type="round_robin_group_chat"
        )
        
        assert result is not None
        assert isinstance(result, int)
        
        # Verify the group chat was created with defaults
        async with await group_chat_model.db.get_session() as session:
            from sqlalchemy import select
            stmt = select(GroupChatTable).where(GroupChatTable.id == result)
            db_result = await session.execute(stmt)
            created_chat = db_result.scalar_one_or_none()
            
            assert created_chat is not None
            assert created_chat.name == "minimal-chat"
            assert created_chat.type == "round_robin_group_chat"
            assert created_chat.description is None
            assert created_chat.labels is None  # SQLite stores as None when no labels provided

    @pytest.mark.asyncio
    async def test_update_group_chat(self, group_chat_model, sample_selector_group_chat):
        """Test update_group_chat"""
        result: bool = await group_chat_model.update_group_chat(
            sample_selector_group_chat.id,
            name="updated-selector-chat",
            description="Updated description",
            selector_prompt="Updated prompt",
            participants=["agent1", "agent2", "agent3", "agent4"],
            model_client=model_client.deepseek_reasoner_DeepSeek.value
        )
        
        assert result is True
        
        # Verify the update
        async with await group_chat_model.db.get_session() as session:
            from sqlalchemy import select
            stmt = select(GroupChatTable).where(GroupChatTable.id == sample_selector_group_chat.id)
            db_result = await session.execute(stmt)
            updated_chat = db_result.scalar_one_or_none()
            
            assert updated_chat is not None
            assert updated_chat.name == "updated-selector-chat"
            assert updated_chat.description == "Updated description"
            assert updated_chat.selector_prompt == "Updated prompt"
            assert updated_chat.model_client == model_client.deepseek_reasoner_DeepSeek.value

    @pytest.mark.asyncio
    async def test_update_group_chat_nonexistent(self, group_chat_model):
        """Test update_group_chat with non-existent ID"""
        result: bool = await group_chat_model.update_group_chat(
            999,
            name="nonexistent-chat"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_update_group_chat_no_valid_fields(self, group_chat_model, sample_selector_group_chat):
        """Test update_group_chat with no valid fields returns True"""
        result: bool = await group_chat_model.update_group_chat(
            sample_selector_group_chat.id,
            invalid_field="value"
        )
        
        assert result is True

    @pytest.mark.asyncio
    async def test_deactivate_group_chat(self, group_chat_model, sample_selector_group_chat):
        """Test deactivate_group_chat"""
        result: bool = await group_chat_model.deactivate_group_chat(sample_selector_group_chat.id)
        
        assert result is True
        
        # Verify the group chat was deactivated
        async with await group_chat_model.db.get_session() as session:
            from sqlalchemy import select
            stmt = select(GroupChatTable).where(GroupChatTable.id == sample_selector_group_chat.id)
            db_result = await session.execute(stmt)
            deactivated_chat = db_result.scalar_one_or_none()
            
            assert deactivated_chat is not None
            assert deactivated_chat.is_active is False

    @pytest.mark.asyncio
    async def test_deactivate_group_chat_nonexistent(self, group_chat_model):
        """Test deactivate_group_chat with non-existent ID"""
        result: bool = await group_chat_model.deactivate_group_chat(999)
        
        assert result is False

    @pytest.mark.asyncio
    async def test_update_component_by_id_selector(self, group_chat_model, sample_selector_group_chat):
        """Test update_component_by_id for selector group chat"""
        # Create updated component info
        updated_info: SelectorGroupChatConfig = SelectorGroupChatConfig(
            type=GroupChatType.SELECTOR_GROUP_CHAT,
            name="updated-component",
            description="Updated via component interface",
            labels=["updated", "component"],
            selector_prompt="Updated selector prompt",
            participants=["agent1", "agent2"],  # Use existing agents
            model_client=model_client.deepseek_reasoner_DeepSeek
        )
        
        result: SelectorGroupChatConfig = await group_chat_model.update_component_by_id(
            sample_selector_group_chat.id, 
            updated_info
        )
        
        assert isinstance(result, SelectorGroupChatConfig)
        assert result.name == "updated-component"
        assert result.description == "Updated via component interface"
        assert result.labels == ["updated", "component"]
        assert result.selector_prompt == "Updated selector prompt"
        # The update should reduce from 3 to 2 participants
        assert len(result.participants) == 2
        assert "agent1" in result.participants
        assert "agent2" in result.participants
        assert result.model_client == model_client.deepseek_reasoner_DeepSeek

    @pytest.mark.asyncio
    async def test_update_component_by_id_not_found(self, group_chat_model):
        """Test update_component_by_id with non-existent ID"""
        updated_info: SelectorGroupChatConfig = SelectorGroupChatConfig(
            type=GroupChatType.SELECTOR_GROUP_CHAT,
            name="test",
            description="test",
            labels=[],
            selector_prompt="test",
            participants=[],
            model_client=model_client.deepseek_chat_DeepSeek
        )
        
        result = await group_chat_model.update_component_by_id(999, updated_info)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_component_by_name(self, group_chat_model, sample_selector_group_chat):
        """Test get_component_by_name"""
        result: ComponentInfo = await group_chat_model.get_component_by_name("test-selector-chat")
        
        assert isinstance(result, SelectorGroupChatConfig)
        assert result.name == "test-selector-chat"
        assert result.type == GroupChatType.SELECTOR_GROUP_CHAT

    @pytest.mark.asyncio
    async def test_get_component_by_name_not_found(self, group_chat_model):
        """Test get_component_by_name with non-existent name"""
        result: ComponentInfo = await group_chat_model.get_component_by_name("nonexistent-chat")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_component_by_id(self, group_chat_model, sample_selector_group_chat):
        """Test get_component_by_id"""
        result: ComponentInfo = await group_chat_model.get_component_by_id(sample_selector_group_chat.id)
        
        assert isinstance(result, SelectorGroupChatConfig)
        assert result.name == "test-selector-chat"
        assert result.type == GroupChatType.SELECTOR_GROUP_CHAT

    @pytest.mark.asyncio
    async def test_get_component_by_id_not_found(self, group_chat_model):
        """Test get_component_by_id with non-existent ID"""
        result: ComponentInfo = await group_chat_model.get_component_by_id(999)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_handle_labels_as_string(self, group_chat_model, sqlite_db):
        """Test that string labels are handled correctly in to_component_info"""
        # Create group chat with labels as string (SQLite compatibility)
        async with await sqlite_db.get_session() as session:
            string_labels_chat = GroupChatTable(
                name="string-labels-chat",
                type="selector_group_chat",
                description="Chat with string labels",
                labels="test,string",  # String instead of list
                selector_prompt="Test prompt",
                model_client=model_client.deepseek_chat_DeepSeek.value,
                group_chat_uuid=str(uuid.uuid4())
            )
            session.add(string_labels_chat)
            await session.commit()
            await session.refresh(string_labels_chat)
        
        component_info: SelectorGroupChatConfig = await group_chat_model.to_component_info(string_labels_chat)
        
        # Should handle string labels gracefully
        assert isinstance(component_info.labels, list)
        assert component_info.labels == ["test", "string"]

    @pytest.mark.asyncio
    async def test_handle_none_values(self, group_chat_model, sqlite_db):
        """Test handling of None values in to_component_info"""
        # Use the create_group_chat method to avoid SQLite list issues
        created_id = await group_chat_model.create_group_chat(
            name="none-values-chat",
            type="selector_group_chat",
            description=None,
            labels=None,
            selector_prompt=None,
            participants=None,
            model_client=model_client.deepseek_chat_DeepSeek.value
        )
        
        # Get the created chat
        async with await sqlite_db.get_session() as session:
            from sqlalchemy import select
            stmt = select(GroupChatTable).where(GroupChatTable.id == created_id)
            result = await session.execute(stmt)
            none_values_chat = result.scalar_one()
        
        component_info: SelectorGroupChatConfig = await group_chat_model.to_component_info(none_values_chat)
        
        assert component_info.description == ""
        assert component_info.labels == []
        assert component_info.selector_prompt == ""
        assert component_info.participants == []
        assert component_info.model_client == model_client.deepseek_chat_DeepSeek.value

    @pytest.mark.asyncio
    async def test_get_all_components_with_participants_join(self, group_chat_model, sample_agents):
        """Test get_all_components method uses JOIN query with group_chat_participants table"""
        # Create multiple group chats with different participants
        gc1_id = await group_chat_model.create_group_chat(
            name="chat-with-agents",
            type="selector_group_chat",
            description="Chat with multiple agents",
            labels=["test", "join"],
            selector_prompt="Test prompt",
            participants=["agent1", "agent2", "agent3"],
            model_client=model_client.deepseek_chat_DeepSeek.value,
            created_by=1
        )
        
        gc2_id = await group_chat_model.create_group_chat(
            name="chat-single-agent",
            type="selector_group_chat", 
            description="Chat with single agent",
            labels=["test", "single"],
            selector_prompt="Single prompt",
            participants=["agent1"],
            model_client=model_client.deepseek_chat_DeepSeek.value,
            created_by=1
        )
        
        gc3_id = await group_chat_model.create_group_chat(
            name="chat-no-agents",
            type="selector_group_chat",
            description="Chat with no agents",
            labels=["test", "empty"],
            selector_prompt="Empty prompt", 
            participants=[],
            model_client=model_client.deepseek_chat_DeepSeek.value,
            created_by=1
        )
        
        # Get all components using the overridden method
        all_components = await group_chat_model.get_all_components()
        
        # Should return all 3 created group chats plus any from fixtures
        assert len(all_components) >= 3
        
        # Find our specific test group chats
        chat_with_agents = next((gc for gc in all_components if gc.name == "chat-with-agents"), None)
        chat_single_agent = next((gc for gc in all_components if gc.name == "chat-single-agent"), None)
        chat_no_agents = next((gc for gc in all_components if gc.name == "chat-no-agents"), None)
        
        assert chat_with_agents is not None
        assert chat_single_agent is not None
        assert chat_no_agents is not None
        
        # Verify participants are correctly loaded via JOIN
        assert len(chat_with_agents.participants) == 3
        assert set(chat_with_agents.participants) == {"agent1", "agent2", "agent3"}
        
        assert len(chat_single_agent.participants) == 1
        assert chat_single_agent.participants == ["agent1"]
        
        assert len(chat_no_agents.participants) == 0
        assert chat_no_agents.participants == []
        
        # Verify other properties are correctly loaded
        assert chat_with_agents.description == "Chat with multiple agents"
        assert chat_with_agents.labels == ["test", "join"]
        assert chat_with_agents.selector_prompt == "Test prompt"

    @pytest.mark.asyncio
    async def test_get_all_components_preserves_participant_order(self, group_chat_model, sample_agents):
        """Test get_all_components preserves participant join order"""
        # Create group chat with specific participant order
        gc_id = await group_chat_model.create_group_chat(
            name="ordered-chat",
            type="selector_group_chat",
            description="Chat with ordered participants",
            participants=["agent3", "agent1", "agent2"],  # Specific order
            model_client=model_client.deepseek_chat_DeepSeek.value,
            created_by=1
        )
        
        # Get all components
        all_components = await group_chat_model.get_all_components()
        
        # Find our test group chat
        ordered_chat = next((gc for gc in all_components if gc.name == "ordered-chat"), None)
        assert ordered_chat is not None
        
        # Verify participant order is preserved (should match join_order, not agent names)
        assert ordered_chat.participants == ["agent3", "agent1", "agent2"]

    @pytest.mark.asyncio
    async def test_create_round_robin_group_chat(self, group_chat_model, sample_agents):
        """Test create_group_chat for round robin type with handoff_target and termination_condition"""
        result: Optional[int] = await group_chat_model.create_group_chat(
            name="round-robin-chat",
            type="round_robin_group_chat",
            description="Round robin chat test",
            labels=["test", "round_robin"],
            participants=["agent1", "agent2"],
            handoff_target="user",
            termination_condition="handoff",
            created_by=1
        )
        
        assert result is not None
        assert isinstance(result, int)
        
        # Verify the group chat was created with round robin fields
        component_info = await group_chat_model.get_component_by_id(result)
        assert isinstance(component_info, RoundRobinGroupChatConfig)
        assert component_info.name == "round-robin-chat"
        assert component_info.type == GroupChatType.ROUND_ROBIN_GROUP_CHAT
        assert component_info.description == "Round robin chat test"
        assert component_info.labels == ["test", "round_robin"]
        assert component_info.participants == ["agent1", "agent2"]
        assert component_info.handoff_target == "user"
        assert component_info.termination_condition == "handoff"

    @pytest.mark.asyncio
    async def test_update_round_robin_group_chat(self, group_chat_model, sample_agents):
        """Test updating round robin group chat with new handoff_target and termination_condition"""
        # Create a round robin group chat
        gc_id = await group_chat_model.create_group_chat(
            name="update-round-robin",
            type="round_robin_group_chat",
            description="Original description",
            participants=["agent1"],
            handoff_target="user",
            termination_condition="handoff",
            created_by=1
        )
        
        # Update it
        updated_info = RoundRobinGroupChatConfig(
            type=GroupChatType.ROUND_ROBIN_GROUP_CHAT,
            name="updated-round-robin",
            description="Updated description",
            labels=["updated"],
            participants=["agent1", "agent2", "agent3"],
            handoff_target="agent1",
            termination_condition="text_mention"
        )
        
        result = await group_chat_model.update_component_by_id(gc_id, updated_info)
        
        assert isinstance(result, RoundRobinGroupChatConfig)
        assert result.name == "updated-round-robin"
        assert result.description == "Updated description"
        assert result.labels == ["updated"]
        assert result.participants == ["agent1", "agent2", "agent3"]
        assert result.handoff_target == "agent1"
        assert result.termination_condition == "text_mention"

    @pytest.mark.asyncio
    async def test_to_component_info_round_robin_group_chat(self, group_chat_model, sample_round_robin_group_chat):
        """Test to_component_info for round robin group chat"""
        component_info = await group_chat_model.to_component_info(sample_round_robin_group_chat)
        
        assert isinstance(component_info, RoundRobinGroupChatConfig)
        assert component_info.name == "test-round-robin-chat"
        assert component_info.description == "A test round robin group chat"
        assert component_info.type == GroupChatType.ROUND_ROBIN_GROUP_CHAT
        assert component_info.participants == ["agent1", "agent2"]
        assert component_info.handoff_target == "user"  # Default value
        assert component_info.termination_condition == "handoff"  # Default value
        assert component_info.labels == ["test", "round_robin"]


if __name__ == "__main__":
    pytest.main([__file__])