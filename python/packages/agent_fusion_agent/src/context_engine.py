"""动态上下文引擎模块

实现变量管理，支持动态上下文的加载和更新。
"""

import re
from typing import Dict, List, Optional, Any, Callable, Union, Iterator
from jinja2 import Template, Environment, BaseLoader, TemplateError
from .exceptions import ContextEngineException
from .context_variable import Context


class ContextEngine:
    """动态上下文引擎
    
    集成在每次LLM交互流程中，自动处理提示词中的变量模板。
    支持变量注册和模板渲染。
    """
    
    def __init__(self):
        """初始化上下文引擎"""
        self.variables: Dict[str, Context] = {}
        self.template_cache: Dict[str, str] = {}
        self._global_context_cache: Optional[Dict[str, Any]] = None
        self._cache_dirty = True
        # 初始化jinja2环境
        self.jinja_env = Environment(loader=BaseLoader())
    
    def register_variable(self, name: str, variable: Union[Context, Any]) -> None:
        """注册变量到引擎
        
        Args:
            name: 变量名称
            variable: 变量实例或值
            
        Raises:
            ContextEngineException: 变量注册失败
        """
        try:
            if not isinstance(variable, Context):
                # 如果不是ContextVariable实例，则包装为StaticContextVariable
                from .context_variable import StaticContextVariable
                variable = StaticContextVariable(variable, context_engine=self)
            else:
                # 设置context_engine引用
                variable.context_engine = self
            
            self.variables[name] = variable
            self._invalidate_cache()
            
        except Exception as e:
            raise ContextEngineException(
                f"Failed to register variable '{name}': {e}",
                error_code="VARIABLE_REGISTRATION_ERROR"
            )
    
    def unregister_variable(self, name: str) -> None:
        """取消注册变量
        
        Args:
            name: 变量名称
        """
        if name in self.variables:
            del self.variables[name]
            self._invalidate_cache()
    
    def get_variable(self, name: str) -> Optional[Context]:
        """获取变量实例
        
        Args:
            name: 变量名称
            
        Returns:
            变量实例，如果不存在则返回None
        """
        return self.variables.get(name)
    
    def get_all_variables(self) -> Dict[str, Context]:
        """获取所有变量
        
        Returns:
            变量字典
        """
        return self.variables
    
    def get_context(self, agent_id: Optional[str] = None) -> Dict[str, Any]:
        """获取上下文信息
        
        Args:
            agent_id: 可选的Agent ID，用于获取Agent特定的上下文
            
        Returns:
            上下文字典
        """
        if agent_id:
            return self.get_agent_context(agent_id)
        else:
            return self.get_global_context()
    
    def get_global_context(self) -> Dict[str, Any]:
        """获取全局上下文信息
        
        Returns:
            全局上下文字典
        """
        if self._cache_dirty or self._global_context_cache is None:
            self._global_context_cache = {
                name: str(var) for name, var in self.variables.items()
            }
            self._cache_dirty = False
        
        return self._global_context_cache.copy()
    
    def get_agent_context(self, agent_id: str) -> Dict[str, Any]:
        """获取Agent特定的上下文信息
        
        Args:
            agent_id: Agent的唯一标识符
            
        Returns:
            Agent特定的上下文字典
        """
        agent_context = {}
        
        for name, variable in self.variables.items():
            try:
                agent_specific_value = variable.update_for_agent(agent_id)
                agent_context[name] = agent_specific_value
            except Exception as e:
                # 如果获取Agent特定上下文失败，使用默认值
                agent_context[name] = str(variable)
        
        return agent_context
    
    def update_context(self, response: Any = None) -> None:
        """更新上下文信息
        
        Args:
            response: 可选的响应对象，用于更新相关变量
        """
        # 更新所有变量
        for variable in self.variables.values():
            try:
                variable.update()
            except Exception as e:
                # 记录错误但不中断流程
                pass
        
        # 可以在这里处理响应，更新相关的上下文变量
        if response and hasattr(response, 'content') and 'history' in self.variables:
            history_var = self.variables['history']
            if hasattr(history_var, 'add_message'):
                history_var.add_message('assistant', response.content)
        
        # 使缓存失效
        self._invalidate_cache()
    
    def render_template(self, template: str, agent_id: Optional[str] = None) -> str:
        """使用jinja2渲染模板字符串
        
        Args:
            template: 包含变量占位符的模板字符串
            agent_id: 可选的Agent ID，用于获取Agent特定的上下文
            
        Returns:
            渲染后的字符串
            
        Raises:
            ContextEngineException: 模板渲染失败
        """
        try:
            # 检查模板缓存
            cache_key = f"{template}_{agent_id}" if agent_id else template
            if cache_key in self.template_cache and not self._cache_dirty:
                return self.template_cache[cache_key]
            
            # 获取上下文数据
            context_data = self.get_context(agent_id)
            
            # 使用jinja2渲染模板
            rendered = self._render_template_with_jinja2(template, context_data)
            
            # 缓存结果
            self.template_cache[cache_key] = rendered
            
            return rendered
            
        except Exception as e:
            raise ContextEngineException(
                f"Template rendering failed: {e}",
                error_code="TEMPLATE_RENDERING_ERROR",
                context={"template": template, "agent_id": agent_id}
            )
    
    def _render_template_with_jinja2(self, template: str, 
                                   context_data: Dict[str, Any]) -> str:
        """使用jinja2渲染模板
        
        Args:
            template: 模板字符串
            context_data: 上下文数据
            
        Returns:
            渲染后的字符串
            
        Raises:
            TemplateError: jinja2模板渲染错误
        """
        try:
            jinja_template = self.jinja_env.from_string(template)
            return jinja_template.render(**context_data)
        except TemplateError as e:
            # 如果jinja2渲染失败，回退到简单的字符串替换
            return self._render_template_with_context(template, context_data)
    
    def _render_template_with_context(self, template: str, 
                                    context_data: Dict[str, Any]) -> str:
        """使用上下文数据渲染模板（简单字符串替换）
        
        Args:
            template: 模板字符串
            context_data: 上下文数据
            
        Returns:
            渲染后的字符串
        """
        # 查找所有变量占位符 {variable_name}
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, template)
        
        rendered = template
        for match in matches:
            variable_name = match.strip()
            
            if variable_name in context_data:
                placeholder = f"{{{variable_name}}}"
                value = str(context_data[variable_name])
                rendered = rendered.replace(placeholder, value)
            else:
                # 如果变量不存在，保留原占位符或替换为空字符串
                placeholder = f"{{{variable_name}}}"
                rendered = rendered.replace(placeholder, f"[UNDEFINED: {variable_name}]")
        
        return rendered
    
    def validate_template(self, template: str) -> List[str]:
        """验证模板中的变量是否已注册
        
        Args:
            template: 模板字符串
            
        Returns:
            未注册的变量名列表
        """
        pattern = r'\{([^}]+)\}'
        matches = re.findall(pattern, template)
        
        undefined_variables = []
        for match in matches:
            variable_name = match.strip()
            if variable_name not in self.variables:
                undefined_variables.append(variable_name)
        
        return undefined_variables
    

    
    def _invalidate_cache(self) -> None:
        """使缓存失效"""
        self._cache_dirty = True
        self.template_cache.clear()
        self._global_context_cache = None
    
    def clear_cache(self) -> None:
        """清除所有缓存"""
        self._invalidate_cache()
        
        # 同时清除所有变量的缓存
        for variable in self.variables.values():
            variable.invalidate_cache()
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取引擎统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "total_variables": len(self.variables),
            "cache_size": len(self.template_cache),
            "cache_dirty": self._cache_dirty
        }


class GroupChatContextEngine(ContextEngine):
    """群聊上下文引擎
    
    扩展基础ContextEngine，为群聊场景提供专门的变量管理。
    """
    
    def __init__(self):
        super().__init__()
    
    def register_groupchat_variable(self, name: str, variable: Context) -> None:
        """注册GroupChat专用变量
        
        Args:
            name: 变量名称
            variable: 变量实例
        """
        self.register_variable(name, variable)
    
    def update_agent_context(self, agent_id: str, response: Any = None) -> None:
        """更新Agent上下文
        
        Args:
            agent_id: Agent的唯一标识符
            response: 可选的响应对象
        """
        # 更新所有变量
        for variable in self.variables.values():
            try:
                if hasattr(variable, 'update_for_agent'):
                    variable.update_for_agent(agent_id)
                else:
                    variable.update()
            except Exception as e:
                # 记录错误但不中断流程
                pass
        
        # 更新群聊相关的上下文变量
        if response and hasattr(response, 'content'):
            # 更新历史记录
            if 'history' in self.variables:
                history_var = self.variables['history']
                if hasattr(history_var, 'add_message'):
                    history_var.add_message(f'agent_{agent_id}', response.content)
            
            # 更新群聊上下文
            if 'group_context' in self.variables:
                group_var = self.variables['group_context']
                if hasattr(group_var, 'set_group_data'):
                    group_var.set_group_data(f'last_speaker', agent_id)
                    group_var.set_group_data(f'last_message', response.content)
        
        # 使缓存失效
        self._invalidate_cache()
    
    def before_agent_interaction(self, template: str, agent_id: str) -> str:
        """Agent交互前的准备工作
        
        Args:
            template: 提示词模板
            agent_id: Agent的唯一标识符
            
        Returns:
            处理后的提示词
        """
        # 更新Agent上下文
        self.update_agent_context(agent_id)
        
        # 渲染模板
        rendered_template = self.render_template(template, agent_id)
        
        return rendered_template
    
    def after_agent_interaction(self, agent_id: str, response: Any) -> None:
        """Agent交互后的处理工作
        
        Args:
            agent_id: Agent的唯一标识符
            response: Agent的响应
        """
        # 更新Agent上下文
        self.update_agent_context(agent_id, response)
    
    def get_group_statistics(self) -> Dict[str, Any]:
        """获取群聊统计信息
        
        Returns:
            群聊统计信息字典
        """
        base_stats = self.get_statistics()
        
        group_stats = {
            "groupchat_variables": len([
                var for var in self.variables.values() 
                if hasattr(var, 'update_for_agent')
            ])
        }
        
        return {**base_stats, **group_stats} 