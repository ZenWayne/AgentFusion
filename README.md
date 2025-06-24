# AgentFusion

A powerful library for combining multiple AI assistant agents into a single, efficient workflow system. This repository provides tools and components to streamline the development of unified multi-agent applications using AutoGen.

## Features

- **Agent Fusion**: Combine multiple specialized agents into unified workflows
- **Efficient Orchestration**: Streamlined management of multi-agent interactions
- **Workflow Management**: Build complex multi-agent workflows with ease
- **AutoGen Studio Integration**: Export configurations for AutoGen Studio
- **Model Client Support**: Multiple model provider integrations
- **Configuration Management**: Centralized configuration system

## Installation

```bash
pip install -e .
```

## Quick Start

### 1. Configure Your Project

1. **Write agent prompts** under `config/prompt/`
2. **Configure agents or workflows** in `config/metadata.json`
3. **Set up test cases** in `test_case.json`

### 2. Run Your Application

```bash
python -m test.main
```

## AutoGen Studio Support

### Starting AutoGen Studio

```bash
python -m autogenstudio.cli ui --port 8080 --appdir ./tmp/app
```

### Export Configuration for AutoGen Studio

To export your configuration for use in AutoGen Studio, add the following case to the `cases` section in `test_case.json`:

```json
{
    "dump_file_system": {
        "name": "dump_file_system",
        "type": "dump",
        "model_client": ["deepseek-chat_DeepSeek"],
        "agents": ["file_system"],
        "group_chats": ["prompt_flow"],
        "output_path": "dumped_config"
    }
}
```

## Project Structure

```
AgentFusion/
├── config/                 # Configuration files
│   ├── prompt/            # Agent prompts
│   └── metadata.json      # Agent/workflow configurations
├── src/                   # Source code
│   ├── agent/            # Agent building components
│   ├── group_chat/       # Group chat functionality
│   ├── model_client/     # Model client implementations
│   └── ...
├── test/                 # Test files
├── dumped_config/        # Exported configurations
└── test_case.json        # Test case definitions
```

## Usage Examples

### Basic Agent Setup

1. Create your agent prompt in `config/prompt/agent/`
2. Configure the agent in `config/metadata.json`
3. Define test cases in `test_case.json`
4. Run with `python -m test.main`

### Workflow Configuration

Configure multi-agent workflows by defining group chats and their interactions in the metadata configuration.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## Thanks

This project is built on top of [AutoGen](https://github.com/microsoft/autogen), an amazing framework for building AI agents and workflows. Special thanks to the Microsoft AutoGen team for their groundbreaking work in making AI agent development accessible and powerful.

## License

[Add your license information here]

## Support

For issues and questions, please [create an issue](link-to-issues) or refer to the documentation.

```bash
pip install -e .
start autogen from python code
```
