import logging
import json

class FilterType:
    LLMCall = 'LLMCall'
    ToolCall = 'ToolCall'

def add_filter(logger:logging.Logger, filter_type:list[FilterType]):
    logger.addFilter(CallFilter(filter_type))

class CallFilter(logging.Filter):
    """过滤器：只允许LLMCall类型的日志通过"""
    def __init__(self, filter_type:list[FilterType]):
        self.filter_type = filter_type
    def filter(self, record):
        try:
            # 尝试解析日志消息为JSON
            message = record.getMessage()
            data = json.loads(message)
            # 检查是否包含type字段且值为LLMCall
            return data.get('type') in self.filter_type
        except (json.JSONDecodeError, AttributeError):
            # 如果不是JSON格式或解析失败，默认通过过滤器
            return True

class ToolCallFilter(logging.Filter):
    """过滤器：只允许LLMCall类型的日志通过"""
    def filter(self, record):
        try:
            # 尝试解析日志消息为JSON
            message = record.getMessage()
            data = json.loads(message)
            # 检查是否包含type字段且值为ToolCall
            return data.get('type') == 'ToolCall'
        except (json.JSONDecodeError, AttributeError):
            # 如果不是JSON格式或解析失败，不通过过滤器
            return False