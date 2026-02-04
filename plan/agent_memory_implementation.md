# Agent Memory System Implementation Plan

## 1. Overview
Implement a persistent, two-layer memory system for AgentFusion agents. The system will use `MemoryContext` (inheriting from `autogen_core.model_context.ChatCompletionContext`) to manage context window efficiency by replacing large outputs with placeholders and allowing on-demand retrieval from a PostgreSQL backend.

## 2. Component Design

### 2.1. Database Schema
- **Table:** `agent_memories`
- **Fields:**
    - `id` (UUID, PK)
    - `user_id` (INTEGER, FK to User)
    - `agent_id` (INTEGER, FK to agents)
    - `thread_id` (UUID, FK to threads)
    - `memory_key` (VARCHAR, Indexed) - The placeholder ID
    - `memory_type` (VARCHAR) - e.g., 'command_output', 'user_preference'
    - `summary` (TEXT) - Brief description for Layer 1
    - `content` (TEXT) - Raw content for Layer 2
    - `content_metadata` (JSONB)
    - `created_at` (TIMESTAMP)

### 2.2. Core Python Component: `MemoryContext`
- **Location:** `python/packages/agent_fusion_memory/src/agent_fusion_memory/context.py`
- **Inheritance:** `autogen_core.model_context.ChatCompletionContext`
- **Responsibilities:**
    - **`add_message(message)` Override:**
        - Intercepts incoming messages.
        - Detects large content (via token count or heuristics).
        - Saves large content to DB via `store()`.
        - Replaces content in the message with `[MemoryRef: <key> - <summary>]`.
        - Scans for `[MemoryRef: ...]` in user prompts/agent intent.
        - If detail is needed (based on heuristic/intent), retrieves content via `retrieve()` and injects it temporarily or permanently.
    - **`store(content, ...)`:** Persists data to PostgreSQL.
    - **`retrieve(key)`:** Fetches data from PostgreSQL.
    - **`search(query)`:** Semantic/Keyword search (future-proof).
    - **`update_user_id(user_id)`:** Sets the current active user context for memory operations.

### 2.3. Agent Integration
- **Target:** `python/packages/agent_fusion/src/agents/codeagent.py` (and others)
- **Change:**
    - Update `CodeAgent` to use `MemoryContext` instead of `UnboundedChatCompletionContext` or `HeadAndTailChatCompletionContext` as the default context manager.
    - Expose `update_user_id` method on the agent which delegates to `self.model_context.update_user_id()`.

### 2.4. Orchestration & Builder
- **Target:** `python/packages/agent_fusion/src/chainlit_web/ui_hook/ui_agent_builder.py`
- **Change:**
    - In `build_with_queue`, after instantiating the agent, call `agent.update_user_id(user_id)`.
    - Ensure `user_id` is passed correctly from the Chainlit session/user context.

## 3. Implementation Steps

### Step 1: Database Setup
- [ ] Add `agent_memories` table to `sql/progresdb.sql`.
- [ ] Run the SQL script to update the local database.

### Step 2: Memory Package Implementation
- [ ] Create `python/packages/agent_fusion_memory/src/agent_fusion_memory/context.py`.
- [ ] Implement `MemoryContext` class.
- [ ] Implement database connection/ORM logic (using `sqlalchemy` or raw `asyncpg`).
- [ ] Implement `store`, `retrieve`, `add_message` logic.

### Step 3: Agent Integration
- [ ] Modify `python/packages/agent_fusion/src/agents/codeagent.py`.
- [ ] Switch to `MemoryContext`.
- [ ] Add `update_user_id` method.

### Step 4: Builder & UI Hook
- [ ] Update `python/packages/agent_fusion/src/chainlit_web/ui_hook/ui_agent_builder.py` to propagate `user_id`.

### Step 5: Testing & Verification
- [ ] Create a test script `test_memory_context.py`.
- [ ] Verify large output interception.
- [ ] Verify database storage.
- [ ] Verify retrieval and context substitution.

## 4. Dependencies
- `autogen-core`
- `sqlalchemy` / `asyncpg`
- `agent-fusion-memory` package