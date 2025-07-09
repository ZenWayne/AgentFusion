import hashlib
import bcrypt
import secrets
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import asyncpg
import chainlit as cl
from chainlit.data.sql_alchemy import SQLAlchemyDataLayer
from chainlit.data.chainlit_data_layer import ChainlitDataLayer


class DatabaseAuth:
    """Database authentication handler with security features"""
    
    def __init__(self, conninfo: str):
        self.conninfo = conninfo
        
    async def get_db_connection(self):
        """Get database connection"""
        return await asyncpg.connect(self.conninfo)
    
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
        conn = None
        try:
            conn = await self.get_db_connection()
            
            # First, check if user exists and get their details
            user_query = """
                SELECT id, username, email, password_hash, role, is_active, is_verified, 
                       failed_login_attempts, locked_until, last_login
                FROM users 
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
                UPDATE users 
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
            if conn:
                await self.log_activity(conn, None, "login_error", details={
                    "error": str(e),
                    "username": username,
                    "ip_address": ip_address
                })
            raise e
        finally:
            if conn:
                await conn.close()
    
    async def record_failed_login(self, conn, username: str):
        """Record failed login attempt and handle account locking"""
        lock_query = """
            UPDATE users 
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
            details, 
            details.get('ip_address'),
            status
        )
    
    async def create_user(self, username: str, email: str, password: str, 
                         role: str = "user", **kwargs) -> Optional[int]:
        """Create a new user account"""
        conn = None
        try:
            conn = await self.get_db_connection()
            
            # Hash the password
            password_hash = await self.hash_password(password)
            
            # Insert user
            user_query = """
                INSERT INTO users (username, email, password_hash, role, first_name, last_name)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING id
            """
            user_id = await conn.fetchval(
                user_query, 
                username, 
                email, 
                password_hash, 
                role,
                kwargs.get('first_name'),
                kwargs.get('last_name')
            )
            
            # Log user creation
            await self.log_activity(conn, user_id, "user_created", details={
                "username": username,
                "email": email,
                "role": role
            })
            
            return user_id
            
        except Exception as e:
            raise e
        finally:
            if conn:
                await conn.close()


# Initialize database auth handler
# Use 'db' for Docker Compose, 'localhost' for local development
DATABASE_URL = "postgresql://postgres:postgres@db:5432/agentfusion"
db_auth = DatabaseAuth(DATABASE_URL)

@cl.data_layer
def get_data_layer():
    # SQLAlchemy needs the psycopg2 driver specification
    sqlalchemy_url = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://")
    return SQLAlchemyDataLayer(conninfo=sqlalchemy_url)

@cl.header_auth_callback
def header_auth_callback(headers: Dict) -> Optional[cl.User]:
  # Verify the signature of a token in the header (ex: jwt token)
  # or check that the value is matching a row from your database
  if headers.get("test-header") == "test-value":
    return cl.User(identifier="admin", metadata={"role": "admin", "provider": "header"})
  else:
    return None

@cl.password_auth_callback
def auth_callback(username: str, password: str):
    """
    Chainlit authentication callback - validates user credentials against database
    """
    try:
        # Get client IP if available (this might need request context)
        ip_address = None  # You might want to get this from request headers
        
        # Run async authentication in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            user_data = loop.run_until_complete(
                db_auth.authenticate_user(username, password, ip_address)
            )
        finally:
            loop.close()
        
        if user_data:
            return cl.User(
                identifier=user_data['username'],
                metadata={
                    "user_id": user_data['id'],
                    "email": user_data['email'],
                    "role": user_data['role'],
                    "is_verified": user_data['is_verified'],
                    "provider": "database"
                }
            )
        else:
            return None
            
    except Exception as e:
        print(f"Authentication error: {e}")
        return None

# Additional utility functions for user management
async def create_admin_user():
    """Create default admin user if it doesn't exist"""
    try:
        # Check if admin user exists
        user_data = await db_auth.authenticate_user("admin", "temp_password")
        if not user_data:
            # Create admin user
            admin_id = await db_auth.create_user(
                username="admin",
                email="admin@agentfusion.com", 
                password="admin123!",  # Change this in production!
                role="admin",
                first_name="System",
                last_name="Administrator"
            )
            print(f"Created admin user with ID: {admin_id}")
    except Exception as e:
        print(f"Error creating admin user: {e}")

# Uncomment this to create admin user on startup
if __name__ == "__main__":
    asyncio.run(create_admin_user())