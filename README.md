# AgentFusion

A comprehensive AI agent management platform that provides multi-agent orchestration, agent building tools, prompt version management, and real-time chat interface. AgentFusion enables you to create, configure, and deploy AI agents through individual agents, group chats, and graph flows with a complete backend infrastructure.

## 🌟 Features

- **Multi-Agent Orchestration**: Deploy individual agents, group chats, or complex graph flows
- **Database Infrastructure**: PostgreSQL with SQLAlchemy ORM for persistent data storage
- **User Authentication**: Complete user management with bcrypt password hashing and activity logging
- **Web Interface**: Chainlit-powered real-time chat interface with WebSocket support
- **MCP Integration**: Model Context Protocol support for external tool integration
- **Prompt Management**: Version-controlled prompt system with built-in optimization agents
- **Activity Logging**: Comprehensive audit trail for all user actions and system events
- **Flexible Configuration**: JSON-based configuration system for agents, workflows, and integrations

## 🚀 Quick Start

### 1. Installation

```bash
# Create and activate virtual environment using uv
uv venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Install the package in development mode
cd python/packages/agent_fusion
uv pip install -e .
```

### 2. Database Setup

```bash
# Set up PostgreSQL database (production)
# Or use SQLite for testing - automatically configured

# Run database migrations if needed
# Database schema is located in sql/progresdb.sql
```

### 3. Environment Setup

Create a `.env` file in the project root with your API keys:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DASHSCOPE_API_KEY=your_aliyun_api_key_here
GEMINI_API_KEY=your_google_api_key_here

# Database configuration (optional - defaults to SQLite for testing)
DATABASE_URL=postgresql://user:password@localhost/agentfusion
```

### 4. Launch Web Interface

```bash
chainlit run python/packages/agent_fusion/src/chainlit_web/run.py
```

The web interface will be available at `http://localhost:8000`

## 📋 Project Structure

```
AgentFusion/
├── config/                          # Configuration files
│   ├── prompt/                      # Agent prompts organized by type
│   │   ├── agent/                   # Individual agent prompts
│   │   ├── group_chat/              # Group chat selectors
│   │   └── ui_design/               # UI design prompts
│   └── mem/                         # Memory configurations
├── python/packages/agent_fusion/    # Main Python package
│   └── src/
│       ├── data_layer/              # Database layer with SQLAlchemy ORM
│       │   ├── models/              # Business logic models
│       │   └── tables/              # Database table definitions
│       ├── schemas/                 # Pydantic data models
│       ├── builders/                # Core builders for agents/workflows
│       ├── chainlit_web/            # Web interface with user authentication
│       │   ├── user/                # User management and authentication
│       │   └── ui_hook/             # UI integration hooks
│       ├── model_client/            # Model client implementations
│       ├── base/                    # Base utilities and MCP support
│       ├── tools/                   # Agent tools and utilities
│       └── dump/                    # Configuration export utilities
├── sql/                            # Database schema and migration scripts
├── config.json                     # Main configuration file
├── dumped_config/                  # Exported configurations
├── CLAUDE.md                       # Project memory and guidelines
└── requirements.txt                # Python dependencies
```

## 🏗️ Architecture

### Technology Stack
- **Backend**: Python 3.11+ with FastAPI + Chainlit
- **Database**: PostgreSQL (production) / SQLite (testing)
- **ORM**: SQLAlchemy 2.0 with async support
- **Authentication**: Custom user authentication with bcrypt
- **Agent Framework**: AutoGen AgentChat
- **Frontend**: Chainlit with real-time WebSocket connections

### Database Architecture
- **User Management**: User accounts, authentication, and activity logging
- **Agent System**: Agent configurations and model clients
- **Chat System**: Threads, steps, elements, and feedback
- **Prompt Management**: Prompts with version control
- **Audit Trail**: Comprehensive activity logging with JSONB metadata

## 🤖 Agent Types

### Individual Agents
- **file_system**: File and directory operations via MCP
- **product_manager**: Product requirement documentation
- **prompt_refiner**: Prompt optimization and refinement
- **executor**: Task execution specialist
- **template_extractor**: Extract parameters from prompt templates
- **prompt_specialization**: Interactive prompt customization

### Group Chats
- **prompt_flow**: Collaborative prompt development workflow
- **hil**: Human-in-the-loop product management

### Graph Flows
- **prompt_specialization**: Template extraction → customization → execution workflow

## ⚙️ Configuration

### Agent Configuration

Agents are defined in `config.json` under the `agents` section:

```json
{
  "agents": {
    "your_agent": {
      "name": "your_agent",
      "description": "Agent description",
      "labels": ["tag1", "tag2"],
      "type": "assistant_agent",
      "prompt_path": "agent/your_prompt.md",
      "model_client": "deepseek-chat_DeepSeek",
      "mcp_tools": ["file_system"]
    }
  }
}
```

### Group Chat Configuration

```json
{
  "group_chats": {
    "your_group": {
      "name": "your_group",
      "description": "Group description",
      "type": "selector_group_chat",
      "selector_prompt": "group_chat/your_selector.md",
      "model_client": "deepseek-chat_DeepSeek",
      "participants": ["agent1", "agent2", "human_proxy"]
    }
  }
}
```

### Graph Flow Configuration

```json
{
  "graph_flows": {
    "your_flow": {
      "name": "your_flow",
      "description": "Workflow description",
      "type": "graph_flow",
      "participants": ["agent1", "agent2"],
      "nodes": [
        ["agent1", "agent2"],
        ["agent2", {"condition": "agent1"}]
      ],
      "start_node": "agent1"
    }
  }
}
```

## 🔧 Usage Examples

### Export Configuration

Use the dump utilities to export your configuration:

```python
from dump import dump_agents, dump_group_chats

# Export specific components
dump_agents(["file_system"], "dumped_config")
dump_group_chats(["prompt_flow"], "dumped_config")
```

## 🛠️ Development

### Database Development
```bash
# Run tests
python -m pytest python/packages/agent_fusion/tests/ -v

# Test specific model
python -m pytest python/packages/agent_fusion/tests/test_user_model.py -v
```

### Adding New Agents

1. Create a prompt file in `config/prompt/agent/`
2. Add agent configuration to `config.json`
3. Update database models if needed (data_layer/models/)
4. Add tests for new functionality
5. Test via the web interface

### Database Migrations

1. Update SQL schema in `sql/progresdb.sql`
2. Update SQLAlchemy models in `data_layer/models/tables/`
3. Update business logic models in `data_layer/models/`
4. Add comprehensive tests

### Custom MCP Tools

Define MCP servers in the `mcpServers` section of `config.json`:

```json
{
  "mcpServers": {
    "your_tool": {
      "command": "your_command",
      "args": ["arg1", "arg2"],
      "env": {},
      "read_timeout_seconds": 30
    }
  }
}
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Make your changes
4. Update tests and documentation
5. Submit a pull request

## 📄 License

MIT License - see LICENSE file for details

## 🙏 Acknowledgments

Built on top of [AutoGen](https://github.com/microsoft/autogen) - a powerful framework for multi-agent AI applications. Special thanks to the AutoGen team for their pioneering work in multi-agent orchestration.

## 📞 Support

- Create an [issue](https://github.com/your-repo/issues) for bug reports or feature requests
- Check the documentation in the `config/prompt/` directory for prompt examples
- Review `config.json` for configuration patterns
