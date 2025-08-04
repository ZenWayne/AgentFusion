from typing import TypeVar, Generic
from base.handoff import FunctionToolWithType, ToolType

T = TypeVar('T')  # function type here

class lazy_tool_loader(Generic[T]):
    def __init__(self, func: T):
        self.func = func
    
    def __call__(self, *args, **kwargs):
        return FunctionToolWithType(
            self.func, 
            name=self.func.__name__,
            description=self.func.__doc__ or f"Tool for {self.func.__name__}", 
            strict=False,
            type=ToolType.NORMAL_TOOL,
        )