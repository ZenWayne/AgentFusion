# Agent Memory System PRD

## 1. Overview
The Agent Memory System is a specialized layer designed to manage the historical interaction information between users and agents. Its primary function is to persistently store critical information and command execution results to facilitate future interactions and complex task execution. 

To address the common challenge of "Context Window Explosion" (where long conversation histories exceed the LLM's token limit), this system implements a **Two-Layer Memory Architecture**. This ensures that the agent maintains a lightweight, efficient active context while retaining the ability to access deep, detailed information when necessary.

## 2. Core Objectives
*   **Context Optimization:** Prevent token overflow by keeping the active conversation context clean and concise.
*   **Persistent Recall:** Allow agents to remember important facts, preferences, and past command outputs across sessions or long conversations.
*   **Structured Storage:** Store command execution results (e.g., extensive logs, file contents, database query results) in a structured Key-Value (K-V) format.
*   **On-Demand Retrieval:** Provide a standard interface (MCP or Agent-based) for agents to query detailed information using lightweight references (placeholders) found in their context.

## 3. Architecture: The Two-Layer Memory Model

### Layer 1: Context Memory (The "Index")
This layer resides in the agent's active prompt/context window. Instead of raw data, it contains human-readable **Placeholders** or **Summaries**.
*   **Format:** `[MemoryRef: <ID> - <Brief Description>]` or structured natural language summaries.
*   **Purpose:** Provides the agent with the *existence* and *nature* of information without burdening the token count.
*   **Example:** instead of pasting 500 lines of logs, the context contains: `Command 'npm install' executed. Logs stored in [MemoryRef: cmd_log_123]. Status: Success.`

### Layer 2: Detail Memory (The "Store")
This layer is the persistent backend storage where the actual raw data resides.
*   **Storage Mechanism:** PostgreSQL (using `jsonb` or text fields) or File System (for large blobs).
*   **Content:** Full command outputs, file contents, API responses, detailed user instructions.
*   **Access:** Accessed only via the Memory Interface/Agent when explicitly requested.

## 4. Functional Specifications

### 4.1. Memory Storage Workflow
1.  **Capture:** When an agent executes a command (via MCP or internal tool) that produces significant output.
2.  **Filter/Truncate:** The system intercepts the output. If it exceeds a defined threshold (e.g., 500 tokens), it triggers the memory storage process.
3.  **Store:** The full output is saved to the **Detail Memory** (Database/KV Store).
4.  **Summarize:** A unique ID and a brief summary/placeholder are generated.
5.  **Context Update:** The agent's context (Thread/Step) is updated with the Placeholder instead of the raw output.

### 4.2. Memory Retrieval Workflow
1.  **Trigger:** An agent encounters a Placeholder (e.g., `[MemoryRef: cmd_log_123]`) in its context and determines it needs the specific details to proceed (e.g., to debug an error in the logs).
2.  **Query:** The agent uses the **Memory Interface** (via a specific tool like `retrieve_memory(id="cmd_log_123")`).
3.  **Fetch:** The system looks up the ID in the Detail Memory.
4.  **Response:** The system returns the specific chunk of data requested. *Note: The agent should ideally request specific parts or summaries if the data is massive, or the system should support pagination.*

### 4.3. Key-Value Storage for Command Results
*   **Key:** Unique Identifier (UUID or Human-readable slug).
*   **Value:** Plain text or JSON object containing the Result.
*   **Metadata:** Timestamp, Source Command, Agent ID, Session ID.

## 5. System Components

### 5.1. Database Schema Extensions (PostgreSQL)
We can utilize the existing `steps` table's `step_metadata` or introduce a dedicated `agent_memories` table.

**Proposed Table: `agent_memories`**
```sql
CREATE TABLE agent_memories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id INTEGER REFERENCES agents(id),
    thread_id UUID REFERENCES threads(id),
    memory_key VARCHAR(255) NOT NULL, -- The ID used in the placeholder
    memory_type VARCHAR(50), -- e.g., 'command_output', 'user_preference', 'file_content'
    summary TEXT, -- Brief description stored in Layer 1
    content TEXT, -- The detailed content (Layer 2)
    content_metadata JSONB DEFAULT '{}', -- Extra info (e.g., command executed, execution time)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE
);
CREATE INDEX idx_memories_key ON agent_memories(memory_key);
CREATE INDEX idx_memories_thread ON agent_memories(thread_id);
```

### 5.2. Memory Agent / MCP Tool
A specialized "Memory Agent" or a set of MCP Tools attached to standard agents.

**Tool: `store_memory`**
*   **Input:** `content` (string), `description` (string), `type` (string).
*   **Output:** `memory_key` (string) - to be inserted into context.

**Tool: `retrieve_memory`**
*   **Input:** `memory_key` (string).
*   **Output:** `content` (string).

**Tool: `search_memory`** (Optional/Future)
*   **Input:** `query` (string), `thread_id` (optional).
*   **Output:** List of matching memory summaries and keys.

## 6. Integration Strategy
1.  **Executor Agent Update:** Modify the `executor` agent (and others) to automatically use the `store_memory` logic when command outputs are large.
2.  **Prompt Engineering:** Update System Prompts to teach agents how to recognize and use `[MemoryRef: ...]` placeholders.
3.  **Context Management:** Ensure the context window manager respects the placeholders and doesn't prune them aggressively (or prunes them intelligently).

## 7. Future Roadmap
*   **Vector Database Integration:** For semantic search over the `agent_memories` table (using `pgvector` or separate DB).
*   **Automatic Summarization:** Use a cheaper model (e.g., GPT-3.5-Turbo or a local model) to automatically generate the summaries for Layer 1.
*   **Memory Consolidation:** Periodic tasks to consolidate short-term memories into long-term knowledge base articles.
