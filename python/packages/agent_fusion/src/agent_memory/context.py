import uuid
import logging
import re
import json
from typing import List, Optional, Union, Dict, Any
from autogen_core.model_context import ChatCompletionContext
from autogen_core.models import ChatMessage, SystemMessage, UserMessage, AssistantMessage, FunctionExecutionResult, ChatCompletionClient
from data_layer.data_layer import AgentFusionDataLayer

logger = logging.getLogger(__name__)

class MemoryContext(ChatCompletionContext):
    """
    A context manager that transparently handles memory storage and retrieval.
    It replaces large message content with placeholders and retrieves them on demand.
    """
    
    def __init__(self, data_layer: AgentFusionDataLayer, user_id: int = 1, threshold: int = 1000, model_client: ChatCompletionClient = None):
        """ 
        Args:
            data_layer: The data layer for database access.
            user_id: The ID of the current user.
            threshold: Token count threshold to trigger memory storage.
            model_client: Optional LLM client for summarization.
        """
        self.data_layer = data_layer
        self.user_id = user_id
        self.threshold = threshold
        self.model_client = model_client
        self._messages: List[ChatMessage] = []
    
    async def _summarize(self, message: ChatMessage) -> str:
        """Generate a concise summary of the content using LLM if available."""
        source = getattr(message, 'source', 'unknown')
        if not self.model_client:
            return f"Large content from {source}"
        
        # Prepare context for LLM to leverage caching
        # [all messages in context] + [newly added message] + [summary prompt]
        messages_for_llm = list(self._messages)
        messages_for_llm.append(message)
        
        prompt = (
            "The message above contains a large amount of content. "
            "Please summarize it concisely (under 50 words) to retain the key information for our conversation context."
        )
        messages_for_llm.append(UserMessage(content=prompt, source="system"))
        
        try:
            result = await self.model_client.create(messages_for_llm)
            return result.content
        except Exception as e:
            logger.error(f"Error summarizing content: {e}")
            return f"Large content from {source}"

    async def add_message(self, message: ChatMessage):
        """
        Adds a message to the context, potentially moving large content to memory.
        """
        content_to_check = ""
        if isinstance(message.content, str):
            content_to_check = message.content
        
        # Rough token count estimate (characters / 4)
        token_count = len(content_to_check) // 4
        
        # Determine if we should offload to memory
        # We generally skip SystemMessages to ensure instructions are kept
        if token_count > self.threshold and not isinstance(message, SystemMessage):
             # Generate key
             memory_key = str(uuid.uuid4())
             
             # Generate summary using LLM
             summary = await self._summarize(message)
             
             # Store
             if self.data_layer.memory:
                await self.store(
                    content=content_to_check,
                    summary=summary,
                    memory_key=memory_key,
                    metadata={"original_role": type(message).__name__}
                )
                
                # Replace content with placeholder
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

    async def get_messages(self) -> List[ChatMessage]:
        """
        Retrieve messages, intelligently expanding memories if relevant to the latest user request.
        """
        messages = list(self._messages)
        if not messages or not self.model_client:
            return messages

        last_message = messages[-1]
        # Only check for expansion if the last message is from the user
        if not isinstance(last_message, UserMessage):
            return messages

        # Find all placeholders in the history
        placeholders = []
        for msg in messages:
            if isinstance(msg.content, str):
                # Regex to match [MemoryRef: <key> - <summary> - <count> tokens]
                matches = re.findall(r"[MemoryRef: ([a-f0-9\-]+) - (.*?) - \d+ tokens]", msg.content)
                for key, summary in matches:
                    placeholders.append({"key": key, "summary": summary})
        
        if not placeholders:
            return messages

        # Ask LLM which memories to expand
        # We don't include the user message explicitly in the prompt string because it's already in 'messages'
        prompt = f"""
        You are a context manager.
        Determine if any of the following compressed memory references are relevant and need to be expanded (retrieved) to answer the user's latest request (the last message in the context).
        
        Available Memories:
        {json.dumps(placeholders, indent=2)}
        
        Return a JSON object with a single key "keys_to_expand" containing a list of memory keys (strings) to retrieve.
        Example: {{"keys_to_expand": ["key1", "key3"]}}
        If none are relevant, return {{"keys_to_expand": []}}.
        Return ONLY the JSON.
        """
        
        try:
            # Prepare context for LLM to leverage caching: [all messages] + [prompt]
            # Using source="system" for the instruction to switch role/context
            messages_for_llm = list(messages)
            messages_for_llm.append(UserMessage(content=prompt, source="system"))
            
            response = await self.model_client.create(messages_for_llm)
            content = response.content
            
            # Robust JSON extraction
            json_str = content
            if "```json" in content:
                json_str = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                json_str = content.split("```")[1].split("```")[0]
            
            try:
                result = json.loads(json_str.strip())
                keys_to_expand = result.get("keys_to_expand", [])
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse JSON from intelligent retrieval: {content}")
                return messages
            
            if not keys_to_expand:
                return messages
            
            # Retrieve and replace
            expanded_messages = []
            for msg in messages:
                new_msg = msg
                if isinstance(msg.content, str):
                    new_content = msg.content
                    replaced = False
                    for key in keys_to_expand:
                        if key in msg.content:
                            memory_content = await self.retrieve(key)
                            if memory_content:
                                # Replace the specific placeholder
                                pattern = re.compile(rf"[MemoryRef: {key} - .*? - \d+ tokens]")
                                new_content = pattern.sub(f"\n[Expanded Memory: {key}]\n{memory_content}\n[End Memory]\n", new_content)
                                replaced = True
                    
                    if replaced:
                        # Reconstruct message with new content
                        if isinstance(msg, UserMessage):
                            new_msg = UserMessage(content=new_content, source=msg.source)
                        elif isinstance(msg, AssistantMessage):
                            new_msg = AssistantMessage(content=new_content, source=msg.source)
                        elif isinstance(msg, FunctionExecutionResult):
                            new_msg = FunctionExecutionResult(content=new_content, call_id=msg.call_id)
                
                expanded_messages.append(new_msg)
            
            return expanded_messages

        except Exception as e:
            logger.error(f"Error in intelligent retrieval: {e}")
            return messages

    async def clear(self):
        self._messages = []

    async def store(self, content: str, summary: str, memory_key: str, type: str = "command_output", metadata: Dict = None) -> str:
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
        if not self.data_layer.memory:
             return None
        info = await self.data_layer.memory.retrieve_memory(key)
        return info.content if info else None
        
    def update_user_id(self, user_id: int):
        self.user_id = user_id
