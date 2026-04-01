# Critics 设计方案

## 1. 定位与作用

现有流程是单向的：Matcher → Assessor → Retriever → Assessor → 输出。

**Critics** 插入在 Assessor 输出之后，扮演"质疑者"角色：

```
Assessor 给出 Assessment
        ↓
+-------------------+
|   SolutionCritic  |  -- 审查推理是否严密、方案有无漏洞
+-------------------+
        ↓
  通过? ──── 是 ──→ 返回最终 Assessment (critic_approved=True)
        │
        否 (发现问题)
        │
        ↓
  反馈给 Assessor 重新评估 (最多 N 轮)
        │
        ↓
  仍不通过 → 在 Assessment 中标记 critic_flags
```

---

## 2. 目录结构变化

```
ai_science/
└── analyzer_agent/
    ├── critic.py          # 新增: SolutionCritic
    ├── prompts/
    │   ├── critic.py      # 新增: CRITIC_PROMPT, ASSESS_WITH_CRITIC_PROMPT
    │   ...
    ├── schemas.py         # 新增: CriticFinding, CritiqueReport; Assessment 扩展
    ...
```

---

## 3. 数据模型

新增到 `schemas.py`：

```python
class CriticFinding(BaseModel):
    type: str           # "logic_error" | "unsupported_claim" | "missing_step"
                        # | "overconfidence" | "better_alternative" | "contradiction"
    target: str         # 指向 RouteStep.step 编号 或 "overall"
    description: str    # 具体问题是什么
    suggestion: str     # 建议如何修正


class CritiqueReport(BaseModel):
    approved: bool                  # 是否通过审查
    findings: list[CriticFinding]   # 发现的问题列表
    revised_confidence: str | None  # 建议调整置信度 (可选)
    reasoning: str                  # 审查推理过程
```

`Assessment` 中增加两个字段：

```python
class Assessment(BaseModel):
    solvable: bool
    confidence: str
    solution_route: list[RouteStep]
    gaps: list[str]
    reasoning: str
    need_user_input: bool = False
    question_to_user: str = ""
    critic_approved: bool = False           # 新增: 是否经过 Critic 审查通过
    critic_flags: list[CriticFinding] = []  # 新增: 未解决的 Critic 问题
```

---

## 4. SolutionCritic 模块 (`critic.py`)

```python
import logging
from .llm_client import LLMClient
from .prompts.critic import CRITIC_PROMPT
from .schemas import Assessment, CriticFinding, CritiqueReport

logger = logging.getLogger(__name__)


class SolutionCritic:
    """审查 Assessment，找出逻辑漏洞、无支撑论断、遗漏步骤"""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    async def critique(
        self,
        problem: str,
        assessment: Assessment,
        summaries: dict[str, str],
    ) -> CritiqueReport:
        prompt = CRITIC_PROMPT.format(
            problem=problem,
            assessment=self._format_assessment(assessment),
            summaries=self._format_summaries(summaries),
        )
        data = await self.llm.generate_json(prompt, temperature=0.4)
        return self._parse(data)

    @staticmethod
    def _format_assessment(assessment: Assessment) -> str:
        lines = [
            f"solvable: {assessment.solvable}",
            f"confidence: {assessment.confidence}",
            f"gaps: {assessment.gaps}",
            "solution_route:",
        ]
        for step in assessment.solution_route:
            lines.append(
                f"  Step {step.step}: {step.action}\n"
                f"    来源: {step.from_article}\n"
                f"    说明: {step.note}"
            )
        lines.append(f"reasoning: {assessment.reasoning}")
        return "\n".join(lines)

    @staticmethod
    def _format_summaries(summaries: dict[str, str]) -> str:
        parts = []
        for i, (title, content) in enumerate(summaries.items(), 1):
            parts.append(f"--- 文章 {i}: {title} ---\n{content}\n")
        return "\n".join(parts)

    @staticmethod
    def _parse(data: dict) -> CritiqueReport:
        findings = [CriticFinding(**f) for f in data.get("findings", [])]
        return CritiqueReport(
            approved=data.get("approved", False),
            findings=findings,
            revised_confidence=data.get("revised_confidence"),
            reasoning=data.get("reasoning", ""),
        )
```

---

## 5. Prompt 设计 (`prompts/critic.py`)

### 5.1 Critic Prompt

```python
CRITIC_PROMPT = """
<role>
你是一位科研方案评审专家。你的职责是质疑和审查已提出的解决方案，
找出逻辑漏洞、无支撑的论断、遗漏的步骤，以及更好的替代方案。
你不是方案的提出者，你的目标是让方案更严密。
</role>

<input>
用户问题: {problem}

待审查的方案:
{assessment}

参考文章摘要:
{summaries}
</input>

<chain_of_thought>
**Step 1: 逐步审查 solution_route**
- 每一步的 action 是否有文章支撑？from_article 是否真实提供了这个方法？
- 步骤之间是否有逻辑跳跃？前一步的输出能否支撑后一步的输入？
- 是否有遗漏的关键步骤？

**Step 2: 检查跨文章一致性**
- 被引用的多篇文章在方法上是否有矛盾？
- note 中描述的互补/对比关系是否准确？

**Step 3: 评估 confidence 是否合理**
- solvable=true 但 gaps 不为空 → 置信度是否过高？
- solution_route 步骤数很少但问题复杂 → 是否过于乐观？

**Step 4: 是否存在更好的替代方案**
- 基于摘要，是否有被忽视的文章可以提供更直接的解法？

**Step 5: 给出审查结论**
- 方案是否通过审查？
- 列出每个发现的问题和修正建议。
</chain_of_thought>

<output_format>
{{
    "approved": true/false,
    "findings": [
        {{
            "type": "logic_error | unsupported_claim | missing_step | overconfidence | better_alternative | contradiction",
            "target": "step 2 或 overall",
            "description": "具体问题描述",
            "suggestion": "建议如何修正"
        }}
    ],
    "revised_confidence": "high / medium / low 或 null (不需要调整时)",
    "reasoning": "Step 1: ... Step 2: ... Step 3: ... Step 4: ... Step 5: ..."
}}
</output_format>
"""
```

### 5.2 Assessor 带 Critic 反馈的 Prompt

```python
ASSESS_WITH_CRITIC_PROMPT = """
<role>
你是一位科研方案评估专家。你正在修订一份被评审退回的方案。
</role>

<input>
用户问题: {problem}

相关文章及摘要:
{articles}

{extra_details_section}
</input>

<critic_feedback>
上一轮方案存在以下问题，你必须在本轮修订中逐条解决：

{critic_feedback}
</critic_feedback>

<chain_of_thought>
**Step 0: 逐条回应 Critic 的问题**
- 对每条 finding，说明你如何在新方案中解决它。
  若认为 Critic 的质疑不成立，给出反驳理由。

**Step 1: 逐篇分析**
- 每篇文章的方法具体能解决问题的哪个部分？

**Step 2: 对比与互补**
- 这些文章之间是什么关系？对比 or 互补 or 两者都有？

**Step 3: 判断**
- 综合来看，这些文章能否解决用户的问题？
- 如果能：给出具体路线，每一步用哪篇文章的什么方法
- 如果不能：缺什么？哪部分没有被覆盖？

**Step 4: 置信度**
- 对你的判断有多大把握？high / medium / low
</chain_of_thought>

<output_format>
{{
    "solvable": true/false,
    "confidence": "high / medium / low",
    "solution_route": [
        {{
            "step": 1,
            "action": "做什么",
            "from_article": "来源文章",
            "note": "与文章B的方法互补/优于文章C的方法因为..."
        }}
    ],
    "gaps": ["缺少X方面的支撑"],
    "reasoning": "Step 0: ... Step 1: ... Step 2: ... Step 3: ... Step 4: ...",
    "critic_responses": [
        {{
            "finding_target": "step 2",
            "action": "adopted | rejected",
            "reason": "已将 from_article 改为文章B / Critic误解了摘要，文章A第3段明确提及..."
        }}
    ]
}}
</output_format>
"""
```

---

## 6. Assessor 扩展 (`assessor.py`)

### 6.1 新增 `_format_critic_feedback` 方法

```python
@staticmethod
def _format_critic_feedback(report: CritiqueReport) -> str:
    lines = []
    for f in report.findings:
        lines.append(
            f"[{f.type}] 针对 {f.target}:\n"
            f"  问题: {f.description}\n"
            f"  建议: {f.suggestion}"
        )
    if report.revised_confidence:
        lines.append(f"[confidence] 建议调整置信度为: {report.revised_confidence}")
    return "\n\n".join(lines)
```

格式化后注入 prompt 的内容示例：

```
[unsupported_claim] 针对 step 2:
  问题: from_article 引用了文章A，但文章A摘要中并未提及该优化方法
  建议: 改为引用文章B，或降低该步骤的确定性描述

[missing_step] 针对 overall:
  问题: 方案缺少数据预处理环节，直接从原始输入跳到模型训练
  建议: 补充文章C中提到的归一化步骤

[confidence] 建议调整置信度为: medium
```

### 6.2 `assess` 方法签名扩展

```python
async def assess(
    self,
    problem: str,
    articles: list[MatchedArticle],
    summaries: dict[str, str],
    extra_details: list[RetrievedDetail] | None = None,
    critic_feedback: CritiqueReport | None = None,   # 新增
) -> Assessment:
    articles_text = self._format_articles(articles, summaries)

    if critic_feedback:
        prompt = ASSESS_WITH_CRITIC_PROMPT.format(
            problem=problem,
            articles=articles_text,
            extra_details_section=(
                self._format_details(extra_details) if extra_details else ""
            ),
            critic_feedback=self._format_critic_feedback(critic_feedback),
        )
    elif extra_details:
        prompt = ASSESS_WITH_DETAILS_PROMPT.format(
            problem=problem,
            articles=articles_text,
            extra_details=self._format_details(extra_details),
        )
    else:
        prompt = ASSESS_PROMPT.format(
            problem=problem,
            articles=articles_text,
        )

    data = await self.llm.generate_json(prompt, temperature=0.3)
    return self._parse(data)
```

---

## 7. AnalyzerAgent 主流程集成 (`agent.py`)

```python
class AnalyzerAgent:
    def __init__(self, config):
        self.llm = LLMClient(config.llm)
        self.matcher = ArticleMatcher(self.llm, config.summary_dir)
        self.assessor = SolutionAssessor(self.llm)
        self.retriever = DetailRetriever(self.llm, config.article_output_dir)
        self.critic = SolutionCritic(self.llm)          # 新增
        self.max_critic_rounds = config.max_critic_rounds

    async def run(self, problem: str) -> Assessment:
        # Step 1: 匹配
        matched = await self.matcher.match(problem)
        if not matched:
            return Assessment(
                solvable=False, confidence="high",
                solution_route=[], gaps=["没有找到相关文章"],
                reasoning="摘要库中无相关文献",
                need_user_input=True,
                question_to_user="未找到相关文章, 请提供更多信息或补充文献",
            )

        # Step 2: 第一次评估 (基于摘要)
        summaries = self.matcher.get_summaries_by_titles([a.title for a in matched])
        assessment = await self.assessor.assess(problem, matched, summaries)

        if not assessment.solvable:
            # Step 3: 信息不足 → 查原文补充
            details = await self.retriever.retrieve(
                problem, assessment.gaps, [a.title for a in matched]
            )
            if details:
                assessment = await self.assessor.assess(
                    problem, matched, summaries, extra_details=details
                )

        if not assessment.solvable:
            assessment.need_user_input = True
            assessment.question_to_user = (
                "现有文章无法完全解决问题, 缺少以下方面的信息:\n"
                + "\n".join(f"- {g}" for g in assessment.gaps)
                + "\n请补充相关资料或调整问题。"
            )
            return assessment

        # Step 4: Critic 审查循环
        return await self._critic_loop(problem, assessment, summaries, matched)

    async def _critic_loop(
        self,
        problem: str,
        assessment: Assessment,
        summaries: dict[str, str],
        matched: list[MatchedArticle],
    ) -> Assessment:
        for round_num in range(self.max_critic_rounds):
            report = await self.critic.critique(problem, assessment, summaries)

            if report.approved:
                assessment.critic_approved = True
                return assessment

            logger.info("Critic 第 %d 轮发现 %d 个问题, 反馈给 Assessor 修订",
                        round_num + 1, len(report.findings))

            # 将 Critic 的发现反馈给 Assessor 重新评估
            assessment = await self.assessor.assess(
                problem, matched, summaries,
                critic_feedback=report,
            )

        # 用尽轮次 → 最终审查一次，标记残余问题
        final_report = await self.critic.critique(problem, assessment, summaries)
        assessment.critic_approved = final_report.approved
        assessment.critic_flags = final_report.findings
        return assessment
```

---

## 8. 配置

```python
class AnalyzerConfig(BaseModel):
    summary_dir: str = "search_agent/context/article_name_summary"
    article_output_dir: str = "workspace/search_agent/output"
    output_dir: str = "output"
    llm_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
    max_critic_rounds: int = 2      # 新增: Critic 审查最大轮次
    critic_temperature: float = 0.4 # 新增: Critic 用略高温度，增加质疑多样性
```

---

## 9. 完整流程总览

```
问题输入
   ↓
ArticleMatcher (摘要匹配)
   ↓
SolutionAssessor (首次评估, temperature=0.3)
   ↓ solvable=False
DetailRetriever + SolutionAssessor (补充评估)
   ↓ 仍不能解决
Ask User (need_user_input=True)

   ↓ solvable=True
┌──────────────────────────────────────────┐
│            Critic Loop (≤N 轮)           │
│                                          │
│  SolutionCritic (temperature=0.4)        │
│      ↓ approved=False                    │
│  _format_critic_feedback → prompt 注入   │
│      ↓                                   │
│  SolutionAssessor 修订 (critic_feedback) │
│      ↓                                   │
│  SolutionCritic 重新审查                 │
│      ↓ approved=True ────────────────────┼──→ Assessment (critic_approved=True)
└──────────────────────────────────────────┘
   ↓ 用尽轮次
Assessment (critic_flags 标记残余问题)
```

---

## 10. 核心设计原则

| 维度 | 设计决策 |
|------|---------|
| 职责分离 | Assessor 提方案，Critic 只质疑，不越界 |
| 温度差异 | Assessor 0.3（偏稳定），Critic 0.4（偏多样化质疑） |
| 终止条件 | approved=True 或轮次用尽，防止死循环 |
| 透明度 | `critic_flags` 保留未解决问题，让上层 agent 知道方案的残余风险 |
| 反馈闭环 | Critic 的 finding 直接传给 Assessor，不是从零重来 |
| 可追溯 | `critic_responses` 记录 Assessor 接受/拒绝了哪些质疑及原因 |
