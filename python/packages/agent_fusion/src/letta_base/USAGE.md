# Letta Agent Chat Demo Usage Guide

This demo shows how to use the Letta Python SDK to create and chat with a stateful agent.

## Prerequisites

### Option 1: Using Letta Cloud (Recommended)
1. Sign up for a free account at [app.letta.com](https://app.letta.com)
2. Create an API key at [app.letta.com/api-keys](https://app.letta.com/api-keys)
3. Set the environment variable:
   ```bash
   export LETTA_API_KEY="your-api-key-here"
   ```

### Option 2: Self-hosted Letta Server
1. Install Letta: `pip install letta`
2. Start the server: `letta server`
3. The demo will automatically connect to `http://localhost:8283`

## Installation

1. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Run the demo:
   ```bash
   python chat_demo.py
   ```

## Features

### Basic Chat
- Type messages to chat with the agent
- The agent maintains memory across conversations
- Responses show different message types (assistant, reasoning, tool calls)

### Commands
- `/stream` - Toggle between streaming and non-streaming modes
- `/agent` - View agent information (ID, model, tools)
- `/memory` - View agent's memory blocks
- `/quit` - Exit the chat

### Agent Capabilities
- **Memory Management**: The agent remembers previous conversations
- **Web Search**: Can search the internet for information
- **Code Execution**: Can run Python code for calculations and analysis
- **Reasoning**: Shows internal reasoning process (when available)

## Example Usage

```bash
$ python chat_demo.py
🚀 Starting Letta Agent Chat Demo
🌩️  Connecting to Letta Cloud...
🤖 Creating new agent...
✅ Agent created successfully! ID: agent-xxxxx
💡 Tip: Set LETTA_AGENT_ID=agent-xxxxx to reuse this agent

==================================================
🎯 LETTA AGENT CHAT DEMO
==================================================
Commands:
  /stream - Toggle streaming mode
  /agent - Get agent info
  /memory - View agent memory
  /quit - Exit the chat
--------------------------------------------------

💬 Enter your message: Hello! What can you help me with?
👤 You: Hello! What can you help me with?
🤖 Agent response:
💬 Hello! I'm Alex, your AI assistant specialized in explaining AI concepts. I'm here to help you understand how Letta agents work and explore their capabilities.

Since we're working with a Letta agent demo, I can help you with:

1. **Understanding stateful agents** - How agents maintain memory and context across conversations
2. **Exploring agent capabilities** - I have access to web search and code execution tools
3. **AI concepts** - Explaining how different AI technologies work
4. **Code examples** - Running Python code to demonstrate concepts

What would you like to explore first?
```

## Key Features Demonstrated

### 1. Stateful Memory
The agent remembers information from previous messages in the conversation. This is different from stateless APIs where you need to send the full conversation history.

### 2. Memory Blocks
The agent has structured memory blocks:
- **Human**: Information about you
- **Persona**: The agent's personality and role
- **Project Context**: Information about the current project/demo

### 3. Tool Integration
The agent can use tools like:
- Web search for real-time information
- Code execution for calculations and analysis

### 4. Streaming vs Non-streaming
Toggle between two response modes:
- **Non-streaming**: Get complete responses at once
- **Streaming**: See responses as they're generated (like ChatGPT)

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `LETTA_API_KEY` | Your Letta Cloud API key | Yes (for Letta Cloud) |
| `LETTA_AGENT_ID` | Existing agent ID to reuse | No |
| `LETTA_BASE_URL` | Custom server URL | No (defaults to localhost:8283) |

## Troubleshooting

### Common Issues

1. **"Failed to setup client"**
   - Make sure you have `LETTA_API_KEY` set for Letta Cloud
   - Or ensure a local Letta server is running

2. **"Agent not found"**
   - The agent ID in `LETTA_AGENT_ID` doesn't exist
   - The demo will create a new agent automatically

3. **Import errors**
   - Run `pip install -r requirements.txt`
   - Make sure you're using Python 3.7+

### Need Help?
- [Letta Documentation](https://docs.letta.com/)
- [Letta Discord](https://discord.gg/letta)
- [GitHub Issues](https://github.com/letta-ai/letta) 