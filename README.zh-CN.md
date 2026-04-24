# AgentFusion

[English](./README.md) · **中文**

AgentFusion 是一个多 Agent AI 编排平台，提供从 **Agent 定义 → 工作流编排 → 数据持久化 → Web 交互** 的完整基础设施。基于 AutoGen AgentChat 与 Chainlit 构建，通过 JSON 配置即可声明式地组合个体 Agent、群聊、Graph Flow，并接入 MCP 工具、GraphRAG 知识图谱、可配置的记忆模型。

## ✨ 核心能力

- **多形态 Agent 编排** — 个体 Agent、SelectorGroupChat、RoundRobinGroupChat、GraphFlow 有向图工作流
- **声明式配置** — 通过 `config.json` 定义 Agent / 工作流 / MCP 工具 / 模型客户端，无需修改代码
- **数据层基础设施** — PostgreSQL + SQLAlchemy 2.0 (异步 ORM)，SQLite 用于测试
- **用户与审计** — bcrypt 密码、账户锁定、JSONB 审计日志
- **可配置记忆系统** — Agent 推理模型与记忆/上下文模型解耦，`MemoryContext` 通过 LLM 在对话开始前完成智能记忆初始化
- **MCP 集成** — 通过 Model Context Protocol 接入外部工具
- **Web UI** — Chainlit + FastAPI，实时 WebSocket 流式输出
- **Prompt 版本管理** — 内置 prompt 优化 Agent，支持版本回溯

## 🚀 快速开始

```bash
# 1. 创建虚拟环境
uv venv && source .venv/bin/activate

# 2. 安装依赖
uv pip install -r requirements.txt
cd python/packages/agent_fusion && uv pip install -e .

# 3. 配置 .env
cat > .env <<EOF
DEEPSEEK_API_KEY=xxx
DASHSCOPE_API_KEY=xxx
GEMINI_API_KEY=xxx
DATABASE_URL=postgresql://user:password@localhost/agentfusion  # 可选，默认 SQLite
EOF

# 4. 启动 Web UI
chainlit run python/packages/agent_fusion/src/chainlit_web/run.py
# 访问 http://localhost:8000
```

## 🏗️ 架构

```
python/packages/agent_fusion/src/
├── data_layer/          # SQLAlchemy ORM 数据层
│   ├── models/          # 业务模型
│   └── tables/          # 表定义
├── schemas/             # Pydantic 配置模型
├── builders/            # Agent / GroupChat / GraphFlow 构造器
├── chainlit_web/        # Web 界面 (用户认证 + UI Hook)
├── model_client/        # LLM 客户端实现
├── base/                # 通用工具 + MCP 支持
├── tools/               # Agent 工具
└── agent_memory/        # 记忆上下文管理
```

### 技术栈

| 层 | 技术 |
|---|---|
| Agent 框架 | AutoGen AgentChat v0.6.4 (DiGraphBuilder / GraphFlow) |
| Web UI | Chainlit + FastAPI + WebSocket |
| 数据层 | SQLAlchemy 2.0 (async) + PostgreSQL / SQLite |
| 包管理 | uv (Python 3.11+) |
| 知识图谱 (可选) | Microsoft GraphRAG |

### Web UI · Chainlit 前端

Web 界面基于 Chainlit 2.10，针对多 Agent 流式输出做了深度定制：

- **Chat Profiles 多流切换** — 通过顶部下拉框选择不同的 Agent / 群聊 / Graph Flow，每个 profile 对应独立的会话上下文 (`@cl.set_chat_profiles`，见 `chainlit_web/run.py`)
- **AutoGen → Chainlit 流式桥接** — `chainlit_web/ui_hook/` 将 AutoGen 的 `run_stream` 输出按消息块拆分推送到前端：
  - `autogen_chat_queue.py` — 单 Agent 队列消费器
  - `ui_round_robin_group_chat.py` / `ui_select_group_chat.py` — 群聊适配器，按 speaker 切换 message author 头像
  - `ui_agent_builder.py` — 单 Agent 模式构造器
- **CoT 全链路展示** — `cot = "full"` 默认开启，工具调用、子任务、handoff 步骤全部可折叠展开
- **用户认证 + 持久化** — `chainlit_web/user/auth.py` 接入 Chainlit `data_layer`，共享 `User` 表与活动审计日志；线程、消息、反馈均写入 PostgreSQL
- **前端 MCP 挂载** — 用户可在 UI 中直接挂载 `sse` / `streamable-http` / `stdio` MCP 服务器 (`allowed_executables = ["npx", "uvx"]`)
- **外观可定制** — 主题、布局、品牌 logo、自定义 CSS/JS、登录页背景均可在 `.chainlit/config.toml` 配置

## ⚙️ 配置

### 个体 Agent

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

### 群聊

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

### Graph Flow (有向图工作流)

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

### MCP 工具

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

## 📦 示例：ASCI — AI for Science Copilot Intelligence

ASCI 是基于 AgentFusion 构建的**多 Agent 科研选题助手**，是展示框架能力的旗舰案例。它充分使用了 AgentFusion 的 GraphFlow 编排、MCP 工具集成和自定义工具链能力，演示如何在真实业务场景中组装一个端到端的 6-Agent 工作流。

> 用户输入研究课题 → 文献检索 → 知识图谱构建 → 可行性分析 → 质量验证 → PoC 实验 → 报告生成 → 交付带溯源引用的结构化研究报告

### Demo

4.40 build index · 10.05 index building complete

[![asci demo](https://markdown-videos-api.jorgenkh.no/url?url=https%3A%2F%2Fyoutu.be%2FRXTVtl6Nbz4)](https://youtu.be/RXTVtl6Nbz4)

### 管线架构

```
用户输入课题
     │
     ▼
┌─────────────────┐
│  Orchestrator   │── <ReviewPlan> ──▶ Plan Reviewer (用户审批)
│  (中央编排器)    │◀── 反馈修改 ────────┘
└────────┬────────┘
         │ <Explore> (审批通过)
         ▼
┌─────────────────┐
│   Explorer      │  Scholar 搜索 → PDF 下载 → OCR → ArticleStore → GraphRAG 索引
│  (文献发现)      │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Analyzer      │  GraphRAG 语义检索 → 收敛为 2-3 条候选研究路线
│  (可行性分析)    │
└────────┬────────┘
         ▼
┌─────────────────┐       <Reject> (最多 2 次)
│    Critics      │──────────────────────▶ Analyzer (修订循环)
│  (质量门控)      │
└────────┬────────┘
         │ <Approve>
         ▼
┌─────────────────┐
│   Executor      │  PoC 概念验证 (编写并执行代码实验)
│  (执行器)        │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Reporter      │  GraphRAG 综合查询 → 生成带溯源引用的研究报告
│  (报告生成)      │
└────────┬────────┘
         ▼
    交付给用户
```

![ASCI Research Flow](./diagram.svg)

### Agent 角色

| Agent | 职责 | 工具 |
|---|---|---|
| **Orchestrator** | 解析课题，制定研究计划 (3-5 组中英文关键词)，提交用户审批 | `bash`, `graphrag_search` |
| **Explorer** | Scholar 搜索 → wget 下载 → pdftotext OCR → ArticleStore → 一次性 GraphRAG 索引；支持断点续跑 | `bash`, `add_article_for_graph`, `graphrag_index`, `graphrag_search` |
| **Analyzer** | GraphRAG global/local 检索，评估可行性、创新性、风险，每步标注 `[来源: ...]` | `bash`, `graphrag_search`, `graphrag_trace` |
| **Critics** | 5 步质量验证 (引用真实性 / 逻辑一致性 / 置信度校准 / 遗漏检查 / 综合判定)；最多拒绝 2 次防死循环 | `bash`, `graphrag_trace`, `graphrag_search` |
| **Executor** | 评估可程序化的步骤，编写代码执行 PoC 实验 (失败重试 ≤ 2 次) | `bash`, `file_system` (MCP) |
| **Reporter** | 综合所有结果，global 综述 + local 细节 + trace 溯源；含 Critics 强制通过路线时附残余风险声明 | `bash`, `graphrag_search`, `graphrag_trace` |

### GraphRAG 工具链

所有 GraphRAG 工具共享 `graphrag_output/asci_session/` 索引数据：Explorer 构建，Analyzer / Critics / Reporter 查询。

| 工具 | 功能 | 使用者 |
|---|---|---|
| `add_article_for_graph` | OCR Markdown 存入内存 ArticleStore | Explorer |
| `graphrag_index` | 一次性构建知识图谱：token 分片 → LLM 实体抽取 → Leiden 社区检测 → 向量化 → Parquet + LanceDB | Explorer |
| `graphrag_search` | 语义搜索：`local` 查实体细节, `global` 跨文档综述 | Explorer / Orchestrator / Analyzer / Critics / Reporter |
| `graphrag_trace` | 溯源追踪：query → text_units → document → source_url | Analyzer / Critics / Reporter |

### ASCI 模型选型

| 用途 | 模型 |
|---|---|
| Agent 推理 | DeepSeek-Chat |
| GraphRAG 实体抽取 | Qwen3-Max (DashScope) |
| Embedding | text-embedding-v4 (DashScope) |

### 运行 ASCI 示例

ASCI 依赖 Playwright 进行 Scholar 抓取。在不受 Playwright 官方支持的发行版 (如 Arch Linux) 上，建议通过 Docker 启动 Playwright 服务端，宿主机仅作为客户端：

```bash
# 1. 启动 Playwright Docker 服务端
docker run -p 3000:3000 --rm --init -it \
  --add-host=hostmachine:host-gateway \
  mcr.microsoft.com/playwright:v1.41.0-jammy \
  /bin/sh -c "cd /home/pwuser && npx -y playwright@1.41.0 run-server --port 3000 --host 0.0.0.0"
# 就绪输出: Listening on ws://127.0.0.1:3000/

# 2. 运行完整 ASCI 工作流
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:3000/ \
  uv run -m cli.chat graphflow ai_science "why repeat prompt can boost accuracy"

# 3. 仅运行单个 search_agent (调试用)
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:3000/ \
  uv run -m cli.chat agent search_agent "搜索 Attention is all you Need 的资料"

# 4. 或通过 Web UI: 选择 ai_science flow，输入研究课题
```

> 容器内访问宿主服务时，将 URL 中的 `localhost` 替换为 `hostmachine`。

### ASCI 关键目录

```
config.json                       # ASCI 管线配置 (asci_* agents + ai_science graph_flow)
config/prompt/agent/asci/         # 6 个 Agent 的 system prompt
  ├── orchestrator_pt.md
  ├── explorer_pt.md
  ├── analyzer_pt.md
  ├── critics_pt.md
  ├── executor_pt.md
  └── reporter_pt.md
graphrag_output/asci_session/     # GraphRAG 索引产物 (Parquet + LanceDB)
search_agent/output/              # OCR 论文 Markdown
ai_science/output/                # 最终研究报告
```

---

## 🛠️ 开发

### 测试

```bash
# 全部
python -m pytest python/packages/agent_fusion/tests/ -v

# 单文件
python -m pytest python/packages/agent_fusion/tests/test_user_model.py -v
```

### 添加新 Agent

1. 在 `config/prompt/agent/` 新建 prompt 文件
2. 在 `config.json` 增加 agent 配置
3. 如需新表，更新 `data_layer/models/tables/`
4. 补充测试 (CRUD + 边界场景)
5. Web UI 验证

### 数据层变更 (CRITICAL)

修改数据库 schema 时**必须协同更新**：
1. SQL schema (`sql/progresdb.sql`)
2. SQLAlchemy ORM (`data_layer/models/tables/`)
3. Pydantic schemas (`schemas/`)
4. 业务模型方法
5. 测试

详见 [`CLAUDE.md`](./CLAUDE.md) 中的强制规范。

## 📄 License

MIT

## 🙏 Acknowledgments

构建于 [AutoGen](https://github.com/microsoft/autogen) 之上。GraphRAG 集成基于 [Microsoft GraphRAG](https://github.com/microsoft/graphrag)。
