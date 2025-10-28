"""
Comprehensive test cases for LLMModel class.

This module tests all functionality of the LLMModel class including:
- Component retrieval and conversion
- Model client configuration updates
- Data model conversions between SQLAlchemy and schema objects
- Error handling and edge cases
"""

import pytest
import pytest_asyncio
import uuid
from datetime import datetime
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, patch

from sqlalchemy import select

# Import the classes we need to test
from data_layer.models.llm_model import LLMModel
from data_layer.models.tables import ModelClientTable
from schemas.model_info import ModelClientConfig
from schemas.types import ComponentType
from ...test_utils import SQLiteDBDataLayer


@pytest_asyncio.fixture
async def sqlite_db():
    """Create a SQLite database for testing"""
    db = SQLiteDBDataLayer()
    await db.connect()
    yield db
    await db.cleanup()


@pytest_asyncio.fixture
async def llm_model(sqlite_db):
    """Create LLMModel instance with test database"""
    return LLMModel(sqlite_db)


@pytest_asyncio.fixture
async def sample_model_client(sqlite_db):
    """Create a sample model client for testing"""
    async with await sqlite_db.get_session() as session:
        model_client = ModelClientTable(
            id=1,
            label="deepseek-chat_DeepSeek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com/v1",
            provider="deepseek",  # Required field
            model_info={"family": "deepseek", "context_window": 32768},
            config={"stream": True, "temperature": 0.7},
            api_key_type="DEEPSEEK_API_KEY",
            client_uuid=str(uuid.uuid4()),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(model_client)
        await session.commit()
        await session.refresh(model_client)
        return model_client


@pytest_asyncio.fixture
async def sample_model_client_minimal(sqlite_db):
    """Create a minimal model client for testing edge cases"""
    async with await sqlite_db.get_session() as session:
        model_client = ModelClientTable(
            id=2,
            label="minimal-model",
            provider="test-provider",  # Required field
            client_uuid=str(uuid.uuid4()),
            is_active=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        session.add(model_client)
        await session.commit()
        await session.refresh(model_client)
        return model_client


class TestLLMModelToComponentInfo:
    """Test cases for LLMModel.to_component_info method"""
    
    @pytest.mark.asyncio
    async def test_to_component_info_full_data(self, llm_model: LLMModel, sample_model_client):
        """Test to_component_info with complete model client data"""
        config = await llm_model.to_component_info(sample_model_client)
        
        assert isinstance(config, ModelClientConfig)
        assert config.type == ComponentType.LLM
        assert config.label == "deepseek-chat_DeepSeek"
        assert config.model_name == "deepseek-chat"
        assert config.base_url == "https://api.deepseek.com/v1"
        assert config.family == "deepseek"
        assert config.api_key_type == "DEEPSEEK_API_KEY"
        assert config.stream is True

    @pytest.mark.asyncio
    async def test_to_component_info_minimal_data(self, llm_model: LLMModel, sample_model_client_minimal):
        """Test to_component_info with minimal model client data"""
        config = await llm_model.to_component_info(sample_model_client_minimal)
        
        assert isinstance(config, ModelClientConfig)
        assert config.type == ComponentType.LLM
        assert config.label == "minimal-model"
        assert config.model_name == ""  # Default for None
        assert config.base_url == ""  # Default for None
        assert config.family == "unknown"  # Default when model_info is None
        assert config.api_key_type == ""  # Default when config is None
        assert config.stream is True  # Default when config is None

    @pytest.mark.asyncio
    async def test_to_component_info_empty_model_info(self, llm_model: LLMModel, sqlite_db):
        """Test to_component_info with empty model_info"""
        async with await sqlite_db.get_session() as session:
            model_client = ModelClientTable(
                id=3,
                label="empty-info-model",
                model_name="test-model",
                base_url="https://api.test.com",
                provider="test-provider",  # Required field
                model_info={},  # Empty dict
                config={"stream": False},
                api_key_type="TEST_KEY",
                client_uuid=str(uuid.uuid4()),
                is_active=True
            )
            session.add(model_client)
            await session.commit()
            await session.refresh(model_client)
        
        config = await llm_model.to_component_info(model_client)
        
        assert config.family == "unknown"  # Default when family key is missing

    @pytest.mark.asyncio
    async def test_to_component_info_empty_config(self, llm_model: LLMModel, sqlite_db):
        """Test to_component_info with empty config"""
        async with await sqlite_db.get_session() as session:
            model_client = ModelClientTable(
                id=4,
                label="empty-config-model",
                model_name="test-model",
                base_url="https://api.test.com",
                provider="test-provider",  # Required field
                model_info={"family": "test-family"},
                config={},  # Empty dict
                client_uuid=str(uuid.uuid4()),
                is_active=True
            )
            session.add(model_client)
            await session.commit()
            await session.refresh(model_client)
        
        config = await llm_model.to_component_info(model_client)
        
        assert config.api_key_type == ""  # Default when api_key_type key is missing
        assert config.stream is True  # Default when stream key is missing


class TestLLMModelUpdateModelClient:
    """Test cases for LLMModel._update_model_client method (internal)"""
    
    @pytest.mark.asyncio
    async def test_update_model_client_success(self, llm_model: LLMModel, sample_model_client):
        """Test successful model client update"""
        result = await llm_model._update_model_client(
            sample_model_client.id,
            label="updated-label",
            model_name="updated-model",
            base_url="https://updated.api.com"
        )
        
        assert result is True
        
        # Verify the update in database
        async with await llm_model.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.id == sample_model_client.id)
            result = await session.execute(stmt)
            updated_model = result.scalar_one()
            
            assert updated_model.label == "updated-label"
            assert updated_model.model_name == "updated-model"
            assert updated_model.base_url == "https://updated.api.com"
            assert updated_model.updated_at is not None

    @pytest.mark.asyncio
    async def test_update_model_client_not_found(self, llm_model: LLMModel):
        """Test update with non-existent model client ID"""
        result = await llm_model._update_model_client(
            999,  # Non-existent ID
            label="test-label"
        )
        
        assert result is False

    @pytest.mark.asyncio
    async def test_update_model_client_json_fields(self, llm_model: LLMModel, sample_model_client):
        """Test updating JSON fields (model_info and config)"""
        new_model_info = {"family": "updated-family", "version": "2.0"}
        new_config = {"stream": False, "temperature": 0.5}
        
        result = await llm_model._update_model_client(
            sample_model_client.id,
            model_info=new_model_info,
            config=new_config
        )
        
        assert result is True
        
        # Verify the JSON updates
        async with await llm_model.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.id == sample_model_client.id)
            result = await session.execute(stmt)
            updated_model = result.scalar_one()
            
            assert updated_model.model_info == new_model_info
            assert updated_model.config == new_config

    @pytest.mark.asyncio
    async def test_update_model_client_partial_update(self, llm_model: LLMModel, sample_model_client):
        """Test partial update - only some fields"""
        original_model_name = sample_model_client.model_name
        
        result = await llm_model._update_model_client(
            sample_model_client.id,
            label="only-label-updated"
        )
        
        assert result is True
        
        # Verify only label was updated, model_name unchanged
        async with await llm_model.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.id == sample_model_client.id)
            result = await session.execute(stmt)
            updated_model = result.scalar_one()
            
            assert updated_model.label == "only-label-updated"
            assert updated_model.model_name == original_model_name

    @pytest.mark.asyncio
    async def test_update_model_client_invalid_field(self, llm_model: LLMModel, sample_model_client):
        """Test update with invalid field name"""
        result = await llm_model._update_model_client(
            sample_model_client.id,
            invalid_field="should-be-ignored",
            label="valid-update"
        )
        
        assert result is True
        
        # Verify valid field was updated, invalid field ignored
        async with await llm_model.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.id == sample_model_client.id)
            result = await session.execute(stmt)
            updated_model = result.scalar_one()
            
            assert updated_model.label == "valid-update"
            assert not hasattr(updated_model, 'invalid_field')

    @pytest.mark.asyncio
    async def test_update_model_client_database_error(self, llm_model: LLMModel, sample_model_client):
        """Test update with database error"""
        # Mock database session to raise an exception
        with patch.object(llm_model.db, 'get_session') as mock_session:
            mock_session.side_effect = Exception("Database connection failed")
            
            with pytest.raises(Exception, match="Database connection failed"):
                await llm_model._update_model_client(
                    sample_model_client.id,
                    label="test-update"
                )


class TestLLMModelUpdateComponentById:
    """Test cases for LLMModel.update_component_by_id method"""
    
    @pytest.mark.asyncio
    async def test_update_component_by_id_success(self, llm_model: LLMModel, sample_model_client):
        """Test successful component update by ID"""
        updated_config = ModelClientConfig(
            type=ComponentType.LLM,
            label="updated-deepseek",
            model_name="deepseek-v2",
            base_url="https://api.deepseek-v2.com/v1",
            family="deepseek-v2",
            api_key_type="DEEPSEEK_V2_KEY",
            stream=False
        )
        
        result = await llm_model.update_component_by_id(sample_model_client.id, updated_config)
        
        assert result is not None
        assert isinstance(result, ModelClientConfig)
        assert result.label == "updated-deepseek"
        assert result.model_name == "deepseek-v2"
        assert result.base_url == "https://api.deepseek-v2.com/v1"
        assert result.family == "deepseek-v2"
        assert result.api_key_type == "DEEPSEEK_V2_KEY"
        assert result.stream is False

    @pytest.mark.asyncio
    async def test_update_component_by_id_not_found(self, llm_model: LLMModel):
        """Test update with non-existent component ID"""
        config = ModelClientConfig(
            type=ComponentType.LLM,
            label="test-label",
            model_name="test-model",
            base_url="https://api.test.com",
            family="test",
            api_key_type="TEST_KEY",
            stream=True
        )
        
        result = await llm_model.update_component_by_id(999, config)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_update_component_by_id_update_fails(self, llm_model: LLMModel, sample_model_client):
        """Test update when internal update method fails"""
        config = ModelClientConfig(
            type=ComponentType.LLM,
            label="test-label",
            model_name="test-model",
            base_url="https://api.test.com",
            family="test",
            api_key_type="TEST_KEY",
            stream=True
        )
        
        # Mock _update_model_client to return False
        with patch.object(llm_model, '_update_model_client', return_value=False):
            result = await llm_model.update_component_by_id(sample_model_client.id, config)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_update_component_by_id_get_component_fails(self, llm_model: LLMModel, sample_model_client):
        """Test update when getting updated component fails"""
        config = ModelClientConfig(
            type=ComponentType.LLM,
            label="test-label",
            model_name="test-model",
            base_url="https://api.test.com",
            family="test",
            api_key_type="TEST_KEY",
            stream=True
        )
        
        # Mock get_component_by_id to return None
        with patch.object(llm_model, 'get_component_by_id', return_value=None):
            result = await llm_model.update_component_by_id(sample_model_client.id, config)
            
            assert result is None

    @pytest.mark.asyncio
    async def test_update_component_by_id_with_minimal_config(self, llm_model: LLMModel, sample_model_client):
        """Test update with minimal ModelClientConfig"""
        minimal_config = ModelClientConfig(
            type=ComponentType.LLM,
            label="minimal-update",
            model_name="",  # Required field
            base_url="",   # Required field
            family="unknown",  # Required field
            api_key_type="",   # Required field
            stream=True        # Required field
        )
        
        result = await llm_model.update_component_by_id(sample_model_client.id, minimal_config)
        
        assert result is not None
        assert result.label == "minimal-update"
        assert result.model_name == ""
        assert result.base_url == ""
        assert result.family == "unknown"
        assert result.api_key_type == ""
        assert result.stream is True


class TestLLMModelInheritedMethods:
    """Test cases for inherited methods from ComponentModel"""
    
    @pytest.mark.asyncio
    async def test_get_all_components_empty(self, llm_model: LLMModel):
        """Test get_all_components with empty database"""
        result = await llm_model.get_all_components()
        
        assert isinstance(result, list)
        assert len(result) == 0

    @pytest.mark.asyncio
    async def test_get_all_components_with_data(self, llm_model: LLMModel, sample_model_client):
        """Test get_all_components with sample data"""
        result = await llm_model.get_all_components()
        
        assert isinstance(result, list)
        assert len(result) == 1
        
        config = result[0]
        assert isinstance(config, ModelClientConfig)
        assert config.label == "deepseek-chat_DeepSeek"
        assert config.model_name == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_get_all_components_filter_inactive(self, llm_model: LLMModel, sqlite_db, sample_model_client):
        """Test get_all_components filters inactive models"""
        # Create an inactive model client
        async with await sqlite_db.get_session() as session:
            inactive_model = ModelClientTable(
                id=10,
                label="inactive-model",
                model_name="inactive",
                provider="test-provider",  # Required field
                client_uuid=str(uuid.uuid4()),
                is_active=False  # Inactive
            )
            session.add(inactive_model)
            await session.commit()
        
        # Should not include inactive model by default
        result = await llm_model.get_all_components(filter_active=True)
        assert len(result) == 1
        assert result[0].label == "deepseek-chat_DeepSeek"
        
        # Should include inactive model when filter is disabled
        result = await llm_model.get_all_components(filter_active=False)
        assert len(result) == 2
        labels = [r.label for r in result]
        assert "inactive-model" in labels
        assert "deepseek-chat_DeepSeek" in labels

    @pytest.mark.asyncio
    async def test_get_component_by_id_success(self, llm_model: LLMModel, sample_model_client):
        """Test get_component_by_id with existing component"""
        result = await llm_model.get_component_by_id(sample_model_client.id)
        
        assert result is not None
        assert isinstance(result, ModelClientConfig)
        assert result.label == "deepseek-chat_DeepSeek"

    @pytest.mark.asyncio
    async def test_get_component_by_id_not_found(self, llm_model: LLMModel):
        """Test get_component_by_id with non-existent ID"""
        result = await llm_model.get_component_by_id(999)
        
        assert result is None

    @pytest.mark.asyncio
    async def test_get_component_by_name_success(self, llm_model: LLMModel, sample_model_client):
        """Test get_component_by_name with existing component"""
        result = await llm_model.get_component_by_name("deepseek-chat_DeepSeek")
        
        assert result is not None
        assert isinstance(result, ModelClientConfig)
        assert result.label == "deepseek-chat_DeepSeek"

    @pytest.mark.asyncio
    async def test_get_component_by_name_not_found(self, llm_model: LLMModel):
        """Test get_component_by_name with non-existent name"""
        result = await llm_model.get_component_by_name("non-existent-model")
        
        assert result is None


class TestLLMModelErrorHandling:
    """Test cases for error handling and edge cases"""
    
    @pytest.mark.asyncio
    async def test_to_component_info_database_error(self, llm_model: LLMModel):
        """Test to_component_info with database connection error"""
        # Create a mock model client that would cause issues
        mock_model = ModelClientTable(
            id=1,
            label="test-model",
            client_uuid=str(uuid.uuid4())
        )
        
        # This should not raise an exception, just return the config
        result = await llm_model.to_component_info(mock_model)
        assert isinstance(result, ModelClientConfig)

    @pytest.mark.asyncio
    async def test_update_model_client_rollback_on_error(self, llm_model: LLMModel, sample_model_client):
        """Test that database rollback happens on error during update"""
        original_label = sample_model_client.label
        
        # Mock session.commit to raise an exception
        with patch.object(llm_model.db, 'get_session') as mock_get_session:
            mock_session = AsyncMock()
            mock_get_session.return_value.__aenter__.return_value = mock_session
            
            # Make commit raise an exception
            mock_session.commit.side_effect = Exception("Commit failed")
            
            result = await llm_model._update_model_client(
                sample_model_client.id,
                label="should-not-be-saved"
            )
            
            assert result is False
            # Verify rollback was called
            mock_session.rollback.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_component_by_id_none_config(self, llm_model: LLMModel, sample_model_client):
        """Test update_component_by_id with None config"""
        # This should handle gracefully or raise appropriate error
        with pytest.raises((AttributeError, TypeError)):
            await llm_model.update_component_by_id(sample_model_client.id, None)

    @pytest.mark.asyncio
    async def test_model_client_with_null_values(self, llm_model: LLMModel, sqlite_db):
        """Test handling of model client with NULL database values"""
        async with await sqlite_db.get_session() as session:
            model_client = ModelClientTable(
                id=20,
                label="null-values-model",
                provider="test-provider",  # Required field
                model_name=None,  # NULL value
                base_url=None,   # NULL value
                model_info=None, # NULL value
                config=None,     # NULL value
                client_uuid=str(uuid.uuid4()),
                is_active=True
            )
            session.add(model_client)
            await session.commit()
            await session.refresh(model_client)
        
        config = await llm_model.to_component_info(model_client)
        
        # Should handle NULL values gracefully with defaults
        assert config.model_name == ""
        assert config.base_url == ""
        assert config.family == "unknown"
        assert config.api_key_type == ""
        assert config.stream is True

    @pytest.mark.asyncio
    async def test_concurrent_updates(self, llm_model: LLMModel, sample_model_client):
        """Test handling of concurrent updates to the same model client"""
        import asyncio
        
        async def update_label(new_label):
            return await llm_model._update_model_client(
                sample_model_client.id,
                label=new_label
            )
        
        # Attempt concurrent updates
        tasks = [
            update_label("concurrent-1"),
            update_label("concurrent-2"),
            update_label("concurrent-3")
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # At least one should succeed, others may succeed or fail
        success_count = sum(1 for r in results if r is True)
        assert success_count >= 1
        
        # Final state should be one of the attempted updates
        async with await llm_model.db.get_session() as session:
            stmt = select(ModelClientTable).where(ModelClientTable.id == sample_model_client.id)
            result = await session.execute(stmt)
            final_model = result.scalar_one()
            
            assert final_model.label in ["concurrent-1", "concurrent-2", "concurrent-3"]


if __name__ == "__main__":
    pytest.main([__file__])