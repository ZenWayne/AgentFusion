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
from ..data_layer.data_layer import AgentFusionDataLayer, AgentFusionUser


# Initialize database auth handler
# Use 'db' for Docker Compose, 'localhost' for local development
DATABASE_URL = os.getenv("DATABASE_URL")

# Create global data layer instance
data_layer_instance = None

@cl.data_layer
def get_data_layer():
    """Get the AgentFusionDataLayer instance"""
    global data_layer_instance
    if data_layer_instance is None:
        # AgentFusionDataLayer uses database_url directly (inherits from ChainlitDataLayer)
        data_layer_instance = AgentFusionDataLayer(database_url=DATABASE_URL)
    return data_layer_instance

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
        
        # Get the data layer instance
        data_layer = get_data_layer()
        
        # Run async authentication in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        try:
            user_data = loop.run_until_complete(
                data_layer.authenticate_user(username, password, ip_address)
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
        # Get the data layer instance
        data_layer = get_data_layer()
        
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