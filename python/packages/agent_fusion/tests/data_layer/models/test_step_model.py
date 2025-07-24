"""
Pytest tests for StepModel class.

This module tests all functionality of the StepModel class using SQLite for testing.
"""

import pytest
import pytest_asyncio
import tempfile
import os
import uuid
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy import text, JSON, Text
from sqlalchemy.dialects.postgresql import JSONB, ARRAY

# Import the classes we need to test
from data_layer.base_data_layer import DBDataLayer
from data_layer.models.step_model import StepModel, StepInfo, ISO_FORMAT
from data_layer.models.tables import Base, StepsTable
from chainlit.step import StepDict
from chainlit.types import FeedbackDict
from ...test_utils import SQLiteDBDataLayer


@pytest_asyncio.fixture
async def sqlite_db():
    """Create a SQLite database for testing"""
    db = SQLiteDBDataLayer()
    await db.connect()
    yield db
    await db.cleanup()


@pytest_asyncio.fixture
async def step_model(sqlite_db):
    """Create StepModel instance with test database"""
    return StepModel(sqlite_db)


@pytest_asyncio.fixture
async def sample_step_dict():
    """Create a sample StepDict for testing"""
    return StepDict(
        id="test-step-1",
        threadId="test-thread-1",
        parentId=None,
        name="Test Step",
        type="run",
        input={"query": "test input"},
        output={"result": "test output"},
        metadata={"key": "value"},
        createdAt=datetime.utcnow().strftime(ISO_FORMAT),
        start=datetime.utcnow().strftime(ISO_FORMAT),
        showInput="json",
        isError=False,
        end=None,
        feedback=None
    )


@pytest_asyncio.fixture
async def sample_step_record(sqlite_db):
    """Create a sample step record in database"""
    async with await sqlite_db.get_session() as session:
        step = StepsTable(
            id="sample-step-1",
            thread_id="sample-thread-1",
            parent_id=None,
            input={"test": "input"},
            step_metadata={"sample": "metadata"},
            name="Sample Step",
            output={"test": "output"},
            type="run",
            start_time=datetime.utcnow(),
            end_time=datetime.utcnow() + timedelta(seconds=1),
            show_input="json",
            is_error=False
        )
        session.add(step)
        await session.commit()
        await session.refresh(step)
        return step


class TestStepModel:
    """Test cases for StepModel class"""
    
    @pytest.mark.asyncio
    async def test_model_to_info(self, step_model, sample_step_record):
        """Test _model_to_info conversion"""
        step_info = step_model._model_to_info(sample_step_record)
        
        assert isinstance(step_info, StepInfo)
        assert step_info.id == "sample-step-1"
        assert step_info.thread_id == "sample-thread-1"
        assert step_info.parent_id is None
        assert step_info.input == {"test": "input"}
        assert step_info.metadata == {"sample": "metadata"}
        assert step_info.name == "Sample Step"
        assert step_info.output == {"test": "output"}
        assert step_info.type == "run"
        assert step_info.show_input == "json"
        assert step_info.is_error is False
        assert step_info.start_time is not None
        assert step_info.end_time is not None

    @pytest.mark.asyncio
    async def test_create_step_new(self, step_model, sample_step_dict):
        """Test creating a new step"""
        await step_model.create_step(sample_step_dict)
        
        # Verify step was created
        step_info = await step_model.get_step_by_id("test-step-1")
        assert step_info is not None
        assert step_info.id == "test-step-1"
        assert step_info.thread_id == "test-thread-1"
        assert step_info.name == "Test Step"
        assert step_info.type == "run"
        assert step_info.input == {"query": "test input"}
        assert step_info.output == {"result": "test output"}
        assert step_info.metadata == {"key": "value"}

    @pytest.mark.asyncio
    async def test_create_step_existing_update(self, step_model, sample_step_record):
        """Test updating an existing step"""
        update_dict = StepDict(
            id="sample-step-1",
            threadId="sample-thread-1",
            parentId=None,
            name="Updated Step",
            type="run",
            input={"updated": "input"},
            output={"updated": "output"},
            metadata={"updated": "metadata"},
            createdAt=datetime.utcnow().strftime(ISO_FORMAT),
            start=datetime.utcnow().strftime(ISO_FORMAT),
            showInput="json",
            isError=False,
            end=None,
            feedback=None
        )
        
        await step_model.create_step(update_dict)
        
        # Verify step was updated
        step_info = await step_model.get_step_by_id("sample-step-1")
        assert step_info is not None
        assert step_info.name == "Updated Step"
        assert step_info.input == {"updated": "input"}
        assert step_info.output == {"updated": "output"}
        assert step_info.metadata == {"updated": "metadata"}

    @pytest.mark.asyncio
    async def test_create_step_with_parent(self, step_model):
        """Test creating a step with parent that doesn't exist"""
        step_dict = StepDict(
            id="child-step",
            threadId="test-thread",
            parentId="parent-step",
            name="Child Step",
            type="run",
            input={},
            output={},
            metadata={},
            createdAt=datetime.utcnow().strftime(ISO_FORMAT),
            start=datetime.utcnow().strftime(ISO_FORMAT),
            showInput="json",
            isError=False,
            end=None,
            feedback=None
        )
        
        await step_model.create_step(step_dict)
        
        # Verify both parent and child were created
        parent_info = await step_model.get_step_by_id("parent-step")
        child_info = await step_model.get_step_by_id("child-step")
        
        assert parent_info is not None
        assert parent_info.type == "run"
        assert child_info is not None
        assert child_info.parent_id == "parent-step"

    @pytest.mark.asyncio
    async def test_update_step(self, step_model, sample_step_dict):
        """Test update_step method"""
        await step_model.create_step(sample_step_dict)
        
        # Update using update_step method
        updated_dict = sample_step_dict.copy()
        updated_dict["name"] = "Updated via update_step"
        
        await step_model.update_step(updated_dict)
        
        step_info = await step_model.get_step_by_id("test-step-1")
        assert step_info.name == "Updated via update_step"

    @pytest.mark.asyncio
    async def test_delete_step(self, step_model, sample_step_record):
        """Test deleting a step"""
        # Verify step exists
        step_info = await step_model.get_step_by_id("sample-step-1")
        assert step_info is not None
        
        # Delete step
        await step_model.delete_step("sample-step-1")
        
        # Verify step was deleted
        step_info = await step_model.get_step_by_id("sample-step-1")
        assert step_info is None

    @pytest.mark.asyncio
    async def test_get_step_by_id(self, step_model, sample_step_record):
        """Test getting step by ID"""
        step_info = await step_model.get_step_by_id("sample-step-1")
        
        assert step_info is not None
        assert step_info.id == "sample-step-1"
        assert step_info.thread_id == "sample-thread-1"

    @pytest.mark.asyncio
    async def test_get_step_by_id_not_found(self, step_model):
        """Test getting non-existent step by ID"""
        step_info = await step_model.get_step_by_id("non-existent")
        assert step_info is None

    @pytest.mark.asyncio
    async def test_get_steps_by_thread_orm(self, step_model, sqlite_db):
        """Test getting steps by thread using ORM"""
        # Create multiple steps in same thread
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(
                    id=f"step-{i}",
                    thread_id="test-thread",
                    name=f"Step {i}",
                    type="run",
                    start_time=datetime.utcnow() + timedelta(seconds=i)
                )
                for i in range(3)
            ]
            session.add_all(steps)
            await session.commit()
        
        # Get steps by thread
        thread_steps = await step_model.get_steps_by_thread_orm("test-thread")
        
        assert len(thread_steps) == 3
        assert all(step.thread_id == "test-thread" for step in thread_steps)
        # Should be ordered by start_time
        assert thread_steps[0].name == "Step 0"
        assert thread_steps[1].name == "Step 1"
        assert thread_steps[2].name == "Step 2"

    @pytest.mark.asyncio
    async def test_get_child_steps_orm(self, step_model, sqlite_db):
        """Test getting child steps using ORM"""
        # Create parent and child steps
        async with await sqlite_db.get_session() as session:
            parent = StepsTable(
                id="parent-step",
                thread_id="test-thread",
                name="Parent Step",
                type="run"
            )
            child1 = StepsTable(
                id="child-1",
                thread_id="test-thread",
                parent_id="parent-step",
                name="Child 1",
                type="run"
            )
            child2 = StepsTable(
                id="child-2",
                thread_id="test-thread",
                parent_id="parent-step",
                name="Child 2",
                type="run"
            )
            session.add_all([parent, child1, child2])
            await session.commit()
        
        # Get child steps
        children = await step_model.get_child_steps_orm("parent-step")
        
        assert len(children) == 2
        assert all(child.parent_id == "parent-step" for child in children)
        child_names = {child.name for child in children}
        assert child_names == {"Child 1", "Child 2"}

    @pytest.mark.asyncio
    async def test_get_root_steps_orm(self, step_model, sqlite_db):
        """Test getting root steps using ORM"""
        # Create root steps and child steps
        async with await sqlite_db.get_session() as session:
            root1 = StepsTable(
                id="root-1",
                thread_id="test-thread",
                parent_id=None,
                name="Root 1",
                type="run"
            )
            root2 = StepsTable(
                id="root-2",
                thread_id="test-thread",
                parent_id=None,
                name="Root 2",
                type="run"
            )
            child = StepsTable(
                id="child-1",
                thread_id="test-thread",
                parent_id="root-1",
                name="Child",
                type="run"
            )
            session.add_all([root1, root2, child])
            await session.commit()
        
        # Get root steps
        roots = await step_model.get_root_steps_orm("test-thread")
        
        assert len(roots) == 2
        assert all(step.parent_id is None for step in roots)
        assert all(step.thread_id == "test-thread" for step in roots)
        root_names = {step.name for step in roots}
        assert root_names == {"Root 1", "Root 2"}

    @pytest.mark.asyncio
    async def test_update_step_output(self, step_model, sample_step_record):
        """Test updating step output"""
        new_output = {"updated": "output", "status": "completed"}
        
        result = await step_model.update_step_output("sample-step-1", new_output)
        assert result is True
        
        # Verify output was updated
        step_info = await step_model.get_step_by_id("sample-step-1")
        assert step_info.output == new_output

    @pytest.mark.asyncio
    async def test_update_step_output_not_found(self, step_model):
        """Test updating output of non-existent step"""
        result = await step_model.update_step_output("non-existent", {"test": "output"})
        assert result is False

    @pytest.mark.asyncio
    async def test_mark_step_as_error(self, step_model, sample_step_record):
        """Test marking step as error"""
        error_message = "Something went wrong"
        
        result = await step_model.mark_step_as_error("sample-step-1", error_message)
        assert result is True
        
        # Verify step was marked as error
        step_info = await step_model.get_step_by_id("sample-step-1")
        assert step_info.is_error is True
        assert step_info.output == error_message

    @pytest.mark.asyncio
    async def test_mark_step_as_error_not_found(self, step_model):
        """Test marking non-existent step as error"""
        result = await step_model.mark_step_as_error("non-existent", "error")
        assert result is False

    @pytest.mark.asyncio
    async def test_get_steps_by_type_orm(self, step_model, sqlite_db):
        """Test getting steps by type using ORM"""
        # Create steps of different types
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(id="step-1", thread_id="test-thread", type="run", name="Run Step"),
                StepsTable(id="step-2", thread_id="test-thread", type="tool", name="Tool Step"),
                StepsTable(id="step-3", thread_id="test-thread", type="run", name="Another Run Step"),
                StepsTable(id="step-4", thread_id="other-thread", type="run", name="Other Thread Run"),
            ]
            session.add_all(steps)
            await session.commit()
        
        # Get run steps from specific thread
        run_steps = await step_model.get_steps_by_type_orm("run", "test-thread")
        assert len(run_steps) == 2
        assert all(step.type == "run" for step in run_steps)
        assert all(step.thread_id == "test-thread" for step in run_steps)
        
        # Get all run steps
        all_run_steps = await step_model.get_steps_by_type_orm("run")
        assert len(all_run_steps) == 3
        assert all(step.type == "run" for step in all_run_steps)

    @pytest.mark.asyncio
    async def test_get_steps_by_error_status(self, step_model, sqlite_db):
        """Test getting steps by error status"""
        # Create steps with different error statuses
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(id="success-1", thread_id="test-thread", type="run", is_error=False),
                StepsTable(id="error-1", thread_id="test-thread", type="run", is_error=True),
                StepsTable(id="success-2", thread_id="test-thread", type="run", is_error=False),
                StepsTable(id="error-2", thread_id="other-thread", type="run", is_error=True),
            ]
            session.add_all(steps)
            await session.commit()
        
        # Get error steps from specific thread
        error_steps = await step_model.get_steps_by_error_status(True, "test-thread")
        assert len(error_steps) == 1
        assert error_steps[0].id == "error-1"
        assert error_steps[0].is_error is True
        
        # Get success steps from specific thread
        success_steps = await step_model.get_steps_by_error_status(False, "test-thread")
        assert len(success_steps) == 2
        assert all(not step.is_error for step in success_steps)

    @pytest.mark.asyncio
    async def test_get_steps_by_time_range(self, step_model, sqlite_db):
        """Test getting steps by time range"""
        base_time = datetime.utcnow()
        
        # Create steps with different start times
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(
                    id="step-1", 
                    thread_id="test-thread", 
                    type="run",
                    start_time=base_time - timedelta(hours=2)
                ),
                StepsTable(
                    id="step-2", 
                    thread_id="test-thread", 
                    type="run",
                    start_time=base_time - timedelta(hours=1)
                ),
                StepsTable(
                    id="step-3", 
                    thread_id="test-thread", 
                    type="run",
                    start_time=base_time
                ),
                StepsTable(
                    id="step-4", 
                    thread_id="test-thread", 
                    type="run",
                    start_time=base_time + timedelta(hours=1)
                ),
            ]
            session.add_all(steps)
            await session.commit()
        
        # Get steps in time range
        start_range = base_time - timedelta(hours=1, minutes=30)
        end_range = base_time + timedelta(minutes=30)
        
        range_steps = await step_model.get_steps_by_time_range(start_range, end_range, "test-thread")
        
        assert len(range_steps) == 2
        step_ids = {step.id for step in range_steps}
        assert step_ids == {"step-2", "step-3"}

    @pytest.mark.asyncio
    async def test_update_step_metadata(self, step_model, sample_step_record):
        """Test updating step metadata"""
        new_metadata = {"updated": True, "version": 2}
        
        result = await step_model.update_step_metadata("sample-step-1", new_metadata)
        assert result is True
        
        # Verify metadata was updated
        step_info = await step_model.get_step_by_id("sample-step-1")
        assert step_info.metadata == new_metadata

    @pytest.mark.asyncio
    async def test_update_step_metadata_not_found(self, step_model):
        """Test updating metadata of non-existent step"""
        result = await step_model.update_step_metadata("non-existent", {"test": "metadata"})
        assert result is False

    @pytest.mark.asyncio
    async def test_bulk_update_steps(self, step_model, sqlite_db):
        """Test bulk updating multiple steps"""
        # Create multiple steps
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(id=f"step-{i}", thread_id="test-thread", type="run", name=f"Step {i}")
                for i in range(3)
            ]
            session.add_all(steps)
            await session.commit()
        
        # Bulk update
        updates = [
            {"id": "step-0", "name": "Updated Step 0", "is_error": True},
            {"id": "step-1", "name": "Updated Step 1", "output": {"result": "success"}},
            {"id": "step-2", "type": "tool"}
        ]
        
        updated_count = await step_model.bulk_update_steps(updates)
        assert updated_count == 3
        
        # Verify updates
        step_0 = await step_model.get_step_by_id("step-0")
        step_1 = await step_model.get_step_by_id("step-1")
        step_2 = await step_model.get_step_by_id("step-2")
        
        assert step_0.name == "Updated Step 0"
        assert step_0.is_error is True
        assert step_1.name == "Updated Step 1"
        assert step_1.output == {"result": "success"}
        assert step_2.type == "tool"

    @pytest.mark.asyncio
    async def test_delete_steps_by_thread(self, step_model, sqlite_db):
        """Test deleting all steps in a thread"""
        # Create steps in multiple threads
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(id="thread1-step1", thread_id="thread-1", type="run"),
                StepsTable(id="thread1-step2", thread_id="thread-1", type="run"),
                StepsTable(id="thread2-step1", thread_id="thread-2", type="run"),
            ]
            session.add_all(steps)
            await session.commit()
        
        # Delete steps from thread-1
        deleted_count = await step_model.delete_steps_by_thread("thread-1")
        assert deleted_count == 2
        
        # Verify thread-1 steps are deleted
        thread1_steps = await step_model.get_steps_by_thread_orm("thread-1")
        assert len(thread1_steps) == 0
        
        # Verify thread-2 steps still exist
        thread2_steps = await step_model.get_steps_by_thread_orm("thread-2")
        assert len(thread2_steps) == 1

    @pytest.mark.asyncio
    async def test_convert_step_row_to_dict(self, step_model):
        """Test converting database row to StepDict"""
        row = {
            "id": "test-step",
            "thread_id": "test-thread",
            "parent_id": "parent-step",
            "name": "Test Step",
            "type": "run",
            "input": {"query": "test"},
            "output": {"result": "success"},
            "metadata": {"key": "value"},
            "created_at": datetime.utcnow(),
            "start_time": datetime.utcnow(),
            "show_input": "json",
            "is_error": False,
            "end_time": datetime.utcnow() + timedelta(seconds=1),
            "feedback_id": "feedback-1",
            "feedback_value": 1,
            "feedback_comment": "Good"
        }
        
        step_dict = step_model._convert_step_row_to_dict(row)
        
        assert isinstance(step_dict, dict)  # StepDict is a TypedDict, check as dict
        assert step_dict["id"] == "test-step"
        assert step_dict["threadId"] == "test-thread"
        assert step_dict["parentId"] == "parent-step"
        assert step_dict["name"] == "Test Step"
        assert step_dict["type"] == "run"
        assert step_dict["input"] == {"query": "test"}
        assert step_dict["output"] == {"result": "success"}
        assert step_dict["metadata"] == {"key": "value"}
        assert step_dict["showInput"] == "json"
        assert step_dict["isError"] is False
        assert step_dict["feedback"] is not None
        assert step_dict["feedback"]["value"] == 1

    @pytest.mark.asyncio
    async def test_convert_step_row_with_string_metadata(self, step_model):
        """Test converting row with metadata as JSON string"""
        row = {
            "id": "test-step",
            "thread_id": "test-thread",
            "parent_id": None,
            "name": "Test Step",
            "type": "run",
            "input": {},
            "output": {},
            "metadata": '{"stringified": "metadata"}',  # JSON string
            "created_at": datetime.utcnow(),
            "start_time": datetime.utcnow(),
            "show_input": "json",
            "is_error": False,
            "end_time": None,
            "feedback_id": None,
            "feedback_value": None,
            "feedback_comment": None
        }
        
        step_dict = step_model._convert_step_row_to_dict(row)
        
        assert step_dict["metadata"] == {"stringified": "metadata"}

    @pytest.mark.asyncio
    async def test_convert_step_row_with_invalid_metadata(self, step_model):
        """Test converting row with invalid JSON metadata"""
        row = {
            "id": "test-step",
            "thread_id": "test-thread",
            "parent_id": None,
            "name": "Test Step",
            "type": "run",
            "input": {},
            "output": {},
            "metadata": "invalid json",  # Invalid JSON
            "created_at": datetime.utcnow(),
            "start_time": datetime.utcnow(),
            "show_input": "json",
            "is_error": False,
            "end_time": None,
            "feedback_id": None,
            "feedback_value": None,
            "feedback_comment": None
        }
        
        step_dict = step_model._convert_step_row_to_dict(row)
        
        assert step_dict["metadata"] == {}  # Should fallback to empty dict

    @pytest.mark.asyncio
    async def test_extract_feedback_dict_from_step_row(self, step_model):
        """Test extracting feedback from step row"""
        row_with_feedback = {
            "id": "test-step",
            "feedback_id": "feedback-1",
            "feedback_value": 1,
            "feedback_comment": "Great step!"
        }
        
        feedback = step_model._extract_feedback_dict_from_step_row(row_with_feedback)
        
        assert feedback is not None
        assert isinstance(feedback, dict)  # FeedbackDict is a TypedDict, check as dict
        assert feedback["forId"] == "test-step"
        assert feedback["id"] == "feedback-1"
        assert feedback["value"] == 1
        assert feedback["comment"] == "Great step!"

    @pytest.mark.asyncio
    async def test_extract_feedback_dict_no_feedback(self, step_model):
        """Test extracting feedback when none exists"""
        row_without_feedback = {
            "id": "test-step",
            "feedback_id": None,
            "feedback_value": None,
            "feedback_comment": None
        }
        
        feedback = step_model._extract_feedback_dict_from_step_row(row_without_feedback)
        assert feedback is None

    @pytest.mark.asyncio
    async def test_error_handling_create_step(self, step_model, sqlite_db):
        """Test error handling in create_step"""
        # Mock session to raise exception
        with patch.object(sqlite_db, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.execute.side_effect = Exception("Database error")
            mock_session.commit.side_effect = Exception("Database error")
            mock_get_session.return_value = mock_session
            
            sample_dict = StepDict(
                id="error-step",
                threadId="test-thread",
                type="run",
                input={},
                output={},
                metadata={},
                createdAt=datetime.utcnow().strftime(ISO_FORMAT)
            )
            
            with pytest.raises(Exception, match="Database error"):
                await step_model.create_step(sample_dict)
            
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_handling_update_step_output(self, step_model, sqlite_db):
        """Test error handling in update_step_output"""
        with patch.object(sqlite_db, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_session.rollback = AsyncMock()
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.execute.side_effect = Exception("Update error")
            mock_get_session.return_value = mock_session
            
            with pytest.raises(Exception, match="Update error"):
                await step_model.update_step_output("test-step", {"output": "test"})
            
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_step_with_complex_data(self, step_model):
        """Test step creation with complex input/output data"""
        complex_data = {
            "nested": {
                "array": [1, 2, 3],
                "object": {"key": "value"},
                "boolean": True,
                "null": None
            },
            "unicode": "测试中文",
            "special_chars": "!@#$%^&*()"
        }
        
        step_dict = StepDict(
            id="complex-step",
            threadId="test-thread",
            type="run",
            input=complex_data,
            output=complex_data,
            metadata=complex_data,
            createdAt=datetime.utcnow().strftime(ISO_FORMAT)
        )
        
        await step_model.create_step(step_dict)
        
        # Verify complex data was stored correctly
        step_info = await step_model.get_step_by_id("complex-step")
        assert step_info.input == complex_data
        assert step_info.output == complex_data
        assert step_info.metadata == complex_data

    @pytest.mark.asyncio
    async def test_get_step_statistics(self, step_model, sqlite_db):
        """Test getting step statistics"""
        # Create steps with different statuses
        async with await sqlite_db.get_session() as session:
            steps = [
                StepsTable(id="stat-step-1", thread_id="stat-thread", type="run", is_error=False,
                          start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(seconds=1)),
                StepsTable(id="stat-step-2", thread_id="stat-thread", type="run", is_error=True,
                          start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(seconds=2)),
                StepsTable(id="stat-step-3", thread_id="stat-thread", type="run", is_error=False,
                          start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(seconds=3)),
                StepsTable(id="stat-step-4", thread_id="other-thread", type="run", is_error=False,
                          start_time=datetime.utcnow(), end_time=datetime.utcnow() + timedelta(seconds=1)),
            ]
            session.add_all(steps)
            await session.commit()
        
        # Get statistics for specific thread
        thread_stats = await step_model.get_step_statistics("stat-thread")
        assert thread_stats["total_steps"] == 3
        assert thread_stats["error_steps"] == 1
        assert thread_stats["success_steps"] == 2
        assert thread_stats["avg_duration_seconds"] is not None
        
        # Get global statistics
        global_stats = await step_model.get_step_statistics()
        assert global_stats["total_steps"] >= 4  # At least the 4 we created
        assert global_stats["error_steps"] >= 1
        assert global_stats["success_steps"] >= 3

    @pytest.mark.asyncio
    async def test_get_step_statistics_empty(self, step_model):
        """Test getting statistics when no steps exist"""
        stats = await step_model.get_step_statistics("non-existent-thread")
        assert stats["total_steps"] == 0
        assert stats["error_steps"] == 0
        assert stats["success_steps"] == 0
        # avg_duration_seconds can be None when no steps exist
        assert stats["avg_duration_seconds"] is None or stats["avg_duration_seconds"] == 0


if __name__ == "__main__":
    pytest.main([__file__])