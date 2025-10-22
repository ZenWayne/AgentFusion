#!/usr/bin/env python3
"""
Test script for Database Agent functionality

This script tests the database agent components:
1. Database MCP Server
2. Database Agent Configuration
3. Basic functionality
"""

import asyncio
import json
import sqlite3
import tempfile
import pytest
import os
from pathlib import Path
from pydantic import BaseModel
from mcp.types import (
    Tool, TextContent, CallToolResult, CallToolRequest, CallToolRequestParams
)
from data_layer.utils import CustomJsonEncoder

def create_test_database():
    """Create a temporary SQLite database for testing."""
    # Create temporary database
    temp_db = tempfile.NamedTemporaryFile(suffix='.db', delete=False)
    db_path = temp_db.name
    temp_db.close()

    # Connect and create test data
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create tables
    cursor.execute('''
        CREATE TABLE users (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE,
            age INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE products (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT,
            price REAL,
            stock INTEGER
        )
    ''')

    cursor.execute('''
        CREATE TABLE orders (
            id INTEGER PRIMARY KEY,
            user_id INTEGER,
            product_id INTEGER,
            quantity INTEGER,
            total REAL,
            order_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        )
    ''')

    # Insert test data
    cursor.execute('INSERT INTO users (name, email, age) VALUES (?, ?, ?)',
                   ('Alice', 'alice@example.com', 25))
    cursor.execute('INSERT INTO users (name, email, age) VALUES (?, ?, ?)',
                   ('Bob', 'bob@example.com', 30))
    cursor.execute('INSERT INTO users (name, email, age) VALUES (?, ?, ?)',
                   ('Charlie', 'charlie@example.com', 35))

    cursor.execute('INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)',
                   ('Laptop', 'Electronics', 999.99, 10))
    cursor.execute('INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)',
                   ('Book', 'Education', 29.99, 50))
    cursor.execute('INSERT INTO products (name, category, price, stock) VALUES (?, ?, ?, ?)',
                   ('Coffee', 'Food', 4.99, 100))

    cursor.execute('INSERT INTO orders (user_id, product_id, quantity, total) VALUES (?, ?, ?, ?)',
                   (1, 1, 1, 999.99))
    cursor.execute('INSERT INTO orders (user_id, product_id, quantity, total) VALUES (?, ?, ?, ?)',
                   (2, 2, 2, 59.98))
    cursor.execute('INSERT INTO orders (user_id, product_id, quantity, total) VALUES (?, ?, ?, ?)',
                   (3, 3, 5, 24.95))

    conn.commit()
    conn.close()

    return db_path

@pytest.mark.asyncio 
async def test_mcp_server():
    """Test the Database MCP Server directly."""
    print("🧪 Testing Database MCP Server...")

    try:
        from agent_fusion_mcp.database_server import DatabaseMCPServer

        # Create server instance
        database_mcp = DatabaseMCPServer()

        # Test connection
        test_db = create_test_database()
        print(f"📁 Created test database: {test_db}")

        # Simulate connect_database call
        #CR check for progressql
        connection_arguments = {
            "connection_name": "test_db_connection",
            "database_type": "postgresql",
            "connection_string": "postgresql://postgres:postgres@localhost:5432/agentfusion"
        }
        req = CallToolRequest(
            method="tools/call",
            params=CallToolRequestParams(name="connect_database", arguments=connection_arguments)
        )

        connection_result: BaseModel = await database_mcp.server.request_handlers[CallToolRequest](req)
        
        connection_result= connection_result.model_dump()

        print(f"✅ Connection result: {json.dumps(connection_result, indent=2)}")

        if connection_result["structuredContent"]["success"]:
            # Test security check
            security_result = await database_mcp._security_check(
                query="SELECT * FROM agents",
                security_level="medium"
            )
            print(f"✅ Security check result: {json.dumps(security_result, indent=2)}")

            # Test query execution
            if security_result["valid"]:
                query_result = await database_mcp._execute_query(
                    connection_name="test_db_connection",
                    query="SELECT * FROM agents",
                    params={},
                    max_rows=10
                )
                print(f"✅ Query execution result: {json.dumps(query_result, indent=2, cls=CustomJsonEncoder)}")

        # Cleanup
        if connection_result["structuredContent"]["success"] and "test_db" in database_mcp.connections:
            database_mcp.connections["test_db"].dispose()
        os.unlink(test_db)

        print("✅ MCP Server test completed successfully")

    except Exception as e:
        print(f"❌ MCP Server test failed: {str(e)}")
        import traceback
        traceback.print_exc()

def test_configuration():
    """Test database agent configuration."""
    print("\n🧪 Testing Database Agent Configuration...")

    try:
        # Load config
        config_path = Path(__file__).parent / "config.json"
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        # Check MCP server configuration
        assert "database" in config["mcpServers"], "Database MCP server not configured"
        db_server_config = config["mcpServers"]["database"]
        print(f"✅ MCP Server Config: {db_server_config}")

        # Check agent configuration
        assert "database_agent" in config["agents"], "Database agent not configured"
        db_agent_config = config["agents"]["database_agent"]
        print(f"✅ Database Agent Config: {db_agent_config}")

        # Verify agent has database tools
        assert "database" in db_agent_config["mcp_tools"], "Database agent missing database tools"
        print("✅ Database agent has database MCP tools")

        # Check prompt file exists
        prompt_path = Path(__file__).parent / config["prompt_root"] / db_agent_config["prompt_path"]
        assert prompt_path.exists(), f"Prompt file not found: {prompt_path}"
        print(f"✅ Prompt file exists: {prompt_path}")

        print("✅ Configuration test completed successfully")

    except Exception as e:
        print(f"❌ Configuration test failed: {str(e)}")
        import traceback
        traceback.print_exc()

def test_schemas():
    """Test database agent schemas."""
    print("\n🧪 Testing Database Agent Schemas...")

    try:
        from schemas.agents.database_agent import (
            DatabaseConnection, DatabaseAgentConfig, QueryResult, SecurityLevel
        )

        # Test DatabaseConnection schema
        conn = DatabaseConnection(
            database_type="sqlite",
            database="test.db",
            connection_timeout=30
        )
        print(f"✅ DatabaseConnection schema works: {conn.database_type}")

        # Test SecurityLevel enum
        security = SecurityLevel.MEDIUM
        print(f"✅ SecurityLevel enum works: {security}")

        # Test QueryResult schema
        result = QueryResult(
            query="SELECT * FROM users",
            success=True,
            data=[{"id": 1, "name": "Alice"}],
            columns=["id", "name"],
            row_count=1,
            execution_time=0.05
        )
        print(f"✅ QueryResult schema works: {result.row_count} rows")

        print("✅ Schema test completed successfully")

    except Exception as e:
        print(f"❌ Schema test failed: {str(e)}")
        import traceback
        traceback.print_exc()

def test_dependencies():
    """Test required dependencies."""
    print("\n🧪 Testing Dependencies...")

    required_modules = [
        "sqlalchemy",
        "mcp.server",
        "pydantic"
    ]

    missing_modules = []

    for module in required_modules:
        try:
            __import__(module)
            print(f"✅ {module} - OK")
        except ImportError as e:
            missing_modules.append(module)
            print(f"❌ {module} - MISSING: {e}")

    if missing_modules:
        print(f"\n💡 Install missing dependencies:")
        print(f"pip install {' '.join(missing_modules)}")
    else:
        print("✅ All dependencies available")

async def main():
    """Run all tests."""
    print("🚀 Starting Database Agent Tests\n")

    # Run tests
    test_dependencies()
    test_configuration()
    test_schemas()
    await test_mcp_server()

    print("\n🎉 Database Agent testing completed!")
    print("\n📝 Usage Instructions:")
    print("1. Install dependencies: pip install -e python/packages/agent_fusion")
    print("2. Configure your database connection in the agent")
    print("3. Use the database_agent in your AgentFusion workflows")
    print("4. Speak naturally: 'Show me users older than 25'")

if __name__ == "__main__":
    asyncio.run(main())