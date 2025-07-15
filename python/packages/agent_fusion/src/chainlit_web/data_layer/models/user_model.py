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

from chainlit_web.data_layer.models.base_model import BaseModel


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
    
    async def get_user(self, identifier: str) -> Optional[PersistedUser]:
        """根据标识符获取用户"""
        query = """
        SELECT * FROM "User" 
        WHERE identifier = $1
        """
        result = await self.execute_single_query(query, [identifier])
        if not result:
            return None

        return PersistedUser(
            id=int(result.get("id")),
            uuid=str(result.get("user_uuid")),
            identifier=str(result.get("identifier")),
            createdAt=result.get("created_at").isoformat(),
            metadata=json.loads(result.get("metadata", "{}")),
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
        async def _authenticate(conn):
            try:
                # First, check if user exists and get their details
                user_query = """
                    SELECT id, user_uuid, username, email, password_hash, role, is_active, is_verified, 
                           failed_login_attempts, locked_until, last_login, 
                           created_at
                    FROM "User" 
                    WHERE username = $1 OR email = $1
                """
                user_record = await conn.fetchrow(user_query, username)
                
                if not user_record:
                    # Log failed login attempt for non-existent user
                    await self._log_activity(conn, None, "login_failed", details={
                        "reason": "user_not_found",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Check if account is locked
                if user_record['locked_until'] and user_record['locked_until'] > datetime.utcnow():
                    await self._log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "account_locked",
                        "username": username,
                        "ip_address": ip_address,
                        "locked_until": user_record['locked_until'].isoformat()
                    })
                    return None
                
                # Check if account is active
                if not user_record['is_active']:
                    await self._log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "account_inactive",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Verify password
                if not self.verify_password(password, user_record['password_hash']):
                    # Record failed login attempt
                    await self._record_failed_login(conn, username)
                    await self._log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "invalid_password",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Password is correct - reset failed attempts and update last login
                update_query = """
                    UPDATE "User" 
                    SET last_login = CURRENT_TIMESTAMP, 
                        failed_login_attempts = 0,
                        locked_until = NULL
                    WHERE id = $1
                """
                await conn.execute(update_query, user_record['id'])
                
                # Log successful login
                await self._log_activity(conn, user_record['id'], "login_success", details={
                    "username": username,
                    "ip_address": ip_address,
                    "last_login": user_record['last_login'].isoformat() if user_record['last_login'] else None
                })
                
                return {
                    "id": user_record['id'],
                    "uuid": str(user_record['user_uuid']),
                    "username": user_record['username'],
                    "email": user_record['email'],
                    "role": user_record['role'],
                    "is_active": user_record['is_active'],
                    "is_verified": user_record['is_verified'],
                    "created_at": user_record['created_at'].isoformat()
                }
                
            except Exception as e:
                # Log authentication error
                await self._log_activity(conn, None, "login_error", details={
                    "error": str(e),
                    "username": username,
                    "ip_address": ip_address
                })
                raise e
        
        return await self.execute_with_connection(_authenticate)
    
    async def _record_failed_login(self, conn, username: str):
        """Record failed login attempt and handle account locking"""
        lock_query = """
            UPDATE "User" 
            SET failed_login_attempts = failed_login_attempts + 1,
                locked_until = CASE 
                    WHEN failed_login_attempts >= 4 THEN CURRENT_TIMESTAMP + INTERVAL '30 minutes'
                    ELSE locked_until
                END
            WHERE username = $1 AND is_active = TRUE
        """
        await conn.execute(lock_query, username)
    
    async def _log_activity(self, conn, user_id: Optional[int], activity_type: str, 
                          details: Dict[str, Any], status: str = "success"):
        """Log user activity"""
        log_query = """
            INSERT INTO user_activity_logs (
                user_id, activity_type, action_details, ip_address, status
            ) VALUES ($1, $2, $3, $4, $5)
        """
        await conn.execute(
            log_query, 
            user_id, 
            activity_type, 
            json.dumps(details),  # Serialize dictionary to JSON string
            details.get('ip_address'),
            status
        )
    
    async def update_user(self, user: PersistedUser) -> Optional[AgentFusionUser]:
        """Update user's last_login timestamp"""
        async def _update_user(conn):
            update_query = """
                UPDATE "User"
                SET last_login = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
            """
            await conn.execute(update_query, user.id)
            return user
        
        return await self.execute_with_connection(_update_user)
    
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
        
        async def _create_user(conn):
            try:
                now = await self.get_current_timestamp()
                
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
                
                # INSERT ... ON CONFLICT DO UPDATE query
                upsert_query = """
                INSERT INTO "User" (
                    id, user_uuid, username, identifier, email, role, first_name, last_name,
                    created_at, last_login, metadata, is_active
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12
                )
                ON CONFLICT (id) DO UPDATE SET
                    last_login = EXCLUDED.last_login
                RETURNING id, user_uuid, username, identifier, email, role, first_name, last_name, 
                        created_at, updated_at, metadata, is_active
                """
                
                params = [
                    user.id,  # id
                    user.uuid or str(uuid.uuid4()),  # user_uuid
                    user.identifier,  # username
                    user.identifier,  # identifier
                    metadata.get('email'),  # email
                    metadata.get('role', 'user'),  # role
                    metadata.get('first_name'),  # first_name
                    metadata.get('last_name'),  # last_name
                    now,  # created_at
                    now,  # last_login
                    json.dumps(metadata),  # metadata
                    True,  # is_active
                ]
                
                result = await conn.fetchrow(upsert_query, *params)
                
                if result:
                    # Convert database result to AgentFusionUser
                    result_metadata = json.loads(result.get('metadata', '{}'))
                    
                    return AgentFusionUser(
                        id=result['id'],
                        uuid=str(result['user_uuid']),
                        identifier=result['identifier'],
                        display_name=user.display_name or result.get('first_name') or result['identifier'],
                        email=result.get('email'),
                        role=result.get('role', 'user'),
                        first_name=result.get('first_name'),
                        last_name=result.get('last_name'),
                        createdAt=result['created_at'].isoformat(),
                        **{k: v for k, v in result_metadata.items() 
                        if k not in ['email', 'role', 'first_name', 'last_name']}
                    )
                
                return None
                
            except Exception as e:
                logger.error(f"Error in create_user: {e}")
                raise
        
        return await self.execute_with_connection(_create_user)
    
    # Helper methods for Hybrid ID Strategy (UUID + SERIAL)
    async def get_user_internal_id(self, user_uuid: str) -> Optional[int]:
        """Convert user UUID to internal SERIAL ID for performance-critical operations"""
        query = """SELECT id FROM "User" WHERE user_uuid = $1"""
        result = await self.execute_single_query(query, [user_uuid])
        return result["id"] if result else None
    
    async def get_user_uuid(self, internal_id: int) -> Optional[str]:
        """Convert internal SERIAL ID to user UUID for external APIs"""
        query = """SELECT user_uuid FROM "User" WHERE id = $1"""
        result = await self.execute_single_query(query, [internal_id])
        return str(result["user_uuid"]) if result else None
    
    async def get_user_by_uuid(self, user_uuid: str) -> Optional[Dict[str, Any]]:
        """Get user details by UUID (for external API queries)"""
        query = """
        SELECT id, user_uuid, username, identifier, email, role, is_active, is_verified,
               first_name, last_name, created_at, metadata
        FROM "User" 
        WHERE user_uuid = $1 AND is_active = TRUE
        """
        result = await self.execute_single_query(query, [user_uuid])
        return dict(result) if result else None 