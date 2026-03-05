"""
MemRecallAgent 工具函数模块

提供记忆搜索、获取详情、扩展上下文窗口和handoff工具。
"""

from typing import Dict, Any, List, Optional, Literal
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# 输入输出模型
# ============================================================================

class SearchMemoriesInput(BaseModel):
    """记忆搜索工具输入"""
    query: str = Field(
        ...,
        description="搜索查询，可以是自然语言描述或关键词。例如：'用户之前配置的数据库参数'"
    )
    search_mode: Literal["semantic", "keyword", "hybrid"] = Field(
        default="hybrid",
        description="搜索模式: semantic-语义匹配, keyword-关键词匹配, hybrid-混合"
    )
    keywords: Optional[List[str]] = Field(
        default=None,
        description="可选的精确关键词列表，用于精确过滤。例如：['database', 'config']"
    )
    memory_types: Optional[List[str]] = Field(
        default=None,
        description="按记忆类型过滤，如 ['user_preference', 'command_output', 'general']"
    )
    time_range_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=365,
        description="时间范围过滤，最近 N 天内的记忆"
    )
    limit: int = Field(
        default=5,
        ge=1,
        le=10,
        description="返回结果数量限制"
    )
    min_relevance_score: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="最小相关性分数阈值，低于此值的记忆将被过滤"
    )


class MemorySearchResultItem(BaseModel):
    """单个记忆搜索结果"""
    memory_key: str = Field(..., description="记忆的唯一标识符")
    summary: str = Field(..., description="记忆摘要")
    content_preview: str = Field(..., description="内容预览（前200字符）")
    memory_type: Optional[str] = Field(None, description="记忆类型")
    relevance_score: float = Field(..., description="相关性分数 0.0-1.0")
    created_at: str = Field(..., description="创建时间 ISO 格式")
    keywords: List[str] = Field(default=[], description="关联的关键词列表")


class SearchMemoriesOutput(BaseModel):
    """记忆搜索工具输出"""
    success: bool = Field(..., description="搜索是否成功")
    total_found: int = Field(..., description="找到的记忆总数")
    results: List[MemorySearchResultItem] = Field(default=[], description="搜索结果列表")
    search_query_expanded: Optional[str] = Field(None, description="扩展后的搜索查询")
    message: Optional[str] = Field(None, description="附加信息或错误消息")


class GetMemoryDetailInput(BaseModel):
    """获取记忆详情输入"""
    memory_key: str = Field(
        ...,
        description="记忆的唯一标识符（从 search_memories 结果中获取）"
    )


class GetMemoryDetailOutput(BaseModel):
    """获取记忆详情输出"""
    success: bool = Field(..., description="是否成功获取")
    memory_key: Optional[str] = Field(None, description="记忆标识符")
    summary: Optional[str] = Field(None, description="记忆摘要")
    content: Optional[str] = Field(None, description="完整内容")
    memory_type: Optional[str] = Field(None, description="记忆类型")
    created_at: Optional[str] = Field(None, description="创建时间")
    metadata: Optional[Dict[str, Any]] = Field(None, description="附加元数据")
    message: Optional[str] = Field(None, description="错误或状态信息")


class ExpandContextWindowInput(BaseModel):
    """请求拓展上下文窗口"""
    reason: str = Field(
        ...,
        description="需要拓展的原因，例如：'搜索结果不理想，需要查看更早的对话'"
    )
    current_size: int = Field(
        ...,
        description="当前使用的消息数"
    )
    requested_size: int = Field(
        ...,
        description="请求拓展到的消息数"
    )


class ExpandContextWindowOutput(BaseModel):
    """拓展上下文窗口输出"""
    approved: bool = Field(..., description="是否批准拓展")
    new_size: int = Field(..., description="新的上下文窗口大小")
    iteration: int = Field(..., description="下一迭代轮数（从1开始）")
    max_iterations: int = Field(..., description="最大允许迭代次数")
    message: str = Field(..., description="状态信息")


class HandoffInput(BaseModel):
    """完成记忆召回任务的输入"""
    reason: str = Field(
        ...,
        description="结束任务的原因，例如：'已找到相关记忆，搜索完成' 或 '达到最大迭代次数，返回当前最佳结果'"
    )
    search_summary: str = Field(
        ...,
        description="搜索结果的总结，包括找到的相关记忆和关键信息"
    )
    relevant_memory_keys: List[str] = Field(
        default=[],
        description="相关记忆的 key 列表"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="对搜索结果相关性的信心度 0.0-1.0"
    )
    needs_more_info: bool = Field(
        default=False,
        description="是否需要更多信息来精确定位记忆"
    )
    follow_up_question: Optional[str] = Field(
        default=None,
        description="如果需要更多信息，向用户提出的问题"
    )
    iteration_used: int = Field(
        default=1,
        description="完成时使用的迭代轮数"
    )
    context_window_used: int = Field(
        default=5,
        description="最终使用的上下文窗口大小（消息数）"
    )


class HandoffOutput(BaseModel):
    """完成记忆召回输出"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="最终结果消息")
    task_completed: bool = Field(True, description="任务是否完成")
    transfer_completed: bool = Field(True, description="移交是否完成")


class MemRecallResult(BaseModel):
    """MemRecallAgent 返回的记忆召回结果"""
    action: Literal["RECALL_SUCCESS", "NO_RELEVANT_MEMORY", "NEED_MORE_INFO"] = Field(
        ..., description="召回结果类型"
    )
    memories: List[MemorySearchResultItem] = Field(
        default=[], description="召回的记忆列表（已展开完整内容）"
    )
    formatted_context: str = Field(
        default="", description="格式化后的记忆文本，可直接注入主Agent上下文"
    )
    search_summary: str = Field(
        default="", description="搜索结果摘要"
    )
    confidence: float = Field(
        default=0.0, ge=0.0, le=1.0, description="召回结果的可信度"
    )
    needs_more_info: bool = Field(
        default=False, description="是否需要更多信息"
    )
    follow_up_question: Optional[str] = Field(
        default=None, description="需要进一步澄清时的问题"
    )


# ============================================================================
# 工具函数
# ============================================================================

async def search_memories_tool(
    data_layer: Any,
    user_id: int,
    input_data: SearchMemoriesInput
) -> SearchMemoriesOutput:
    """
    执行记忆搜索

    Args:
        data_layer: 数据层访问接口
        user_id: 用户ID
        input_data: 搜索输入参数

    Returns:
        SearchMemoriesOutput: 搜索结果
    """
    try:
        # 检查数据层是否有高级搜索方法
        if hasattr(data_layer.memory, 'search_memories_advanced'):
            # 使用高级搜索
            memories = await data_layer.memory.search_memories_advanced(
                user_id=user_id,
                query=input_data.query,
                keywords=input_data.keywords,
                memory_types=input_data.memory_types,
                time_range_days=input_data.time_range_days,
                min_relevance_score=input_data.min_relevance_score,
                limit=input_data.limit,
                search_mode=input_data.search_mode
            )
        else:
            # 降级到基本搜索
            memories = await data_layer.memory.search_memories(
                query=input_data.query,
                user_id=user_id,
                limit=input_data.limit
            )

        # 转换为输出格式
        results = [
            MemorySearchResultItem(
                memory_key=mem.memory_key,
                summary=mem.summary or "",
                content_preview=mem.content[:200] + "..." if mem.content and len(mem.content) > 200 else (mem.content or ""),
                memory_type=mem.memory_type,
                relevance_score=getattr(mem, 'relevance_score', 0.5),
                created_at=mem.created_at.isoformat() if isinstance(mem.created_at, datetime) else str(mem.created_at),
                keywords=getattr(mem, 'keywords', [])
            )
            for mem in memories
        ]

        return SearchMemoriesOutput(
            success=True,
            total_found=len(results),
            results=results,
            search_query_expanded=", ".join(input_data.keywords) if input_data.keywords else None
        )

    except Exception as e:
        logger.error(f"Error in search_memories_tool: {e}")
        return SearchMemoriesOutput(
            success=False,
            total_found=0,
            results=[],
            message=f"搜索失败: {str(e)}"
        )


async def get_memory_detail_tool(
    data_layer: Any,
    user_id: int,
    input_data: GetMemoryDetailInput
) -> GetMemoryDetailOutput:
    """获取记忆的完整内容"""
    try:
        memory = await data_layer.memory.retrieve_memory(
            memory_key=input_data.memory_key
        )

        if not memory:
            return GetMemoryDetailOutput(
                success=False,
                message=f"未找到记忆: {input_data.memory_key}"
            )

        # 验证用户权限
        if memory.user_id != user_id:
            return GetMemoryDetailOutput(
                success=False,
                message="无权访问此记忆"
            )

        return GetMemoryDetailOutput(
            success=True,
            memory_key=memory.memory_key,
            summary=memory.summary,
            content=memory.content,
            memory_type=memory.memory_type,
            created_at=memory.created_at.isoformat() if isinstance(memory.created_at, datetime) else str(memory.created_at),
            metadata=memory.content_metadata
        )

    except Exception as e:
        logger.error(f"Error in get_memory_detail_tool: {e}")
        return GetMemoryDetailOutput(
            success=False,
            message=f"获取记忆详情失败: {str(e)}"
        )


async def expand_context_window_tool(
    input_data: ExpandContextWindowInput,
    current_iteration: int,
    max_iterations: int
) -> ExpandContextWindowOutput:
    """
    处理上下文窗口拓展请求

    注意: 此工具被调用后，MemRecallAgent 会立即结束当前迭代，
    MemoryContext 将使用新的窗口大小重新发起调用。
    """
    # 检查是否还有迭代次数
    if current_iteration >= max_iterations:
        return ExpandContextWindowOutput(
            approved=False,
            new_size=input_data.current_size,
            iteration=current_iteration,
            max_iterations=max_iterations,
            message=f"已达到最大迭代次数 ({max_iterations})，无法继续拓展"
        )

    # 批准拓展
    next_iteration = current_iteration + 1

    return ExpandContextWindowOutput(
        approved=True,
        new_size=input_data.requested_size,
        iteration=next_iteration,
        max_iterations=max_iterations,
        message=f"批准拓展到 {input_data.requested_size} 条消息，进入第 {next_iteration} 轮迭代"
    )


async def handoff_tool(
    input_data: HandoffInput
) -> HandoffOutput:
    """
    完成记忆召回任务

    注意: 此工具被调用后，MemRecallAgent 会立即结束运行。
    """
    # 构建结果消息
    message_parts = [
        f"## 记忆搜索完成 (信心度: {input_data.confidence:.0%})",
        "",
        f"### 搜索总结",
        input_data.search_summary,
        "",
        f"### 相关性分析",
        input_data.reason,
    ]

    if input_data.relevant_memory_keys:
        message_parts.extend([
            "",
            f"### 相关记忆标识",
            f"共找到 {len(input_data.relevant_memory_keys)} 个相关记忆:",
            *[f"- {key}" for key in input_data.relevant_memory_keys]
        ])

    if input_data.needs_more_info and input_data.follow_up_question:
        message_parts.extend([
            "",
            f"### 需要进一步澄清",
            input_data.follow_up_question
        ])

    return HandoffOutput(
        success=True,
        message="\n".join(message_parts),
        task_completed=True,
        transfer_completed=True
    )


# ============================================================================
# 工具注册表
# ============================================================================

MEMRECALL_TOOLS: Dict[str, Dict[str, Any]] = {
    "search_memories": {
        "name": "search_memories",
        "description": """搜索用户的历史记忆。

使用场景:
1. 用户提到之前讨论过的话题时
2. 需要了解用户偏好或历史操作时
3. 需要验证或引用之前的结论时
4. 上下文出现不明确的引用时（如"按照之前的配置"）

搜索策略:
- 模糊查询时使用 search_mode="semantic"
- 有明确关键词时使用 search_mode="keyword"
- 不确定时使用默认的 "hybrid" 模式

示例:
- "我之前的数据库配置" -> keywords=["数据库", "配置"]
- "上次的方案" -> search_mode="semantic", query="上次讨论的方案"
""",
        "input_model": SearchMemoriesInput,
        "output_model": SearchMemoriesOutput,
        "func": search_memories_tool,
    },
    "get_memory_detail": {
        "name": "get_memory_detail",
        "description": """获取特定记忆的完整内容。

使用场景:
1. search_memories 返回的记忆摘要不完整
2. 需要查看记忆的具体内容细节
3. 需要确认记忆的具体元数据

注意: 必须通过 search_memories 获取 memory_key 后再调用此工具
""",
        "input_model": GetMemoryDetailInput,
        "output_model": GetMemoryDetailOutput,
        "func": get_memory_detail_tool,
    },
    "expand_context_window": {
        "name": "expand_context_window",
        "description": """请求拓展上下文窗口大小。

使用场景:
1. 当前搜索结果不理想，需要查看更多历史消息
2. 用户查询涉及久远的对话，需要回溯更早的上下文
3. 当前上下文不足以理解用户意图

重要: 调用此工具后会立即结束当前迭代，系统将重新发起调用并提供更多消息！
此工具只能在未达到最大迭代次数时使用。

示例:
- reason="搜索结果太少，需要查看更早的对话来找到相关记忆"
- current_size=5, requested_size=10
""",
        "input_model": ExpandContextWindowInput,
        "output_model": ExpandContextWindowOutput,
        "func": expand_context_window_tool,
        "is_expansion": True,
    },
    "handoff": {
        "name": "handoff",
        "description": """完成记忆搜索任务并结束 Agent。

使用场景:
1. 已完成记忆搜索并整理出结果
2. 无法找到相关记忆，需要报告完成情况
3. 已达到最大迭代次数，必须结束

重要: 调用此工具后 MemRecallAgent 会立即结束！这是唯一的正常退出方式。

示例:
- reason="已找到3个相关记忆，搜索完成"
- reason="达到最大迭代次数，返回当前最佳结果"
""",
        "input_model": HandoffInput,
        "output_model": HandoffOutput,
        "func": handoff_tool,
        "is_handoff": True,
    },
}
