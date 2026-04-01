# Analyzer Agent 实现方案

## 1. 总体架构

**接收问题 → 摘要匹配 → 判断能否解决 → 缺就查原文补**。

orchestrator 已经分析好用户问题，analyzer 先从摘要库匹配文章，评估能否解决。如果摘要信息不够，回到原文中找补充细节。

```
orchestrator 分析出的用户问题
        |
        v
+-------------------+
| Article Matcher   |  -- 从摘要库中找出与问题相关的文章
+-------------------+       (search_agent/context/article_name_summary/)
        |
        v
+-------------------+
| Solution Assessor |  -- 对比/互补分析, 判断能否解决问题
+-------------------+
        |
   能解决?──── 是 ──→ 输出路线
        |
        否 / 信息不足
        |
        v
+-------------------+
| Detail Retriever  |  -- 回到原文中查找缺失的细节
+-------------------+       (workspace/search_agent/output/)
        |
        v
+-------------------+
| Solution Assessor |  -- 带着补充信息再次评估
+-------------------+
        |
   能解决?──── 是 ──→ 输出路线
        |
        否
        |
        v
+-------------------+
| Ask User          |  -- 告知用户缺什么, 请求补充
+-------------------+
```

## 2. 目录结构

```
ai_science/
├── analyzer_agent/
│   ├── __init__.py
│   ├── agent.py              # AnalyzerAgent 入口
│   ├── matcher.py            # 文章匹配
│   ├── assessor.py           # 方案评估
│   ├── retriever.py          # 原文细节检索
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── match.py          # 匹配 prompt
│   │   ├── assess.py         # 评估 prompt
│   │   └── retrieve.py       # 原文检索 prompt
│   ├── schemas.py            # 数据模型
│   └── config.py
├── search_agent/
│   ├── context/
│   │   └── article_name_summary/   # 摘要库
│   └── output/                     # 原文存放目录
└── output/
```

## 3. 核心模块

---

### 3.1 Article Matcher (`matcher.py`)

从摘要库中找出与问题相关的文章，标注每篇文章能提供什么。

```python
class ArticleMatcher:
    def __init__(self, llm_client, summary_dir: str):
        self.llm = llm_client
        self.summary_dir = Path(summary_dir)

    async def match(self, problem: str) -> list[MatchedArticle]:
        """加载所有摘要, 找出与问题相关的文章"""
        summaries = self._load_summaries()
        prompt = MATCH_PROMPT.format(
            problem=problem,
            summaries=self._format_summaries(summaries)
        )
        response = await self.llm.generate(prompt, temperature=0.2)
        return self._parse(response)
```

**数据模型**:
```python
class MatchedArticle(BaseModel):
    title: str
    what_it_offers: str       # 这篇文章能提供什么 (一句话)
    relevance: str            # high / medium / low
```

---

### 3.2 Solution Assessor (`assessor.py`)

拿到匹配的文章后，做对比/互补分析，判断能否解决问题，给出结论。

```python
class SolutionAssessor:
    def __init__(self, llm_client):
        self.llm = llm_client

    async def assess(self, problem: str,
                     articles: list[MatchedArticle],
                     summaries: dict[str, str]) -> Assessment:
        """对比/互补分析, 判断能否解决问题"""
        prompt = ASSESS_PROMPT.format(
            problem=problem,
            articles=self._format_articles(articles, summaries)
        )
        response = await self.llm.generate(prompt, temperature=0.3)
        return self._parse(response)
```

**数据模型**:
```python
class Assessment(BaseModel):
    solvable: bool                    # 能否解决
    confidence: str                   # high / medium / low
    solution_route: list[RouteStep]   # 解决路线
    gaps: list[str]                   # 缺什么 (如果不能完全解决)
    reasoning: str                    # 推理过程
    need_user_input: bool = False     # 是否需要问用户
    question_to_user: str = ""        # 问用户什么

class RouteStep(BaseModel):
    step: int
    action: str                       # 做什么
    from_article: str                 # 来自哪篇文章
    note: str                         # 补充说明 (对比/互补关系)
```

---

### 3.3 Detail Retriever (`retriever.py`)

当摘要信息不足以判断时，回到原文中查找缺失的细节。

```python
class DetailRetriever:
    def __init__(self, llm_client, output_dir: str):
        self.llm = llm_client
        self.output_dir = Path(output_dir)  # workspace/search_agent/output/

    async def retrieve(self, problem: str, gaps: list[str],
                       article_titles: list[str]) -> list[RetrievedDetail]:
        """根据缺失点, 从原文中查找补充信息"""
        results = []
        for title in article_titles:
            full_text = self._load_full_article(title)
            if not full_text:
                continue
            prompt = RETRIEVE_PROMPT.format(
                problem=problem,
                gaps=gaps,
                article_title=title,
                full_text=full_text
            )
            response = await self.llm.generate(prompt, temperature=0.2)
            detail = self._parse(response)
            if detail.found_useful:
                results.append(detail)
        return results
```

**数据模型**:
```python
class RetrievedDetail(BaseModel):
    article_title: str
    found_useful: bool            # 是否找到有用信息
    details: list[str]            # 找到的具体细节
    fills_gaps: list[str]         # 填补了哪些缺失
```

---

### 3.4 Agent 主流程 (`agent.py`)

```python
class AnalyzerAgent:
    def __init__(self, config):
        self.llm = LLMClient(config.llm)
        self.matcher = ArticleMatcher(self.llm, config.summary_dir)
        self.assessor = SolutionAssessor(self.llm)
        self.retriever = DetailRetriever(self.llm, config.article_output_dir)

    async def run(self, problem: str) -> Assessment:
        """
        1. 从摘要库匹配文章
        2. 评估能否解决
        3. 不够就查原文补充, 再评估
        4. 还不行就问用户
        """
        # Step 1: 匹配
        matched = await self.matcher.match(problem)
        if not matched:
            return Assessment(
                solvable=False, confidence="high",
                solution_route=[], gaps=["没有找到相关文章"],
                reasoning="摘要库中无相关文献",
                need_user_input=True,
                question_to_user="未找到相关文章, 请提供更多信息或补充文献"
            )

        # Step 2: 第一次评估 (基于摘要)
        summaries = self.matcher.get_summaries_by_titles([a.title for a in matched])
        assessment = await self.assessor.assess(problem, matched, summaries)

        if assessment.solvable:
            return assessment

        # Step 3: 信息不足 → 查原文补充
        details = await self.retriever.retrieve(
            problem, assessment.gaps, [a.title for a in matched]
        )

        if details:
            # 带着补充信息再评估一次
            assessment = await self.assessor.assess(
                problem, matched, summaries, extra_details=details
            )
            if assessment.solvable:
                return assessment

        # Step 4: 还是不行 → 问用户
        assessment.need_user_input = True
        assessment.question_to_user = (
            f"现有文章无法完全解决问题, 缺少以下方面的信息:\n"
            + "\n".join(f"- {g}" for g in assessment.gaps)
            + "\n请补充相关资料或调整问题。"
        )
        return assessment
```

---

## 4. CoT Prompt

---

### 4.1 文章匹配 Prompt

```python
MATCH_PROMPT = """
<role>
你是一位科研文献匹配专家。
</role>

<input>
用户问题: {problem}

文章摘要库:
{summaries}
</input>

<chain_of_thought>
**Step 1**: 理解问题的核心需求是什么。
**Step 2**: 逐篇扫描摘要, 判断是否与问题相关。只保留确实有用的, 不要勉强。
**Step 3**: 对每篇相关文章, 一句话说明它能提供什么。
</chain_of_thought>

<output_format>
{{
    "matched": [
        {{
            "title": "...",
            "what_it_offers": "该文章提出了X方法, 可用于解决问题中的Y部分",
            "relevance": "high / medium"
        }}
    ],
    "reasoning": "Step 1: ... Step 2: ... Step 3: ..."
}}
如果没有相关文章, matched 返回空列表。
</output_format>
"""
```

---

### 4.2 方案评估 Prompt

```python
ASSESS_PROMPT = """
<role>
你是一位科研方案评估专家。你需要判断已找到的文章能否解决用户的问题。
</role>

<input>
用户问题: {problem}

相关文章及摘要:
{articles}
</input>

<chain_of_thought>
**Step 1: 逐篇分析**
- 每篇文章的方法具体能解决问题的哪个部分?

**Step 2: 对比与互补**
- 这些文章之间是什么关系?
  - 对比: 多篇文章用不同方法解决同一问题 → 哪个更优?
  - 互补: 单篇文章只能解决问题的一部分, 不同文章各覆盖问题的不同环节,
    拼在一起才能形成完整方案。
    例如: 文章A有方法但缺数据处理, 文章B有数据处理但没做这个方向,
    A补B的短板, B补A的短板, 串起来就是完整路线。
  - 既对比又互补: 部分环节有多篇文章可选(对比择优), 部分环节只有一篇覆盖(互补拼接)

**Step 3: 判断**
- 综合来看, 这些文章能否解决用户的问题?
- 如果能: 给出具体路线, 每一步用哪篇文章的什么方法
- 如果不能: 缺什么? 哪部分没有被覆盖?

**Step 4: 置信度**
- 对你的判断有多大把握? high / medium / low
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
    "reasoning": "Step 1: ... Step 2: ... Step 3: ... Step 4: ..."
}}
</output_format>
"""
```

---

### 4.3 原文检索 Prompt

```python
RETRIEVE_PROMPT = """
<role>
你是一位科研文献精读专家。摘要信息不足, 你需要从原文中找到缺失的细节。
</role>

<input>
用户问题: {problem}
目前缺少的信息: {gaps}
文章标题: {article_title}
文章原文:
{full_text}
</input>

<chain_of_thought>
**Step 1**: 逐条检查缺失信息, 在原文中搜索是否有相关内容。
**Step 2**: 如果找到, 提取关键段落/数据, 说明它填补了哪个缺失。
**Step 3**: 如果没找到, 如实说明。
</chain_of_thought>

<output_format>
{{
    "found_useful": true/false,
    "details": ["从原文第X节找到: ..."],
    "fills_gaps": ["缺失点1"],
    "reasoning": "Step 1: ... Step 2: ... Step 3: ..."
}}
</output_format>
"""
```

---

## 5. 配置

```python
class AnalyzerConfig(BaseModel):
    summary_dir: str = "search_agent/context/article_name_summary"
    article_output_dir: str = "workspace/search_agent/output"  # 原文目录
    output_dir: str = "output"
    llm_model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 4096
```

---

## 6. 要点

| 维度 | 做法 |
|------|------|
| 流程 | 摘要匹配 → 评估 → 不够查原文 → 还不行问用户 |
| 数据源 | 摘要: `search_agent/context/article_name_summary/`; 原文: `workspace/search_agent/output/` |
| 评估核心 | 对比(同一环节谁更优) + 互补(不同文章各补短板, 拼成完整路线) |
| 降级策略 | 摘要不够 → 查原文补; 原文也不够 → 问用户 |
| 输出 | 能解决 → 给路线; 不能 → 说缺什么 + 问用户 |
| CoT | 每个 prompt 强制分步推理, 保留 reasoning |
