"""
Comprehensive test cases for UserModel class.

This module tests all functionality of the UserModel class including:
- User authentication and password handling
- User creation and management 
- User activity logging
- UUID/ID conversion helper methods
- Data model conversions
- Security features (account locking, activity logging)
- Edge cases and error handling
"""

import pytest
import pytest_asyncio
import uuid
import bcrypt
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional
from unittest.mock import patch, AsyncMock
from chainlit.user import User

from sqlalchemy import text, select

# Import the classes we need to test
from data_layer.models.user_model import UserModel, UserInfo, PersistedUser, AgentFusionUser
from data_layer.models.tables import UserTable, UserActivityLogsTable
from ...test_utils import SQLiteDBDataLayer


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
        user_uuid = str(uuid.uuid4())
        
        user = UserTable(
            id=1,
            user_uuid=user_uuid,
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
            user_metadata={"test_key": "test_value"}
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
            assert log_entry.action_details["reason"] == "user_not_found"

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
            assert log_entry.action_details["reason"] == "invalid_password"

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
            assert log_entry.action_details["reason"] == "account_locked"

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
            assert log_entry.action_details["reason"] == "account_inactive"

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
            assert log_entry.action_details["username"] == "testuser"

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


class TestUserModelDataConversion:
    """Test cases for UserModel data conversion methods"""
    
    @pytest.mark.asyncio
    async def test_model_to_info(self, user_model: UserModel, sample_user):
        """Test _model_to_info conversion"""
        user_info = user_model._model_to_info(sample_user)
        
        assert isinstance(user_info, UserInfo)
        assert user_info.id == sample_user.id
        assert user_info.user_uuid == str(sample_user.user_uuid)
        assert user_info.username == sample_user.username
        assert user_info.identifier == sample_user.identifier
        assert user_info.email == sample_user.email
        assert user_info.role == sample_user.role
        assert user_info.first_name == sample_user.first_name
        assert user_info.last_name == sample_user.last_name
        assert user_info.is_active == sample_user.is_active
        assert user_info.is_verified == sample_user.is_verified
        assert user_info.failed_login_attempts == sample_user.failed_login_attempts

    @pytest.mark.asyncio
    async def test_model_to_info_none_metadata(self, user_model: UserModel, sqlite_db):
        """Test _model_to_info with None user_metadata"""
        async with await sqlite_db.get_session() as session:
            user = UserTable(
                id=10,
                user_uuid=str(uuid.uuid4()),
                username="nometadata",
                identifier="nometadata",
                email="nometadata@example.com",
                password_hash="hash",
                role="user",
                is_active=True,
                is_verified=True,
                failed_login_attempts=0,
                user_metadata=None  # None metadata
            )
            session.add(user)
            await session.commit()
            await session.refresh(user)
        
        user_info = user_model._model_to_info(user)
        assert user_info.user_metadata == {}


class TestUserModelPasswordHandling:
    """Test cases for password hashing and verification"""
    
    @pytest.mark.asyncio
    async def test_hash_password(self, user_model: UserModel):
        """Test password hashing"""
        password = "test_password123"
        hashed = await user_model.hash_password(password)
        
        assert hashed != password
        assert hashed.startswith("$2b$")
        assert len(hashed) >= 50  # bcrypt hashes are typically ~60 chars

    @pytest.mark.asyncio
    async def test_hash_password_special_chars(self, user_model: UserModel):
        """Test password hashing with special characters"""
        password = "pässwörd!@#$%^&*()"
        hashed = await user_model.hash_password(password)
        
        assert hashed != password
        assert hashed.startswith("$2b$")

    @pytest.mark.asyncio
    async def test_hash_password_empty(self, user_model: UserModel):
        """Test password hashing with empty string"""
        password = ""
        hashed = await user_model.hash_password(password)
        
        assert hashed != password
        assert hashed.startswith("$2b$")

    def test_verify_password_correct(self, user_model: UserModel):
        """Test password verification with correct password"""
        password = "test_password123"
        # Create a hash manually to test verification
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        assert user_model.verify_password(password, hashed) is True

    def test_verify_password_incorrect(self, user_model: UserModel):
        """Test password verification with incorrect password"""
        password = "test_password123"
        wrong_password = "wrong_password"
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        assert user_model.verify_password(wrong_password, hashed) is False

    def test_verify_password_empty(self, user_model: UserModel):
        """Test password verification with empty password"""
        password = "test_password123"
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
        
        assert user_model.verify_password("", hashed) is False


class TestUserModelGetUser:
    """Test cases for get_user method"""
    
    @pytest.mark.asyncio
    async def test_get_user_exists(self, user_model: UserModel, sample_user):
        """Test get_user with existing user"""
        user = await user_model.get_user("testuser")
        
        assert user is not None
        assert isinstance(user, PersistedUser)
        assert user.id == sample_user.id
        assert user.identifier == "testuser"
        assert user.uuid == str(sample_user.user_uuid)
        assert user.createdAt == sample_user.created_at.isoformat()

    @pytest.mark.asyncio
    async def test_get_user_not_exists(self, user_model: UserModel):
        """Test get_user with non-existent user"""
        user = await user_model.get_user("nonexistent")
        assert user is None

    @pytest.mark.asyncio
    async def test_get_user_none_metadata(self, user_model: UserModel, sqlite_db):
        """Test get_user with user having None metadata"""
        async with await sqlite_db.get_session() as session:
            user = UserTable(
                id=11,
                user_uuid=str(uuid.uuid4()),
                username="nometauser",
                identifier="nometauser",
                email="nometa@example.com",
                role="user",
                is_active=True,
                user_metadata=None
            )
            session.add(user)
            await session.commit()

        result = await user_model.get_user("nometauser")
        assert result is not None
        assert result.metadata == {}


class TestUserModelUpdateUser:
    """Test cases for update_user method"""
    
    @pytest.mark.asyncio
    async def test_update_user_success(self, user_model: UserModel, sample_user):
        """Test successful user update"""
        persisted_user = PersistedUser(
            id=sample_user.id,
            uuid=str(sample_user.user_uuid),
            identifier=sample_user.identifier,
            createdAt=sample_user.created_at.isoformat()
        )
        
        result = await user_model.update_user(persisted_user)
        assert result == persisted_user
        
        # Verify last_login was updated
        async with await user_model.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.id == sample_user.id)
            updated_user = await session.execute(stmt)
            user_record = updated_user.scalar_one()
            assert user_record.last_login is not None

    @pytest.mark.asyncio
    async def test_update_user_not_found(self, user_model: UserModel):
        """Test update user with non-existent user"""
        non_existent_user = PersistedUser(
            id=999,
            uuid=str(uuid.uuid4()),
            identifier="nonexistent",
            createdAt=datetime.now().isoformat()
        )
        
        result = await user_model.update_user(non_existent_user)
        assert result is None

    @pytest.mark.asyncio
    async def test_update_user_database_error(self, user_model: UserModel, sample_user):
        """Test update user with database error"""
        persisted_user = PersistedUser(
            id=sample_user.id,
            uuid=str(sample_user.user_uuid),
            identifier=sample_user.identifier,
            createdAt=sample_user.created_at.isoformat()
        )
        
        with patch.object(user_model.db, 'get_session') as mock_session:
            mock_session.side_effect = Exception("Database error")
            
            with pytest.raises(Exception, match="Database error"):
                await user_model.update_user(persisted_user)


class TestUserModelCreateUser:
    """Test cases for create_user method"""
    
    @pytest.mark.asyncio
    async def test_create_user_new(self, user_model: UserModel):
        """Test creating a new user"""
        user_id = 100
        user_uuid = str(uuid.uuid4())
        
        chainlit_user = User(
            identifier="newuser",
            metadata={
                "email": "newuser@example.com",
                "role": "admin",
                "first_name": "New",
                "last_name": "User"
            }
        )
        # Set the id manually since User class may not accept it in constructor
        chainlit_user.id = user_id
        chainlit_user.uuid = user_uuid
        
        result = await user_model.create_user(chainlit_user)
        
        assert result is not None
        assert isinstance(result, AgentFusionUser)
        assert result.id == user_id
        assert result.identifier == "newuser"
        assert result.email == "newuser@example.com"
        assert result.role == "admin"
        assert result.first_name == "New"
        assert result.last_name == "User"

    @pytest.mark.asyncio
    async def test_create_user_existing(self, user_model: UserModel, sample_user):
        """Test creating user when user already exists"""
        chainlit_user = User(
            identifier=sample_user.identifier,
            metadata={}
        )
        chainlit_user.id = sample_user.id
        chainlit_user.uuid = str(sample_user.user_uuid)
        
        result = await user_model.create_user(chainlit_user)
        assert result is not None
        # Should return existing user, not create new one

    @pytest.mark.asyncio
    async def test_create_user_no_email_metadata(self, user_model: UserModel):
        """Test creating user without email in metadata"""
        user_id = 101
        
        chainlit_user = User(
            identifier="nomail",
            metadata={
                "role": "user",
                "first_name": "No",
                "last_name": "Mail"
            }
        )
        chainlit_user.id = user_id
        chainlit_user.uuid = str(uuid.uuid4())
        
        result = await user_model.create_user(chainlit_user)
        
        assert result is not None
        assert result.email == "nomail@example.com"  # Default email

    @pytest.mark.asyncio
    async def test_create_user_nested_metadata(self, user_model: UserModel):
        """Test creating user with nested metadata structure"""
        user_id = 102
        
        chainlit_user = User(
            identifier="nested",
            metadata={
                "metadata": {
                    "email": "nested@example.com"
                },
                "role": "user"
            }
        )
        chainlit_user.id = user_id
        chainlit_user.uuid = str(uuid.uuid4())
        
        result = await user_model.create_user(chainlit_user)
        
        assert result is not None
        assert result.email == "nested@example.com"

    @pytest.mark.asyncio
    async def test_create_user_database_error(self, user_model: UserModel):
        """Test create user with database error"""
        chainlit_user = User(
            identifier="erroruser",
            metadata={"email": "error@example.com"}
        )
        chainlit_user.id = 103
        
        with patch.object(user_model.db, 'get_session') as mock_session:
            mock_session.side_effect = Exception("Database error")
            
            with pytest.raises(Exception, match="Database error"):
                await user_model.create_user(chainlit_user)


class TestUserModelUUIDHelpers:
    """Test cases for UUID/ID conversion helper methods"""
    
    @pytest.mark.asyncio
    async def test_get_user_internal_id_success(self, user_model: UserModel, sample_user):
        """Test getting internal ID from UUID"""
        internal_id = await user_model.get_user_internal_id(str(sample_user.user_uuid))
        assert internal_id == sample_user.id

    @pytest.mark.asyncio
    async def test_get_user_internal_id_not_found(self, user_model: UserModel):
        """Test getting internal ID for non-existent UUID"""
        internal_id = await user_model.get_user_internal_id(str(uuid.uuid4()))
        assert internal_id is None

    @pytest.mark.asyncio
    async def test_get_user_uuid_success(self, user_model: UserModel, sample_user):
        """Test getting UUID from internal ID"""
        user_uuid = await user_model.get_user_uuid(sample_user.id)
        assert user_uuid == str(sample_user.user_uuid)

    @pytest.mark.asyncio
    async def test_get_user_uuid_not_found(self, user_model: UserModel):
        """Test getting UUID for non-existent internal ID"""
        user_uuid = await user_model.get_user_uuid(999)
        assert user_uuid is None

    @pytest.mark.asyncio
    async def test_get_user_by_uuid_success(self, user_model: UserModel, sample_user):
        """Test getting user details by UUID"""
        user_details = await user_model.get_user_by_uuid(str(sample_user.user_uuid))
        
        assert user_details is not None
        assert user_details['id'] == sample_user.id
        assert user_details['user_uuid'] == str(sample_user.user_uuid)
        assert user_details['username'] == sample_user.username
        assert user_details['email'] == sample_user.email
        assert user_details['role'] == sample_user.role
        assert user_details['is_active'] == sample_user.is_active
        assert user_details['is_verified'] == sample_user.is_verified

    @pytest.mark.asyncio
    async def test_get_user_by_uuid_not_found(self, user_model: UserModel):
        """Test getting user details for non-existent UUID"""
        user_details = await user_model.get_user_by_uuid(str(uuid.uuid4()))
        assert user_details is None

    @pytest.mark.asyncio
    async def test_get_user_by_uuid_inactive_user(self, user_model: UserModel, sqlite_db):
        """Test getting inactive user by UUID (should return None)"""
        async with await sqlite_db.get_session() as session:
            inactive_uuid = str(uuid.uuid4())
            user = UserTable(
                id=12,
                user_uuid=inactive_uuid,
                username="inactive",
                identifier="inactive",
                email="inactive@example.com",
                role="user",
                is_active=False,  # Inactive
                user_metadata={}
            )
            session.add(user)
            await session.commit()

        user_details = await user_model.get_user_by_uuid(inactive_uuid)
        assert user_details is None  # Should not return inactive users


class TestAgentFusionUser:
    """Test cases for AgentFusionUser class"""
    
    def test_agent_fusion_user_creation_full(self):
        """Test AgentFusionUser creation with all parameters"""
        user = AgentFusionUser(
            id=1,
            uuid="test-uuid",
            identifier="testuser",
            display_name="Test User",
            email="test@example.com",
            role="admin",
            first_name="Test",
            last_name="User",
            custom_field="custom_value"
        )
        
        assert user.id == 1
        assert user.uuid == "test-uuid"
        assert user.identifier == "testuser"
        assert user.display_name == "Test User"
        assert user.email == "test@example.com"
        assert user.role == "admin"
        assert user.first_name == "Test"
        assert user.last_name == "User"

    def test_agent_fusion_user_defaults(self):
        """Test AgentFusionUser creation with default values"""
        user = AgentFusionUser(
            id=1,
            identifier="testuser"
        )
        
        assert user.id == 1
        assert user.identifier == "testuser"
        assert user.role == "user"  # Default role
        assert user.email is None
        assert user.first_name is None
        assert user.last_name is None

    def test_agent_fusion_user_properties(self):
        """Test AgentFusionUser properties access"""
        user = AgentFusionUser(
            id=1,
            identifier="testuser",
            email="test@example.com",
            role="admin",
            first_name="Test",
            last_name="User",
            password="secret"
        )
        
        assert user.email == "test@example.com"
        assert user.role == "admin"
        assert user.first_name == "Test"
        assert user.last_name == "User"
        assert user.password == "secret"

    def test_agent_fusion_user_none_values_filtered(self):
        """Test that None values are filtered from metadata"""
        user = AgentFusionUser(
            id=1,
            identifier="testuser",
            email=None,
            role="user",
            first_name=None,
            last_name="User"
        )
        
        assert user.email is None
        assert user.role == "user"
        assert user.first_name is None
        assert user.last_name == "User"

    def test_agent_fusion_user_display_name_override(self):
        """Test display_name override functionality"""
        user = AgentFusionUser(
            id=1,
            identifier="testuser",
            display_name="Custom Display Name",
            first_name="Test"
        )
        
        assert user.display_name == "Custom Display Name"

    def test_agent_fusion_user_created_at_default(self):
        """Test createdAt default value"""
        user = AgentFusionUser(
            id=1,
            identifier="testuser"
        )
        
        # Should have a createdAt value
        assert user.createdAt is not None
        # Should be a valid ISO format
        datetime.fromisoformat(user.createdAt.replace('Z', '+00:00'))


class TestUserModelQueryExamples:
    """Example test cases showing how to use sqlite_db for query testing"""
    
    @pytest.mark.asyncio
    async def test_raw_sql_query(self, sqlite_db, sample_user):
        """Example: Test using raw SQL queries"""
        # Test execute_query method (returns list of dicts)
        result = await sqlite_db.execute_query(
            "SELECT * FROM User WHERE username = :username", 
            {"username": "testuser"}
        )
        
        assert len(result) == 1
        assert result[0]["username"] == "testuser"
        assert result[0]["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_raw_sql_single_query(self, sqlite_db, sample_user):
        """Example: Test using execute_single_query method"""
        # Test execute_single_query method (returns single dict or None)
        result = await sqlite_db.execute_single_query(
            "SELECT id, username, email FROM User WHERE id = :user_id", 
            {"user_id": sample_user.id}
        )
        
        assert result is not None
        assert result["username"] == "testuser"
        assert result["email"] == "test@example.com"
    
    @pytest.mark.asyncio
    async def test_raw_sql_command(self, sqlite_db, sample_user):
        """Example: Test using execute_command method for updates"""
        # Test execute_command method (returns affected row count)
        result = await sqlite_db.execute_command(
            "UPDATE User SET email = :email WHERE id = :user_id", 
            {"email": "newemail@example.com", "user_id": sample_user.id}
        )
        
        assert result == "1"  # One row affected
        
        # Verify the update
        updated = await sqlite_db.execute_single_query(
            "SELECT email FROM User WHERE id = :user_id", 
            {"user_id": sample_user.id}
        )
        assert updated["email"] == "newemail@example.com"
    
    @pytest.mark.asyncio
    async def test_orm_session_query(self, sqlite_db, sample_user):
        """Example: Test using ORM session directly"""
        async with await sqlite_db.get_session() as session:
            # Use SQLAlchemy ORM for queries
            stmt = select(UserTable).where(UserTable.username == "testuser")
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            assert user is not None
            assert user.username == "testuser"
            assert user.email == "test@example.com"
            assert user.id == sample_user.id
    
    @pytest.mark.asyncio
    async def test_orm_session_create_and_query(self, sqlite_db):
        """Example: Test creating data with ORM and querying it"""
        async with await sqlite_db.get_session() as session:
            # Create a new user using ORM
            new_user = UserTable(
                id=99,
                user_uuid=str(uuid.uuid4()),
                username="ormuser",
                identifier="ormuser",
                email="orm@example.com",
                role="user",
                is_active=True,
                is_verified=False,
                user_metadata={"created_by": "test"}
            )
            session.add(new_user)
            await session.commit()
            await session.refresh(new_user)
            
            # Query it back
            stmt = select(UserTable).where(UserTable.username == "ormuser")
            result = await session.execute(stmt)
            queried_user = result.scalar_one()
            
            assert queried_user.username == "ormuser"
            assert queried_user.email == "orm@example.com"
            assert queried_user.user_metadata["created_by"] == "test"
    
    @pytest.mark.asyncio
    async def test_complex_query_with_joins(self, sqlite_db, sample_user):
        """Example: Test complex queries with joins"""
        # First create some activity logs for the user
        async with await sqlite_db.get_session() as session:
            activity_log = UserActivityLogsTable(
                user_id=sample_user.id,
                activity_type="login_success",
                action_details={"ip": "127.0.0.1"},
                ip_address="127.0.0.1",
                status="success"
            )
            session.add(activity_log)
            await session.commit()
        
        # Now query using raw SQL with joins
        result = await sqlite_db.execute_query("""
            SELECT u.username, u.email, ual.activity_type, ual.status
            FROM User u
            JOIN user_activity_logs ual ON u.id = ual.user_id
            WHERE u.id = :user_id
        """, {"user_id": sample_user.id})
        
        assert len(result) == 1
        assert result[0]["username"] == "testuser"
        assert result[0]["activity_type"] == "login_success"
        assert result[0]["status"] == "success"
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, sqlite_db, sample_user):
        """Example: Test transaction handling and rollback"""
        original_email = sample_user.email
        
        try:
            async with await sqlite_db.get_session() as session:
                # Update user
                stmt = select(UserTable).where(UserTable.id == sample_user.id)
                result = await session.execute(stmt)
                user = result.scalar_one()
                user.email = "rollback@example.com"
                
                # Simulate an error that causes rollback
                raise Exception("Simulated error")
                
        except Exception:
            # Transaction should be rolled back automatically
            pass
        
        # Verify email wasn't changed due to rollback
        result = await sqlite_db.execute_single_query(
            "SELECT email FROM User WHERE id = :user_id", 
            {"user_id": sample_user.id}
        )
        assert result["email"] == original_email


if __name__ == "__main__":
    pytest.main([__file__])