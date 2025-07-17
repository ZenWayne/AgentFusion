"""
测试LLM模型功能

验证从数据库加载模型信息的功能
"""

import asyncio
import os
import sys
from dotenv import load_dotenv

# 添加项目路径
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from chainlit_web.data_layer.data_layer import AgentFusionDataLayer
from chainlit_web.data_layer.models.llm_model import LLMModel, LLMModelInfo


async def test_llm_model():
    """测试LLM模型功能"""
    print("Testing LLM Model functionality...")
    
    # 加载环境变量
    load_dotenv()
    
    # 获取数据库URL
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/agentfusion")
    
    try:
        # 创建数据层实例
        data_layer = AgentFusionDataLayer(
            database_url=database_url,
            show_logger=True
        )
        
        # 连接数据库
        await data_layer.connect()
        print("✅ Connected to database")
        
        # 测试获取所有活跃模型
        print("\n📋 Testing get_all_active_models...")
        models = await data_layer.get_all_active_models()
        print(f"Found {len(models)} active models:")
        for model in models:
            print(f"  - {model.label}: {model.description}")
        
        # 测试获取模型标签列表
        print("\n🏷️ Testing get_model_labels_for_chat_settings...")
        model_options = await data_layer.get_model_labels_for_chat_settings()
        print(f"Found {len(model_options)} model options for chat settings:")
        for option in model_options:
            print(f"  - {option['label']}: {option['description']}")
            print(f"    Capabilities: {option['capabilities']}")
        
        # 测试获取特定模型配置
        if models:
            test_model = models[0]
            print(f"\n⚙️ Testing get_model_config_for_agent_builder for {test_model.label}...")
            config = await data_layer.get_model_config_for_agent_builder(test_model.label)
            if config:
                print(f"✅ Found config for {test_model.label}")
                print(f"  Model name: {config.get('model_name')}")
                print(f"  Base URL: {config.get('base_url')}")
                print(f"  Provider: {config.get('provider')}")
            else:
                print(f"❌ No config found for {test_model.label}")
        
        # 测试获取不存在的模型
        print("\n❌ Testing get_model_by_label with non-existent model...")
        non_existent_model = await data_layer.get_model_by_label("non-existent-model")
        if non_existent_model is None:
            print("✅ Correctly returned None for non-existent model")
        else:
            print("❌ Unexpectedly found non-existent model")
        
        print("\n✅ All tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理连接
        if 'data_layer' in locals():
            await data_layer.cleanup()


async def test_model_client_builder():
    """测试模型客户端构建器"""
    print("\n🔧 Testing Model Client Builder...")
    
    # 加载环境变量
    load_dotenv()
    
    # 获取数据库URL
    database_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@localhost:5432/agentfusion")
    
    try:
        # 创建数据层实例
        data_layer = AgentFusionDataLayer(
            database_url=database_url,
            show_logger=True
        )
        
        # 连接数据库
        await data_layer.connect()
        print("✅ Connected to database")
        
        # 导入模型客户端构建器
        from model_client.database_model_client import DatabaseModelClientBuilder
        
        # 创建模型客户端构建器
        builder = DatabaseModelClientBuilder(data_layer)
        
        # 获取所有模型客户端
        print("\n📋 Testing get_all_model_clients...")
        model_clients = await builder.get_all_model_clients()
        print(f"Created {len(model_clients)} model clients:")
        for label, client in model_clients.items():
            print(f"  - {label}: {client.model}")
        
        # 测试获取特定模型客户端
        if model_clients:
            test_label = list(model_clients.keys())[0]
            print(f"\n⚙️ Testing get_model_client for {test_label}...")
            client = await builder.get_model_client(test_label)
            if client:
                print(f"✅ Successfully created model client for {test_label}")
                print(f"  Model: {client.model}")
                print(f"  Base URL: {client.base_url}")
            else:
                print(f"❌ Failed to create model client for {test_label}")
        
        print("\n✅ Model client builder tests completed successfully!")
        
    except Exception as e:
        print(f"❌ Error during model client builder testing: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 清理连接
        if 'data_layer' in locals():
            await data_layer.cleanup()


if __name__ == "__main__":
    print("🚀 Starting LLM Model Tests...")
    
    # 运行测试
    asyncio.run(test_llm_model())
    asyncio.run(test_model_client_builder())
    
    print("\n🎉 All tests completed!") 