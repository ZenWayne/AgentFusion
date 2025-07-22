"""
Test cases for UserModel.authenticate_user method.

This module comprehensively tests the authenticate_user method including:
- Successful authentication scenarios
- Various failure scenarios (wrong password, locked account, etc.)
- Security features (account locking, activity logging)
- Edge cases and error handling
"""

import pytest
import pytest_asyncio
import uuid
import bcrypt
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from unittest.mock import patch

from sqlalchemy import text, select

# Import the classes we need to test
from data_layer.models.user_model import UserModel
from data_layer.models.tables.user_table import UserTable
from data_layer.models.tables.user_activity_logs_table import UserActivityLogsTable
from test_utils import SQLiteDBDataLayer


@pytest_asyncio.fixture
async def sqlite_db():
    """Create a SQLite database for testing"""
    db = SQLiteDBDataLayer()
    await db.connect()
    yield db
    await db.cleanup()


@pytest_asyncio.fixture
async def user_model(sqlite_db):
    """Create UserModel instance with test database"""
    return UserModel(sqlite_db)


@pytest_asyncio.fixture
async def sample_user(sqlite_db):
    """Create a sample user for testing"""
    async with await sqlite_db.get_session() as session:
        # Hash a test password
        password_hash = bcrypt.hashpw("testpass123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user = UserTable(
            id=1,
            user_uuid=str(uuid.uuid4()),
            username="testuser",
            identifier="testuser",
            email="test@example.com",
            password_hash=password_hash,
            role="user",
            first_name="Test",
            last_name="User",
            is_active=True,
            is_verified=True,
            failed_login_attempts=0,
            locked_until=None,
            last_login=None,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            user_metadata={}
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def locked_user(sqlite_db):
    """Create a locked user for testing"""
    async with await sqlite_db.get_session() as session:
        password_hash = bcrypt.hashpw("testpass123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user = UserTable(
            id=2,
            user_uuid=str(uuid.uuid4()),
            username="lockeduser",
            identifier="lockeduser",
            email="locked@example.com",
            password_hash=password_hash,
            role="user",
            is_active=True,
            is_verified=True,
            failed_login_attempts=5,
            locked_until=datetime.utcnow() + timedelta(minutes=30),
            user_metadata={}
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


@pytest_asyncio.fixture
async def inactive_user(sqlite_db):
    """Create an inactive user for testing"""
    async with await sqlite_db.get_session() as session:
        password_hash = bcrypt.hashpw("testpass123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        user = UserTable(
            id=3,
            user_uuid=str(uuid.uuid4()),
            username="inactiveuser",
            identifier="inactiveuser",
            email="inactive@example.com",
            password_hash=password_hash,
            role="user",
            is_active=False,
            is_verified=True,
            failed_login_attempts=0,
            user_metadata={}
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


class TestUserAuthenticate:
    """Test cases for UserModel.authenticate_user method"""
    
    @pytest.mark.asyncio
    async def test_authenticate_user_success_with_username(self, user_model: UserModel, sample_user):
        """Test successful authentication using username"""
        result = await user_model.authenticate_user("testuser", "testpass123", "127.0.0.1")
        
        assert result is not None
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
        assert result["role"] == "user"
        assert result["is_active"] is True
        assert result["is_verified"] is True
        assert "created_at" in result
        assert "id" in result
        assert "uuid" in result
        
        # Verify that failed login attempts were reset
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            result_user = await session.execute(stmt)
            updated_user = result_user.scalar_one()
            assert updated_user.failed_login_attempts == 0
            assert updated_user.locked_until is None
            assert updated_user.last_login is not None

    @pytest.mark.asyncio
    async def test_authenticate_user_success_with_email(self, user_model: UserModel, sample_user):
        """Test successful authentication using email"""
        result = await user_model.authenticate_user("test@example.com", "testpass123", "127.0.0.1")
        
        assert result is not None
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_authenticate_user_invalid_username(self, user_model: UserModel):
        """Test authentication with non-existent username"""
        result = await user_model.authenticate_user("nonexistent", "testpass123", "127.0.0.1")
        
        assert result is None
        
        # Verify activity was logged
        async with await user_model.db.get_session() as session:
            stmt = select(UserActivityLogsTable).where(
                UserActivityLogsTable.activity_type == 'login_failed'
            ).order_by(UserActivityLogsTable.created_at.desc()).limit(1)
            log_result = await session.execute(stmt)
            log_entry = log_result.scalar_one_or_none()
            assert log_entry is not None
            assert "user_not_found" in log_entry.action_details

    @pytest.mark.asyncio
    async def test_authenticate_user_invalid_password(self, user_model: UserModel, sample_user):
        """Test authentication with wrong password"""
        result = await user_model.authenticate_user("testuser", "wrongpassword", "127.0.0.1")
        
        assert result is None
        
        # Verify failed login attempts were incremented
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            result_user = await session.execute(stmt)
            updated_user = result_user.scalar_one()
            assert updated_user.failed_login_attempts == 1
            
        # Verify activity was logged
        async with await user_model.db.get_session() as session:
            stmt = select(UserActivityLogsTable).where(
                UserActivityLogsTable.activity_type == 'login_failed'
            ).order_by(UserActivityLogsTable.created_at.desc()).limit(1)
            log_result = await session.execute(stmt)
            log_entry = log_result.scalar_one_or_none()
            assert log_entry is not None
            assert "invalid_password" in log_entry.action_details

    @pytest.mark.asyncio
    async def test_authenticate_user_locked_account(self, user_model: UserModel, locked_user):
        """Test authentication with locked account"""
        result = await user_model.authenticate_user("lockeduser", "testpass123", "127.0.0.1")
        
        assert result is None
        
        # Verify activity was logged
        async with await user_model.db.get_session() as session:
            stmt = select(UserActivityLogsTable).where(
                UserActivityLogsTable.activity_type == 'login_failed'
            ).order_by(UserActivityLogsTable.created_at.desc()).limit(1)
            log_result = await session.execute(stmt)
            log_entry = log_result.scalar_one_or_none()
            assert log_entry is not None
            assert "account_locked" in log_entry.action_details

    @pytest.mark.asyncio
    async def test_authenticate_user_inactive_account(self, user_model: UserModel, inactive_user):
        """Test authentication with inactive account"""
        result = await user_model.authenticate_user("inactiveuser", "testpass123", "127.0.0.1")
        
        assert result is None
        
        # Verify activity was logged
        async with await user_model.db.get_session() as session:
            stmt = select(UserActivityLogsTable).where(
                UserActivityLogsTable.activity_type == 'login_failed'
            ).order_by(UserActivityLogsTable.created_at.desc()).limit(1)
            log_result = await session.execute(stmt)
            log_entry = log_result.scalar_one_or_none()
            assert log_entry is not None
            assert "account_inactive" in log_entry.action_details

    @pytest.mark.asyncio
    async def test_authenticate_user_account_locking_mechanism(self, user_model: UserModel, sample_user):
        """Test that account gets locked after multiple failed attempts"""
        # Make 4 failed attempts (not enough to lock)
        for i in range(4):
            result = await user_model.authenticate_user("testuser", "wrongpassword", "127.0.0.1")
            assert result is None
        
        # Verify account is not locked yet
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            result_user = await session.execute(stmt)
            updated_user = result_user.scalar_one()
            assert updated_user.failed_login_attempts == 4
            assert updated_user.locked_until is None
        
        # Make 5th failed attempt (should trigger lock)
        result = await user_model.authenticate_user("testuser", "wrongpassword", "127.0.0.1")
        assert result is None
        
        # Verify account is now locked
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            result_user = await session.execute(stmt)
            updated_user = result_user.scalar_one()
            assert updated_user.failed_login_attempts == 5
            assert updated_user.locked_until is not None
            assert updated_user.locked_until > datetime.utcnow()

    @pytest.mark.asyncio
    async def test_authenticate_user_expired_lock(self, user_model: UserModel, sqlite_db):
        """Test authentication with expired account lock"""
        # Create a user with expired lock
        async with await sqlite_db.get_session() as session:
            password_hash = bcrypt.hashpw("testpass123".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            expired_lock_user = UserTable(
                id=4,
                user_uuid=str(uuid.uuid4()),
                username="expiredlockuser",
                identifier="expiredlockuser",
                email="expired@example.com",
                password_hash=password_hash,
                role="user",
                is_active=True,
                is_verified=True,
                failed_login_attempts=5,
                locked_until=datetime.utcnow() - timedelta(minutes=1),  # Expired lock
                user_metadata={}
            )
            session.add(expired_lock_user)
            await session.commit()
        
        # Should be able to authenticate
        result = await user_model.authenticate_user("expiredlockuser", "testpass123", "127.0.0.1")
        
        assert result is not None
        assert result["username"] == "expiredlockuser"

    @pytest.mark.asyncio
    async def test_authenticate_user_no_ip_address(self, user_model: UserModel, sample_user):
        """Test authentication without IP address (None)"""
        result = await user_model.authenticate_user("testuser", "testpass123")
        
        assert result is not None
        assert result["username"] == "testuser"

    @pytest.mark.asyncio
    async def test_authenticate_user_empty_password(self, user_model: UserModel, sample_user):
        """Test authentication with empty password"""
        result = await user_model.authenticate_user("testuser", "", "127.0.0.1")
        
        assert result is None

    @pytest.mark.asyncio
    async def test_authenticate_user_none_password(self, user_model: UserModel, sample_user):
        """Test authentication with None password"""
        with pytest.raises(AttributeError):
            # Should raise error when trying to encode None
            await user_model.authenticate_user("testuser", None, "127.0.0.1")

    @pytest.mark.asyncio
    async def test_authenticate_user_database_error(self, user_model: UserModel, sample_user):
        """Test authentication with database error"""
        # Mock the session to raise an exception
        with patch.object(user_model.db, 'get_session') as mock_session:
            mock_session.side_effect = Exception("Database connection failed")
            
            with pytest.raises(Exception, match="Database connection failed"):
                await user_model.authenticate_user("testuser", "testpass123", "127.0.0.1")

    @pytest.mark.asyncio
    async def test_authenticate_user_successful_login_logging(self, user_model: UserModel, sample_user):
        """Test that successful login is properly logged"""
        result = await user_model.authenticate_user("testuser", "testpass123", "192.168.1.100")
        
        assert result is not None
        
        # Verify success activity was logged
        async with await user_model.db.get_session() as session:
            stmt = select(UserActivityLogsTable).where(
                UserActivityLogsTable.activity_type == 'login_success'
            ).order_by(UserActivityLogsTable.created_at.desc()).limit(1)
            log_result = await session.execute(stmt)
            log_entry = log_result.scalar_one_or_none()
            assert log_entry is not None
            assert log_entry.user_id == sample_user.id
            assert log_entry.ip_address == "192.168.1.100"
            assert "testuser" in log_entry.action_details

    @pytest.mark.asyncio
    async def test_authenticate_user_password_reset_after_success(self, user_model: UserModel, sample_user):
        """Test that failed login attempts are reset after successful login"""
        # First, create some failed attempts
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            result_user = await session.execute(stmt)
            user_record = result_user.scalar_one()
            user_record.failed_login_attempts = 3
            await session.commit()
        
        # Now authenticate successfully
        result = await user_model.authenticate_user("testuser", "testpass123", "127.0.0.1")
        
        assert result is not None
        
        # Verify failed attempts were reset
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            result_user = await session.execute(stmt)
            updated_user = result_user.scalar_one()
            assert updated_user.failed_login_attempts == 0
            assert updated_user.locked_until is None

    @pytest.mark.asyncio
    async def test_authenticate_user_with_special_characters(self, user_model: UserModel, sqlite_db):
        """Test authentication with special characters in username and password"""
        # Create user with special characters
        async with await sqlite_db.get_session() as session:
            password_hash = bcrypt.hashpw("pässwörd!@#$%".encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
            
            special_user = UserTable(
                id=5,
                user_uuid=str(uuid.uuid4()),
                username="üser@domain.com",
                identifier="üser@domain.com",
                email="üser@domain.com",
                password_hash=password_hash,
                role="user",
                is_active=True,
                is_verified=True,
                failed_login_attempts=0,
                user_metadata={}
            )
            session.add(special_user)
            await session.commit()
        
        # Should authenticate successfully
        result = await user_model.authenticate_user("üser@domain.com", "pässwörd!@#$%", "127.0.0.1")
        
        assert result is not None
        assert result["username"] == "üser@domain.com"


if __name__ == "__main__":
    pytest.main([__file__])