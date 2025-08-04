"""
基于DashScope文本重排序的rerank函数实现
用于重排文档并返回对应的索引排名，结合self._tools[i]对工具重排
"""

import dashscope
from http import HTTPStatus
import logging
from typing import List, Dict, Any, Tuple, Optional
from autogen_core.tools import BaseTool
from tools.utils.base import lazy_tool_loader

logger = logging.getLogger(__name__)


def rerank_documents_with_dashscope(query: str, documents: List[str], top_n: int = 10, 
                                  model: str = "gte-rerank-v2") -> Tuple[List[int], List[float]]:
    """
    使用DashScope重排序文档，返回重排后的索引列表
    
    Args:
        query: 查询文本
        documents: 文档列表
        top_n: 返回前N个结果
        model: 重排序模型名称
        
    Returns:
        Tuple[List[int], List[float]]: (重排后的原始索引列表, 相关性分数列表)
        例如：如果原来序列中第3个文档排名最高，则返回的第一个索引是3
    """
    try:
        # 调用DashScope文本重排序API
        resp = dashscope.TextReRank.call(
            model=model,
            query=query,
            documents=documents,
            top_n=top_n,
            return_documents=True
        )
        
        if resp.status_code == HTTPStatus.OK:
            results = resp.output.get('results', [])
            
            # 提取重排后的索引和分数
            reranked_indices = []
            relevance_scores = []
            
            for result in results:
                original_index = result['index']  # 原始文档在输入列表中的索引
                score = result['relevance_score']  # 相关性分数
                
                reranked_indices.append(original_index)
                relevance_scores.append(score)
            
            logger.info(f"DashScope rerank成功: 查询='{query}', 重排索引={reranked_indices}, 分数={relevance_scores}")
            return reranked_indices, relevance_scores
            
        else:
            logger.error(f"DashScope rerank失败: status={resp.status_code}, message={resp.message}")
            # 失败时返回原始顺序
            original_indices = list(range(len(documents)))
            default_scores = [1.0] * len(documents)  # 默认分数
            return original_indices[:top_n], default_scores[:top_n]
            
    except Exception as e:
        logger.error(f"DashScope rerank异常: {str(e)}")
        # 异常时返回原始顺序
        original_indices = list(range(len(documents)))
        default_scores = [1.0] * len(documents)
        return original_indices[:top_n], default_scores[:top_n]


def rerank_tools_with_dashscope(query: str, tools: List[BaseTool[Any, Any]], top_n: int = 10, 
                               model: str = "gte-rerank-v2") -> List[BaseTool[Any, Any]]:
    """
    使用DashScope重排序工具列表，返回重排后的工具
    
    Args:
        query: 查询文本
        tools: 工具列表 (self._tools)
        top_n: 返回前N个工具
        model: 重排序模型名称
        
    Returns:
        List[Any]: 重排后的工具列表
    """
    if not tools or len(query.strip()) == 0:
        return tools[:top_n] if tools else []
    
    # 构建文档列表 - 使用工具的名称和描述作为文档内容
    documents = []
    for tool in tools:
        if hasattr(tool, 'name') and hasattr(tool, 'description'):
            doc = f"{tool.name}: {tool.description}"
        elif hasattr(tool, 'name'):
            doc = tool.name
        elif hasattr(tool, '__name__'):
            doc = tool.__name__  # 对于函数工具
        else:
            doc = str(tool)
        documents.append(doc)
    
    logger.info(f"准备重排序 {len(tools)} 个工具，查询: '{query}'")
    
    # 使用DashScope进行重排序
    reranked_indices, scores = rerank_documents_with_dashscope(
        query=query,
        documents=documents,
        top_n=top_n,
        model=model
    )
    
    # 根据重排后的索引重新排列工具
    # reranked_indices中包含原始工具在tools列表中的索引
    reranked_tools = []
    for idx in reranked_indices:
        if 0 <= idx < len(tools):  # 确保索引有效
            reranked_tools.append(tools[idx])  # 这里的tools[idx]就是self._tools[i]的模式
    
    logger.info(f"工具重排序完成: 原始索引顺序={reranked_indices}, 分数={scores}")
    return reranked_tools


class DashScopeReranker:
    """DashScope重排序器类，封装重排序逻辑"""
    
    def __init__(self, model: str = "gte-rerank-v2", top_n: int = 10):
        self.model = model
        self.top_n = top_n
    
    def rerank(self, query: str, items: List[Any], 
               text_extractor=None) -> Tuple[List[int], List[float], List[Any]]:
        """
        通用重排序方法
        
        Args:
            query: 查询文本
            items: 要重排序的项目列表
            text_extractor: 文本提取函数，用于从项目中提取文本用于重排序
            
        Returns:
            Tuple[List[int], List[float], List[Any]]: (重排索引, 分数, 重排项目)
        """
        if not items:
            return [], [], []
        
        # 提取文本用于重排序
        if text_extractor:
            documents = [text_extractor(item) for item in items]
        else:
            documents = [str(item) for item in items]
        
        # 执行重排序
        reranked_indices, scores = rerank_documents_with_dashscope(
            query=query,
            documents=documents,
            top_n=self.top_n,
            model=self.model
        )
        
        # 重排项目
        reranked_items = [items[idx] for idx in reranked_indices if 0 <= idx < len(items)]
        
        return reranked_indices, scores, reranked_items


# 工具函数实现
def dashscope_rerank_documents(query: str, documents: List[str], top_n: int = 10, 
                              model: str = "gte-rerank-v2") -> Dict[str, Any]:
    """
    使用DashScope重排序文档的工具函数
    
    Returns:
        Dict包含: reranked_indices, scores, reranked_documents, query
    """
    reranked_indices, scores = rerank_documents_with_dashscope(query, documents, top_n, model)
    reranked_documents = [documents[idx] for idx in reranked_indices if 0 <= idx < len(documents)]
    
    return {
        "reranked_indices": reranked_indices,
        "scores": scores,
        "reranked_documents": reranked_documents,
        "query": query,
        "model": model
    }


def dashscope_rerank_tools(query: str, tools: List[Any], top_n: int = 10, 
                          model: str = "gte-rerank-v2") -> List[Any]:
    """
    使用DashScope重排序工具的工具函数
    """
    return rerank_tools_with_dashscope(query, tools, top_n, model)


# 工具函数的懒加载lambda
dashscope_rerank_documents_tool = lambda: lazy_tool_loader(dashscope_rerank_documents)
dashscope_rerank_tools_tool = lambda: lazy_tool_loader(dashscope_rerank_tools)