# Agent Memory System PRD

## 1. Overview
The Agent Memory System is a specialized layer designed to manage the historical interaction information between users and agents. Its primary function is to persistently store critical information and command execution results to facilitate future interactions and complex task execution. 

To address the common challenge of "Context Window Explosion" (where long conversation histories exceed the LLM's token limit), this system implements a **Two-Layer Memory Architecture**. This ensures that the agent maintains a lightweight, efficient active context while retaining the ability to access deep, detailed information when necessary.

## 2. Core Objectives
*   **Context Optimization:** Prevent token overflow by keeping the active conversation context clean and concise.
*   **Persistent Recall:** Allow agents to remember important facts, preferences, and past command outputs across sessions or long conversations.
*   **Structured Storage:** Store command execution results (e.g., extensive logs, file contents, database query results) in a structured Key-Value (K-V) format.
*   **On-Demand Retrieval:** Provide a standard interface (Module-based, with optional MCP wrapper) for agents to query detailed information using lightweight references (placeholders) found in their context.
*   **User-Centric Context:** Link memories to specific users, enabling the automatic loading of user-layer memory (preferences, history, secrets) when an agent is invoked.

## 3. Architecture: The Two-Layer Memory Model

### Layer 1: Context Memory (The "Index")
This layer resides in the agent's active prompt/context window. Instead of raw data, it contains human-readable **Placeholders** or **Summaries**.
*   **Format:** `[MemoryRef: <ID> - <Brief Description> - <Token Count> tokens]` or structured natural language summaries.
*   **Purpose:** Provides the agent with the *existence* and *nature* of information without burdening the token count.
*   **Example:** instead of pasting 500 lines of logs, the context contains: `Command 'npm install' executed. Logs stored in [MemoryRef: cmd_log_123 - NPM Install Output - 2340 tokens]. Status: Success.`

### Layer 2: Detail Memory (The "Store")
This layer is the persistent backend storage where the actual raw data resides.
*   **Storage Mechanism:** PostgreSQL (using `jsonb` or text fields) or File System (for large blobs).
*   **Content:** Full command outputs, file contents, API responses, detailed user instructions.
*   **Access:** Accessed only via the Memory Interface/Agent when explicitly requested.

## 4. Functional Specifications

### 4.1. Memory Storage Workflow
1.  **Capture:** When an agent executes a command (via MCP or internal tool) that produces significant output.
2.  **Filter/Truncate:** The system intercepts the output. If it exceeds a defined threshold (e.g., 500 tokens), it triggers the memory storage process.
3.  **Store:** The full output is saved to the **Detail Memory** (Database/KV Store), associating it with the current `user_id`.
4.  **Summarize:** A unique ID and a brief summary/placeholder are generated.
5.  **Context Update:** The agent's context (Thread/Step) is updated with the Placeholder instead of the raw output.

### 4.2. Intelligent Memory Retrieval Workflow
1.  **Intent Analysis & Context Check:**
    *   When an agent receives a user instruction, it analyzes the intent against the current active context.
    *   **Concrete Intent:** If the intent is specific and sufficient context exists (e.g., "Connect to AgentFusion database" when previously discussed), the system **SKIPS** broad memory retrieval to optimize performance.
    *   **Ambiguous Intent:** If the intent is vague (e.g., "Connect to the DB") or missing parameters, the system **TRIGGERS** a memory search to resolve the ambiguity (e.g., finding the user's last used or preferred database).
2.  **Trigger:** 
    *   **Explicit:** An agent encounters a Placeholder (e.g., `[MemoryRef: cmd_log_123]`) and determines it needs the specific details.
    *   **Implicit:** The Ambiguity Resolution logic triggers a search for relevant past memories.
3.  **Context Loading (Abstracted):** The system invokes the **Memory Manager Interface**. This interface encapsulates the logic to determine the appropriate source (e.g., SQL DB, Vector Store, File System) and retrieval method based on the trigger type and user ID. It then fetches the relevant data (or high-level summaries) and injects it into the active context.
4.  **Query via Interface:** The agent requests specific details through the **Memory Manager Interface** (e.g., calling `memory_manager.retrieve(key="cmd_log_123")` or `memory_manager.search(query="database credentials")`), abstracting away the underlying storage complexity.
5.  **Resolution & Fetch:** The **Memory Manager Interface** resolves the request to the correct storage backend (SQL, Vector, File), enforces user access permissions, and retrieves the data.
6.  **Response:** The system returns the specific chunk of data requested.

### 4.3. Key-Value Storage for Command Results
*   **Key:** Unique Identifier (UUID or Human-readable slug).
*   **Value:** Plain text or JSON object containing the Result.
*   **Metadata:** Timestamp, Source Command, Agent ID, Session ID, User ID.

## 5. System Components

### 5.1. Database Schema Extensions (PostgreSQL)
We can utilize the existing `steps` table's `step_metadata` or introduce a dedicated `agent_memories` table.

**Proposed Table: `agent_memories`**
```sql
CREATE TABLE agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id INTEGER NOT NULL REFERENCES "User"(id) ON DELETE CASCADE,
    agent_id INTEGER REFERENCES agents(id),
    thread_id UUID REFERENCES threads(id),
    memory_key VARCHAR(255) NOT NULL, -- The ID used in the placeholder
    memory_type VARCHAR(50), -- e.g., 'command_output'(generate when execute command), 'user_preference'(auto-generated),
    summary TEXT, -- Brief description stored in Layer 1
    content TEXT, -- The detailed content (Layer 2)
    content_metadata JSONB DEFAULT '{}', -- Extra info (e.g., command executed, execution time)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_memories_key ON agent_memories(memory_key);
CREATE INDEX idx_memories_thread ON agent_memories(thread_id);
CREATE INDEX idx_memories_user ON agent_memories(user_id);
```
add in postgresdb.sql do not create new file

### 5.2. Memory Component & Interface (Agent Composition)
The memory system is implemented as a core component (`MemoryContext` class) that is composed within the Agent (a "has-a" relationship). This allows every agent to possess native memory capabilities without needing external service calls for basic operations.

**Core Python Component (`MemoryContext`):**
*   **Inheritance:** Inherits from `autogen_core.model_context.ChatCompletionContext`.
*   **Composition:** `class Agent: ... self.model_context = MemoryContext(...)`
*   **Methods:**
    *   `store(content: str, description: str, type: str, ...) -> memory_key: str`
        *   Saves content to the `agent_memories` table.
    *   `retrieve(memory_key: str) -> content: str`
        *   Fetches raw content by key.
    *   `search(query: str, limit: int) -> List[MemoryItem]`
        *   Performs semantic or keyword search.
    *   `add_message(message: ChatMessage)` (Override)
        *   Intercepts messages to detect large content or memory placeholders.
        *   Automatically stores large outputs and replaces them with placeholders.
        *   Intelligently retrieves memory content when placeholders are encountered and context requires it. Utilize a lightweight LLM call to analyze the new message and determine if any existing memory placeholders need to be expanded based on relevance to the current task.

**Agent Integration (`CodeAgent` & `UIAgentBuilder`):**
*   **CodeAgent:** Accepts `model_context` in its constructor. No internal changes required if context is passed externally.
*   **User Association:** `MemoryContext` is initialized with `user_id` to link memories to the current user.
*   **Builder Update:** `UIAgentBuilder` (in `chainlit_web/ui_hook/ui_agent_builder.py`) overrides `build_model_context` to instantiate `MemoryContext` with the active `user_id` and `data_layer`, ensuring seamless integration for UI-driven agent creation.

**MCP Wrapper (Development/Diagnosis):**
An optional MCP server/interface can be wrapped around the `MemoryContext` component to expose these functions as tools. This is primarily for:
*   **Diagnosis:** Manually inspecting memory contents via an MCP client.
*   **Development:** Testing the memory logic in isolation.
*   **Agent Tooling:** If an agent needs to explicitly call memory functions as tools.

**MCP Tools (Exposed via Wrapper):**
*   `store_memory` -> Wraps `MemoryContext.store`
*   `retrieve_memory` -> Wraps `MemoryContext.retrieve`
*   `search_memory` -> Wraps `MemoryContext.search`

## 6. Integration Strategy
1.  **Executor Agent Update:** Modify the `executor` agent (and others) to automatically use the `store_memory` logic when command outputs are large.
2.  **Prompt Engineering:** Update System Prompts to teach agents how to recognize and use `[MemoryRef: ...]` placeholders.
3.  **Context Management:** Ensure the context window manager respects the placeholders and doesn't prune them aggressively (or prunes them intelligently).

## 7. Future Roadmap
*   **Vector Database Integration:** For semantic search over the `agent_memories` table (using `pgvector` or separate DB).
*   **Automatic Summarization:** Use a cheaper model (e.g., GPT-3.5-Turbo or a local model) to automatically generate the summaries for Layer 1.
*   **Memory Consolidation:** Periodic tasks to consolidate short-term memories into long-term knowledge base articles.

