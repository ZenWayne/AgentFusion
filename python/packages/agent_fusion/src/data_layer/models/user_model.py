"""
用户模型

处理用户相关的所有数据库操作
"""

import hashlib
import bcrypt
import secrets
import json
import uuid
from typing import Optional, Dict, Any, List
from datetime import datetime
from chainlit.user import User
from chainlit.logger import logger
from dataclasses import dataclass

from data_layer.models.base_model import BaseModel
from data_layer.models.tables.user_table import UserTable
from data_layer.models.tables.user_activity_logs_table import UserActivityLogsTable

from sqlalchemy import select, insert, update, delete, and_, text
from sqlalchemy.sql import func


@dataclass
class UserInfo:
    """用户信息数据类"""
    id: int
    user_uuid: str
    username: str
    identifier: str
    email: str
    password_hash: Optional[str]
    role: str
    first_name: Optional[str]
    last_name: Optional[str]
    is_active: bool
    is_verified: bool
    failed_login_attempts: int
    locked_until: Optional[datetime]
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime
    user_metadata: Dict[str, Any]


@dataclass
class PersistedUserFields:
    id: int
    uuid: str
    createdAt: str

@dataclass
class PersistedUser(User, PersistedUserFields):
    pass

class AgentFusionUser(PersistedUser):
    """Extended PersistedUser class with additional AgentFusion-specific fields"""
    
    def __init__(self, 
                 id: int,
                 uuid: Optional[str] = None,
                 identifier: str = None,
                 display_name: Optional[str] = None,
                 email: Optional[str] = None,
                 password: Optional[str] = None,
                 role: str = "user",
                 first_name: Optional[str] = None,
                 last_name: Optional[str] = None,
                 createdAt: Optional[str] = None,
                 **kwargs):
        """
        Initialize AgentFusionUser
        
        Args:
            id: User ID (UUID)
            uuid: User UUID (optional, defaults to id)
            identifier: Unique identifier (username)
            display_name: Display name for the user
            email: User email
            password: Plain text password (will be hashed)
            role: User role (user, admin, reviewer, developer)
            first_name: First name
            last_name: Last name
            createdAt: Creation timestamp
            **kwargs: Additional metadata
        """
        # Prepare metadata with all our custom fields
        metadata = {
            "email": email,
            "password": password,  # Will be hashed by data layer
            "role": role,
            "first_name": first_name,
            "last_name": last_name,
            **kwargs
        }
        
        # Remove None values
        metadata = {k: v for k, v in metadata.items() if v is not None}
        
        super().__init__(
            id=id,
            uuid=uuid,
            identifier=identifier or id,
            createdAt=createdAt or datetime.now().isoformat(),
            metadata=metadata
        )
        
        # Override display_name if provided
        if display_name:
            self.display_name = display_name
    
    @property
    def email(self) -> Optional[str]:
        return self.metadata.get("email")
    
    @property
    def role(self) -> str:
        return self.metadata.get("role", "user")
    
    @property
    def first_name(self) -> Optional[str]:
        return self.metadata.get("first_name")
    
    @property
    def last_name(self) -> Optional[str]:
        return self.metadata.get("last_name")
    
    @property
    def password(self) -> Optional[str]:
        return self.metadata.get("password")


class UserModel(BaseModel):
    """用户数据模型"""
    
    def _model_to_info(self, model: UserTable) -> UserInfo:
        """Convert SQLAlchemy model to UserInfo"""
        return UserInfo(
            id=model.id,
            user_uuid=str(model.user_uuid),
            username=model.username,
            identifier=model.identifier,
            email=model.email,
            password_hash=model.password_hash,
            role=model.role,
            first_name=model.first_name,
            last_name=model.last_name,
            is_active=model.is_active,
            is_verified=model.is_verified,
            failed_login_attempts=model.failed_login_attempts,
            locked_until=model.locked_until,
            last_login=model.last_login,
            created_at=model.created_at,
            updated_at=model.updated_at,
            user_metadata=model.user_metadata if model.user_metadata else {}
        )
    
    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        """根据标识符获取用户"""
        async with await self.db.get_session() as session:
            stmt = select(UserTable).where(UserTable.identifier == identifier)
            result = await session.execute(stmt)
            user = result.scalar_one_or_none()
            
            if not user:
                return None

            return PersistedUser(
                id=user.id,
                uuid=str(user.user_uuid),
                identifier=user.identifier,
                createdAt=user.created_at.isoformat(),
                metadata=user.user_metadata if user.user_metadata else {},
            )
    
    async def hash_password(self, password: str) -> str:
        """Hash password using bcrypt"""
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    def verify_password(self, password: str, hashed: str) -> bool:
        """Verify password against hash"""
        return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
    
    async def authenticate_user(self, username: str, password: str, ip_address: str = None) -> Optional[Dict[str, Any]]:
        """
        Authenticate user with database lookup and security checks
        """
        async with await self.db.get_session() as session:
            try:
                # First, check if user exists and get their details
                stmt = select(UserTable).where(
                    (UserTable.username == username) | (UserTable.email == username)
                )
                result = await session.execute(stmt)
                user_record = result.scalar_one_or_none()
                
                if not user_record:
                    # Log failed login attempt for non-existent user
                    await self._log_activity_orm(session, None, "login_failed", details={
                        "reason": "user_not_found",
                        "username": username,
                        "ip_address": ip_address
                    })
                    await session.commit()
                    return None
                
                # Check if account is locked
                if user_record.locked_until and user_record.locked_until > datetime.utcnow():
                    await self._log_activity_orm(session, user_record.id, "login_failed", details={
                        "reason": "account_locked",
                        "username": username,
                        "ip_address": ip_address,
                        "locked_until": user_record.locked_until.isoformat()
                    })
                    await session.commit()
                    return None
                
                # Check if account is active
                if not user_record.is_active:
                    await self._log_activity_orm(session, user_record.id, "login_failed", details={
                        "reason": "account_inactive",
                        "username": username,
                        "ip_address": ip_address
                    })
                    await session.commit()
                    return None
                
                # Verify password
                if not self.verify_password(password, user_record.password_hash):
                    # Record failed login attempt
                    await self._record_failed_login_orm(session, username)
                    await self._log_activity_orm(session, user_record.id, "login_failed", details={
                        "reason": "invalid_password",
                        "username": username,
                        "ip_address": ip_address
                    })
                    await session.commit()
                    return None
                
                # Password is correct - reset failed attempts and update last login
                now = datetime.utcnow()
                user_record.last_login = now
                user_record.failed_login_attempts = 0
                user_record.locked_until = None
                user_record.updated_at = now
                
                # Log successful login
                await self._log_activity_orm(session, user_record.id, "login_success", details={
                    "username": username,
                    "ip_address": ip_address,
                    "last_login": now.isoformat()
                })
                
                await session.commit()
                
                return {
                    "id": user_record.id,
                    "uuid": str(user_record.user_uuid),
                    "username": user_record.username,
                    "email": user_record.email,
                    "role": user_record.role,
                    "is_active": user_record.is_active,
                    "is_verified": user_record.is_verified,
                    "created_at": user_record.created_at.isoformat()
                }
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error in authenticate_user: {e}")
                raise e
    
    async def _record_failed_login_orm(self, session, username: str):
        """记录失败登录尝试并处理账户锁定 - ORM 版本"""
        stmt = select(UserTable).where(
            and_(UserTable.username == username, UserTable.is_active == True)
        )
        result = await session.execute(stmt)
        user = result.scalar_one_or_none()
        
        if user:
            from datetime import timedelta
            user.failed_login_attempts += 1
            if user.failed_login_attempts >= 5:
                # Use datetime calculation for better database compatibility
                user.locked_until = datetime.utcnow() + timedelta(minutes=30)
            user.updated_at = datetime.utcnow()
    
    async def _log_activity_orm(self, session, user_id: Optional[int], activity_type: str, 
                              details: Dict[str, Any], status: str = "success"):
        """记录用户活动 - ORM 版本"""
        # 使用 ORM 模型插入记录
        activity_log = UserActivityLogsTable(
            user_id=user_id,
            activity_type=activity_type,
            action_details=details,
            ip_address=details.get('ip_address'),
            status=status
        )
        session.add(activity_log)
    
    async def update_user(self, user: PersistedUser) -> Optional[AgentFusionUser]:
        """Update user's last_login timestamp"""
        async with await self.db.get_session() as session:
            try:
                stmt = select(UserTable).where(UserTable.id == user.id)
                result = await session.execute(stmt)
                user_record = result.scalar_one_or_none()
                
                if user_record:
                    now = datetime.utcnow()
                    user_record.last_login = now
                    user_record.updated_at = now
                    await session.commit()
                    return user
                
                return None
            except Exception as e:
                await session.rollback()
                logger.error(f"Error updating user: {e}")
                raise
    
    async def create_user(self, user: User) -> Optional[AgentFusionUser]:
        """
        When it reach here, it means that the user must be exists
        there is two cases:
        1. user is authenticated by oauth, we should create a new user if it doesn't exist
        2. user is authenticated by password, we should fetch the user, 
           and it should never create a new user, because it already checked 
           from password_auth_callback and is exists in db
        """
        _user: Optional[PersistedUser] = await self.get_user(identifier=user.identifier)
        if _user:
            # if user is authenticated by password, it should never create a new user, 
            # and if the user is created from the last oauth, 
            # it should update the user's last_login timestamp
            await self.update_user(_user)
            return _user
        
        async with await self.db.get_session() as session:
            try:
                now = datetime.utcnow()
                
                # Extract user metadata
                metadata = user.metadata if hasattr(user, 'metadata') else {}
                
                # Handle nested metadata structure - extract email from nested metadata if present
                email = None
                if 'email' in metadata:
                    email = metadata['email']
                elif 'metadata' in metadata and isinstance(metadata['metadata'], dict):
                    email = metadata['metadata'].get('email')
                
                # Provide default email if still None to satisfy NOT NULL constraint
                if email is None:
                    email = f"{user.identifier}@example.com"  # Default email based on identifier
                
                # Check if user already exists
                existing_stmt = select(UserTable).where(UserTable.id == user.id)
                existing_result = await session.execute(existing_stmt)
                existing_user = existing_result.scalar_one_or_none()
                
                if existing_user:
                    # Update last_login
                    existing_user.last_login = now
                    existing_user.updated_at = now
                else:
                    # Create new user
                    new_user = UserTable(
                        id=user.id,
                        user_uuid=user.uuid or str(uuid.uuid4()),
                        username=user.identifier,
                        identifier=user.identifier,
                        email=email,
                        role=metadata.get('role', 'user'),
                        first_name=metadata.get('first_name'),
                        last_name=metadata.get('last_name'),
                        created_at=now,
                        last_login=now,
                        user_metadata=metadata,
                        is_active=True
                    )
                    session.add(new_user)
                    existing_user = new_user
                
                await session.commit()
                await session.refresh(existing_user)
                
                # Convert to AgentFusionUser
                result_metadata = existing_user.user_metadata if existing_user.user_metadata else {}
                
                return AgentFusionUser(
                    id=existing_user.id,
                    uuid=str(existing_user.user_uuid),
                    identifier=existing_user.identifier,
                    display_name=user.display_name or existing_user.first_name or existing_user.identifier,
                    email=existing_user.email,
                    role=existing_user.role,
                    first_name=existing_user.first_name,
                    last_name=existing_user.last_name,
                    createdAt=existing_user.created_at.isoformat(),
                    **{k: v for k, v in result_metadata.items() 
                    if k not in ['email', 'role', 'first_name', 'last_name']}
                )
                
            except Exception as e:
                await session.rollback()
                logger.error(f"Error in create_user: {e}")
                raise
    
    # Helper methods for Hybrid ID Strategy (UUID + SERIAL)
    async def get_user_internal_id(self, user_uuid: str) -> Optional[int]:
        """Convert user UUID to internal SERIAL ID for performance-critical operations"""
        async with await self.db.get_session() as session:
            stmt = select(UserTable.id).where(UserTable.user_uuid == user_uuid)
            result = await session.execute(stmt)
            user_id = result.scalar_one_or_none()
            return user_id
    
    async def get_user_uuid(self, internal_id: int) -> Optional[str]:
        """Convert internal SERIAL ID to user UUID for external APIs"""
        async with await self.db.get_session() as session:
            stmt = select(UserTable.user_uuid).where(UserTable.id == internal_id)
            result = await session.execute(stmt)
            user_uuid = result.scalar_one_or_none()
            return str(user_uuid) if user_uuid else None
    
    async def get_user_by_uuid(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user details by UUID (for external API queries)"""
        async with await self.db.get_session() as session:
            stmt = select(
                UserTable.id, UserTable.user_uuid, UserTable.username, UserTable.identifier,
                UserTable.email, UserTable.role, UserTable.is_active, UserTable.is_verified,
                UserTable.first_name, UserTable.last_name, UserTable.created_at, UserTable.user_metadata
            ).where(
                and_(UserTable.user_uuid == user_uuid, UserTable.is_active == True)
            )
            result = await session.execute(stmt)
            row = result.first()
            
            if row:
                return {
                    'id': row.id,
                    'user_uuid': str(row.user_uuid),
                    'username': row.username,
                    'identifier': row.identifier,
                    'email': row.email,
                    'role': row.role,
                    'is_active': row.is_active,
                    'is_verified': row.is_verified,
                    'first_name': row.first_name,
                    'last_name': row.last_name,
                    'created_at': row.created_at,
                    'metadata': row.user_metadata
                }
            return None 