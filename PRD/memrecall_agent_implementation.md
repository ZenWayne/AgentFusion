# MemRecallAgent 实现文档

## 文档信息
- **版本**: 1.0
- **日期**: 2026-02-06
- **状态**: 草案

---

## 1. 概述

MemRecallAgent 是一个专门用于记忆搜索和召回的专用 Agent。它基于 CodeAgent 的架构进行了简化和特化，专注于单一职责：高效地搜索和召回用户的历史记忆。

### 1.1 设计原则

1. **单一职责**: 只负责记忆搜索和召回，不做其他处理
2. **工具固定**: 内置固定的 4 个工具，不通过 workbench 动态加载
3. **快速终止**: 调用 handoff 工具后立即结束，不进行额外迭代
4. **无状态设计**: 每次调用都是独立的，不保留运行状态

### 1.2 与 CodeAgent 的主要区别

| 特性 | CodeAgent | MemRecallAgent |
|------|-----------|----------------|
| Workbench | 支持动态工具加载 | 无 workbench，工具固定 |
| 工具数量 | 动态 | 固定 4 个 |
| 迭代次数 | 可配置 max_tool_iterations | 单次执行，handoff 即结束 |
| 代码执行 | 支持 Python 代码执行 | 不执行代码 |
| 职责范围 | 通用代码执行 | 专用记忆召回 |

---

## 2. 类定义

### 2.1 MemRecallAgent

```python
from typing import AsyncGenerator, List, Sequence, Optional, Dict, Any, Tuple
import asyncio
import uuid
import json

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response, TaskResult
from autogen_agentchat.messages import (
    BaseAgentEvent,
    BaseChatMessage,
    TextMessage,
    ToolCallRequestEvent,
    ToolCallExecutionEvent,
    HandoffMessage,
)
from autogen_core.models import (
    AssistantMessage,
    ChatCompletionClient,
    CreateResult,
    FunctionExecutionResult,
    FunctionExecutionResultMessage,
    LLMMessage,
    SystemMessage,
    UserMessage,
)
from autogen_agentchat.messages import ModelClientStreamingChunkEvent, ThoughtEvent
from autogen_core import CancellationToken, FunctionCall
from autogen_core.model_context import ChatCompletionContext, UnboundedChatCompletionContext
from autogen_agentchat.utils import remove_images
from pydantic import BaseModel, Field
import logging

from base.groupchat_queue import BaseChatQueue
from base.handoff import ToolType
from data_layer.data_layer import AgentFusionDataLayer

# 导入工具函数（从 memrecall_agent_tools.md 定义）
from tools.memrecall_tools import (
    search_memories_tool,
    get_memory_detail_tool,
    extract_search_keywords_tool,
    expand_context_window_tool,
    handoff_tool,
    SearchMemoriesInput,
    GetMemoryDetailInput,
    ExtractKeywordsInput,
    ExpandContextWindowInput,
    HandoffInput,
    MEMRECALL_TOOLS,
)

logger = logging.getLogger(__name__)


class MemRecallAgent(BaseChatQueue, BaseChatAgent):
    """
    专门用于记忆召回的 Agent。

    MemRecallAgent 接收用户的记忆查询请求，使用内置工具搜索相关记忆，
    然后通过 handoff 将结果返回给父 Agent。

    特点:
    - 工具固定（4 个内置工具）
    - 调用 handoff 后立即结束
    - 支持流式输出（思考过程）
    """

    # 系统提示词基础模板（动态生成时会添加迭代状态）
    DEFAULT_SYSTEM_MESSAGE_TEMPLATE = """你是一个专门负责搜索和召回用户历史记忆的助手。

## 你的职责
1. 分析用户的查询意图，理解他们想要找什么历史记忆
2. 使用 search_memories 工具搜索相关记忆
3. 如需要，使用 get_memory_detail 获取完整内容
4. 整理搜索结果，通过 handoff 工具结束任务并返回结果

## 工具使用指南

### 1. search_memories（主要工具）
- 用于搜索用户的历史记忆
- 优先使用 hybrid 模式，它结合了语义和关键词匹配
- 如果用户提到具体时间（如"上周"、"昨天"），使用 time_range_days 参数
- 如果用户提到具体类型（如"配置"、"命令"），使用 memory_types 参数

### 2. get_memory_detail（辅助工具）
- 当 search_memories 返回的摘要不够详细时使用
- 需要 memory_key（从 search_memories 结果中获取）

### 3. extract_search_keywords（可选工具）
- 当用户查询很复杂，不确定搜索什么关键词时使用
- 通常 search_memories 会自动处理，很少需要直接调用

### 4. expand_context_window（拓展工具）
- **当当前搜索结果不理想，需要查看更多历史消息时使用**
- 调用后会立即结束当前迭代，系统将提供更多消息重新发起调用
- 只能在未达到最大迭代次数时使用

### 5. handoff（必须最终调用）
- **重要：完成搜索后必须调用此工具！**
- 传入所有相关记忆的总结
- 包含你的相关性分析和置信度
- 如果没找到相关记忆，也要调用并说明情况

## 迭代工作流程

1. **分析**: 基于当前可用的消息分析用户意图
2. **搜索**: 调用 search_memories 搜索记忆（可调整参数多次搜索）
3. **评估**: 评估搜索结果质量
4. **决策**:
   - 结果满意 → 调用 handoff 结束
   - 需要更多上下文 → 调用 expand_context_window（如还有迭代次数）
   - 达到最大迭代 → 调用 handoff 结束（报告当前最佳结果）

## 注意事项

- 不要向用户直接回复，你的结果应该通过 handoff 工具返回
- 如果搜索结果不理想，优先考虑拓展上下文窗口（如果还有迭代次数）
- 置信度低于 0.5 时，考虑设置 needs_more_info=True
- 始终保持专业、准确的搜索态度
"""

    def __init__(
        self,
        name: str,
        model_client: ChatCompletionClient,
        data_layer: AgentFusionDataLayer,
        user_id: int,
        model_context: Optional[ChatCompletionContext] = None,
        system_message: Optional[str] = None,
        max_search_iterations: int = 3,  # 最多搜索次数
    ):
        """
        初始化 MemRecallAgent

        Args:
            name: Agent 名称
            model_client: LLM 客户端
            data_layer: 数据层访问接口
            user_id: 当前用户 ID（用于数据隔离）
            model_context: 可选的模型上下文
            system_message: 可选的自定义系统提示
            max_search_iterations: 最多搜索迭代次数（防止无限循环）
        """
        BaseChatAgent.__init__(
            self,
            name,
            "A specialized agent for searching and recalling user memories."
        )
        BaseChatQueue.__init__(self)

        self._model_client = model_client
        self._data_layer = data_layer
        self._user_id = user_id
        self._system_message_template = system_message or self.DEFAULT_SYSTEM_MESSAGE_TEMPLATE
        self._max_iterations = max_search_iterations

        # 迭代状态跟踪
        self._current_iteration = 1
        self._context_window_size = 5  # 默认使用最近5条消息

        # 初始化模型上下文（使用动态生成的系统提示词）
        if model_context is None:
            initial_prompt = self._build_system_prompt(iteration=1, max_iterations=max_search_iterations)
            model_context = UnboundedChatCompletionContext([
                SystemMessage(content=initial_prompt, source="system")
            ])
        self._model_context = model_context

        # 内部状态
        self._is_running = False
        self._cancellation_token: Optional[CancellationToken] = None
        self._search_count = 0  # 记录搜索次数

        # 预定义工具列表（固定工具，无 workbench）
        self._tools = self._build_tool_schemas()
        self._handoff_tool_name = "handoff"

    def _build_tool_schemas(self) -> List[Dict[str, Any]]:
        """构建工具 schema 列表（固定工具）"""
        tools = []
        for tool_name, tool_info in MEMRECALL_TOOLS.items():
            tool_schema = {
                "name": tool_info["name"],
                "description": tool_info["description"],
                "parameters": tool_info["input_model"].model_json_schema(),
                "type": ToolType.HANDOFF_TOOL if tool_info.get("is_handoff") else ToolType.NORMAL_TOOL,
            }
            tools.append(tool_schema)
        return tools

    def _build_system_prompt(self, iteration: int, max_iterations: int) -> str:
        """
        构建包含迭代状态的动态系统提示词

        Args:
            iteration: 当前迭代轮数（从1开始）
            max_iterations: 最大允许迭代次数

        Returns:
            完整的系统提示词，包含环境感知信息
        """
        base_prompt = self._system_message_template

        # 添加环境状态信息
        environment_status = f"""

## 当前环境状态（ENVIRONMENT STATUS）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 当前迭代轮数: {iteration}/{max_iterations}
📊 上下文窗口: 最近 {self._context_window_size} 条消息可用
📨 总消息数: 根据传入的消息列表动态确定
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        # 如果是后续迭代，添加警告提示
        if iteration > 1:
            environment_status += f"""
⚠️  **这是第 {iteration} 轮迭代**
之前的搜索结果未能找到满意的记忆，已拓展上下文窗口。
现在有更多历史消息可供分析，请重新评估并搜索。
"""

        # 添加迭代限制提示
        if iteration >= max_iterations:
            environment_status += f"""
🚫 **注意：已达到最大迭代次数 ({max_iterations})**
本轮搜索后必须调用 handoff 结束任务，无论结果如何。
"""
        else:
            remaining = max_iterations - iteration
            environment_status += f"""
💡 提示：还可拓展 {remaining} 次上下文窗口（如需）
"""

        return base_prompt + environment_status

    def set_iteration_state(self, iteration: int, context_window_size: int) -> None:
        """
        设置当前迭代状态（由 MemoryContext 在重新发起调用时设置）

        Args:
            iteration: 当前迭代轮数
            context_window_size: 当前上下文窗口大小（消息数）
        """
        self._current_iteration = iteration
        self._context_window_size = context_window_size

        # 更新模型上下文中的系统提示词
        new_prompt = self._build_system_prompt(iteration, self._max_iterations)
        # 注意：这里需要清空上下文并重新添加系统消息
        # 实际实现可能需要根据具体上下文类型调整

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        """此 Agent 可以产生的消息类型"""
        return [TextMessage, ToolCallRequestEvent, ToolCallExecutionEvent, HandoffMessage]

    async def start(
        self,
        cancellation_token: Optional[CancellationToken] = None,
        output_task_messages: bool = True
    ) -> None:
        """启动 Agent"""
        if self._is_running:
            raise ValueError("Agent is already running")

        self._cancellation_token = cancellation_token
        self._is_running = True
        self._search_count = 0

    async def push(
        self,
        messages: Union[str, List[LLMMessage]]
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None]:
        """
        Push 接口接收新消息

        支持两种输入格式:
        - str: 用户查询字符串
        - List[LLMMessage]: 完整的消息列表
        """
        try:
            # 转换输入为消息列表
            if isinstance(messages, str):
                # 构建包含用户查询的消息
                user_message = TextMessage(content=messages, source="user")
                messages_to_process = [user_message]
            else:
                messages_to_process = messages

            # 调用流式处理
            async for result in self.on_messages_stream(
                messages_to_process,
                self._cancellation_token
            ):
                # 分发消息到对应处理器
                await self._dispatch_message(result)

        except Exception as e:
            raise RuntimeError(f"Error in MemRecallAgent push: {str(e)}") from e

    async def _dispatch_message(
        self,
        message: BaseAgentEvent | BaseChatMessage | TaskResult | Response
    ) -> None:
        """根据消息类型分发到对应处理器"""
        if isinstance(message, TaskResult):
            await self.handle_task_result(message)
        elif isinstance(message, Response):
            await self.handle_response(message)
        elif isinstance(message, ModelClientStreamingChunkEvent):
            await self.handle_streaming_chunk(message)
        elif isinstance(message, ThoughtEvent):
            await self.handle_thought(message)
        elif isinstance(message, BaseAgentEvent):
            await self.handle_agent_event(message)
        elif isinstance(message, BaseChatMessage):
            await self.handle_chat_message(message)
        else:
            await self.handle_unknown_message(message)

    # --- 消息处理器（可被重写） ---

    async def handle_task_result(self, message: TaskResult) -> None:
        """处理 TaskResult"""
        pass

    async def handle_response(self, message: Response) -> None:
        """处理 Response"""
        pass

    async def handle_agent_event(self, message: BaseAgentEvent) -> None:
        """处理 Agent 事件"""
        pass

    async def handle_chat_message(self, message: BaseChatMessage) -> None:
        """处理聊天消息"""
        pass

    async def handle_streaming_chunk(self, message: ModelClientStreamingChunkEvent) -> None:
        """处理流式输出块"""
        pass

    async def handle_thought(self, message: ThoughtEvent) -> None:
        """处理思考事件"""
        pass

    async def handle_unknown_message(self, message: Any) -> None:
        """处理未知消息类型"""
        logger.warning(f"Unknown message type in MemRecallAgent: {type(message)}")

    async def task_finished(self, task_result: TaskResult) -> None:
        """任务完成处理"""
        self._is_running = False

    # --- 核心处理逻辑 ---

    async def on_messages_stream(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: Optional[CancellationToken]
    ) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | Response, None]:
        """
        流式消息处理核心逻辑

        流程:
        1. 添加消息到上下文
        2. 调用 LLM 获取工具调用
        3. 执行工具调用
        4. 如果是 handoff 工具，立即结束
        5. 否则继续迭代（最多 max_search_iterations 次）
        """
        message_id = str(uuid.uuid4())

        # 添加消息到上下文
        for message in messages:
            await self._model_context.add_message(message.to_model_message())

        # 获取工具 schemas（传递给 LLM）
        tool_schemas = self._get_tool_schemas_for_llm()

        # 迭代处理工具调用
        for iteration in range(self._max_search_iterations):
            # 调用 LLM
            llm_messages = await self._get_compatible_context()

            model_result: Optional[CreateResult] = None
            async for chunk in self._call_llm(
                message_id,
                llm_messages,
                tool_schemas,
                cancellation_token
            ):
                if isinstance(chunk, CreateResult):
                    model_result = chunk
                elif isinstance(chunk, ModelClientStreamingChunkEvent):
                    yield chunk

            if model_result is None:
                raise RuntimeError("No model result produced")

            # 输出思考内容
            if model_result.thought:
                yield ThoughtEvent(content=model_result.thought, source=self.name)

            # 创建助手消息
            assistant_message = AssistantMessage(
                content=model_result.content,
                source=self.name,
                thought=getattr(model_result, "thought", None),
            )
            await self._model_context.add_message(assistant_message)

            # 检查是否是工具调用
            if isinstance(model_result.content, str):
                # 不是工具调用，返回最终响应
                yield self._create_response(model_result, message_id)
                return

            # 是工具调用
            tool_calls = model_result.content
            if not isinstance(tool_calls, list) or not all(
                isinstance(tc, FunctionCall) for tc in tool_calls
            ):
                yield self._create_response(model_result, message_id)
                return

            # 发送工具调用请求事件
            tool_call_msg = ToolCallRequestEvent(
                content=tool_calls,
                source=self.name,
                models_usage=model_result.usage,
            )
            yield tool_call_msg

            # 执行工具调用
            exec_results = await self._execute_tool_calls(tool_calls)

            # 发送工具执行结果事件
            tool_result_msg = ToolCallExecutionEvent(
                content=exec_results,
                source=self.name,
            )
            yield tool_result_msg

            # 添加工具结果到上下文
            await self._model_context.add_message(
                FunctionExecutionResultMessage(content=exec_results)
            )

            # 检查是否调用了终止类工具（handoff 或 expand_context_window）
            is_termination, termination_type = self._check_termination_call(tool_calls, exec_results)

            if is_termination and termination_type == "handoff":
                # 调用了 handoff，任务完成
                handoff_response = self._create_handoff_response(exec_results, model_result)
                if handoff_response:
                    yield handoff_response
                return

            elif is_termination and termination_type == "expand":
                # 调用了 expand_context_window，检查是否被批准
                if self._is_expand_approved(exec_results):
                    # 拓展请求已批准，结束当前迭代
                    # MemoryContext 将重新发起调用（迭代计数+1）
                    yield TextMessage(
                        content="[系统] 上下文拓展请求已批准，准备重新搜索...",
                        source=self.name
                    )
                    return
                else:
                    # 拓展被拒绝（达到最大迭代次数），继续搜索或 handoff
                    logger.warning("Expand context window request was denied")
                    # 继续下一轮迭代，让 Agent 决定是否 handoff

            # 不是终止调用，继续下一轮迭代
            self._search_count += 1

        # 达到最大迭代次数，强制结束
        logger.warning(f"Max search iterations ({self._max_search_iterations}) reached")
        yield TextMessage(
            content="[系统] 达到最大搜索次数限制，结束记忆召回。",
            source=self.name
        )

    def _get_tool_schemas_for_llm(self) -> List[Dict[str, Any]]:
        """获取传递给 LLM 的工具 schemas"""
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            }
            for tool in self._tools
        ]

    async def _execute_tool_calls(
        self,
        tool_calls: List[FunctionCall]
    ) -> List[FunctionExecutionResult]:
        """执行工具调用列表"""
        results = []

        for call in tool_calls:
            result = await self._execute_single_tool(call)
            results.append(result)

        return results

    async def _execute_single_tool(
        self,
        tool_call: FunctionCall
    ) -> FunctionExecutionResult:
        """执行单个工具调用"""
        try:
            arguments = json.loads(tool_call.arguments)
        except json.JSONDecodeError as e:
            return FunctionExecutionResult(
                content=f"Error parsing arguments: {e}",
                call_id=tool_call.id,
                is_error=True,
                name=tool_call.name,
            )

        # 查找工具
        tool_info = MEMRECALL_TOOLS.get(tool_call.name)
        if not tool_info:
            return FunctionExecutionResult(
                content=f"Unknown tool: {tool_call.name}",
                call_id=tool_call.id,
                is_error=True,
                name=tool_call.name,
            )

        # 执行工具
        try:
            if tool_call.name == "search_memories":
                input_data = SearchMemoriesInput(**arguments)
                output = await search_memories_tool(
                    self._data_layer,
                    self._user_id,
                    input_data
                )

            elif tool_call.name == "get_memory_detail":
                input_data = GetMemoryDetailInput(**arguments)
                output = await get_memory_detail_tool(
                    self._data_layer,
                    self._user_id,
                    input_data
                )

            elif tool_call.name == "extract_search_keywords":
                input_data = ExtractKeywordsInput(**arguments)
                output = await extract_search_keywords_tool(
                    self._model_client,
                    input_data
                )

            elif tool_call.name == "expand_context_window":
                input_data = ExpandContextWindowInput(**arguments)
                output = await expand_context_window_tool(
                    input_data,
                    current_iteration=self._current_iteration,
                    max_iterations=self._max_iterations
                )

            elif tool_call.name == "handoff":
                input_data = HandoffInput(**arguments)
                output = await handoff_tool(input_data)

            else:
                return FunctionExecutionResult(
                    content=f"Unhandled tool: {tool_call.name}",
                    call_id=tool_call.id,
                    is_error=True,
                    name=tool_call.name,
                )

            return FunctionExecutionResult(
                content=output.model_dump_json(),
                call_id=tool_call.id,
                is_error=not output.success,
                name=tool_call.name,
            )

        except Exception as e:
            logger.error(f"Error executing tool {tool_call.name}: {e}")
            return FunctionExecutionResult(
                content=f"Tool execution error: {str(e)}",
                call_id=tool_call.id,
                is_error=True,
                name=tool_call.name,
            )

    def _check_termination_call(
        self,
        tool_calls: List[FunctionCall],
        exec_results: List[FunctionExecutionResult]
    ) -> Tuple[bool, str]:
        """
        检查是否调用了终止类工具（handoff 或 expand_context_window）

        Returns:
            (is_termination, termination_type)
            - is_termination: 是否调用了终止工具
            - termination_type: "handoff" | "expand" | ""
        """
        for call in tool_calls:
            if call.name == "handoff":
                return True, "handoff"
            elif call.name == "expand_context_window":
                return True, "expand"
        return False, ""

    def _is_expand_approved(self, exec_results: List[FunctionExecutionResult]) -> bool:
        """检查 expand_context_window 是否被批准"""
        for result in exec_results:
            if result.name == "expand_context_window" and not result.is_error:
                try:
                    output = json.loads(result.content)
                    return output.get("approved", False)
                except json.JSONDecodeError:
                    pass
        return False

    def _create_handoff_response(
        self,
        exec_results: List[FunctionExecutionResult],
        model_result: CreateResult
    ) -> Optional[HandoffMessage]:
        """从执行结果创建 HandoffMessage"""
        for result in exec_results:
            if result.name == self._handoff_tool_name and not result.is_error:
                try:
                    output = json.loads(result.content)
                    if output.get("transfer_completed"):
                        return HandoffMessage(
                            content=output.get("message", "记忆搜索完成"),
                            target="parent",  # 固定交还给父 Agent
                            source=self.name,
                            context=self._build_handoff_context(model_result)
                        )
                except json.JSONDecodeError:
                    pass
        return None

    def _build_handoff_context(self, model_result: CreateResult) -> List[LLMMessage]:
        """构建移交上下文"""
        context: List[LLMMessage] = []

        # 添加思考内容
        if model_result.thought:
            context.append(AssistantMessage(
                content=model_result.thought,
                source=self.name,
            ))

        return context

    async def _call_llm(
        self,
        message_id: str,
        llm_messages: Sequence[LLMMessage],
        tools: List[Dict[str, Any]],
        cancellation_token: Optional[CancellationToken],
    ) -> AsyncGenerator[Union[ModelClientStreamingChunkEvent, CreateResult], None]:
        """调用 LLM"""
        try:
            if hasattr(self._model_client, 'create_stream'):
                async for chunk in self._model_client.create_stream(
                    llm_messages,
                    tools=tools,
                    cancellation_token=cancellation_token or CancellationToken(),
                ):
                    if isinstance(chunk, CreateResult):
                        yield chunk
                    elif isinstance(chunk, str):
                        yield ModelClientStreamingChunkEvent(
                            content=chunk,
                            source=self.name,
                            full_message_id=message_id
                        )
                    else:
                        raise RuntimeError(f"Invalid chunk type: {type(chunk)}")
            else:
                # 非流式调用
                result = await self._model_client.create(
                    llm_messages,
                    tools=tools,
                    cancellation_token=cancellation_token or CancellationToken(),
                )
                yield result
        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            raise

    async def _get_compatible_context(self) -> Sequence[LLMMessage]:
        """获取兼容的上下文（移除图像如果模型不支持）"""
        messages = await self._model_context.get_messages()
        if self._model_client.model_info.get("vision", False):
            return messages
        return remove_images(messages)

    def _create_response(self, model_result: CreateResult, message_id: str) -> Response:
        """创建 Response 对象"""
        return Response(
            chat_message=TextMessage(
                content=model_result.content
                if isinstance(model_result.content, str)
                else "记忆搜索完成",
                source=self.name
            )
        )

    async def on_messages(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: Optional[CancellationToken]
    ) -> Response:
        """非流式消息处理"""
        result_messages = []
        async for chunk in self.on_messages_stream(messages, cancellation_token):
            if isinstance(chunk, Response):
                return chunk
            result_messages.append(chunk)

        # 默认响应
        return Response(
            chat_message=TextMessage(
                content="记忆召回处理完成",
                source=self.name
            )
        )

    async def on_reset(self, cancellation_token: Optional[CancellationToken]) -> None:
        """重置 Agent 状态"""
        if self._model_context:
            await self._model_context.clear()
        self._is_running = False
        self._search_count = 0

    def get_search_count(self) -> int:
        """获取本次运行的搜索次数"""
        return self._search_count
```

---

## 3. 使用示例

### 3.1 基本使用

```python
from autogen_ext.models.openai import OpenAIChatCompletionClient
from data_layer.data_layer import AgentFusionDataLayer

# 初始化
model_client = OpenAIChatCompletionClient(model="gpt-4")
data_layer = AgentFusionDataLayer(database_url="...")

# 创建 Agent
mem_recall_agent = MemRecallAgent(
    name="memory_searcher",
    model_client=model_client,
    data_layer=data_layer,
    user_id=123,
    max_search_iterations=3
)

# 使用
await mem_recall_agent.start()

async for event in mem_recall_agent.push("查找我之前的数据库配置"):
    if isinstance(event, HandoffMessage):
        print(f"搜索结果: {event.content}")
        print(f"相关记忆: {event.context}")
    elif isinstance(event, ThoughtEvent):
        print(f"思考: {event.content}")
    elif isinstance(event, TextMessage):
        print(f"消息: {event.content}")
```

### 3.2 在 Group Chat 中使用

```python
from autogen_agentchat.teams import SelectorGroupChat

# 创建记忆召回 Agent
memory_agent = MemRecallAgent(
    name="memory_recall",
    model_client=model_client,
    data_layer=data_layer,
    user_id=user_id
)

# 创建主处理 Agent
main_agent = AssistantAgent(
    name="main_assistant",
    model_client=model_client,
    system_message="你是主助手，需要记忆时交给 memory_recall 处理"
)

# 配置 Group Chat
team = SelectorGroupChat(
    participants=[main_agent, memory_agent],
    model_client=model_client,
    selector_prompt="""
    根据用户请求选择合适的 Agent:
    - 如果用户提到历史信息、之前的配置、以前的话题，选择 memory_recall
    - 其他情况选择 main_assistant
    """
)

# 运行
result = await team.run(task="按照我之前的数据库配置来")
```

### 3.3 自定义系统提示

```python
custom_system_message = """你是一个专业的记忆搜索助手。

特殊规则:
1. 对于配置类查询，优先搜索 memory_types=["config"]
2. 如果搜索结果为空，尝试使用更宽泛的关键词
3. 移交时始终包含完整的记忆内容摘要
"""

agent = MemRecallAgent(
    name="custom_memory_agent",
    model_client=model_client,
    data_layer=data_layer,
    user_id=user_id,
    system_message=custom_system_message,
    max_search_iterations=5  # 允许更多搜索尝试
)
```

---

## 4. 配置参数

### 4.1 构造参数

| 参数 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| name | str | 是 | - | Agent 名称 |
| model_client | ChatCompletionClient | 是 | - | LLM 客户端 |
| data_layer | AgentFusionDataLayer | 是 | - | 数据层访问 |
| user_id | int | 是 | - | 用户 ID |
| model_context | ChatCompletionContext | 否 | None | 自定义上下文 |
| system_message | str | 否 | DEFAULT_SYSTEM_MESSAGE | 自定义系统提示 |
| max_search_iterations | int | 否 | 3 | 最大搜索次数 |

### 4.2 类常量

| 常量 | 值 | 说明 |
|------|-----|------|
| DEFAULT_SYSTEM_MESSAGE | 见代码 | 默认系统提示 |

---

## 5. 错误处理

### 5.1 常见错误

```python
# 1. Agent 已在运行
try:
    await agent.start()
    await agent.start()  # 抛出 ValueError
except ValueError as e:
    print(f"启动错误: {e}")

# 2. LLM 调用失败
try:
    async for event in agent.push("查询"):
        ...
except RuntimeError as e:
    print(f"处理错误: {e}")

# 3. 数据层错误
# 工具函数内部处理，返回 is_error=True 的结果
```

### 5.2 重试策略

```python
# 在工具函数层面实现重试
async def search_memories_with_retry(..., max_retries=2):
    for attempt in range(max_retries):
        try:
            return await search_memories_tool(...)
        except TransientError:
            if attempt == max_retries - 1:
                raise
            await asyncio.sleep(2 ** attempt)  # 指数退避
```

---

## 6. 性能优化

### 6.1 上下文管理

- 使用 `UnboundedChatCompletionContext`（默认）
- 每次调用 `on_reset` 时清空上下文
- 支持自定义上下文实现

### 6.2 并发控制

- 单次工具调用串行执行（保持顺序）
- 单次迭代中多个工具调用可并发（如果需要）

### 6.3 资源限制

- `max_search_iterations` 防止无限循环
- 数据层查询超时控制
- LLM 调用超时控制

---

## 7. 测试策略

### 7.1 单元测试

```python
import pytest
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_mem_recall_agent_basic():
    # Mock 依赖
    mock_model = AsyncMock()
    mock_model.create_stream.return_value = [
        CreateResult(content="工具调用结果", ...)
    ]
    mock_data = MagicMock()

    # 创建 Agent
    agent = MemRecallAgent(
        name="test",
        model_client=mock_model,
        data_layer=mock_data,
        user_id=1
    )

    # 测试
    await agent.start()
    results = []
    async for event in agent.push("测试查询"):
        results.append(event)

    # 验证
    assert len(results) > 0
    assert any(isinstance(e, HandoffMessage) for e in results)
```

### 7.2 集成测试

```python
@pytest.mark.asyncio
async def test_mem_recall_integration():
    # 使用真实数据层（测试数据库）
    data_layer = AgentFusionDataLayer("sqlite:///test.db")

    # 插入测试数据
    await data_layer.memory.store_memory(
        user_id=1,
        memory_key="test_config",
        content="测试配置内容",
        summary="测试配置"
    )

    # 运行 Agent
    agent = MemRecallAgent(...)
    # ... 验证搜索结果
```

---

## 8. 扩展指南

### 8.1 添加新工具

1. 在 `memrecall_agent_tools.md` 中定义工具函数
2. 在 `MEMRECALL_TOOLS` 中注册
3. 在 `_execute_single_tool` 中添加执行逻辑

### 8.2 自定义移交逻辑

```python
class CustomMemRecallAgent(MemRecallAgent):
    async def _create_handoff_response(self, exec_results, model_result):
        # 自定义移交逻辑
        response = await super()._create_handoff_response(exec_results, model_result)
        if response:
            # 添加额外上下文
            response.content += "\n\n[自定义信息]"
        return response
```

### 8.3 自定义消息处理器

```python
class LoggingMemRecallAgent(MemRecallAgent):
    async def handle_thought(self, message: ThoughtEvent) -> None:
        # 记录所有思考过程
        logger.info(f"Agent 思考: {message.content}")
        await super().handle_thought(message)
```

---

## 9. 部署建议

1. **资源隔离**: MemRecallAgent 应该运行在与主 Agent 相同的进程中（低延迟）
2. **连接池**: 确保 data_layer 使用连接池管理数据库连接
3. **超时配置**: 设置合理的 LLM 调用超时（30-60 秒）
4. **监控**: 记录搜索次数、延迟、成功率等指标
