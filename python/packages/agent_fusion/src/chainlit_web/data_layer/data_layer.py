import hashlib
import bcrypt
import secrets
import json
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import asyncpg
import chainlit as cl
from chainlit.data.chainlit_data_layer import ChainlitDataLayer
from chainlit.user import User, PersistedUser


class AgentFusionUser(User):
    """Extended User class with additional AgentFusion-specific fields"""
    
    def __init__(self, 
                 identifier: str,
                 display_name: Optional[str] = None,
                 email: Optional[str] = None,
                 password: Optional[str] = None,
                 role: str = "user",
                 first_name: Optional[str] = None,
                 last_name: Optional[str] = None,
                 **kwargs):
        """
        Initialize AgentFusionUser
        
        Args:
            identifier: Unique identifier (username)
            display_name: Display name for the user
            email: User email
            password: Plain text password (will be hashed)
            role: User role (user, admin, reviewer, developer)
            first_name: First name
            last_name: Last name
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
            identifier=identifier,
            display_name=display_name or first_name or identifier,
            metadata=metadata
        )
    
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


class AgentFusionDataLayer(ChainlitDataLayer):
    """Enhanced data layer with authentication and security features"""
    
    def __init__(self, database_url: str, **kwargs):
        super().__init__(database_url=database_url, **kwargs)
        
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
        # Ensure we have a connection pool
        await self.connect()
        
        async with self.pool.acquire() as conn:
            try:
                # First, check if user exists and get their details
                user_query = """
                    SELECT id, username, email, password_hash, role, is_active, is_verified, 
                           failed_login_attempts, locked_until, last_login
                    FROM "User" 
                    WHERE username = $1 OR email = $1
                """
                user_record = await conn.fetchrow(user_query, username)
                
                if not user_record:
                    # Log failed login attempt for non-existent user
                    await self.log_activity(conn, None, "login_failed", details={
                        "reason": "user_not_found",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Check if account is locked
                if user_record['locked_until'] and user_record['locked_until'] > datetime.utcnow():
                    await self.log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "account_locked",
                        "username": username,
                        "ip_address": ip_address,
                        "locked_until": user_record['locked_until'].isoformat()
                    })
                    return None
                
                # Check if account is active
                if not user_record['is_active']:
                    await self.log_activity(conn, user_record['id'], "login_failed", details={
                        "reason": "account_inactive",
                        "username": username,
                        "ip_address": ip_address
                    })
                    return None
                
                # Verify password
                if not self.verify_password(password, user_record['password_hash']):
                    # Record failed login attempt
                    await self.record_failed_login(conn, username)
                    await self.log_activity(conn, user_record['id'], "login_failed", details={
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
                await self.log_activity(conn, user_record['id'], "login_success", details={
                    "username": username,
                    "ip_address": ip_address,
                    "last_login": user_record['last_login'].isoformat() if user_record['last_login'] else None
                })
                
                return {
                    "id": user_record['id'],
                    "username": user_record['username'],
                    "email": user_record['email'],
                    "role": user_record['role'],
                    "is_active": user_record['is_active'],
                    "is_verified": user_record['is_verified']
                }
                
            except Exception as e:
                # Log authentication error
                await self.log_activity(conn, None, "login_error", details={
                    "error": str(e),
                    "username": username,
                    "ip_address": ip_address
                })
                raise e
    
    async def record_failed_login(self, conn, username: str):
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
    
    async def log_activity(self, conn, user_id: Optional[int], activity_type: str, 
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
    
    async def create_user(self, user) -> Optional[PersistedUser]:
        """Create a new user account - supports both AgentFusionUser and User objects"""
        # If it's a regular User object, convert it to AgentFusionUser
        if isinstance(user, User) and not isinstance(user, AgentFusionUser):
            user = AgentFusionUser(
                identifier=user.identifier,
                display_name=user.display_name,
                email=user.metadata.get('email'),
                password=user.metadata.get('password'),
                role=user.metadata.get('role', 'user'),
                first_name=user.metadata.get('first_name'),
                last_name=user.metadata.get('last_name'),
                **{k: v for k, v in user.metadata.items() 
                   if k not in ['email', 'password', 'role', 'first_name', 'last_name']}
            )
        
        return await self._create_agentfusion_user(user)
    
    async def _create_agentfusion_user(self, user: AgentFusionUser) -> Optional[PersistedUser]:
        """Internal method to create AgentFusionUser object"""
        # Ensure we have a connection pool
        await self.connect()
        
        async with self.pool.acquire() as conn:
            try:
                # Hash the password if provided
                password_hash = None
                if user.password:
                    password_hash = await self.hash_password(user.password)
                
                # Insert user
                user_query = """
                    INSERT INTO "User" (username, identifier, email, password_hash, role, first_name, last_name)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING id, created_at
                """
                result = await conn.fetchrow(
                    user_query, 
                    user.identifier,  # username
                    user.identifier,  # identifier for Chainlit compatibility
                    user.email or f"{user.identifier}@agentfusion.com",
                    password_hash or 'temp_password_hash',
                    user.role,
                    user.first_name,
                    user.last_name
                )
                
                user_id = result['id']
                created_at = result['created_at']
                
                # Log user creation
                await self.log_activity(conn, user_id, "user_created", details={
                    "username": user.identifier,
                    "email": user.email,
                    "role": user.role
                })
                
                # Return PersistedUser following Chainlit pattern
                return PersistedUser(
                    id=str(user_id),
                    identifier=user.identifier,
                    createdAt=created_at.isoformat(),
                    metadata=user.metadata
                )
                
            except Exception as e:
                raise e