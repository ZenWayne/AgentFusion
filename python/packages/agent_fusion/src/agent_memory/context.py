import uuid
import logging
import re
import json
from typing import List, Optional, Union, Dict, Any
from autogen_core.model_context import ChatCompletionContext
from autogen_core.models import LLMMessage, SystemMessage, UserMessage, AssistantMessage, FunctionExecutionResult, ChatCompletionClient
from data_layer.data_layer import AgentFusionDataLayer
from agent_memory.memrecall_agent import MemRecallAgent
from agent_memory.memrecall_tools import MemRecallResult

logger = logging.getLogger(__name__)


class MemoryContext(ChatCompletionContext):
    """
    A context manager that handles memory storage, retrieval, and intelligent recall.

    Features:
    1. Dynamic memory recall - triggered when get_messages() is called
    2. Integration with MemRecallAgent for intelligent memory search
    3. Memory state management - tracks recalled memories and system messages

    Architecture:
    - MemoryContext: Manages memory state and coordinates recall timing
    - MemRecallAgent: Executes actual search logic
    - Data Layer: Provides storage and search capabilities
    """

    def __init__(
        self,
        data_layer: AgentFusionDataLayer,
        user_id: int = 1,
        memory_model_client: Optional[ChatCompletionClient] = None,
        threshold: int = 1000,
    ):
        """
        Args:
            data_layer: The data layer for database access
            user_id: The ID of the current user
            memory_model_client: LLM client for memory recall operations
            threshold: Token count threshold to trigger memory storage
        """
        self.data_layer = data_layer
        self.user_id = user_id
        self.memory_model_client = memory_model_client
        self.threshold = threshold
        self._messages: List[LLMMessage] = []

        # Memory state management
        self._recalled_memories: List[str] = []  # List of memory_keys already recalled
        self._memory_system_message: Optional[SystemMessage] = None
        self._search_summary: str = ""

        # Initialize MemRecallAgent if model client is available
        self._recall_agent: Optional[MemRecallAgent] = None
        if memory_model_client and data_layer:
            self._recall_agent = MemRecallAgent(
                name="memrecall_agent",
                model_client=memory_model_client,
                data_layer=data_layer,
                user_id=user_id,
                max_search_iterations=2,  # Limit iterations for performance
            )

    def update_user_id(self, user_id: int) -> None:
        """Update the user ID and propagate to recall agent"""
        self.user_id = user_id
        if self._recall_agent:
            self._recall_agent._user_id = user_id

    async def _summarize(self, message: LLMMessage) -> str:
        """Generate a concise summary of the content using LLM if available."""
        source = getattr(message, 'source', 'unknown')
        if not self.memory_model_client:
            return f"Large content from {source}"

        # Prepare context for LLM: 对话在前，system在后（cache-friendly）
        messages_for_llm: List[LLMMessage] = list(self._messages)
        messages_for_llm.append(message)

        system_prompt = (
            "The message above contains a large amount of content. "
            "Please summarize it concisely (under 50 words) to retain the key information for our conversation context."
        )
        messages_for_llm.append(SystemMessage(content=system_prompt, source="system"))

        try:
            result = await self.memory_model_client.create(messages=messages_for_llm)
            return result.content
        except Exception as e:
            logger.error(f"Error summarizing content: {e}")
            return f"Large content from {source}"

    async def add_message(self, message: LLMMessage) -> None:
        """Adds a message to the context, potentially moving large content to memory."""
        content_to_check = ""
        if isinstance(message.content, str):
            content_to_check = message.content

        # Rough token count estimate (characters / 4)
        token_count = len(content_to_check) // 4

        # Determine if we should offload to memory
        if token_count > self.threshold and not isinstance(message, SystemMessage):
            memory_key = str(uuid.uuid4())
            summary = await self._summarize(message)

            if self.data_layer.memory:
                await self.store(
                    content=content_to_check,
                    summary=summary,
                    memory_key=memory_key,
                    metadata={"original_role": type(message).__name__}
                )

                placeholder = f"[MemoryRef: {memory_key} - {summary} - {token_count} tokens]"

                # Create a new message with placeholder
                if isinstance(message, UserMessage):
                    message = UserMessage(content=placeholder, source=message.source)
                elif isinstance(message, AssistantMessage):
                    message = AssistantMessage(content=placeholder, source=message.source)
                elif isinstance(message, FunctionExecutionResult):
                    message = FunctionExecutionResult(content=placeholder, call_id=message.call_id)
            else:
                logger.warning("Memory model not available, skipping offload.")

        self._messages.append(message)

    async def init_memory(self, user_message: Union[str, LLMMessage]) -> List[LLMMessage]:
        """
        Initialize memory recall at the start of a conversation.

        Triggered when a new conversation starts. Analyzes the initial message
        and recalls relevant memories if available.

        Args:
            user_message: The initial user message (str or LLMMessage)

        Returns:
            List of messages including the original and potentially memory system messages
        """
        # Convert to LLMMessage if needed
        if isinstance(user_message, str):
            message = UserMessage(content=user_message, source="user")
        else:
            message = user_message

        # Check if recall is possible
        if not self._recall_agent or not self.data_layer.memory:
            return [message]

        try:
            # Use MemRecallAgent for initial recall
            content = message.content if hasattr(message, 'content') else str(message)
            result = await self._recall_agent.recall_single_shot([message])

            if result.action == "RECALL_SUCCESS" and result.formatted_context:
                # Build memory system message
                self._memory_system_message = self._build_memory_system_message(result)
                self._search_summary = result.search_summary
                self._recalled_memories = [m.memory_key for m in result.memories]

                return [self._memory_system_message, message]

            return [message]

        except Exception as e:
            logger.error(f"Error in init_memory: {e}")
            return [message]

    async def get_messages(self) -> List[LLMMessage]:
        """
        Retrieve messages with intelligent memory recall.

        Triggered before the main Agent calls the LLM. Delegates to MemRecallAgent
        to analyze the conversation and decide if memory recall is needed.

        Returns:
            List of messages including memory context and conversation history
        """
        messages = list(self._messages)

        # Check if recall is needed and possible
        if not self._recall_agent or not messages:
            return messages

        # Only trigger recall on user messages
        last_message = messages[-1]
        if not isinstance(last_message, UserMessage):
            return self._inject_memory_message(messages)

        try:
            # Call MemRecallAgent for dynamic recall
            result = await self._recall_agent.recall_with_context(messages)

            # Update memory state if new memories found
            if result.action == "RECALL_SUCCESS" and result.memories:
                # Filter out already recalled memories
                new_memories = [
                    m for m in result.memories
                    if m.memory_key not in self._recalled_memories
                ]

                if new_memories:
                    # Update recalled memories list
                    self._recalled_memories.extend([m.memory_key for m in new_memories])

                    # Update memory system message
                    self._memory_system_message = self._build_memory_system_message(result)
                    self._search_summary = result.search_summary

            return self._inject_memory_message(messages)

        except Exception as e:
            logger.error(f"Error in dynamic memory recall: {e}")
            return messages

    def _inject_memory_message(self, messages: List[LLMMessage]) -> List[LLMMessage]:
        """Inject memory system message at the beginning of messages"""
        if self._memory_system_message:
            return [self._memory_system_message] + messages
        return messages

    def _build_memory_system_message(self, result: MemRecallResult) -> SystemMessage:
        """Build the memory system message from recall result"""
        content_parts = [
            "## 历史记忆上下文",
            "",
            "以下是根据用户当前问题召回的相关历史记忆。请在回复时参考这些信息：",
            "",
            result.formatted_context,
            "",
            "---",
            "",
            "## 记忆使用指南",
            "",
            "1. **命令类记忆**: 如果用户要求'重新执行'、'再次运行'等，使用记忆中的完整命令",
            "2. **信息类记忆**: 基于记忆中的信息回答用户问题",
            "3. **无相关记忆**: 如果记忆不足以回答用户，正常对话即可",
            "",
            f"搜索摘要: {result.search_summary}",
        ]

        return SystemMessage(content="\n".join(content_parts))

    def clear_memory_context(self) -> None:
        """Clear memory context (called when conversation ends)"""
        self._recalled_memories = []
        self._memory_system_message = None
        self._search_summary = ""

    async def clear(self) -> None:
        """Clear all messages and memory context"""
        self._messages = []
        self.clear_memory_context()

    async def store(
        self,
        content: str,
        summary: str,
        memory_key: str,
        type: str = "command_output",
        metadata: Dict = None
    ) -> str:
        """Store content to memory"""
        if not self.data_layer.memory:
            logger.error("Memory model not available in data layer")
            return ""

        return await self.data_layer.memory.store_memory(
            user_id=self.user_id,
            memory_key=memory_key,
            content=content,
            summary=summary,
            memory_type=type,
            metadata=metadata
        )

    async def retrieve(self, key: str) -> Optional[str]:
        """Retrieve content from memory by key"""
        if not self.data_layer.memory:
            return None
        info = await self.data_layer.memory.retrieve_memory(key)
        return info.content if info else None
