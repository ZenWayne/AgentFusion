# ASCI — AI for Science Copilot Intelligence

ASCI 是一个多 Agent 科研选题助手。用户输入研究课题后，系统自动完成 **文献检索 → 知识图谱构建 → 可行性分析 → 质量验证 → PoC 实验 → 报告生成** 全流程，交付一份带溯源引用的结构化研究报告。

底层基于 AgentFusion 框架（AutoGen GraphFlow + Chainlit），通过 GraphRAG 知识图谱将多篇论文的实体、关系、社区结构串联起来，为 Agent 间的分析和验证提供共享的语义记忆。

## demo
4.40 build index  
10.05 index building complete

[![asci demo](https://markdown-videos-api.jorgenkh.no/url?url=https%3A%2F%2Fyoutu.be%2FRXTVtl6Nbz4)](https://youtu.be/RXTVtl6Nbz4)


## 管线架构

```
用户输入课题
     │
     ▼
┌─────────────────┐
│  Orchestrator    │── <ReviewPlan> ──▶ Plan Reviewer (用户审批)
│  (中央编排器)     │◀── 反馈修改 ────────┘
└────────┬────────┘
         │ <Explore> (审批通过)
         ▼
┌─────────────────┐
│   Explorer       │  Scholar搜索 → PDF下载 → OCR → 存入ArticleStore → 构建GraphRAG索引
│  (文献发现)       │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Analyzer       │  GraphRAG语义检索 → 收敛为2-3条候选研究路线
│  (可行性分析)     │
└────────┬────────┘
         ▼
┌─────────────────┐       <Reject> (最多2次)
│    Critics       │──────────────────────▶ Analyzer (修订循环)
│  (质量门控)       │
└────────┬────────┘
         │ <Approve>
         ▼
┌─────────────────┐
│   Executor       │  PoC概念验证 (编写并执行代码实验)
│  (执行器)         │
└────────┬────────┘
         ▼
┌─────────────────┐
│   Reporter       │  GraphRAG综合查询 → 生成带溯源引用的研究报告
│  (报告生成)       │
└────────┬────────┘
         ▼
    交付给用户
```

![ASCI Research Flow](./diagram.svg)

## Agent 详情

### Orchestrator — 中央编排器

接收用户课题，分解为搜索关键词组合（中英文 3-5 组），制定包含搜索策略、分析维度、执行约束的研究计划，提交用户审批后协调下游 Agent 按计划执行。

- **路由**: 输出 `<ReviewPlan>` → 转 Plan Reviewer 审批; 输出 `<Explore>` → 转 Explorer 开始搜索
- **工具**: `bash` (读文件/检查状态), `graphrag_search` (查询已建索引)

### Explorer — 文献发现

按 Orchestrator 的关键词搜索 Google Scholar，下载论文 PDF 并 OCR 为 Markdown，存入 ArticleStore，最终一次性构建 GraphRAG 知识图谱索引。支持断点续跑 — 每次启动检查 ToDoList 和已有索引状态，跳过已完成阶段。

- **阶段**: Search → OCR → Store → GraphRAG Index Build → Verify
- **工具**:

| 工具 | 说明 |
|---|---|
| `bash` | 执行 `scholar` 搜索脚本、`wget` 下载 PDF、`pdftotext` OCR、`todo_tracker` 进度管理 |
| `add_article_for_graph` | 将 OCR Markdown 文件存入内存 ArticleStore (GraphRAG 索引的数据源) |
| `graphrag_index` | 对 ArticleStore 所有文章构建知识图谱: token 分片 → LLM 实体抽取 → 关系构建 → 社区检测 → 社区报告 → Parquet + LanceDB 持久化 |
| `graphrag_search` | 索引构建后的语义搜索，用于抽查验证索引质量 |

### Analyzer — 可行性分析

利用 GraphRAG 知识图谱进行 global (跨文档综述) 和 local (实体级细节) 语义检索，评估每个研究方向的可行性、创新性和风险，收敛为 2-3 条候选研究路线。每条路线的每个步骤都标注 `[来源: <文章名>]`。收到 Critics 的 CriticFinding 反馈时进入修订模式。

- **工具**: `bash`, `graphrag_search` (local/global), `graphrag_trace` (溯源验证)

### Critics — 质量门控

对每条候选路线执行 5 步验证协议:
1. **引用真实性** — `graphrag_trace` 溯源，检查原文是否支持声明
2. **逻辑一致性** — 不同文章引用间是否矛盾
3. **置信度校准** — 证据强度是否匹配给出的置信度
4. **遗漏检查** — `graphrag_search` 检查是否有被忽略的重要发现
5. **综合判定** — PASS / WARN / FAIL

- **路由**: `<Approve>` 放行至 Executor; `<Reject>` 打回 Analyzer 附带结构化 CriticFinding
- **防死循环**: 最多拒绝 2 次，第 3 次强制通过并标注残余风险，残余风险及历次拒绝原因传递给 Reporter 在最终报告中说明
- **工具**: `bash`, `graphrag_trace`, `graphrag_search`

### Executor — PoC 执行

接收验证通过的候选路线，评估哪些步骤可以通过编程实现 PoC (数据分析、模型训练、算法验证等)，编写代码执行并收集结果。不可逆操作需确认，失败最多重试 2 次。

- **工具**: `bash` (Python 脚本执行、环境准备), `file_system` MCP (文件读写)
- **输出**: `ai_science/execution/<route_name>/`

### Reporter — 报告生成

综合前序所有 Agent 的分析和执行结果，通过 GraphRAG 的 global 搜索生成领域全景综述，local 搜索补充路线细节，`graphrag_trace` 为关键声明提供原文溯源引用，输出完整的结构化研究报告。若存在 Critics 强制通过的路线，报告中须包含**残余风险声明**，列出 Critics 历次拒绝原因及未解决的问题。

- **工具**: `bash`, `graphrag_search` (local/global), `graphrag_trace`
- **输出**: `ai_science/output/report.md`

## GraphRAG 工具链

所有 GraphRAG 工具共享同一份索引数据 (`graphrag_output/asci_session/`)，由 Explorer 构建，Analyzer / Critics / Reporter 查询。

| 工具 | 功能 | 使用者 |
|---|---|---|
| `add_article_for_graph` | 将 OCR Markdown 存入内存 ArticleStore | Explorer |
| `graphrag_index` | 一次性构建知识图谱 (实体/关系/社区/向量)，输出 Parquet + LanceDB | Explorer |
| `graphrag_search` | 语义搜索 — `local` 查实体/关系细节, `global` 生成跨文档综述 | Explorer, Orchestrator, Analyzer, Critics, Reporter |
| `graphrag_trace` | 溯源追踪 — query → text_units → document → source_url，返回原文片段 + 来源 | Analyzer, Critics, Reporter |

## 技术栈

| 组件 | 技术 |
|---|---|
| Agent 编排 | AutoGen AgentChat v0.6.4 — DiGraphBuilder / GraphFlow 构建有向图，条件标签驱动路由 |
| 知识图谱 | Microsoft GraphRAG — token chunking → LLM 实体抽取 → Leiden 社区检测 → 向量化 |
| 推理 LLM | DeepSeek-Chat |
| GraphRAG 抽取 LLM | Qwen3-Max (DashScope) |
| Embedding | text-embedding-v4 (DashScope) |
| Web UI | Chainlit + FastAPI |

## 快速开始

```bash
# 安装
uv venv && source .venv/bin/activate
cd python/packages/agent_fusion && uv pip install -e .

# Playwright 安装（不支持的 Linux 发行版）

如在不受 Playwright 官方支持的 Linux 发行版（如 Arch Linux）上运行，可通过 Docker 启动 Playwright 服务端，测试/应用仍在宿主机运行。

**1. 启动 Playwright Docker 服务端**

docker run -p 3000:3000 --rm --init -it mcr.microsoft.com/playwright:v1.41.0-jammy /bin/sh -c "cd /home/pwuser && npx -y playwright@1.41.0 run-server --port 3000 --host 0.0.0.0"

服务就绪后输出：

Listening on ws://127.0.0.1:3000/

**2. 将 Playwright 客户端指向 Docker 服务端**

使用 `@playwright/test` 时，只需设置环境变量，无需修改代码：

PW_TEST_CONNECT_WS_ENDPOINT=ws://127.0.0.1:3000/ npx playwright test

**3. 网络访问宿主机本地服务**

若需在 Docker 容器中访问宿主机上的服务，添加 `--add-host` 参数：

docker run -p 3000:3000 --rm --init -it --add-host=hostmachine:host-gateway \
  mcr.microsoft.com/playwright:v1.41.0-jammy /bin/sh -c \
  "cd /home/pwuser && npx -y playwright@1.41.0 run-server --port 3000 --host 0.0.0.0"

此时测试中的 URL 需将 `localhost` 替换为 `hostmachine`。

# 配置 .env
DEEPSEEK_API_KEY=xxx
DASHSCOPE_API_KEY=xxx

# 启动
start the hole asci workflow
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:3000/ uv run -m cli.chat graphflow ai_science "why repeat prompt can boost accuracy"
only start the search_agent
PLAYWRIGHT_WS_ENDPOINT=ws://127.0.0.1:3000/ uv run -m cli.chat agent search_agent "搜索文章Attention is all you Need的资料"
# 访问 http://localhost:8000，选择 ai_science flow，输入研究课题即可
```


## 关键目录

```
config.json                              # ASCI 管线配置 (agents + graph_flow 定义)
config/prompt/agent/asci/                # 6 个 Agent 的 system prompt
  ├── orchestrator_pt.md
  ├── explorer_pt.md
  ├── analyzer_pt.md
  ├── critics_pt.md
  ├── executor_pt.md
  └── reporter_pt.md
graphrag_output/asci_session/            # GraphRAG 索引产物 (Parquet + LanceDB)
search_agent/output/                     # OCR 论文 Markdown
ai_science/output/                       # 最终研究报告
```
