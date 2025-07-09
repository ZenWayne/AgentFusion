#!/usr/bin/env python3
"""
Setup script for AgentFusion Authentication System
Quickly initialize the authentication system with default users
"""

import asyncio
import sys
from auth import db_auth


async def setup_authentication():
    """Setup authentication system with default users"""
    print("🚀 Setting up AgentFusion Authentication System...")
    
    try:
        # Test database connection
        print("📡 Testing database connection...")
        conn = await db_auth.get_db_connection()
        await conn.close()
        print("✅ Database connection successful")
        
        # Create default admin user
        print("\n👤 Creating default admin user...")
        try:
            admin_id = await db_auth.create_user(
                username="admin",
                email="admin@agentfusion.com",
                password="admin123!",
                role="admin",
                first_name="System",
                last_name="Administrator"
            )
            print(f"✅ Admin user created with ID: {admin_id}")
            print("   Username: admin")
            print("   Password: admin123!")
            print("   ⚠️  Please change the default password in production!")
        except Exception as e:
            if "duplicate key" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️  Admin user already exists")
            else:
                print(f"❌ Error creating admin user: {e}")
        
        # Create demo user
        print("\n👤 Creating demo user...")
        try:
            demo_id = await db_auth.create_user(
                username="demo",
                email="demo@agentfusion.com",
                password="demo123!",
                role="user",
                first_name="Demo",
                last_name="User"
            )
            print(f"✅ Demo user created with ID: {demo_id}")
            print("   Username: demo")
            print("   Password: demo123!")
        except Exception as e:
            if "duplicate key" in str(e).lower() or "already exists" in str(e).lower():
                print("ℹ️  Demo user already exists")
            else:
                print(f"❌ Error creating demo user: {e}")
        
        print("\n🎉 Authentication setup completed!")
        print("\n📚 Next steps:")
        print("1. Start your Chainlit application")
        print("2. Navigate to the login page")
        print("3. Login with admin/admin123! or demo/demo123!")
        print("4. Use user_manager.py to create additional users")
        print("\n💡 Tips:")
        print("- Change default passwords in production")
        print("- Review user roles and permissions") 
        print("- Monitor user activity logs")
        
    except Exception as e:
        print(f"❌ Setup failed: {e}")
        print("\n🔧 Troubleshooting:")
        print("1. Ensure PostgreSQL is running")
        print("2. Verify database connection string")
        print("3. Check if database tables are created (run progresdb.sql)")
        print("4. Install required dependencies: pip install bcrypt asyncpg")
        sys.exit(1)


async def verify_setup():
    """Verify authentication setup"""
    print("🔍 Verifying authentication setup...")
    
    try:
        # Test admin login
        print("🧪 Testing admin login...")
        admin_data = await db_auth.authenticate_user("admin", "admin123!")
        if admin_data:
            print("✅ Admin authentication successful")
            print(f"   User ID: {admin_data['id']}")
            print(f"   Role: {admin_data['role']}")
        else:
            print("❌ Admin authentication failed")
        
        # Test demo login
        print("\n🧪 Testing demo login...")
        demo_data = await db_auth.authenticate_user("demo", "demo123!")
        if demo_data:
            print("✅ Demo authentication successful")
            print(f"   User ID: {demo_data['id']}")
            print(f"   Role: {demo_data['role']}")
        else:
            print("❌ Demo authentication failed")
        
        print("\n✅ Authentication verification completed!")
        
    except Exception as e:
        print(f"❌ Verification failed: {e}")


async def main():
    """Main function"""
    if len(sys.argv) > 1 and sys.argv[1] == "verify":
        await verify_setup()
    else:
        await setup_authentication()


if __name__ == "__main__":
    print("=" * 60)
    print("   AgentFusion Authentication Setup")
    print("=" * 60)
    asyncio.run(main()) 