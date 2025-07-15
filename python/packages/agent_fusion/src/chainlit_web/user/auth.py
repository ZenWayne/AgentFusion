import hashlib
import bcrypt
import secrets
import json
from typing import Optional, Dict, Any
from datetime import datetime
import asyncio
import asyncpg
import chainlit as cl
import os
from ..data_layer.data_layer import AgentFusionDataLayer, AgentFusionUser, PersistedUser
from starlette.requests import cookie_parser
from chainlit.auth.cookie import get_token_from_cookies
import jwt as pyjwt

# Initialize database auth handler
# Use 'db' for Docker Compose, 'localhost' for local development

# Create global data layer instance
data_layer_instance: Optional[AgentFusionDataLayer] = None

@cl.data_layer
def get_data_layer() -> AgentFusionDataLayer:
    """Get the AgentFusionDataLayer instance"""
    global data_layer_instance
    if data_layer_instance is None:
        database_url = os.getenv("DATABASE_URL")
        # AgentFusionDataLayer uses database_url directly (inherits from ChainlitDataLayer)
        data_layer_instance = AgentFusionDataLayer(database_url=database_url)
    return data_layer_instance

@cl.oauth_callback
def oauth_callback(
  provider_id: str,
  token: str,
  raw_user_data: Dict[str, str],
  default_user: cl.User,
) -> Optional[cl.User]:
  data_layer:AgentFusionDataLayer = get_data_layer()
  user_data = data_layer.create_user(raw_user_data['email'])
  if user_data:
    return cl.User(
      id=user_data['id'],
      identifier=user_data['username'],
      metadata=user_data['metadata']
    )
  return default_user

def decode_jwt(token: str) -> AgentFusionUser:
    secret = os.environ.get("CHAINLIT_AUTH_SECRET")
    assert secret

    dict = pyjwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        options={"verify_signature": True},
    )
    del dict["exp"]
    return AgentFusionUser(**dict)


@cl.header_auth_callback
async def header_auth_callback(headers: Dict[str, str]) -> Optional[cl.User]:
    cookies = cookie_parser(headers.get('cookie'))
    access_token = get_token_from_cookies(cookies)
    if access_token:
        try:
            User: AgentFusionUser = decode_jwt(access_token)
            return User
        except Exception as e:
            print(f"Authentication error: {e}")
            return None
    return None

@cl.password_auth_callback
async def password_auth_callback(username: str, password: str):
    """
    Chainlit authentication callback - validates user credentials against database
    should not create user in db cause it already exists
    """
    try:
        # Get client IP if available (this might need request context)
        ip_address = None  # You might want to get this from request headers
        
        # Get the data layer instance
        data_layer:AgentFusionDataLayer = get_data_layer()
        
        # Run async authentication in sync context
        user_data = await data_layer.authenticate_user(username, password, ip_address)
        
        if user_data:
            return AgentFusionUser(
                id=int(user_data['id']),
                uuid=user_data['uuid'],
                identifier=user_data['username'],
                createdAt=user_data['created_at'],
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
        # Get the data layer instance
        data_layer:AgentFusionDataLayer = get_data_layer()
        
        # Check if admin user exists
        user_data = await data_layer.authenticate_user("admin", "admin123!")
        if not user_data:
            # Create admin user using AgentFusionUser
            admin_user = AgentFusionUser(
                identifier="admin",
                email="admin@agentfusion.com", 
                password="admin123!",  # Change this in production!
                role="admin",
                first_name="System",
                last_name="Administrator"
            )
            
            persisted_user = await data_layer.create_user(admin_user)
            print(f"Created admin user with ID: {persisted_user.id}")
    except Exception as e:
        print(f"Error creating admin user: {e}")

# Uncomment this to create admin user on startup
if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(create_admin_user())