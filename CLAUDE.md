# CLAUDE.md - AgentFusion Project Memory

This file contains long-term memory and context for Claude when working on the AgentFusion project.

## Project Overview

**AgentFusion** is a comprehensive AI agent management platform that provides:
- Multi-agent orchestration and communication
- Agent building and configuration tools
- Prompt version management system
- User authentication and activity logging
- Real-time chat interface using Chainlit
- PostgreSQL database with SQLAlchemy ORM

## Technology Stack

### Backend
- **Language**: Python 3.11+
- **Framework**: FastAPI + Chainlit
- **Database**: PostgreSQL (production) / SQLite (testing)
- **ORM**: SQLAlchemy 2.0 with async support
- **Authentication**: Custom user authentication with bcrypt
- **Agent Framework**: AutoGen AgentChat

### Frontend
- **UI Framework**: Chainlit for chat interface
- **Real-time**: WebSocket connections for live chat

### Infrastructure  
- **Database**: PostgreSQL with JSONB support
- **Testing**: pytest with asyncio support
- **Environment**: .env configuration

## Database Architecture

### Core Tables Structure
- **User** (`"User"`) - User accounts and authentication
- **user_activity_logs** - Comprehensive activity logging
- **threads** - Conversation/chat sessions
- **steps** - Individual messages/actions in conversations
- **elements** - File attachments and media
- **feedbacks** - User feedback and ratings
- **agents** - AI agent configurations
- **model_clients** - LLM client configurations
- **prompts** - Prompt definitions and versioning
- **prompt_versions** - Version history for prompts

### Key Database Design Patterns
1. **Hybrid ID Strategy**: SERIAL (internal) + UUID (external) for security
2. **JSONB Fields**: Used for flexible metadata storage
3. **Activity Logging**: Comprehensive audit trail for all user actions
4. **Soft Deletes**: is_active flags instead of hard deletes

## Code Organization

```
python/packages/agent_fusion/src/
├── data_layer/
│   ├── models/
│   │   ├── tables/          # SQLAlchemy ORM models
│   │   ├── base_model.py    # Base model with common functionality
│   │   ├── user_model.py    # User authentication and management
│   │   ├── feedback_model.py # Feedback and rating system
│   │   └── *_model.py       # Other domain models
│   └── data_layer.py        # Main data layer interface
├── tests/                   # Test files
└── ...
```

## Important Implementation Details

### Authentication System
- **Password Hashing**: bcrypt with salt
- **Account Locking**: 5 failed attempts = 30min lock
- **Activity Logging**: All auth events logged to user_activity_logs
- **Session Management**: Track login times and reset failed attempts

### Database Field Naming Conventions
- Use `user_metadata` not `metadata` (SQLAlchemy reserves `metadata`)
- Use `action_details` as JSONB for activity logging
- Use `ip_address` with database-agnostic IPAddress type (INET for PostgreSQL, String for SQLite)

### Common Patterns
1. **ORM over Raw SQL**: Always prefer SQLAlchemy ORM to raw SQL queries
2. **Session Management**: Use `async with await self.db.get_session() as session:`
3. **Error Handling**: Always rollback on exceptions and log errors
4. **Type Safety**: Use proper type hints and dataclasses
5. **Import Rules**: **MANDATORY** - Always reference imports from project root based on pyproject.toml structure
   - Project structure: `python/packages/agent_fusion/src/` contains the main package
   - ✅ GOOD: `from agents.base.handoff import HandoffType` (from src root, full path)
   - ✅ GOOD: `from base.groupchat_queue import BaseChatQueue` (from src root, full path)
   - ✅ GOOD: `from .handoff import HandoffType` (same-level module within same directory)
   - ❌ BAD: `from ..base.handoff import HandoffType` (multiple parent directory traversal)
   - ❌ BAD: `from base.handoff import HandoffType` (incorrect - handoff is in agents/base not base)
   - **Rule**: Never use `..` to traverse up directories; always import from src root with full path or same level

### Type Hint Guidelines
**MANDATORY REQUIREMENT**: All code must include proper type hints following these rules:
1. **Generic Types for Flexibility**: Use generic/union types instead of specific concrete types
   - ✅ GOOD: `GroupChatType` (covers all group chat types)
   - ❌ BAD: `TypedRoundRobinGroupChat` (too specific)
2. **Universal Component Types**: When dealing with components that could be agents or group chats:
   - ✅ GOOD: `ComponentInfo | AgentConfig | GroupChatConfig`
   - ❌ BAD: `AssistantAgent` (excludes other types)
3. **Function Signatures**: All functions must have complete type hints for parameters and return values
4. **Generic Type Variables**: Use `TypeVar` and `Generic` for reusable code:
   ```python
   T = TypeVar('T', bound=BaseGroupChat)
   class AutoGenGroupChatQueue(BaseChatQueue, Generic[T]):
   ```
5. **Union Types**: Use `|` syntax for union types in Python 3.10+:
   ```python
   def process_component(component: AgentType | GroupChatType) -> ComponentInfo | None:
   ```

## Recent Major Changes

### 2025-07-26: Single Agent Mode Implementation
- **AutoGenAgentChatQueue**: New queue-based wrapper for single agents supporting run_stream integration
- **UIAgentBuilder**: Builder class for single agent mode following same patterns as group chat builders
- **Enhanced User Session Management**: Updated to support both agents and group chats in component map
- **Comprehensive Testing**: 13 test cases covering core functionality, error handling, and integration scenarios
- **Type Safety Improvements**: Applied new type hint guidelines with generic/union types instead of specific concrete types

### 2025-07-26: Type Hint Guidelines Addition & Module Refactoring
- **MANDATORY REQUIREMENT**: All code must include proper type hints following project guidelines
- **Generic Types**: Use `GroupChatType` instead of `TypedRoundRobinGroupChat` for flexibility
- **Union Types**: Use `ComponentInfo | AgentConfig | GroupChatConfig` for universal component handling
- **Type Aliases**: Created `AgentConfigTypes`, `ComponentConfigTypes`, and `InputFuncType` for consistency
- **Module Separation**: Created `schemas/typed_components.py` to separate typed wrapper classes following CR feedback
  - Moved `TypedSelectorGroupChat`, `TypedRoundRobinGroupChat` from `component.py`
  - Moved `GroupChatType`, `AgentType` union types to dedicated module
  - Updated all import references across codebase

### 2025-07-24: Database Schema Alignment
- Fixed field type mismatches between SQL schema and SQLAlchemy models
- Updated UserActivityLogsTable to match PostgreSQL schema exactly
- Added missing fields to UserTable (avatar_url, timezone, language, etc.)
- Created database-agnostic IPAddress type for ip_address fields

### 2025-07-24: FeedbackModel Refactoring  
- Converted all raw SQL queries to pure SQLAlchemy ORM
- Enhanced error handling and transaction management
- Added proper JOIN operations with StepsTable
- Fixed metadata field naming conflicts

### 2025-07-24: User Authentication Fixes
- Fixed func.current_timestamp() issues by using datetime.utcnow()
- Corrected metadata field access (user_metadata vs metadata)
- Enhanced activity logging with proper JSONB structure
- Fixed failed login attempt tracking and account locking

## Testing Guidelines

### **MANDATORY REQUIREMENT**
**Every new data module interface MUST include comprehensive test code**
- All CRUD operations must be tested
- All edge cases and error conditions must be covered
- Both successful and failure scenarios must be tested
- Test coverage should be comprehensive for all public methods

### Test Structure
- **File**: `tests/test_user_model.py` (54 tests, all passing)
- **Database**: Uses SQLite for test compatibility
- **Fixtures**: sqlite_db, user_model, sample_user, etc.
- **Pattern**: Class-based test organization (TestUserAuthenticate, TestUserModelCreateUser, etc.)

### Running Tests
```bash
cd E:\ZenWayne\AgentFusion
python -m pytest python\packages\agent_fusion\tests\test_user_model.py -v
```

## Common Commands and Patterns

### Database Type Compatibility
```python
# For fields that need different types per database
class IPAddress(TypeDecorator):
    impl = String
    def load_dialect_impl(self, dialect):
        if dialect.name == 'postgresql':
            return dialect.type_descriptor(INET())
        else:
            return dialect.type_descriptor(String(45))
```

### Activity Logging Pattern
```python
await self._log_activity_orm(session, user_id, "login_success", details={
    "username": username,
    "ip_address": ip_address,
    "last_login": now.isoformat()
})
```

### ORM Query Patterns
```python
# Basic select
stmt = select(UserTable).where(UserTable.username == username)
result = await session.execute(stmt)
user = result.scalar_one_or_none()

# Complex aggregation
stmt = select(
    func.count().label('total'),
    func.avg(FeedbackTable.value).label('avg_rating')
).where(FeedbackTable.thread_id == thread_id)
```

## Known Issues and TODOs

### Missing Table Models
These tables exist in SQL schema but lack SQLAlchemy models:
- `user_sessions` 
- `user_preferences`
- `user_api_keys` 
- `password_reset_tokens`

### Type Mismatches (Lower Priority)
- Steps and Elements tables use String instead of UUID for IDs
- Some field size mismatches (resolved for critical fields)

## Development Workflow

1. **Before Making Changes**: Always read this CLAUDE.md file
2. **Coordinated Schema Changes**: When modifying SQL schema or models, ALL related components MUST be updated together in this order:
   - SQL schema (`sql/progresdb.sql`)
   - SQLAlchemy ORM table models (`data_layer/models/tables/`)
   - Pydantic ComponentInfo schemas (`schemas/`)
   - Model methods that use the changed fields
   - Test cases for all changes
3. **Database Changes**: Update both SQL schema AND SQLAlchemy models
4. **Testing**: Run tests after any data layer changes AND write new tests for new interfaces
5. **Activity Logging**: Log significant user actions for audit trail
6. **Error Handling**: Always use proper session management with rollback

## Contact and Context

This project uses:
- **Windows Development Environment**: `E:\ZenWayne\AgentFusion`
- **Python Virtual Environment**: `.venv`
- **Primary IDE**: VS Code
- **Database**: PostgreSQL (production), SQLite (testing)

When working on this project, prioritize:
1. Database consistency between schema and models
2. Test coverage and passing tests  
3. Proper error handling and logging
4. Type safety and ORM usage over raw SQL
5. Security best practices (especially for authentication)
6. **Mandatory test coverage**: Every new data module interface MUST include comprehensive test code
7. **Coordinated schema changes**: When modifying SQL schema or models, ALL related components must be updated together (SQL → ORM tables → ComponentInfo schemas → model methods → tests)

---
*Last Updated: 2025-07-24*
*This file should be updated whenever significant architectural changes are made*