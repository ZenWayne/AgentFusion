import logging
import os
import codecs
import re
from .filter import add_filter, FilterType

def get_short_path(path):
    parts = path.split(os.sep)
    if len(parts) > 2:
        return os.sep.join(parts[-2:])
    return path

def decode_unicode_escapes(text):
    """解码Unicode转义序列，如 \\u4f60 -> 你，但不转义换行符"""
    try:
        # 只匹配和替换 \uXXXX 格式的Unicode转义序列
        return re.sub(r'\\u([0-9a-fA-F]{4})', lambda m: chr(int(m.group(1), 16)), text)
    except (ValueError, OverflowError):
        # 如果解码失败，返回原始文本
        return text


class ShortPathFormatter(logging.Formatter):
    def format(self, record):
        record.pathname = get_short_path(record.pathname)
        # 格式化消息
        formatted_message = super().format(record)
        # 添加异常堆栈跟踪信息
        if record.exc_info:
            formatted_message += '\n' + self.formatException(record.exc_info)
        # 解码Unicode转义序列
        return decode_unicode_escapes(formatted_message)
    
global_log_filterer = logging.StreamHandler()
global_log_filterer.setFormatter(ShortPathFormatter(
'%(asctime)s [%(levelname)s] %(pathname)s:%(lineno)d - %(message)s'
))

def enable_chainlit_logger(log_level:int=logging.INFO):
    logger = logging.getLogger("chainlit")
    logger.setLevel(log_level)
    logger.addHandler(global_log_filterer)


def enable_autogen_logger(name:list[str], supress_other_level:int=logging.WARNING, filter_types:list[FilterType]=[FilterType.LLMCall]):
    # 设置根logger级别，但不创建默认handler
    logging.getLogger().setLevel(supress_other_level)

    # 如果启用LLMCall过滤器，添加到handler
    if len(filter_types)>0:
        add_filter(global_log_filterer, filter_types)
    
    for n in name:
        logger = logging.getLogger(n)
        # 检查是否已经添加了我们的handler，避免重复添加
        if global_log_filterer not in logger.handlers:
            logger.addHandler(global_log_filterer)
        logger.setLevel(logging.INFO)
        # 防止向上传播到根logger（避免重复输出）
        logger.propagate = False

