from autogen_core.tools import StaticStreamWorkbench, Workbench
from abc import ABC, abstractmethod
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_agentchat import TRACE_LOGGER_NAME
from openai import NOT_GIVEN, AsyncAzureOpenAI, AsyncOpenAI
#from .rerank import rerank_tools_with_dashscope
from autogen_core.tools import BaseTool, ToolOverride
from typing import Any, Callable, Awaitable, Sequence
from autogen_core.models import LLMMessage, SystemMessage
from autogen_agentchat.messages import TextMessage
from autogen_core.tools import ToolSchema
from autogen_core import CancellationToken
import logging

logger = logging.getLogger(TRACE_LOGGER_NAME)

class DynamicWorkbench(ABC):
    @abstractmethod
    def add_tool(
        self, tool: BaseTool | Callable[..., Any] | Callable[..., Awaitable[Any]], enabled: bool = True
    ) -> None: ...

    @abstractmethod
    def remove_tool(self, tool_name: str) -> None: ...

    @abstractmethod
    def remove_all_tools(self) -> None: ...

    @abstractmethod
    def get_tools_for_context(self, tool_name: str) -> None: ...


class VectorStreamWorkbench(StaticStreamWorkbench):
   
    def __init__(
        self, 
        tools: list[BaseTool[Any, Any]], 
        tool_overrides: dict[str, ToolOverride]| None = None,
        top_k: int = 10,
    ):
       super().__init__(
        tools=tools,
        tool_overrides=tool_overrides
        )
       self._top_k = top_k
       
    def get_tools_for_context(self, context: Sequence[LLMMessage]) -> list[BaseTool]:

        query = "\n".join([msg.content for msg in context if not isinstance(msg, SystemMessage)][-5:]).strip()
        return self._get_tools_for_query(query)
   
    def _get_tools_for_query(self, query: str) -> list[ToolSchema]:        
        # 使用DashScope重排序进行二次排序            
        # reranked_tools = rerank_tools_with_dashscope(
        #     query=query,
        #     tools=self._tools,
        #     top_n=self._top_k
        # )

        reranked_tools = self._tools
        result_schemas: list[ToolSchema] = []
        for tool in reranked_tools:
            original_schema = tool.schema

            # Apply overrides if they exist for this toolp
            if tool.name in self._tool_overrides:
                override = self._tool_overrides[tool.name]
                # Create a new ToolSchema with overrides applied
                schema: ToolSchema = {
                    "name": override.name if override.name is not None else original_schema["name"],
                    "description": override.description
                    if override.description is not None
                    else original_schema.get("description", ""),
                }
                # Copy optional fields
                if "parameters" in original_schema:
                    schema["parameters"] = original_schema["parameters"]
                if "strict" in original_schema:
                    schema["strict"] = original_schema["strict"]
            else:
                schema = original_schema

            result_schemas.append(schema)
        return reranked_tools
