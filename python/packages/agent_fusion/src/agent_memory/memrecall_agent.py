"""
MemRecallAgent 实现模块

专门用于记忆搜索和召回的专用 Agent。
"""

from typing import AsyncGenerator, List, Sequence, Optional, Dict, Any, Tuple, Union
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

from agent_memory.memrecall_tools import (
    search_memories_tool,
    get_memory_detail_tool,
    expand_context_window_tool,
    handoff_tool,
    SearchMemoriesInput,
    SearchMemoriesOutput,
    GetMemoryDetailInput,
    ExpandContextWindowInput,
    HandoffInput,
    MEMRECALL_TOOLS,
    MemorySearchResultItem,
    MemRecallResult,
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

### 3. expand_context_window（拓展工具）
- **当当前搜索结果不理想，需要查看更多历史消息时使用**
- 调用后会立即结束当前迭代，系统将提供更多消息重新发起调用
- 只能在未达到最大迭代次数时使用

### 4. handoff（必须最终调用）
- **重要：完成搜索后必须调用此工具！**
- 传入所有相关记忆的总结
- 包含你的相关性分析和置信度
- 如果没找到相关记忆，也要调用并说明情况

## 迭代工作流程

1. **分析**: 基于当前可用的消息分析用户意图
2. **搜索**: 调用 search_memories 搜索记忆（可调整参数多次搜索）
3. **评估**: 评估搜索结果质量
4. **决策**:
   - 结果满意 -> 调用 handoff 结束
   - 需要更多上下文 -> 调用 expand_context_window（如还有迭代次数）
   - 达到最大迭代 -> 调用 handoff 结束（报告当前最佳结果）

## 注意事项

- 不要向用户直接回复，你的结果应该通过 handoff 工具返回
- 如果搜索结果不理想，优先考虑拓展上下文窗口（如果还有迭代次数）
- 置信度低于 0.5 时，考虑设置 needs_more_info=True
- 始终保持专业、准确的搜索态度
"""

    # 单层决策模式的系统提示（cache-friendly: 对话在前，system在后）
    SINGLE_SHOT_SYSMSG = """基于上述对话，分析用户意图并输出搜索参数 JSON。

输出格式：
{
    "query": "搜索意图描述",
    "keywords": ["关键词1", "关键词2"],
    "memory_types": ["command_output"|"user_preference"|"general"],
    "search_mode": "hybrid"|"keyword"|"semantic",
    "limit": 5,
    "min_relevance_score": 0.6
}

判断规则：
- 提到"执行/运行/重新执行/再次训练" -> memory_types=["command_output"]
- 提到"配置/设置/按照之前的" -> memory_types=["user_preference"]
- 模糊指代 -> search_mode="hybrid"
- 只输出 JSON，无其他内容"""

    def __init__(
        self,
        name: str,
        model_client: ChatCompletionClient,
        data_layer: AgentFusionDataLayer,
        user_id: int,
        model_context: Optional[ChatCompletionContext] = None,
        system_message: Optional[str] = None,
        max_search_iterations: int = 3,
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
        self._context_window_size = 5

        # 初始化模型上下文
        if model_context is None:
            initial_prompt = self._build_system_prompt(iteration=1, max_iterations=max_search_iterations)
            model_context = UnboundedChatCompletionContext([
                SystemMessage(content=initial_prompt, source="system")
            ])
        self._model_context = model_context

        # 内部状态
        self._is_running = False
        self._cancellation_token: Optional[CancellationToken] = None
        self._search_count = 0

        # 预定义工具列表
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
        """
        base_prompt = self._system_message_template

        environment_status = f"""

## 当前环境状态（ENVIRONMENT STATUS）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 当前迭代轮数: {iteration}/{max_iterations}
📊 上下文窗口: 最近 {self._context_window_size} 条消息可用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

        if iteration > 1:
            environment_status += f"""
⚠️  **这是第 {iteration} 轮迭代**
之前的搜索结果未能找到满意的记忆，已拓展上下文窗口。
现在有更多历史消息可供分析，请重新评估并搜索。
"""

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
        """设置当前迭代状态"""
        self._current_iteration = iteration
        self._context_window_size = context_window_size

        # 更新模型上下文中的系统提示词
        new_prompt = self._build_system_prompt(iteration, self._max_iterations)
        # Note: Actual context update depends on the context implementation

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
        """
        try:
            # 转换输入为消息列表
            if isinstance(messages, str):
                user_message = TextMessage(content=messages, source="user")
                messages_to_process = [user_message]
            else:
                messages_to_process = messages

            # 调用流式处理
            async for result in self.on_messages_stream(
                messages_to_process,
                self._cancellation_token
            ):
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
        """
        message_id = str(uuid.uuid4())

        # 添加消息到上下文
        for message in messages:
            await self._model_context.add_message(message.to_model_message())

        # 获取工具 schemas
        tool_schemas = self._get_tool_schemas_for_llm()

        # 迭代处理工具调用
        for iteration in range(self._max_iterations):
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
                yield self._create_response(model_result, message_id)
                return

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

            # 检查是否调用了终止类工具
            is_termination, termination_type = self._check_termination_call(tool_calls, exec_results)

            if is_termination and termination_type == "handoff":
                handoff_response = self._create_handoff_response(exec_results, model_result)
                if handoff_response:
                    yield handoff_response
                return

            elif is_termination and termination_type == "expand":
                if self._is_expand_approved(exec_results):
                    yield TextMessage(
                        content="[系统] 上下文拓展请求已批准，准备重新搜索...",
                        source=self.name
                    )
                    return
                else:
                    logger.warning("Expand context window request was denied")

            self._search_count += 1

        # 达到最大迭代次数
        logger.warning(f"Max search iterations ({self._max_iterations}) reached")
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

        tool_info = MEMRECALL_TOOLS.get(tool_call.name)
        if not tool_info:
            return FunctionExecutionResult(
                content=f"Unknown tool: {tool_call.name}",
                call_id=tool_call.id,
                is_error=True,
                name=tool_call.name,
            )

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
                is_error=not getattr(output, 'success', True),
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
        """检查是否调用了终止类工具"""
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
                            target="parent",
                            source=self.name,
                            context=self._build_handoff_context(model_result)
                        )
                except json.JSONDecodeError:
                    pass
        return None

    def _build_handoff_context(self, model_result: CreateResult) -> List[LLMMessage]:
        """构建移交上下文"""
        context: List[LLMMessage] = []

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
        """获取兼容的上下文"""
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

    # --- 单层决策模式（Single Shot Mode）---

    async def recall_single_shot(
        self,
        messages: Sequence[LLMMessage]
    ) -> MemRecallResult:
        """
        单层决策模式：LLM 生成参数 -> 代码执行 -> 直接返回

        消息顺序（cache-friendly）：
            [对话历史 messages] + [记忆提取 sys_msg]
            └─ 已缓存部分 ─┘     └─ 动态角色 ─┘
        """
        # 构造消息列表：对话在前，system在后（利于缓存命中且可动态更改角色）
        llm_messages: List[LLMMessage] = list(messages)
        llm_messages.append(SystemMessage(content=self.SINGLE_SHOT_SYSMSG, source="system"))

        try:
            # LLM 单次调用生成搜索参数
            response = await self._model_client.create(messages=llm_messages)

            # 解析 JSON 参数
            content = response.content.strip()
            if content.startswith("```json"):
                content = content[7:]
            if content.startswith("```"):
                content = content[3:]
            if content.endswith("```"):
                content = content[:-3]
            content = content.strip()

            params = SearchMemoriesInput.model_validate_json(content)

            # 代码执行搜索
            search_output = await search_memories_tool(
                self._data_layer,
                self._user_id,
                params
            )

            memories = search_output.results if search_output.success else []

            # 如果是命令类型，获取完整内容
            if memories and params.memory_types and "command_output" in params.memory_types:
                memories = await self._expand_memories(memories)

            # 格式化并返回
            formatted_context = self._format_memories_for_return(memories)

            return MemRecallResult(
                action="RECALL_SUCCESS" if memories else "NO_RELEVANT_MEMORY",
                memories=memories,
                formatted_context=formatted_context,
                search_summary=f"单层召回完成，找到 {len(memories)} 条记忆",
                confidence=max(m.relevance_score for m in memories) if memories else 0.0
            )

        except Exception as e:
            logger.error(f"Error in recall_single_shot: {e}")
            return MemRecallResult(
                action="NO_RELEVANT_MEMORY",
                search_summary=f"召回失败: {str(e)}",
                confidence=0.0
            )

    async def _expand_memories(
        self,
        memories: List[MemorySearchResultItem]
    ) -> List[MemorySearchResultItem]:
        """获取记忆的完整内容"""
        expanded = []
        for mem in memories:
            if mem.memory_type == "command_output":
                try:
                    detail = await self._data_layer.memory.retrieve_memory(
                        memory_key=mem.memory_key
                    )
                    if detail:
                        # Update content_preview with full content
                        mem.content_preview = detail.content
                except Exception as e:
                    logger.warning(f"Failed to expand memory {mem.memory_key}: {e}")
            expanded.append(mem)
        return expanded

    def _format_memories_for_return(
        self,
        memories: List[MemorySearchResultItem]
    ) -> str:
        """格式化记忆为上下文字符串"""
        if not memories:
            return "未找到相关历史记忆。"

        parts = ["## 相关历史记忆"]
        for mem in memories:
            parts.append(f"\n[{mem.memory_key}] {mem.summary}")
            parts.append(f"内容: {mem.content_preview[:500]}")
        return "\n".join(parts)

    async def recall_with_context(
        self,
        messages: List[LLMMessage]
    ) -> MemRecallResult:
        """
        基于对话上下文召回记忆（动态召回入口）

        由 MemoryContext.get_messages() 在每次调用大模型前触发。
        """
        if not messages:
            return MemRecallResult(
                action="NO_RELEVANT_MEMORY",
                search_summary="无消息需要分析",
                confidence=0.0
            )

        # Step 1: 分析是否需要召回记忆
        should_recall = await self._analyze_recall_need_with_context(messages)

        if not should_recall:
            return MemRecallResult(
                action="NO_RELEVANT_MEMORY",
                search_summary="当前对话无需召回历史记忆",
                confidence=0.0
            )

        # Step 2: 使用单层决策模式执行召回
        return await self.recall_single_shot(messages)

    async def _analyze_recall_need_with_context(
        self,
        messages: List[LLMMessage]
    ) -> bool:
        """分析消息列表是否需要召回历史记忆"""
        recent_messages = messages[-5:] if len(messages) > 5 else messages

        # 构建分析用的对话消息（保持原始消息格式）
        llm_messages: List[LLMMessage] = []
        for msg in recent_messages:
            if hasattr(msg, 'content') and msg.content:
                llm_messages.append(msg)

        # system消息放在最后（cache-friendly，动态角色）
        system_prompt = """分析上述对话是否需要召回历史记忆。

判断标准：
1. 用户消息是否包含指代词（那个、之前、上次等）？
2. 是否提到时间相关的词（昨天、上周、之前说过）？
3. 是否涉及任务延续（继续、接着做）？
4. 是否有未明确的上下文需要历史信息补充？
5. 用户是否在询问之前讨论过的内容？

只回答 "YES" 或 "NO"。"""
        llm_messages.append(SystemMessage(content=system_prompt, source="system"))

        try:
            response = await self._model_client.create(messages=llm_messages)
            return "YES" in response.content.upper()
        except Exception:
            # 出错时回退到简单规则判断
            last_msg = messages[-1]
            if isinstance(last_msg, UserMessage) and last_msg.content:
                recall_indicators = [
                    "那个", "之前", "上次", "以前", "之前说过",
                    "昨天", "上周", "前几天", "继续", "接着"
                ]
                return any(ind in last_msg.content for ind in recall_indicators)
            return False
