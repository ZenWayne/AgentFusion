# AgentFusion

A powerful multi-agent orchestration framework built on ag2. AgentFusion enables you to create, configure, and deploy complex AI agent workflows through three distinct interaction patterns: individual agents, group chats, and graph flows.

## 🌟 Features

- **Multi-Agent Orchestration**: Deploy individual agents, group chats, or complex graph flows
- **Flexible Configuration**: JSON-based configuration system for agents, workflows, and integrations
- **Web Interface**: Chainlit-powered web UI for interactive agent conversations
- **MCP Integration**: Model Context Protocol support for external tool integration
- **Prompt Engineering**: Built-in agents for prompt optimization and specialization
- **File System Operations**: MCP-enabled file system agent for document management

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

### 2. Environment Setup

Create a `.env` file in the project root with your API keys:

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DASHSCOPE_API_KEY=your_aliyun_api_key_here
GEMINI_API_KEY=your_google_api_key_here
```

### 3. Launch Web Interface

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
│       ├── schemas/                 # Pydantic data models (formerly dataclass)
│       ├── builders/                # Core builders for agents/workflows
│       ├── chainlit_web/            # Web interface
│       ├── model_client/            # Model client implementations
│       ├── base/                    # Base utilities and MCP support
│       └── dump/                    # Configuration export utilities
├── config.json                     # Main configuration file
├── dumped_config/                  # Exported configurations
└── requirements.txt                # Python dependencies
```

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

### Adding New Agents

1. Create a prompt file in `config/prompt/agent/`
2. Add agent configuration to `config.json`
3. Test via the web interface

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

Built on top of [ag2](https://github.com/ag2ai/ag2) - an incredible framework for multi-agent AI applications. Special thanks to the ag2 team for their pioneering work in multi-agent orchestration.

## 📞 Support

- Create an [issue](https://github.com/your-repo/issues) for bug reports or feature requests
- Check the documentation in the `config/prompt/` directory for prompt examples
- Review `config.json` for configuration patterns
