# Analyzer Agent 实现方案

## 1. 定位

analyzer_agent 是 orchestrator 下游的分析模块。orchestrator 已经把用户问题拆解好了，analyzer 的职责是：**拿着问题去文献库里找答案，找得到就给路线，找不到就精确告诉用户缺什么资料。**

不做搜索，不做问题拆解——只做"手里这些文章够不够用"的判断。

## 2. 核心流程

```
orchestrator 传入的问题
        |
        v
+-------------------+
| Article Matcher   |  从摘要库匹配相关文章
+-------------------+
        |
   匹配到了?── 否 ──→ Resource Advisor (无匹配模式)
        |                    |
        是                   v
        |              结构化告诉用户:
        v              问题需要哪些方向的资料, 建议搜什么关键词
+-------------------+
| Solution Assessor |  对比/互补分析, 判断能否解决
+-------------------+
        |
   能解决?──── 是 ──→ Critic 审查循环 ──→ 输出解决路线
        |
        否 / 信息不足
        v
+-------------------+
| Detail Retriever  |  回到原文中查找摘要遗漏的细节
+-------------------+
        |
        v
+-------------------+
| Solution Assessor |  带着补充信息再评估一次
+-------------------+
        |
   能解决?──── 是 ──→ Critic 审查循环 ──→ 输出解决路线
        |
        否
        v
+-------------------+
| Resource Advisor  |  分析现有覆盖范围, 生成结构化资料需求
+-------------------+
        |
        v
   告诉用户: 现有文献覆盖到哪里, 缺什么类型的资料,
            建议搜什么关键词, 下一步怎么做
```

**关键设计：两层降级 + Critic 审查**

第一层降级: 摘要不够 → 查原文补细节。大部分情况摘要就够，但有些方法论细节（参数、实验条件）摘要里没有，需要回原文。

第二层降级: 原文也不够 → 不是简单说"解决不了"，而是让 ResourceAdvisor 做一次专门分析，输出结构化的资料需求。用户拿到的不是"请补充资料"这种废话，而是具体到"需要一篇关于X的方法论论文，建议搜关键词A、B、C"。

Critic 审查: 评估出 solvable=True 的方案不直接输出，先过一轮 Critic 审查——检查逻辑跳跃、无支撑论断、遗漏步骤。Critic 退回则 Assessor 带着反馈修订，最多 N 轮。

## 3. 代码位置

```
python/packages/agent_fusion/src/agents/analyzer_agent/
├── __init__.py
├── agent.py              # AnalyzerAgent 入口, 编排整个流程
├── matcher.py            # ArticleMatcher: 摘要库匹配
├── assessor.py           # SolutionAssessor: 对比/互补评估
├── critic.py             # SolutionCritic: 方案审查
├── retriever.py          # DetailRetriever: 原文细节检索
├── advisor.py            # ResourceAdvisor: 资料需求生成
├── llm_client.py         # Anthropic Claude API 封装
├── schemas.py            # 所有 Pydantic 数据模型
├── config.py             # AnalyzerConfig
└── prompts/
    ├── __init__.py
    ├── match.py           # 文章匹配 prompt
    ├── assess.py          # 方案评估 prompt (含二轮带细节版)
    ├── critic.py          # Critic 审查 prompt + Assessor 修订 prompt
    ├── retrieve.py        # 原文检索 prompt
    └── advise.py          # 资料需求建议 prompt (含无匹配版)
```

## 4. 六个模块各自干什么

---

### 4.1 ArticleMatcher

**输入**: 问题 + 摘要库目录
**输出**: 相关文章列表 `list[MatchedArticle]`

从 `search_agent/context/article_name_summary/` 加载所有 `.txt` / `.md` 摘要文件，用 LLM 逐篇扫描，筛出与问题相关的文章。每篇标注：能提供什么、相关度（high/medium/low）。

不相关的不要勉强。宁可少匹配，不要拉进来一堆噪音。

**数据模型**:
```python
class MatchedArticle(BaseModel):
    title: str
    what_it_offers: str       # 一句话: 这篇文章能提供什么
    relevance: str            # high / medium / low
```

---

### 4.2 SolutionAssessor

**输入**: 问题 + 匹配到的文章 + 摘要内容 (+ 可选的原文补充细节) (+ 可选的 Critic 反馈)
**输出**: `Assessment`

核心评估逻辑，做两件事：

1. **对比**: 多篇文章解决同一环节 → 谁更优？为什么？
2. **互补**: 不同文章各覆盖不同环节 → 能否拼成完整路线？

如果能解决，给出 step-by-step 路线（每步用哪篇文章的什么方法）。
如果不能，列出 gaps（哪些环节没被覆盖）。

有三个 prompt 版本：
- `ASSESS_PROMPT`: 首轮，只有摘要
- `ASSESS_WITH_DETAILS_PROMPT`: 二轮，摘要 + 原文补充细节
- `ASSESS_WITH_CRITIC_PROMPT`: 被 Critic 退回后的修订版，带 Critic 反馈，逐条回应

**数据模型**:
```python
class Assessment(BaseModel):
    solvable: bool
    confidence: str                   # high / medium / low
    solution_route: list[RouteStep]   # 能解决时的路线
    gaps: list[str]                   # 不能解决时缺什么
    reasoning: str                    # LLM 的推理过程
    need_user_input: bool = False
    question_to_user: str = ""        # 可读文本
    user_query: UserQuery | None = None  # 结构化资料需求
    critic_approved: bool = False     # 是否经过 Critic 审查通过
    critic_flags: list[CriticFinding] = []  # 未解决的 Critic 问题

class RouteStep(BaseModel):
    step: int
    action: str           # 做什么
    from_article: str     # 来自哪篇
    note: str             # 对比/互补说明
```

---

### 4.3 SolutionCritic

**输入**: 问题 + Assessment + 文章摘要
**输出**: `CritiqueReport`

Assessor 给出 solvable=True 的方案后，Critic 审查找漏洞：

- 每步 action 是否有文章支撑？from_article 是否真的提供了这个方法？
- 步骤间是否有逻辑跳跃？前一步输出能否支撑后一步输入？
- 是否遗漏关键步骤？
- 多篇文章方法上是否矛盾？
- confidence 是否合理？（solvable=true 但 gaps 不空 → 过高？）
- 是否有被忽视的更优替代方案？

审查不通过则退回 Assessor，带着具体问题修订。最多 `max_critic_rounds` 轮（默认 2），用尽轮次则标记残余问题一并输出。

**数据模型**:
```python
class CriticFinding(BaseModel):
    type: str       # logic_error | unsupported_claim | missing_step
                    # | overconfidence | better_alternative | contradiction
    target: str     # 指向 RouteStep.step 编号 或 "overall"
    description: str
    suggestion: str

class CritiqueReport(BaseModel):
    approved: bool
    findings: list[CriticFinding]
    revised_confidence: str | None
    reasoning: str
```

**Critic 循环在 agent.py 中的位置**:
```
assessment = await self.assessor.assess(...)  # solvable=True
assessment = await self._critic_loop(...)     # Critic 审查
  ├── critic.critique() → approved? → 返回
  └── 不通过 → assessor.assess(critic_feedback=report) → 下一轮 critic
```

---

### 4.4 DetailRetriever

**输入**: 问题 + gaps 列表 + 文章标题
**输出**: `list[RetrievedDetail]`

当摘要不够判断时，回到 `workspace/search_agent/output/` 读原文，针对 gaps 逐条搜索。

文件匹配策略：先精确匹配文件名，找不到就模糊匹配（文件名包含标题关键词）。

**数据模型**:
```python
class RetrievedDetail(BaseModel):
    article_title: str
    found_useful: bool
    details: list[str]      # 从原文中提取的具体内容
    fills_gaps: list[str]   # 填补了哪些缺失
```

---

### 4.5 ResourceAdvisor

**输入**: 问题 + 评估结果 + 匹配的文章 + 摘要 (+ 可选的原文补充细节)
**输出**: `UserQuery`

当文献确实不够用时，不是简单抛一句"缺资料"，而是做一次专门分析：

1. **现有覆盖**: 已有文章合在一起能走到哪一步？用一段话说清楚。
2. **逐条拆解缺失**: 每个 gap 具体需要什么类型的资料（方法论论文/实验数据/综述/代码/数据集）、建议搜什么关键词、现有文章在这个方向已经走到哪了。
3. **下一步建议**: 给用户 2-3 个可执行的行动（搜文献/调整问题/先做部分方案）。

**两种模式**:
- `advise()`: 有匹配文章但不足以解决——分析已有覆盖和缺失
- `advise_no_match()`: 完全没有匹配文章——纯基于问题分析需要什么方向的资料

**数据模型**:
```python
class ResourceRequest(BaseModel):
    gap: str                       # 缺失点
    why_needed: str                # 为什么需要——缺了它方案在哪断掉
    resource_type: str             # 资料类型
    suggested_keywords: list[str]  # 建议搜索关键词
    existing_coverage: str         # 现有文章已覆盖到哪里

class UserQuery(BaseModel):
    summary: str                            # 概述
    resource_requests: list[ResourceRequest] # 逐条资料需求
    suggested_actions: list[str]            # 下一步建议
```

---

### 4.6 LLMClient

Anthropic Claude API 的 async 封装。两个核心方法:
- `generate(prompt, temperature)` → 文本
- `generate_json(prompt, temperature)` → 解析后的 dict

JSON 提取自动处理 markdown 代码块包裹 (```json ... ```) 和前后多余文本。

## 5. Prompt 设计

所有 prompt 遵循统一结构: `<role>` → `<input>` → `<chain_of_thought>` → `<output_format>`

CoT 是核心——强制 LLM 分步推理，每一步的输出在下一步被引用。不是装饰性的"请一步步思考"，而是每个 step 有明确任务。

| Prompt | 文件 | 核心 CoT 步骤 |
|--------|------|---------------|
| MATCH_PROMPT | match.py | 理解问题 → 逐篇扫描 → 标注贡献 |
| ASSESS_PROMPT | assess.py | 逐篇分析 → 对比互补 → 判断可解性 → 置信度 |
| ASSESS_WITH_DETAILS_PROMPT | assess.py | 同上，输入多了原文补充细节 |
| ASSESS_WITH_CRITIC_PROMPT | critic.py | **Step 0: 逐条回应 Critic** → 逐篇分析 → 对比互补 → 判断 → 置信度 |
| CRITIC_PROMPT | critic.py | 逐步审查路线 → 跨文章一致性 → 置信度合理性 → 替代方案 → 结论 |
| RETRIEVE_PROMPT | retrieve.py | 逐条检查缺失 → 在原文中定位 → 提取或如实说没有 |
| ADVISE_PROMPT | advise.py | 已有覆盖 → 逐条拆解缺失(类型/关键词/已走到哪) → 行动建议 |
| ADVISE_NO_MATCH_PROMPT | advise.py | 问题拆解 → 各方向资料需求(类型/关键词) → 行动建议 |

## 6. 数据流向

```
数据源:
  摘要库: search_agent/context/article_name_summary/*.txt|md
  原文库: workspace/search_agent/output/*.txt|md

输出:
  output/analysis_result.json
  {
    "problem": "用户问题",
    "assessment": {
      "solvable": true/false,
      "confidence": "...",
      "solution_route": [...],       // 能解决时
      "gaps": [...],                 // 不能解决时
      "critic_approved": true/false, // 是否经过 Critic 审查
      "critic_flags": [...],         // 未解决的 Critic 问题
      "user_query": {                // 不能解决时, 结构化资料需求
        "summary": "...",
        "resource_requests": [...],
        "suggested_actions": [...]
      }
    }
  }
```

## 7. 配置

```python
class AnalyzerConfig(BaseModel):
    summary_dir: str = "search_agent/context/article_name_summary"
    article_output_dir: str = "workspace/search_agent/output"
    output_dir: str = "output"
    llm_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    max_critic_rounds: int = 2  # Critic 审查最大轮次
```

支持 `resolve_paths(base_dir)` 将相对路径转为绝对路径。

## 8. 四种结局

| 结局 | 触发条件 | 输出 |
|------|----------|------|
| 直接解决 (审查通过) | 摘要评估 solvable + Critic approved | solution_route + critic_approved=True |
| 补充后解决 (审查通过) | 查原文后评估 solvable + Critic approved | solution_route + critic_approved=True |
| 解决但有残余问题 | solvable + Critic 轮次用尽未全部通过 | solution_route + critic_flags (残余问题列表) |
| 要用户补资料 | 评估不行 / 无匹配文章 | user_query: 结构化资料需求 + 下一步建议 |

第四种是最常见的——搜到的文献不可能总是刚好够用。关键是让用户拿到可执行的信息，而不是"请补充资料"这种空话。无匹配文章时也会走 advisor 的无匹配模式，基于问题本身分析需要什么方向的资料。
