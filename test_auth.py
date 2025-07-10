import asyncio
import os
from dotenv import load_dotenv
import sys
sys.path.append('python/packages/agent_fusion/src')

from chainlit_web.data_layer.data_layer import AgentFusionDataLayer, AgentFusionUser

async def test_auth():
    # 加载环境变量
    load_dotenv()
    
    database_url = os.getenv("DATABASE_URL")
    print(f"DATABASE_URL: {database_url}")
    
    if not database_url:
        print("❌ DATABASE_URL not set. Please set it in .env file or environment")
        return
    
    try:
        # 创建数据层
        data_layer = AgentFusionDataLayer(database_url=database_url)
        print("✅ Data layer created")
        
        # 测试数据库连接
        await data_layer.connect()
        print("✅ Database connection successful")
        
        # 测试用户认证（使用默认管理员账户）
        admin_user = await data_layer.authenticate_user("admin", "admin123!", "127.0.0.1")
        if admin_user:
            print(f"✅ Admin user authenticated successfully: {admin_user}")
        else:
            print("❌ Admin user authentication failed")
            
            # 尝试创建管理员用户
            print("📝 Attempting to create admin user...")
            try:
                admin = AgentFusionUser(
                    identifier="admin",
                    email="admin@agentfusion.com",
                    password="admin123!",
                    role="admin",
                    first_name="Admin",
                    last_name="User"
                )
                
                created_user = await data_layer.create_user(admin)
                if created_user:
                    print(f"✅ Admin user created successfully: {created_user.id}")
                    
                    # 再次尝试认证
                    admin_user = await data_layer.authenticate_user("admin", "admin123!", "127.0.0.1")
                    if admin_user:
                        print(f"✅ Admin user authentication successful after creation: {admin_user}")
                    else:
                        print("❌ Admin user authentication still failed after creation")
                else:
                    print("❌ Failed to create admin user")
                    
            except Exception as e:
                print(f"❌ Error creating admin user: {e}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_auth()) 