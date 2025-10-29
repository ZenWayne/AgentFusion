from abc import ABC, abstractmethod
from typing import AsyncGenerator, List, Union

from autogen_agentchat.messages import BaseAgentEvent, BaseChatMessage
from autogen_agentchat.base import TaskResult
from autogen_core import CancellationToken
from autogen_core.models import LLMMessage


class BaseChatQueue(ABC):
    """Base abstract class for chat queue with push interface"""
    
    def __init__(self):
        self._is_running = False
    
    async def start(
        self,
        *,
        cancellation_token: CancellationToken | None = None,
        output_task_messages: bool = True,
    ):
        """Base start method - can be overridden by derived classes"""
        pass
    
    async def on_switch(self):
        """Base switch method - can be overridden by derived classes"""
        pass
    @abstractmethod
    async def push(self, messages: Union[str, List[LLMMessage]]) -> AsyncGenerator[BaseAgentEvent | BaseChatMessage | TaskResult, None]:
        """Abstract push interface - must be implemented by derived classes"""
        pass
    
    @abstractmethod
    async def task_finished(self, task_result: TaskResult) -> None:
        """Abstract task finished method - must be implemented by derived classes"""
        pass