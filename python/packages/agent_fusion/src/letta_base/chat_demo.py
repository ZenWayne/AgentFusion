#!/usr/bin/env python3
"""
Letta Agent Chat Demo

This demo shows how to use the Letta Python SDK to create and chat with an agent.
It demonstrates both streaming and non-streaming message handling.

Prerequisites:
- pip install letta-client
- Set LETTA_API_KEY environment variable for Letta Cloud
- Or run a local Letta server for self-hosted usage

Usage:
python chat_demo.py
"""

import os
import sys
from typing import Optional
from letta_client import Letta
from letta_client.schemas import MessageCreate


def setup_client() -> Letta:
    """Setup and return a Letta client."""
    # Check for API key (Letta Cloud)
    api_key = os.getenv("LETTA_API_KEY")
    base_url = os.getenv("LETTA_BASE_URL", "http://localhost:8283")
    
    if api_key:
        print("🌩️  Connecting to Letta Cloud...")
        client = Letta(token=api_key)
    else:
        print("🏠 Connecting to self-hosted Letta server...")
        client = Letta(base_url=base_url)
    
    return client


def create_agent(client: Letta) -> str:
    """Create a new agent with memory blocks and return its ID."""
    print("🤖 Creating new agent...")
    
    agent = client.agents.create(
        memory_blocks=[
            {
                "label": "human",
                "value": "The user is a developer learning about Letta agents. They are interested in AI and want to understand how stateful agents work."
            },
            {
                "label": "persona",
                "value": "I am Alex, a helpful AI assistant specialized in explaining AI concepts. I'm friendly, knowledgeable, and enjoy helping developers understand complex topics through clear examples."
            },
            {
                "label": "project_context",
                "value": "We're exploring Letta's agent capabilities through a Python demo. The goal is to understand how agents maintain state and memory across conversations.",
                "description": "Stores information about the current project and learning goals"
            }
        ],
        tools=["web_search", "run_code"],  # Built-in tools
        model="openai/gpt-4.1",  # Recommended model from the guidelines
        embedding="openai/text-embedding-3-small"  # Recommended embedding model
    )
    
    print(f"✅ Agent created successfully! ID: {agent.id}")
    return agent.id


def send_message_sync(client: Letta, agent_id: str, message: str) -> None:
    """Send a message to the agent and handle the response (non-streaming)."""
    print(f"\n👤 You: {message}")
    
    try:
        response = client.agents.messages.create(
            agent_id=agent_id,
            messages=[{"role": "user", "content": message}]
        )
        
        # Process the response messages
        print("🤖 Agent response:")
        for msg in response.messages:
            if msg.message_type == "assistant_message":
                print(f"💬 {msg.content}")
            elif msg.message_type == "reasoning_message":
                print(f"🧠 Reasoning: {msg.reasoning}")
            elif msg.message_type == "tool_call_message":
                print(f"🔧 Tool call: {msg.tool_call.name}")
                if msg.tool_call.arguments:
                    print(f"   Arguments: {msg.tool_call.arguments}")
            elif msg.message_type == "tool_return_message":
                print(f"🔧 Tool result: {msg.tool_return}")
                
    except Exception as e:
        print(f"❌ Error sending message: {e}")


def send_message_stream(client: Letta, agent_id: str, message: str) -> None:
    """Send a message to the agent and handle the response (streaming)."""
    print(f"\n👤 You: {message}")
    
    try:
        stream = client.agents.messages.create_stream(
            agent_id=agent_id,
            messages=[MessageCreate(role="user", content=message)],
            stream_tokens=True  # Token-based streaming
        )
        
        print("🤖 Agent response (streaming):")
        
        # Collect streaming response
        assistant_content = []
        reasoning_content = []
        
        for chunk in stream:
            if chunk.message_type == "assistant_message":
                content = chunk.content or ""
                assistant_content.append(content)
                print(content, end='', flush=True)
            elif chunk.message_type == "reasoning_message":
                reasoning = chunk.reasoning or ""
                reasoning_content.append(reasoning)
            elif chunk.message_type == "tool_call_message":
                if chunk.tool_call.name:
                    print(f"\n🔧 Tool call: {chunk.tool_call.name}")
                if chunk.tool_call.arguments:
                    print(f"   Arguments: {chunk.tool_call.arguments}")
            elif chunk.message_type == "tool_return_message":
                if chunk.tool_return:
                    print(f"\n🔧 Tool result: {chunk.tool_return}")
            elif chunk.message_type == "usage_statistics":
                print(f"\n📊 Usage: {chunk}")
        
        # Show reasoning if any
        if reasoning_content:
            print(f"\n🧠 Reasoning: {''.join(reasoning_content)}")
        
        print()  # New line after streaming
        
    except Exception as e:
        print(f"❌ Error sending message: {e}")


def chat_loop(client: Letta, agent_id: str) -> None:
    """Main chat loop."""
    print("\n" + "="*50)
    print("🎯 LETTA AGENT CHAT DEMO")
    print("="*50)
    print("Commands:")
    print("  /stream - Toggle streaming mode")
    print("  /agent - Get agent info")
    print("  /memory - View agent memory")
    print("  /quit - Exit the chat")
    print("-" * 50)
    
    streaming_mode = False
    
    while True:
        try:
            user_input = input("\n💬 Enter your message: ").strip()
            
            if not user_input:
                continue
                
            # Handle commands
            if user_input.lower() == '/quit':
                print("👋 Goodbye!")
                break
            elif user_input.lower() == '/stream':
                streaming_mode = not streaming_mode
                print(f"🔄 Streaming mode: {'ON' if streaming_mode else 'OFF'}")
                continue
            elif user_input.lower() == '/agent':
                try:
                    agent_info = client.agents.get(agent_id)
                    print(f"🤖 Agent ID: {agent_info.id}")
                    print(f"📝 Model: {agent_info.model}")
                    print(f"🔧 Tools: {agent_info.tools}")
                except Exception as e:
                    print(f"❌ Error getting agent info: {e}")
                continue
            elif user_input.lower() == '/memory':
                try:
                    memory_blocks = client.agents.memory.list(agent_id)
                    print("🧠 Agent Memory Blocks:")
                    for block in memory_blocks:
                        print(f"  📋 {block.label}: {block.value[:100]}...")
                except Exception as e:
                    print(f"❌ Error getting memory: {e}")
                continue
            
            # Send message
            if streaming_mode:
                send_message_stream(client, agent_id, user_input)
            else:
                send_message_sync(client, agent_id, user_input)
                
        except KeyboardInterrupt:
            print("\n👋 Goodbye!")
            break
        except Exception as e:
            print(f"❌ Unexpected error: {e}")


def main():
    """Main function."""
    print("🚀 Starting Letta Agent Chat Demo")
    
    # Setup client
    try:
        client = setup_client()
    except Exception as e:
        print(f"❌ Failed to setup client: {e}")
        print("💡 Make sure you have:")
        print("   - Set LETTA_API_KEY for Letta Cloud, or")
        print("   - Started a local Letta server")
        sys.exit(1)
    
    # Create or use existing agent
    agent_id = os.getenv("LETTA_AGENT_ID")
    
    if agent_id:
        print(f"🔍 Using existing agent: {agent_id}")
        try:
            # Verify agent exists
            client.agents.get(agent_id)
        except Exception as e:
            print(f"❌ Agent not found: {e}")
            print("🔨 Creating new agent...")
            agent_id = create_agent(client)
    else:
        agent_id = create_agent(client)
        print(f"💡 Tip: Set LETTA_AGENT_ID={agent_id} to reuse this agent")
    
    # Start chat loop
    chat_loop(client, agent_id)


if __name__ == "__main__":
    main() 