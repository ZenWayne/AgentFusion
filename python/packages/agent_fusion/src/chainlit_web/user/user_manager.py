#!/usr/bin/env python3
"""
User Management Script for AgentFusion
Provides CLI interface for user creation, password reset, and account management
"""

import asyncio
import sys
import getpass
from datetime import datetime
from typing import Optional, List, Dict, Any
import asyncpg
from auth import DatabaseAuth


class UserManager:
    """User management utility class"""
    
    def __init__(self, database_url: str):
        self.db_auth = DatabaseAuth(database_url)
        self.database_url = database_url
    
    async def get_db_connection(self):
        """Get database connection"""
        return await asyncpg.connect(self.database_url)
    
    async def create_user_interactive(self):
        """Interactive user creation"""
        print("\n=== Create New User ===")
        
        username = input("Username: ").strip()
        if not username:
            print("Username cannot be empty!")
            return
        
        email = input("Email: ").strip()
        if not email:
            print("Email cannot be empty!")
            return
        
        password = getpass.getpass("Password: ")
        password_confirm = getpass.getpass("Confirm Password: ")
        
        if password != password_confirm:
            print("Passwords do not match!")
            return
        
        print("\nAvailable roles: user, admin, reviewer, developer")
        role = input("Role (default: user): ").strip() or "user"
        
        first_name = input("First Name (optional): ").strip() or None
        last_name = input("Last Name (optional): ").strip() or None
        
        try:
            user_id = await self.db_auth.create_user(
                username=username,
                email=email,
                password=password,
                role=role,
                first_name=first_name,
                last_name=last_name
            )
            print(f"✅ User created successfully with ID: {user_id}")
            
        except Exception as e:
            print(f"❌ Error creating user: {e}")
    
    async def create_user_batch(self, users_data: List[Dict[str, Any]]):
        """Create multiple users from data"""
        print(f"\n=== Creating {len(users_data)} users ===")
        
        for user_data in users_data:
            try:
                user_id = await self.db_auth.create_user(**user_data)
                print(f"✅ Created user '{user_data['username']}' with ID: {user_id}")
            except Exception as e:
                print(f"❌ Failed to create user '{user_data['username']}': {e}")
    
    async def list_users(self):
        """List all users"""
        conn = None
        try:
            conn = await self.get_db_connection()
            
            query = """
                SELECT id, username, email, role, is_active, is_verified, 
                       created_at, last_login, failed_login_attempts
                FROM users 
                ORDER BY created_at DESC
            """
            users = await conn.fetch(query)
            
            print(f"\n=== Users ({len(users)} total) ===")
            print(f"{'ID':<5} {'Username':<15} {'Email':<30} {'Role':<10} {'Active':<7} {'Verified':<9} {'Last Login':<20}")
            print("-" * 110)
            
            for user in users:
                last_login = user['last_login'].strftime('%Y-%m-%d %H:%M') if user['last_login'] else "Never"
                print(f"{user['id']:<5} {user['username']:<15} {user['email']:<30} {user['role']:<10} "
                      f"{'Yes' if user['is_active'] else 'No':<7} {'Yes' if user['is_verified'] else 'No':<9} {last_login:<20}")
        
        except Exception as e:
            print(f"❌ Error listing users: {e}")
        finally:
            if conn:
                await conn.close()
    
    async def reset_password(self, username: str, new_password: Optional[str] = None):
        """Reset user password"""
        conn = None
        try:
            conn = await self.get_db_connection()
            
            # Check if user exists
            user_query = "SELECT id, username FROM users WHERE username = $1"
            user = await conn.fetchrow(user_query, username)
            
            if not user:
                print(f"❌ User '{username}' not found!")
                return
            
            if not new_password:
                new_password = getpass.getpass(f"New password for {username}: ")
                confirm_password = getpass.getpass("Confirm new password: ")
                
                if new_password != confirm_password:
                    print("❌ Passwords do not match!")
                    return
            
            # Hash new password
            password_hash = await self.db_auth.hash_password(new_password)
            
            # Update password and reset security fields
            update_query = """
                UPDATE users 
                SET password_hash = $1, 
                    failed_login_attempts = 0,
                    locked_until = NULL
                WHERE username = $2
            """
            await conn.execute(update_query, password_hash, username)
            
            # Log password reset
            await self.db_auth.log_activity(conn, user['id'], "password_reset", details={
                "username": username,
                "reset_by": "admin"
            })
            
            print(f"✅ Password reset successfully for user '{username}'")
            
        except Exception as e:
            print(f"❌ Error resetting password: {e}")
        finally:
            if conn:
                await conn.close()
    
    async def toggle_user_status(self, username: str, active: bool):
        """Activate or deactivate user account"""
        conn = None
        try:
            conn = await self.get_db_connection()
            
            # Check if user exists
            user_query = "SELECT id, username, is_active FROM users WHERE username = $1"
            user = await conn.fetchrow(user_query, username)
            
            if not user:
                print(f"❌ User '{username}' not found!")
                return
            
            if user['is_active'] == active:
                status = "active" if active else "inactive"
                print(f"ℹ️  User '{username}' is already {status}")
                return
            
            # Update user status
            update_query = "UPDATE users SET is_active = $1 WHERE username = $2"
            await conn.execute(update_query, active, username)
            
            # Log status change
            action = "activated" if active else "deactivated"
            await self.db_auth.log_activity(conn, user['id'], f"user_{action}", details={
                "username": username,
                "changed_by": "admin"
            })
            
            print(f"✅ User '{username}' has been {action}")
            
        except Exception as e:
            print(f"❌ Error updating user status: {e}")
        finally:
            if conn:
                await conn.close()
    
    async def unlock_user(self, username: str):
        """Unlock locked user account"""
        conn = None
        try:
            conn = await self.get_db_connection()
            
            # Check if user exists
            user_query = "SELECT id, username, locked_until FROM users WHERE username = $1"
            user = await conn.fetchrow(user_query, username)
            
            if not user:
                print(f"❌ User '{username}' not found!")
                return
            
            # Unlock user
            update_query = """
                UPDATE users 
                SET failed_login_attempts = 0, locked_until = NULL 
                WHERE username = $1
            """
            await conn.execute(update_query, username)
            
            # Log unlock
            await self.db_auth.log_activity(conn, user['id'], "user_unlocked", details={
                "username": username,
                "unlocked_by": "admin"
            })
            
            print(f"✅ User '{username}' has been unlocked")
            
        except Exception as e:
            print(f"❌ Error unlocking user: {e}")
        finally:
            if conn:
                await conn.close()


async def main():
    """Main CLI interface"""
    DATABASE_URL = "postgresql://postgres:postgres@db:5432/agentfusion"
    user_manager = UserManager(DATABASE_URL)
    
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python user_manager.py create-user          # Interactive user creation")
        print("  python user_manager.py list-users           # List all users")
        print("  python user_manager.py reset-password <username>")
        print("  python user_manager.py activate-user <username>")
        print("  python user_manager.py deactivate-user <username>")
        print("  python user_manager.py unlock-user <username>")
        print("  python user_manager.py create-defaults      # Create default users")
        return
    
    command = sys.argv[1]
    
    try:
        if command == "create-user":
            await user_manager.create_user_interactive()
        
        elif command == "list-users":
            await user_manager.list_users()
        
        elif command == "reset-password":
            if len(sys.argv) < 3:
                print("Usage: python user_manager.py reset-password <username>")
                return
            username = sys.argv[2]
            await user_manager.reset_password(username)
        
        elif command == "activate-user":
            if len(sys.argv) < 3:
                print("Usage: python user_manager.py activate-user <username>")
                return
            username = sys.argv[2]
            await user_manager.toggle_user_status(username, True)
        
        elif command == "deactivate-user":
            if len(sys.argv) < 3:
                print("Usage: python user_manager.py deactivate-user <username>")
                return
            username = sys.argv[2]
            await user_manager.toggle_user_status(username, False)
        
        elif command == "unlock-user":
            if len(sys.argv) < 3:
                print("Usage: python user_manager.py unlock-user <username>")
                return
            username = sys.argv[2]
            await user_manager.unlock_user(username)
        
        elif command == "create-defaults":
            # Create default users
            default_users = [
                {
                    "username": "admin",
                    "email": "admin@agentfusion.com",
                    "password": "admin123!",
                    "role": "admin",
                    "first_name": "System",
                    "last_name": "Administrator"
                },
                {
                    "username": "demo",
                    "email": "demo@agentfusion.com", 
                    "password": "demo123!",
                    "role": "user",
                    "first_name": "Demo",
                    "last_name": "User"
                }
            ]
            await user_manager.create_user_batch(default_users)
        
        else:
            print(f"Unknown command: {command}")
    
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == "__main__":
    asyncio.run(main()) 