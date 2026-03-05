# Configurable Memory Model Client PRD

## 1. Overview
Currently, the `AgentBuilder` initializes the `model_context` (which often handles memory) using the same `model_client` as the agent itself, or a default one. 
This PRD proposes decoupling the `model_client` used for the Agent's reasoning from the `model_client` used for Memory/Context operations (like summarization, retrieval, or context management).

## 2. Problem Statement
*   **Cost/Performance Mismatch:** The main agent might use a high-intelligence, expensive model (e.g., GPT-4, DeepSeek-V3). However, memory operations (summarizing logs, searching context) often require less intelligence but higher speed or lower cost (e.g., GPT-3.5, Gemini Flash).
*   **Context Window Constraints:** The memory system might need a model with a massive context window to process large history logs, while the main agent might be optimized for reasoning.
*   **Flexibility:** Users cannot currently configure which model drives the memory/context logic.

## 3. Core Requirements

### 3.1. Database Changes
*   **Table:** `agents`
*   **New Column:** `memory_model_client_id` (Integer, Nullable, Foreign Key to `model_clients.id`)
*   **Description:** References the model client configuration to be used specifically for the agent's `model_context` (Memory).

### 3.2. Schema Changes (`schemas/agent.py`)
*   **Class:** `AssistantAgentConfig` (and potentially `CodeAgentConfig` if applicable).
*   **New Field:** `memory_model_client` (str | None).
*   **Description:** The label/name of the model client to use for memory. If `None`, it defaults to the agent's main `model_client` or a system default.

### 3.3. Application Logic (`AgentBuilder`)
*   **Location:** `python/packages/agent_fusion/src/builders/agent_builder.py`
*   **Function:** `build` and `build_model_context`.
*   **Logic:**
    1.  In `build` method, check if `agent_info.memory_model_client` is set.
    2.  If set, resolve this string to a `ModelClient` instance using `model_client_builder`.
    3.  Pass this specific `memory_model_client` to `self.build_model_context(...)`.
    4.  Update `build_model_context` signature to accept `memory_model_client` (distinct from the agent's main `model_client`).

## 4. Implementation Plan

### 4.1. Database Migration
Update `sql/progresdb.sql` to include the new column.

```sql
ALTER TABLE agents ADD COLUMN memory_model_client_id INTEGER REFERENCES model_clients(id);
CREATE INDEX idx_agents_memory_model_client ON agents(memory_model_client_id);
```

### 4.2. Python Schema Update
Modify `python/packages/agent_fusion/src/schemas/agent.py`:

```python
class AssistantAgentConfig(BaseAgentConfig):
    # ... existing fields ...
    model_client: str
    memory_model_client: str | None = None # New optional field
    # ...
```

### 4.3. Builder Logic Update
Modify `python/packages/agent_fusion/src/builders/agent_builder.py`:

```python
    # Logic to fetch memory model client if configured
    memory_model_client_instance = None
    if agent_info.memory_model_client:
         memory_model_config = await model_client_builder.get_component_by_name(agent_info.memory_model_client)
         # We need to manage the lifecycle of this client similarly to the main one
         # Or pass the config/builder to build_model_context to handle it
```
