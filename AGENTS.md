# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**AgentFusion** is a multi-agent AI orchestration platform built with Python, Chainlit, and AutoGen. It provides a database-backed infrastructure for creating, configuring, and deploying AI agents through individual agents, group chats, and graph flows.

## Technology Stack

- **Language**: Python 3.11+
- **Backend**: FastAPI + Chainlit
- **Database**: PostgreSQL (production) / SQLite (testing)
- **ORM**: SQLAlchemy 2.0 with async support
- **Agent Framework**: AutoGen AgentChat (v0.6.4)
- **Package Management**: uv

## Common Commands

### Installation
```bash
# Create and activate virtual environment
uv venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install dependencies
uv pip install -r requirements.txt

# Install main package in development mode
cd python/packages/agent_fusion
uv pip install -e .
```

### Running the Application
```bash
# Launch web interface (Chainlit)
chainlit run python/packages/agent_fusion/src/chainlit_web/run.py

# Web interface available at: http://localhost:8000
```

### Testing
```bash
# Run all tests
python -m pytest python/packages/agent_fusion/tests/ -v

# Run specific test file
python -m pytest python/packages/agent_fusion/tests/test_user_model.py -v

# Run tests from within package directory
cd python/packages/agent_fusion
python -m pytest tests/ -v
```

## Architecture Overview

The codebase follows a **layered architecture** with clear separation of concerns:

### Directory Structure
```
python/packages/agent_fusion/src/
├── data_layer/              # Database layer with SQLAlchemy ORM
│   ├── models/              # Business logic models
│   │   ├── tables/          # Database table definitions
│   │   ├── base_model.py    # Base model with common functionality
│   │   ├── user_model.py    # User authentication and management
│   │   └── *_model.py       # Other domain models
│   └── data_layer.py        # Main data layer interface
├── schemas/                 # Pydantic data models
│   ├── agents/              # Agent-specific schemas
│   ├── component.py         # Core component types
│   └── typed_components.py  # Typed wrapper classes
├── builders/                # Core builders for agents/workflows
│   ├── agent_builder.py     # Individual agent construction
│   └── ui_agent_builder.py  # Single agent mode builder
├── chainlit_web/            # Web interface
│   ├── user/                # User management and authentication
│   ├── ui_hook/             # UI integration hooks
│   └── run.py               # Main entry point
├── model_client/            # LLM client implementations
├── base/                    # Base utilities and MCP support
├── tools/                   # Agent tools and utilities
└── agent_memory/            # Memory context management
```

### Entry Points
- **Primary**: `python/packages/agent_fusion/src/chainlit_web/run.py` - Chainlit web interface
- **MCP Server**: `python/packages/agent_fusion_mcp/` - Model Context Protocol server

## Critical Development Rules

### 1. Import Path Rules (MANDATORY)
**Never use `..` (double dot) to traverse parent directories.** Always import from the project root or use same-level relative imports.

Project structure: `python/packages/agent_fusion/src/` contains the main package

- ✅ GOOD: `from agents.base.handoff import HandoffType` (from src root)
- ✅ GOOD: `from base.groupchat_queue import BaseChatQueue` (from src root)
- ✅ GOOD: `from .handoff import HandoffType` (same-level module)
- ❌ BAD: `from ..base.handoff import HandoffType` (parent traversal)
- ❌ BAD: `from base.handoff import HandoffType` (incorrect path)

**When package is installed** (`agent_fusion`), use direct imports without `.src`:
- ✅ GOOD: `from agent_fusion_mcp.database_server import DatabaseMCPServer`
- ✅ GOOD: `from schemas.agents.database_agent import`
- ❌ BAD: `from agent_fusion.src.schemas.agents.database_agent import`

### 2. Type Hint Guidelines (MANDATORY)
All code must include proper type hints following these rules:

**Use Generic/Union Types for Flexibility:**
- ✅ GOOD: `GroupChatType` (covers all group chat types)
- ❌ BAD: `TypedRoundRobinGroupChat` (too specific)

**Universal Component Types:**
- ✅ GOOD: `ComponentInfo | AgentConfig | GroupChatConfig`
- ❌ BAD: `AssistantAgent` (excludes other types)

**Union Syntax (Python 3.10+):**
```python
def process_component(component: AgentType | GroupChatType) -> ComponentInfo | None:
```

**Generic Type Variables:**
```python
T = TypeVar('T', bound=BaseGroupChat)
class AutoGenGroupChatQueue(BaseChatQueue, Generic[T]):
```

### 3. Database Schema Changes (CRITICAL)
When modifying database schema, **ALL related components must be updated together** in this order:
1. SQL schema (`sql/progresdb.sql`)
2. SQLAlchemy ORM table models (`data_layer/models/tables/`)
3. Pydantic schemas (`schemas/`)
4. Model methods that use the changed fields
5. Test cases for all changes

**Database Foreign Key Standard:** Foreign keys must be defined with the same name as the referenced table's field (e.g., `user_id` for `User.id`) and include appropriate constraints.

### 4. Testing Requirements (MANDATORY)
**Every new data module interface MUST include comprehensive test code:**
- All CRUD operations must be tested
- All edge cases and error conditions must be covered
- Both successful and failure scenarios must be tested
- Test coverage should be comprehensive for all public methods

**Running tests:**
```bash
# Always use this format
python -m pytest python/packages/agent_fusion/tests/ -v
```

### 5. ORM Usage (MANDATORY)
**Always prefer SQLAlchemy ORM over raw SQL queries:**

- ✅ GOOD: Use `session.execute(select(UserTable).where(...))`
- ❌ BAD: Use `session.execute(text("SELECT * FROM users..."))`

**Session Management Pattern:**
```python
async with await self.db.get_session() as session:
    try:
        # Database operations
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise
```

## Key Architectural Patterns

### Multi-Agent Architecture
- **Individual Agents**: AssistantAgent, UserProxyAgent, CodeAgent
- **Group Chats**: Selector-based and round-robin group chats
- **Graph Flows**: Complex workflow orchestration with conditional routing
- **Single Agent Mode**: Queue-based wrapper for individual agents with run_stream integration

### Database Design Patterns
1. **Hybrid ID Strategy**: SERIAL (internal) + UUID (external) for security
2. **JSONB Fields**: Used for flexible metadata storage (user_metadata, action_details)
3. **Soft Deletes**: `is_active` flags instead of hard deletes
4. **Activity Logging**: Comprehensive audit trail in `user_activity_logs` table

### Memory Management
- **Configurable Memory Models**: Agent's reasoning model can be decoupled from memory/context operations via `memory_model_client` field
- **Memory Context**: `MemoryContext` class handles intelligent memory initialization using LLM-based search before conversations start

### Authentication System
- **Password Hashing**: bcrypt with salt
- **Account Locking**: 5 failed attempts = 30min lock
- **Activity Logging**: All auth events logged to `user_activity_logs`
- **Database-Agnostic Types**: Custom IPAddress type for PostgreSQL INET / SQLite String compatibility

## Database Type Compatibility

For fields requiring different types per database:

```python
class IPAddress(TypeDecorator):
    impl = String
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(INET())
        else:
            return dialect.type_descriptor(String(45))
```

## Configuration System

### Agent Configuration (config.json)
```json
{
  "agents": {
    "your_agent": {
      "name": "your_agent",
      "type": "assistant_agent",
      "prompt_path": "agent/your_prompt.md",
      "model_client": "deepseek-chat_DeepSeek",
      "memory_model_client": "gemini-2.5-flash-preview-04-17_Google",
      "mcp_tools": ["file_system"]
    }
  }
}
```

### MCP Servers Configuration
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

## Environment Setup

Create `.env` file in project root:
```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DASHSCOPE_API_KEY=your_aliyun_api_key_here
GEMINI_API_KEY=your_google_api_key_here

# Database (optional - defaults to SQLite for testing)
DATABASE_URL=postgresql://user:password@localhost/agentfusion
```

## Important Field Naming Conventions
- Use `user_metadata` not `metadata` (SQLAlchemy reserves `metadata`)
- Use `action_details` as JSONB for activity logging
- Use `ip_address` with database-agnostic IPAddress type

## Known Missing Components
These tables exist in SQL schema but lack SQLAlchemy models:
- `user_sessions`
- `user_preferences`
- `user_api_keys`
- `password_reset_tokens`

## Recent Major Changes

### 2025-02-05: Configurable Memory Model & Memory Context
- Decoupled agent's reasoning model from memory/context operations
- Added `memory_model_client` field to `AssistantAgentConfig` and `AgentBuilder`
- Added `memory_model_client_id` to `agents` table
- Implemented `init_memory` in `MemoryContext` for intelligent memory initialization

### 2025-07-26: Single Agent Mode & Type Safety
- Added `AutoGenAgentChatQueue` for queue-based single agent execution
- Enhanced `UIAgentBuilder` for single agent mode
- Applied mandatory type hint guidelines with generic/union types
- Created `schemas/typed_components.py` module for typed wrapper classes

## Development Workflow

1. **Before Making Changes**: Always read this file
2. **Coordinated Schema Changes**: Update SQL → ORM tables → schemas → models → tests together
3. **Testing**: Run tests after any data layer changes
4. **Activity Logging**: Log significant user actions for audit trail
5. **Error Handling**: Always use proper session management with rollback
6. **Type Safety**: Follow mandatory type hint guidelines
7. **Import Rules**: Never use `..` for parent directory traversal

---

## Memory System Conventions (Added 2026-02-10)

### 8. SQLAlchemy ORM - No Raw SQL

**Strict rule: No `text()`, no string SQL construction.**

Use ORM methods exclusively:

```python
# ✅ CORRECT
select(Model).where(Model.field == value)
Model.embedding.op('<=>')(vector)  # pgvector
func.sum(Model.weight).label('score')

# ❌ INCORRECT
text("SELECT * FROM table...")
session.execute(f"SELECT ... {variable}")
```

### 10. Tool Design Rules

1. **LLM extracts keywords directly** into tool parameters - no separate keyword extraction tool
2. **Single tool call pattern**: Use `tool.run_json()` consistently, no streaming
3. **handoff is the ONLY termination mechanism**
4. **Atomic tools**: One operation per tool, LLM composes them via multiple calls

### 11. Memory Injection Strategy

| Context | Method | When |
|---------|--------|------|
| User chat message | Direct expansion | Content injected immediately as SystemMessage |
| Command execution | Slot placeholder `[memory:key]` | Resolved at execution time via exec_locals |
