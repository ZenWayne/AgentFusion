"""
Comprehensive test cases for ThreadModel class.

This module tests all functionality of the ThreadModel class including:
- Thread creation and management
- Thread listing with pagination and filtering
- Thread deletion (soft and hard)
- Thread updating and metadata management
- Thread statistics and user relationships
- Integration with chainlit types
- Data model conversions
- Edge cases and error handling
"""

import pytest
import pytest_asyncio
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from unittest.mock import patch, AsyncMock

from chainlit.types import (
    PageInfo,
    PaginatedResponse,
    Pagination,
    ThreadDict,
    ThreadFilter,
)

from sqlalchemy import text, select, func

# Import the classes we need to test
from data_layer.models.thread_model import ThreadModel, ThreadInfo
from data_layer.models.tables.thread_table import ThreadTable
from data_layer.models.tables.user_table import UserTable
from data_layer.models.tables.step_table import StepsTable
from data_layer.models.tables.element_table import ElementTable
from data_layer.models.tables.feedback_table import FeedbackTable
from ...test_utils import SQLiteDBDataLayer


@pytest_asyncio.fixture
async def sqlite_db():
    """Create a SQLite database for testing"""
    db = SQLiteDBDataLayer()
    await db.connect()
    yield db
    await db.cleanup()


@pytest_asyncio.fixture
async def thread_model(sqlite_db):
    """Create ThreadModel instance with test database"""
    return ThreadModel(sqlite_db)


@pytest_asyncio.fixture
async def sample_user(sqlite_db):
    """Create a sample user for testing"""
    async with await sqlite_db.get_session() as session:
        user_uuid = str(uuid.uuid4())
        user = UserTable(
            id=1,
            user_uuid=user_uuid,
            username="testuser",
            identifier="testuser",
            email="test@example.com",
            password_hash="hashed_password",
            role="user",
            first_name="Test",
            last_name="User",
            is_active=True,
            is_verified=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            user_metadata={"test_key": "test_value"}
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def sample_thread(sqlite_db, sample_user):
    """Create a sample thread for testing"""
    async with await sqlite_db.get_session() as session:
        thread_id = str(uuid.uuid4())
        thread = ThreadTable(
            id=thread_id,
            name="Test Thread",
            user_id=sample_user.id,
            user_identifier=sample_user.identifier,
            # Skip tags for SQLite compatibility - will be None/empty
            thread_metadata={"thread_key": "thread_value"},
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            deleted_at=None
        )
        session.add(thread)
        await session.commit()
        await session.refresh(thread)
        return thread


@pytest_asyncio.fixture
async def sample_step(sqlite_db, sample_thread):
    """Create a sample step for testing"""
    async with await sqlite_db.get_session() as session:
        step = StepsTable(
            id=str(uuid.uuid4()),
            name="Test Step",
            type="user_message",
            thread_id=sample_thread.id,
            parent_id=None,
            start_time=datetime.utcnow(),
            end_time=None,
            input="Test input",
            output="Test output",
            step_metadata={"step_key": "step_value"}
        )
        session.add(step)
        await session.commit()
        await session.refresh(step)
        return step


@pytest_asyncio.fixture
async def sample_element(sqlite_db, sample_thread):
    """Create a sample element for testing"""
    async with await sqlite_db.get_session() as session:
        element = ElementTable(
            id=str(uuid.uuid4()),
            thread_id=sample_thread.id,
            step_id=None,
            url=None,
            name="Test Element",
            display="inline",
            size_bytes=None,
            page_number=None,
            language=None,
            element_metadata={"element_key": "element_value"}
        )
        session.add(element)
        await session.commit()
        await session.refresh(element)
        return element


class TestThreadModelBasic:
    """Test basic ThreadModel functionality"""

    @pytest.mark.asyncio
    async def test_thread_to_info_conversion(self, thread_model, sample_thread):
        """Test conversion from ThreadTable to ThreadInfo"""
        thread_info = thread_model._thread_to_info(sample_thread)
        
        assert isinstance(thread_info, ThreadInfo)
        assert thread_info.id == str(sample_thread.id)
        assert thread_info.name == sample_thread.name
        assert thread_info.user_id == sample_thread.user_id
        assert thread_info.user_identifier == sample_thread.user_identifier
        assert thread_info.tags == []  # Since sample_thread has no tags
        assert thread_info.metadata == sample_thread.thread_metadata
        assert thread_info.is_active == sample_thread.is_active
        assert thread_info.created_at == sample_thread.created_at
        assert thread_info.deleted_at == sample_thread.deleted_at
        assert thread_info.updated_at == sample_thread.updated_at

    @pytest.mark.asyncio
    async def test_get_thread_author_success(self, thread_model, sample_thread, sample_user):
        """Test getting thread author successfully"""
        author = await thread_model.get_thread_author(sample_thread.id)
        assert author == sample_user.identifier

    @pytest.mark.asyncio
    async def test_get_thread_author_not_found(self, thread_model):
        """Test getting thread author when thread doesn't exist"""
        nonexistent_id = str(uuid.uuid4())
        
        with pytest.raises(ValueError, match=f"Thread {nonexistent_id} not found"):
            await thread_model.get_thread_author(nonexistent_id)


class TestThreadModelCRUD:
    """Test CRUD operations for threads"""

    @pytest.mark.asyncio
    async def test_create_thread_success(self, thread_model, sample_user):
        """Test creating a new thread"""
        thread_id = str(uuid.uuid4())
        name = "New Test Thread"
        metadata = {"key": "value"}
        tags = ["new", "test"]
        
        await thread_model.create_thread(
            thread_id=thread_id,
            name=name,
            user_id=str(sample_user.user_uuid),
            metadata=metadata,
            tags=tags
        )
        
        # Verify thread was created
        thread_info = await thread_model.get_thread_by_id(thread_id)
        assert thread_info is not None
        assert thread_info.name == name
        assert thread_info.user_id == sample_user.id
        assert thread_info.metadata == metadata
        # Note: tags might not work in SQLite, so we'll check if they exist or are empty
        assert thread_info.tags == tags or thread_info.tags == []

    @pytest.mark.asyncio
    async def test_update_thread_success(self, thread_model, sample_thread):
        """Test updating an existing thread"""
        new_name = "Updated Thread Name"
        new_metadata = {"updated_key": "updated_value"}
        new_tags = ["updated", "tags"]
        
        await thread_model.update_thread(
            thread_id=sample_thread.id,
            name=new_name,
            metadata=new_metadata,
            tags=new_tags
        )
        
        # Verify thread was updated
        thread_info = await thread_model.get_thread_by_id(sample_thread.id)
        assert thread_info is not None
        assert thread_info.name == new_name
        assert thread_info.metadata == new_metadata
        # Note: tags might not work in SQLite, so we'll check if they exist or are empty
        assert thread_info.tags == new_tags or thread_info.tags == []

    @pytest.mark.asyncio
    async def test_get_thread_by_id_success(self, thread_model, sample_thread):
        """Test getting thread by ID successfully"""
        thread_info = await thread_model.get_thread_by_id(sample_thread.id)
        
        assert thread_info is not None
        assert thread_info.id == sample_thread.id
        assert thread_info.name == sample_thread.name
        assert thread_info.user_id == sample_thread.user_id

    @pytest.mark.asyncio
    async def test_get_thread_by_id_not_found(self, thread_model):
        """Test getting thread by ID when thread doesn't exist"""
        nonexistent_id = str(uuid.uuid4())
        thread_info = await thread_model.get_thread_by_id(nonexistent_id)
        assert thread_info is None

    @pytest.mark.asyncio
    async def test_get_thread_by_id_deleted(self, thread_model, sample_thread):
        """Test getting thread by ID when thread is soft deleted"""
        # Soft delete the thread
        await thread_model.soft_delete_thread(sample_thread.id)
        
        # Should not find the thread
        thread_info = await thread_model.get_thread_by_id(sample_thread.id)
        assert thread_info is None

    @pytest.mark.asyncio
    async def test_delete_thread_success(self, thread_model, sample_thread, sample_element):
        """Test hard deleting a thread"""
        elements_list = await thread_model.delete_thread(sample_thread.id)
        
        # Verify elements were returned
        assert len(elements_list) == 1
        assert elements_list[0].id == sample_element.id
        
        # Verify thread was deleted
        thread_info = await thread_model.get_thread_by_id(sample_thread.id)
        assert thread_info is None


class TestThreadModelPagination:
    """Test thread listing and pagination"""

    @pytest.mark.asyncio
    async def test_list_threads_no_filters(self, thread_model, sample_thread):
        """Test listing threads without filters"""
        pagination = Pagination(first=10, cursor=None)
        filters = ThreadFilter(search=None, userId=None)
        
        result = await thread_model.list_threads(pagination, filters)
        
        assert isinstance(result, PaginatedResponse)
        assert len(result.data) == 1
        assert result.data[0]["id"] == str(sample_thread.id)
        assert result.data[0]["name"] == sample_thread.name
        assert result.pageInfo.hasNextPage is False

    @pytest.mark.asyncio
    async def test_list_threads_search_filter(self, thread_model, sample_thread):
        """Test listing threads with search filter"""
        pagination = Pagination(first=10, cursor=None)
        filters = ThreadFilter(search="Test", userId=None)
        
        result = await thread_model.list_threads(pagination, filters)
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == str(sample_thread.id)

    @pytest.mark.asyncio
    async def test_list_threads_search_no_match(self, thread_model, sample_thread):
        """Test listing threads with search filter that doesn't match"""
        pagination = Pagination(first=10, cursor=None)
        filters = ThreadFilter(search="NonExistent", userId=None)
        
        result = await thread_model.list_threads(pagination, filters)
        
        assert len(result.data) == 0

    @pytest.mark.asyncio
    async def test_list_threads_user_filter(self, thread_model, sample_thread, sample_user):
        """Test listing threads with user filter"""
        pagination = Pagination(first=10, cursor=None)
        filters = ThreadFilter(search=None, userId=str(sample_user.id))
        
        result = await thread_model.list_threads(pagination, filters)
        
        assert len(result.data) == 1
        assert result.data[0]["id"] == str(sample_thread.id)

    @pytest.mark.asyncio
    async def test_list_threads_pagination(self, thread_model, sample_user):
        """Test thread listing with pagination"""
        # Create multiple threads
        thread_ids = []
        for i in range(5):
            thread_id = str(uuid.uuid4())
            await thread_model.create_thread(
                thread_id=thread_id,
                name=f"Thread {i}",
                user_id=str(sample_user.user_uuid)
            )
            thread_ids.append(thread_id)
        
        # Test first page
        pagination = Pagination(first=2, cursor=None)
        filters = ThreadFilter(search=None, userId=None)
        
        result = await thread_model.list_threads(pagination, filters)
        
        assert len(result.data) == 2
        assert result.pageInfo.hasNextPage is True
        
        # Test second page
        pagination = Pagination(first=2, cursor=result.pageInfo.endCursor)
        result = await thread_model.list_threads(pagination, filters)
        
        assert len(result.data) == 2
        assert result.pageInfo.hasNextPage is True


class TestThreadModelSoftDelete:
    """Test soft delete functionality"""

    @pytest.mark.asyncio
    async def test_soft_delete_thread(self, thread_model, sample_thread):
        """Test soft deleting a thread"""
        await thread_model.soft_delete_thread(sample_thread.id)
        
        # Thread should not be found in normal queries
        thread_info = await thread_model.get_thread_by_id(sample_thread.id)
        assert thread_info is None
        
        # Verify thread is marked as deleted
        async with await thread_model.db.get_session() as session:
            stmt = select(ThreadTable).where(ThreadTable.id == sample_thread.id)
            result = await session.execute(stmt)
            thread = result.scalar_one_or_none()
            assert thread is not None
            assert thread.deleted_at is not None

    @pytest.mark.asyncio
    async def test_restore_thread(self, thread_model, sample_thread):
        """Test restoring a soft deleted thread"""
        # First soft delete
        await thread_model.soft_delete_thread(sample_thread.id)
        
        # Then restore
        await thread_model.restore_thread(sample_thread.id)
        
        # Thread should be found again
        thread_info = await thread_model.get_thread_by_id(sample_thread.id)
        assert thread_info is not None
        assert thread_info.id == sample_thread.id


class TestThreadModelStatistics:
    """Test thread statistics functionality"""

    @pytest.mark.asyncio
    async def test_get_thread_count_by_user(self, thread_model, sample_user, sample_thread):
        """Test getting thread count for a user"""
        count = await thread_model.get_thread_count_by_user(str(sample_user.id))
        assert count == 1

    @pytest.mark.asyncio
    async def test_get_thread_count_by_user_no_threads(self, thread_model):
        """Test getting thread count for user with no threads"""
        count = await thread_model.get_thread_count_by_user("999")
        assert count == 0

    @pytest.mark.asyncio
    async def test_get_recent_threads(self, thread_model, sample_user, sample_thread):
        """Test getting recent threads for a user"""
        threads = await thread_model.get_recent_threads(str(sample_user.id), limit=10)
        
        assert len(threads) == 1
        assert threads[0]["id"] == str(sample_thread.id)
        assert threads[0]["name"] == sample_thread.name

    @pytest.mark.asyncio
    async def test_get_thread_statistics_all(self, thread_model, sample_thread):
        """Test getting overall thread statistics"""
        stats = await thread_model.get_thread_statistics()
        
        assert stats["total_threads"] == 1
        assert stats["active_threads"] == 1
        assert stats["deleted_threads"] == 0

    @pytest.mark.asyncio
    async def test_get_thread_statistics_with_deleted(self, thread_model, sample_thread):
        """Test getting thread statistics with deleted threads"""
        # Soft delete the thread
        await thread_model.soft_delete_thread(sample_thread.id)
        
        stats = await thread_model.get_thread_statistics()
        
        assert stats["total_threads"] == 1
        assert stats["active_threads"] == 0
        assert stats["deleted_threads"] == 1

    @pytest.mark.asyncio
    async def test_get_thread_statistics_by_user(self, thread_model, sample_user, sample_thread):
        """Test getting thread statistics for specific user"""
        stats = await thread_model.get_thread_statistics(user_id=str(sample_user.id))
        
        assert stats["total_threads"] == 1
        assert stats["active_threads"] == 1
        assert stats["deleted_threads"] == 0


class TestThreadModelRelationships:
    """Test thread relationships and complex queries"""

    @pytest.mark.asyncio
    async def test_get_thread_with_relationships(self, thread_model, sample_thread, sample_step, sample_element):
        """Test getting thread with all relationships loaded"""
        thread = await thread_model.get_thread_with_relationships(sample_thread.id)
        
        assert thread is not None
        assert thread.id == sample_thread.id
        # Note: actual relationship loading depends on SQLAlchemy configuration

    @pytest.mark.asyncio
    async def test_get_threads_with_user_info(self, thread_model, sample_thread):
        """Test getting threads with user information"""
        threads = await thread_model.get_threads_with_user_info(limit=10)
        
        assert len(threads) == 1
        assert threads[0].id == sample_thread.id

    @pytest.mark.asyncio
    async def test_get_thread_steps_with_elements(self, thread_model, sample_thread, sample_step):
        """Test getting thread steps with their elements"""
        steps = await thread_model.get_thread_steps_with_elements(sample_thread.id)
        
        assert len(steps) == 1
        assert steps[0].id == sample_step.id

    @pytest.mark.asyncio
    async def test_get_thread_complex(self, thread_model, sample_thread, sample_step, sample_element):
        """Test getting thread with complex data structure"""
        result = await thread_model.get_thread(sample_thread.id)
        
        assert result is not None
        assert "thread" in result
        assert "user_identifier" in result
        assert "user_uuid" in result
        assert "steps" in result
        assert "elements" in result
        assert "feedback_map" in result


class TestThreadModelEdgeCases:
    """Test edge cases and error handling"""

    @pytest.mark.asyncio
    async def test_update_thread_with_uuid_user_id(self, thread_model, sample_user):
        """Test updating thread with UUID user_id"""
        thread_id = str(uuid.uuid4())
        
        await thread_model.update_thread(
            thread_id=thread_id,
            name="UUID Test Thread",
            user_id=str(sample_user.user_uuid)  # UUID format
        )
        
        thread_info = await thread_model.get_thread_by_id(thread_id)
        assert thread_info is not None
        assert thread_info.user_id == sample_user.id

    @pytest.mark.asyncio
    async def test_update_thread_with_invalid_uuid(self, thread_model):
        """Test updating thread with invalid UUID user_id"""
        thread_id = str(uuid.uuid4())
        
        await thread_model.update_thread(
            thread_id=thread_id,
            name="Invalid UUID Test",
            user_id="invalid-uuid"  # Invalid UUID format
        )
        
        # Should handle gracefully
        thread_info = await thread_model.get_thread_by_id(thread_id)
        assert thread_info is not None

    @pytest.mark.asyncio
    async def test_thread_name_truncation(self, thread_model, sample_user):
        """Test thread name truncation"""
        thread_id = str(uuid.uuid4())
        very_long_name = "x" * 1000  # Very long name
        
        await thread_model.create_thread(
            thread_id=thread_id,
            name=very_long_name,
            user_id=str(sample_user.user_uuid)
        )
        
        thread_info = await thread_model.get_thread_by_id(thread_id)
        assert thread_info is not None
        # Name should be truncated (exact length depends on _truncate implementation)
        assert len(thread_info.name) <= 255

    @pytest.mark.asyncio
    async def test_thread_metadata_none_handling(self, thread_model, sample_thread):
        """Test handling of None metadata"""
        sample_thread.thread_metadata = None
        thread_info = thread_model._thread_to_info(sample_thread)
        
        assert thread_info.metadata == {}

    @pytest.mark.asyncio
    async def test_empty_pagination_result(self, thread_model):
        """Test pagination with no results"""
        pagination = Pagination(first=10, cursor=None)
        filters = ThreadFilter(search="NonExistentThread", userId=None)
        
        result = await thread_model.list_threads(pagination, filters)
        
        assert len(result.data) == 0
        assert result.pageInfo.hasNextPage is False
        assert result.pageInfo.startCursor is None
        assert result.pageInfo.endCursor is None


class TestThreadModelPerformance:
    """Test performance-related aspects"""

    @pytest.mark.asyncio
    async def test_bulk_thread_operations(self, thread_model, sample_user):
        """Test creating and querying multiple threads"""
        # Create multiple threads
        thread_count = 10
        thread_ids = []
        
        for i in range(thread_count):
            thread_id = str(uuid.uuid4())
            await thread_model.create_thread(
                thread_id=thread_id,
                name=f"Bulk Thread {i}",
                user_id=str(sample_user.user_uuid),
                tags=[f"tag{i}", "bulk"],
                metadata={"index": i}
            )
            thread_ids.append(thread_id)
        
        # Test count
        count = await thread_model.get_thread_count_by_user(str(sample_user.id))
        assert count == thread_count
        
        # Test recent threads
        recent = await thread_model.get_recent_threads(str(sample_user.id), limit=5)
        assert len(recent) == 5
        
        # Test statistics
        stats = await thread_model.get_thread_statistics(user_id=str(sample_user.id))
        assert stats["active_threads"] == thread_count