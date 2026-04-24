# AgentFusion

**English** · [中文](./README.zh-CN.md)

AgentFusion is a multi-agent AI orchestration platform that provides end-to-end infrastructure spanning **agent definition → workflow orchestration → data persistence → web interaction**. Built on AutoGen AgentChat and Chainlit, it lets you declaratively compose individual agents, group chats, and graph flows from a single JSON config — with first-class support for MCP tools, GraphRAG knowledge graphs, and decoupled memory models.

## ✨ Core Capabilities

- **Multi-form agent orchestration** — individual agents, `SelectorGroupChat`, `RoundRobinGroupChat`, and directed-graph `GraphFlow` workflows
- **Declarative configuration** — define agents / workflows / MCP tools / model clients in `config.json` without touching code
- **Data-layer infrastructure** — PostgreSQL with SQLAlchemy 2.0 (async ORM); SQLite for testing
- **Users & audit trail** — bcrypt password hashing, account locking, JSONB activity logs
- **Pluggable memory system** — an agent's reasoning model is decoupled from its memory/context model; `MemoryContext` performs LLM-driven memory initialization before a conversation starts
- **MCP integration** — connect external tools via the Model Context Protocol
- **Web UI** — Chainlit + FastAPI with real-time WebSocket streaming
- **Versioned prompts** — built-in prompt-refinement agents with version history

## 🚀 Quick Start

```bash
# 1. Create a virtual environment
uv venv && source .venv/bin/activate

# 2. Install dependencies
uv pip install -r requirements.txt
cd python/packages/agent_fusion && uv pip install -e .

# 3. Configure .env
cat > .env <<EOF
DEEPSEEK_API_KEY=xxx
DASHSCOPE_API_KEY=xxx
GEMINI_API_KEY=xxx
DATABASE_URL=postgresql://user:password@localhost/agentfusion  # optional, defaults to SQLite
EOF

# 4. Launch the web UI
chainlit run python/packages/agent_fusion/src/chainlit_web/run.py
# Visit http://localhost:8000
```

## 🏗️ Architecture

```
python/packages/agent_fusion/src/
├── data_layer/          # SQLAlchemy ORM data layer
│   ├── models/          # Business models
│   └── tables/          # Table definitions
├── schemas/             # Pydantic config schemas
├── builders/            # Agent / GroupChat / GraphFlow builders
├── chainlit_web/        # Web interface (auth + UI hooks)
├── model_client/        # LLM client implementations
├── base/                # Shared utilities + MCP support
├── tools/               # Agent tools
└── agent_memory/        # Memory context management
```

### Tech Stack

| Layer | Technology |
|---|---|
| Agent framework | AutoGen AgentChat v0.6.4 (DiGraphBuilder / GraphFlow) |
| Web UI | Chainlit + FastAPI + WebSocket |
| Data layer | SQLAlchemy 2.0 (async) + PostgreSQL / SQLite |
| Package manager | uv (Python 3.11+) |
| Knowledge graph (optional) | Microsoft GraphRAG |

### Web UI · Chainlit Frontend

The web interface is built on Chainlit 2.10 with deep customization for streaming multi-agent output:

- **Chat profiles for flow switching** — pick an agent / group chat / graph flow from the header dropdown; each profile gets its own session context (`@cl.set_chat_profiles` in `chainlit_web/run.py`)
- **AutoGen → Chainlit streaming bridge** — `chainlit_web/ui_hook/` chunks AutoGen's `run_stream` output into per-message updates rendered live in the browser:
  - `autogen_chat_queue.py` — single-agent queue consumer
  - `ui_round_robin_group_chat.py` / `ui_select_group_chat.py` — group-chat adapters that swap the message author/avatar per speaker
  - `ui_agent_builder.py` — single-agent-mode builder
- **Full Chain-of-Thought view** — `cot = "full"` is on by default; tool calls, sub-tasks, and handoff steps are all collapsible inline
- **Auth + persistence** — `chainlit_web/user/auth.py` plugs into Chainlit's `data_layer`, sharing the `User` table and activity logs; threads, messages, and feedback are persisted to PostgreSQL
- **In-UI MCP** — users can mount `sse` / `streamable-http` / `stdio` MCP servers directly from the UI (`allowed_executables = ["npx", "uvx"]`)
- **Customizable shell** — theme, layout, brand logo, custom CSS/JS, and login-page background are all configurable in `.chainlit/config.toml`

## ⚙️ Configuration

### Individual Agent

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

### Group Chat

```json
{
  "group_chats": {
    "your_group": {
      "type": "selector_group_chat",
      "selector_prompt": "group_chat/your_selector.md",
      "model_client": "deepseek-chat_DeepSeek",
      "participants": ["agent1", "agent2", "human_proxy"]
    }
  }
}
```

### Graph Flow (Directed-Graph Workflow)

```json
{
  "graph_flows": {
    "your_flow": {
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

### MCP Tools

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

---

## 📦 Example: ASCI — AI for Science Copilot Intelligence

ASCI is a **multi-agent research-topic copilot** built on AgentFusion — the flagship example showcasing the framework's capabilities. It exercises GraphFlow orchestration, MCP integration, and custom toolchains to assemble an end-to-end 6-agent workflow for a real-world domain.

> User submits a research topic → literature search → knowledge-graph construction → feasibility analysis → quality validation → PoC experiment → report generation → delivers a structured, citation-traceable research report

### Demo

4.40 build index · 10.05 index building complete

[![asci demo](https://markdown-videos-api.jorgenkh.no/url?url=https%3A%2F%2Fyoutu.be%2FRXTVtl6Nbz4)](https://youtu.be/RXTVtl6Nbz4)

### Pipeline Architecture

```
User research topic
     │
     ▼
┌─────────────────┐
│  Orchestrator   │── <ReviewPlan> ──▶ Plan Reviewer (user approval)
│   (central)     │◀── feedback ────────┘
└────────┬────────┘
         │ <Explore> (after approval)
         ▼
┌─────────────────┐
│   Explorer      │  Scholar search → PDF download → OCR → ArticleStore → GraphRAG index
│  (lit. discovery)│
└────────┬────────┘
         ▼
┌─────────────────┐
│   Analyzer      │  GraphRAG semantic search → converge to 2–3 candidate routes
│  (feasibility)  │
└────────┬────────┘
         ▼
┌─────────────────┐       <Reject> (max 2)
│    Critics      │──────────────────────▶ Analyzer (revision loop)
│  (quality gate) │
└────────┬────────┘
         │ <Approve>
         ▼
┌─────────────────┐
│   Executor      │  PoC concept validation (writes & runs code experiments)
│   (executor)    │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Reporter      │  GraphRAG synthesis → final report with traceable citations
│   (reporting)   │
└────────┬────────┘
         ▼
   Delivered to user
```

![ASCI Research Flow](./diagram.svg)

### Agent Roles

| Agent | Responsibility | Tools |
|---|---|---|
| **Orchestrator** | Parse the topic, draft a research plan (3–5 EN/CN keyword groups), submit for user approval | `bash`, `graphrag_search` |
| **Explorer** | Scholar search → `wget` PDF → `pdftotext` OCR → ArticleStore → one-shot GraphRAG index; resumable across runs | `bash`, `add_article_for_graph`, `graphrag_index`, `graphrag_search` |
| **Analyzer** | GraphRAG global/local retrieval; assess feasibility, novelty, risk; tag every step with `[source: ...]` | `bash`, `graphrag_search`, `graphrag_trace` |
| **Critics** | 5-step validation (citation authenticity / logical consistency / confidence calibration / omission check / verdict); ≤2 rejections to prevent loops | `bash`, `graphrag_trace`, `graphrag_search` |
| **Executor** | Identify programmable steps, write & run code for PoC experiments (≤2 retries on failure) | `bash`, `file_system` (MCP) |
| **Reporter** | Synthesize all outputs: global overview + local detail + trace-backed citations; include residual-risk note when Critics force-passed any route | `bash`, `graphrag_search`, `graphrag_trace` |

### GraphRAG Toolchain

All GraphRAG tools share the `graphrag_output/asci_session/` index — built by Explorer, queried by Analyzer / Critics / Reporter.

| Tool | Function | Used by |
|---|---|---|
| `add_article_for_graph` | Store OCR markdown in the in-memory ArticleStore | Explorer |
| `graphrag_index` | One-shot knowledge-graph build: token chunking → LLM entity extraction → Leiden community detection → vectorization → Parquet + LanceDB | Explorer |
| `graphrag_search` | Semantic search — `local` for entity detail, `global` for cross-document synthesis | Explorer / Orchestrator / Analyzer / Critics / Reporter |
| `graphrag_trace` | Provenance — query → text_units → document → source_url | Analyzer / Critics / Reporter |

### ASCI Model Lineup

| Purpose | Model |
|---|---|
| Agent reasoning | DeepSeek-Chat |
| GraphRAG entity extraction | Qwen3-Max (DashScope) |
| Embedding | text-embedding-v4 (DashScope) |

### Running the ASCI Example

ASCI depends on Playwright for Scholar scraping. On distros not officially supported by Playwright (e.g. Arch Linux), run the Playwright server in Docker and keep the host as the client:

```bash
# 1. Start the Playwright Docker server
docker run -p 3000:3000 --rm --init -it \
  --add-host=hostmachine:host-gateway \
  mcr.microsoft.com/playwright:v1.41.0-jammy \
  /bin/sh -c "cd /home/pwuser && npx -y playwright@1.41.0 run-server --port 3000 --host 0.0.0.0"
# Ready when you see: Listening on ws://127.0.0.1:3000/

# 2. Run the full ASCI workflow
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:3000/ \
  uv run -m cli.chat graphflow ai_science "why repeat prompt can boost accuracy"

# 3. Run only the search_agent (debugging)
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:3000/ \
  uv run -m cli.chat agent search_agent "search for the paper Attention Is All You Need"

# 4. Or via the web UI: pick the ai_science flow and submit a topic
```

> When reaching host services from inside the container, replace `localhost` in URLs with `hostmachine`.

### ASCI Layout

```
config.json                       # ASCI pipeline config (asci_* agents + ai_science graph_flow)
config/prompt/agent/asci/         # System prompts for the 6 agents
  ├── orchestrator_pt.md
  ├── explorer_pt.md
  ├── analyzer_pt.md
  ├── critics_pt.md
  ├── executor_pt.md
  └── reporter_pt.md
graphrag_output/asci_session/     # GraphRAG index artifacts (Parquet + LanceDB)
search_agent/output/              # OCR'd paper markdown
ai_science/output/                # Final research report
```

---

## 🛠️ Development

### Tests

```bash
# All
python -m pytest python/packages/agent_fusion/tests/ -v

# Single file
python -m pytest python/packages/agent_fusion/tests/test_user_model.py -v
```

### Adding a New Agent

1. Drop a prompt file under `config/prompt/agent/`
2. Add the agent entry to `config.json`
3. Update `data_layer/models/tables/` if new tables are needed
4. Add tests (CRUD + edge cases)
5. Verify via the web UI

### Schema Changes (CRITICAL)

When modifying the database schema, **all of the following must be updated together**:
1. SQL schema (`sql/progresdb.sql`)
2. SQLAlchemy ORM (`data_layer/models/tables/`)
3. Pydantic schemas (`schemas/`)
4. Business-model methods
5. Tests

See the mandatory rules in [`CLAUDE.md`](./CLAUDE.md).

## 📄 License

MIT

## 🙏 Acknowledgments

Built on top of [AutoGen](https://github.com/microsoft/autogen). GraphRAG integration is based on [Microsoft GraphRAG](https://github.com/microsoft/graphrag).
