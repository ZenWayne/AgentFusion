"""群聊系统模块

实现多Agent协作功能，通过智能提示词动态选择下一个发言的Agent。
"""

import uuid
from typing import Dict, List, Optional, Any, AsyncGenerator, Callable
from dataclasses import dataclass, field
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from .agent import AgentBase, AgentConfig
from .context_engine import GroupChatContextEngine
from .message_queue import MessageQueueBase, Message, get_message_queue_manager
from .exceptions import GroupChatException, ValidationException

# 获取tracer
tracer = trace.get_tracer(__name__)


@dataclass
class GroupChatConfig:
    """群聊配置数据类"""
    group_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "GroupChat"
    description: str = ""
    selector_model: str = "gpt-3.5-turbo"
    selector_prompt: str = ""
    max_rounds: int = 10
    max_messages_per_round: int = 1
    allow_self_talk: bool = False
    message_queue_id: Optional[str] = None
    context_variables: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            "group_id": self.group_id,
            "name": self.name,
            "description": self.description,
            "selector_model": self.selector_model,
            "selector_prompt": self.selector_prompt,
            "max_rounds": self.max_rounds,
            "max_messages_per_round": self.max_messages_per_round,
            "allow_self_talk": self.allow_self_talk,
            "message_queue_id": self.message_queue_id,
            "context_variables": self.context_variables,
            "metadata": self.metadata
        }


@dataclass
class GroupChatSession:
    """群聊会话数据类"""
    session_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    group_id: str = ""
    current_round: int = 0
    messages_in_round: int = 0
    last_speaker: Optional[str] = None
    participants: List[AgentBase] = field(default_factory=list)
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)


class GroupChat:
    """群聊系统
    
    管理多个Agent的协作对话，通过智能选择机制确定下一个发言的Agent。
    """
    
    @tracer.start_as_current_span("groupchat_init")
    def __init__(self, config: GroupChatConfig):
        """初始化群聊
        
        Args:
            config: 群聊配置
        """
        span = trace.get_current_span()
        span.set_attribute("group_id", config.group_id)
        span.set_attribute("group_name", config.name)
        span.set_attribute("max_rounds", config.max_rounds)
        
        self.config = config
        self.agents: Dict[str, AgentBase] = {}
        self.context_engine = GroupChatContextEngine()
        self.message_manager = get_message_queue_manager()
        
        # 初始化组件
        self._initialize_components()
        
        # 会话管理
        self.current_session: Optional[GroupChatSession] = None
        self._selector_cache: Dict[str, str] = {}
        self._observers: List[Callable[[str, Any], None]] = []
        
        span.add_event("groupchat_initialized")
    
    @tracer.start_as_current_span("add_agent")
    def add_agent(self, agent: AgentBase, role: Optional[str] = None) -> None:
        """添加Agent到群聊
        
        Args:
            agent: Agent实例
            role: 可选的角色描述
        """
        span = trace.get_current_span()
        span.set_attribute("agent_id", agent.config.agent_id)
        span.set_attribute("agent_name", agent.config.name)
        span.set_attribute("group_id", self.config.group_id)
        if role:
            span.set_attribute("role", role)
        
        if agent.config.agent_id in self.agents:
            span.set_status(Status(StatusCode.ERROR, "Agent already in group"))
            raise GroupChatException(f"Agent {agent.config.agent_id} already in group")
        
        self.agents[agent.config.agent_id] = agent
        
        # 设置Agent的消息队列为群聊队列
        if self.config.message_queue_id:
            agent.config.message_queue_id = self.config.message_queue_id
        
        span.add_event("agent_added_to_group")
        
        self._notify_observers("agent_added", {
            "agent_id": agent.config.agent_id,
            "agent_name": agent.config.name,
            "role": role
        })
    
    @tracer.start_as_current_span("remove_agent")
    def remove_agent(self, agent_id: str) -> None:
        """从群聊中移除Agent
        
        Args:
            agent_id: Agent ID
        """
        span = trace.get_current_span()
        span.set_attribute("agent_id", agent_id)
        span.set_attribute("group_id", self.config.group_id)
        
        if agent_id in self.agents:
            agent = self.agents[agent_id]
            del self.agents[agent_id]
            
            span.add_event("agent_removed_from_group")
            
            self._notify_observers("agent_removed", {
                "agent_id": agent_id,
                "agent_name": agent.config.name
            })
        else:
            span.add_event("agent_not_found")
    
    def get_agent(self, agent_id: str) -> Optional[AgentBase]:
        """获取Agent
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent实例，如果不存在则返回None
        """
        return self.agents.get(agent_id)
    
    def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有Agent信息
        
        Returns:
            Agent信息列表
        """
        return [
            {
                "agent_id": agent.config.agent_id,
                "name": agent.config.name,
                "description": agent.config.description,
                "model": agent.config.model
            }
            for agent in self.agents.values()
        ]
    
    @tracer.start_as_current_span("start_session")
    def start_session(self, participants: Optional[List[str]] = None) -> GroupChatSession:
        """开始新的群聊会话
        
        Args:
            participants: 参与者Agent ID列表，如果为None则包含所有Agent
            
        Returns:
            群聊会话对象
        """
        span = trace.get_current_span()
        span.set_attribute("group_id", self.config.group_id)
        
        if self.current_session and self.current_session.is_active:
            span.set_status(Status(StatusCode.ERROR, "Another session is already active"))
            raise GroupChatException("Another session is already active")
        
        if not participants:
            participants = list(self.agents.keys())
        
        span.set_attribute("participant_count", len(participants))
        
        # 验证参与者
        for agent_id in participants:
            if agent_id not in self.agents:
                span.set_status(Status(StatusCode.ERROR, f"Agent {agent_id} not found"))
                raise GroupChatException(f"Agent {agent_id} not found in group")
        
        self.current_session = GroupChatSession(
            group_id=self.config.group_id,
            participants=participants
        )
        
        span.set_attribute("session_id", self.current_session.session_id)
        span.add_event("session_started")
        
        self._notify_observers("session_started", {
            "session_id": self.current_session.session_id,
            "participants": participants
        })
        
        return self.current_session
    
    @tracer.start_as_current_span("end_session")
    def end_session(self) -> None:
        """结束当前会话"""
        span = trace.get_current_span()
        if self.current_session:
            span.set_attribute("session_id", self.current_session.session_id)
            span.set_attribute("total_rounds", self.current_session.current_round)
            
            self.current_session.is_active = False
            
            span.add_event("session_ended")
            
            self._notify_observers("session_ended", {
                "session_id": self.current_session.session_id,
                "total_rounds": self.current_session.current_round
            })
        else:
            span.add_event("no_active_session")
    
    async def process_message(self, message: str, sender_id: Optional[str] = None,
                             **kwargs) -> List[Dict[str, Any]]:
        """处理群聊消息
        
        Args:
            message: 输入消息
            sender_id: 发送者ID，如果为None则自动选择第一个发言者
            **kwargs: 其他参数
            
        Returns:
            响应消息列表
        """
        with tracer.start_as_current_span("process_message") as span:
            span.set_attribute("message_length", len(message))
            span.set_attribute("group_id", self.config.group_id)
            if sender_id:
                span.set_attribute("sender_id", sender_id)
            
            if not self.current_session or not self.current_session.is_active:
                span.set_status(Status(StatusCode.ERROR, "No active session"))
                raise GroupChatException("No active session")
            
            if not self.current_session.participants:
                span.set_status(Status(StatusCode.ERROR, "No participants in session"))
                raise GroupChatException("No participants in session")
            
            span.set_attribute("session_id", self.current_session.session_id)
            span.set_attribute("participant_count", len(self.current_session.participants))
            
            responses = []
            
            try:
                # 添加用户消息到历史
                self._add_message_to_history("user", message, sender_id="user")
                
                # 重置轮次计数器
                self.current_session.current_round += 1
                self.current_session.messages_in_round = 0
                
                # 选择第一个发言者
                if not sender_id:
                    sender_id = await self._select_next_speaker(message)
                
                current_speaker = sender_id
                span.set_attribute("first_speaker", current_speaker)
                
                # 进行对话轮次
                while (self.current_session.current_round <= self.config.max_rounds and
                       self.current_session.messages_in_round < self.config.max_messages_per_round):
                    
                    with tracer.start_as_current_span("agent_turn") as agent_span:
                        agent_span.set_attribute("current_speaker", current_speaker)
                        agent_span.set_attribute("round", self.current_session.current_round)
                        agent_span.set_attribute("message_index", self.current_session.messages_in_round)
                        
                        # 获取当前发言者
                        agent = self.get_agent(current_speaker)
                        if not agent:
                            agent_span.add_event("agent_not_found")
                            break
                        
                        # 准备Agent上下文
                        agent_context = self._prepare_agent_context(current_speaker)
                        
                        # 处理消息
                        if self.current_session.messages_in_round == 0:
                            # 第一条消息使用原始输入
                            agent_message = message
                        else:
                            # 后续消息基于上下文生成
                            agent_message = self._generate_followup_message(current_speaker)
                        
                        response = await agent.process_message(agent_message, **kwargs)
                        
                        # 记录响应
                        response_data = {
                            "agent_id": current_speaker,
                            "agent_name": agent.config.name,
                            "content": response.content,
                            "model": response.model,
                            "usage": response.usage,
                            "round": self.current_session.current_round,
                            "message_index": self.current_session.messages_in_round
                        }
                        responses.append(response_data)
                        
                        # 添加到历史记录
                        self._add_message_to_history("assistant", response.content, 
                                                   sender_id=current_speaker,
                                                   model=response.model,
                                                   usage=response.usage)
                        
                        # 更新会话状态
                        self.current_session.last_speaker = current_speaker
                        self.current_session.messages_in_round += 1
                        
                        # 触发Agent交互后的Hook
                        self.context_engine.post_agent_interaction(current_speaker, response)
                        
                        agent_span.add_event("agent_response_generated")
                        
                        # 选择下一个发言者
                        if self.current_session.messages_in_round < self.config.max_messages_per_round:
                            next_speaker = await self._select_next_speaker(response.content, current_speaker)
                            
                            # 检查是否允许自言自语
                            if next_speaker == current_speaker and not self.config.allow_self_talk:
                                agent_span.add_event("self_talk_not_allowed")
                                break
                            
                            current_speaker = next_speaker
                        else:
                            break
                
                span.set_attribute("response_count", len(responses))
                span.add_event("message_processing_completed")
                return responses
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise GroupChatException(f"Message processing failed: {e}")
    
    @tracer.start_as_current_span("stream_process_message")
    async def stream_process_message(self, message: str, sender_id: Optional[str] = None,
                                   **kwargs) -> AsyncGenerator[Dict[str, Any], None]:
        """流式处理群聊消息
        
        Args:
            message: 输入消息
            sender_id: 发送者ID
            **kwargs: 其他参数
            
        Returns:
            异步生成器，产生流式响应
        """
        #CR:这里的trace都去掉
        with tracer.start_as_current_span("stream_process_message") as span:
            span.set_attribute("message_length", len(message))
            span.set_attribute("group_id", self.config.group_id)
            if sender_id:
                span.set_attribute("sender_id", sender_id)
            
            if not self.current_session or not self.current_session.is_active:
                span.set_status(Status(StatusCode.ERROR, "No active session"))
                raise GroupChatException("No active session")
            
            span.set_attribute("session_id", self.current_session.session_id)
            
            try:
                # 添加用户消息到历史
                self._add_message_to_history("user", message, sender_id="user")
                
                # 选择发言者
                if not sender_id:
                    participant_name = await self._select_next_speaker(message)
                
                agent = self.get_agent(participant_name)
                if not agent:
                    span.set_status(Status(StatusCode.ERROR, f"Agent {participant_name} not found"))
                    raise GroupChatException(f"Agent {participant_name} not found")
                
                span.set_attribute("selected_agent", sender_id)
                
                # 准备Agent上下文
                agent_context = self._prepare_agent_context(sender_id)
                
                # 流式处理
                accumulated_content = ""
                chunk_count = 0
                
                async for chunk in agent.stream_process_message(message, **kwargs):
                    chunk_count += 1
                    accumulated_content += chunk.content
                    
                    # 产生流式响应
                    yield {
                        "agent_id": sender_id,
                        "agent_name": agent.config.name,
                        "chunk": chunk.content,
                        "is_final": chunk.is_final,
                        "accumulated_content": accumulated_content,
                        "metadata": chunk.metadata
                    }
                    
                    # 如果是最终块，添加到历史记录
                    if chunk.is_final:
                        self._add_message_to_history("assistant", accumulated_content,
                                                   sender_id=sender_id,
                                                   model=agent.config.model)
                        
                        # 更新会话状态
                        self.current_session.last_speaker = sender_id
                        
                        span.set_attribute("total_chunks", chunk_count)
                        span.set_attribute("response_length", len(accumulated_content))
                        span.add_event("stream_processing_completed")
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise GroupChatException(f"Stream processing failed: {e}")

    @tracer.start_as_current_span("select_next_speaker")
    async def _select_next_speaker(self, message: str, 
                                 current_speaker: Optional[str] = None) -> str:
        """选择下一个发言者"""
        #CR:这里的trace都去掉
        with tracer.start_as_current_span("select_next_speaker") as span:
            if not self.current_session:
                span.set_status(Status(StatusCode.ERROR, "No active session"))
                raise GroupChatException("No active session")
            
            participants = self.current_session.participants
            span.set_attribute("participant_count", len(participants))
            if current_speaker:
                span.set_attribute("current_speaker", current_speaker)
            
            if len(participants) == 1:
                span.add_event("single_participant")
                return participants[0]
            
            #CR:这里需要一个选择器，选择器需要一个方法来选择下一个发言者
            # 这个选择器可以是一个函数，但默认是根据message_queue及传入的prompt来选择speaker
            # 简化版本：轮流选择
            try:
                if not current_speaker:
                    selected = participants[0]
                else:
                    current_index = participants.index(current_speaker)
                    next_index = (current_index + 1) % len(participants)
                    selected = participants[next_index].name
                
                span.set_attribute("selected_agent", selected)
                span.add_event("speaker_selected")
                return selected.name
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                return participants[0].name
    
    def _prepare_selector_prompt(self, message: str, 
                               current_speaker: Optional[str] = None) -> str:
        """准备选择器提示词
        
        Args:
            message: 当前消息
            current_speaker: 当前发言者
            
        Returns:
            选择器提示词
        """
        if self.config.selector_prompt:
            # 使用自定义选择器提示词
            base_prompt = self.config.selector_prompt
        else:
            # 使用默认选择器提示词
            base_prompt = """You are a conversation moderator in a group chat with multiple AI agents.
Your task is to select the most appropriate agent to respond next based on the conversation context.

Available agents:
{agent_list}

Current conversation context:
{conversation_history}

Recent message: {message}
Current speaker: {current_speaker}

Select the agent ID who should respond next. Only return the agent ID, nothing else."""
        
        # 准备变量
        agent_list = "\n".join([
            f"- {agent_id}: {agent.config.name} - {agent.config.description}"
            for agent_id, agent in self.agents.items()
        ])
        
        conversation_history = self._get_recent_conversation(limit=5)
        
        # 渲染提示词
        rendered_prompt = base_prompt.format(
            agent_list=agent_list,
            conversation_history=conversation_history,
            message=message,
            current_speaker=current_speaker or "None"
        )
        
        return rendered_prompt
    
    def _parse_selector_response(self, response: str, participants: List[str]) -> str:
        """解析选择器响应
        
        Args:
            response: 选择器响应
            participants: 参与者列表
            
        Returns:
            选择的Agent ID
        """
        response = response.strip()
        
        # 检查是否直接匹配Agent ID
        for agent_id in participants:
            if agent_id in response:
                return agent_id
        
        # 检查是否匹配Agent名称
        for agent_id in participants:
            agent = self.agents[agent_id]
            if agent.config.name.lower() in response.lower():
                return agent_id
        
        # 如果都不匹配，返回第一个参与者
        return participants[0]
    
    def _fallback_speaker_selection(self, current_speaker: Optional[str] = None) -> str:
        """备用的发言者选择策略
        
        Args:
            current_speaker: 当前发言者
            
        Returns:
            选择的Agent ID
        """
        if not self.current_session:
            return list(self.agents.keys())[0]
        
        participants = self.current_session.participants
        
        if not current_speaker:
            return participants[0]
        
        # 轮流选择
        try:
            current_index = participants.index(current_speaker)
            next_index = (current_index + 1) % len(participants)
            return participants[next_index]
        except ValueError:
            return participants[0]
    
    def _prepare_agent_context(self, agent_id: str) -> str:
        """准备Agent特定的上下文
        
        Args:
            agent_id: Agent ID
            
        Returns:
            Agent上下文字符串
        """
        return self.context_engine.prepare_for_agent_interaction("", agent_id)
    
    def _generate_followup_message(self, agent_id: str) -> str:
        """生成后续消息
        
        Args:
            agent_id: Agent ID
            
        Returns:
            后续消息内容
        """
        # 简单实现：基于最近的对话历史生成
        recent_history = self._get_recent_conversation(limit=3)
        return f"Continue the conversation based on: {recent_history}"
    
    def _add_message_to_history(self, role: str, content: str, 
                              sender_id: Optional[str] = None, **metadata) -> None:
        """添加消息到历史记录
        
        Args:
            role: 消息角色
            content: 消息内容
            sender_id: 发送者ID
            **metadata: 额外元数据
        """
        if self.config.message_queue_id:
            queue = self.message_manager.get_queue(self.config.message_queue_id)
            if queue:
                message = Message(
                    role=role,
                    content=content,
                    agent_id=sender_id,
                    metadata={
                        "session_id": self.current_session.session_id if self.current_session else None,
                        "round": self.current_session.current_round if self.current_session else 0,
                        **metadata
                    }
                )
                queue.update(message)
    
    def _get_recent_conversation(self, limit: int = 10) -> str:
        """获取最近的对话记录
        
        Args:
            limit: 限制消息数量
            
        Returns:
            格式化的对话记录
        """
        if not self.config.message_queue_id:
            return ""
        
        queue = self.message_manager.get_queue(self.config.message_queue_id)
        if not queue:
            return ""
        
        messages = queue.get_messages(limit=limit)
        
        formatted = []
        for msg in messages[-limit:]:  # 获取最近的消息
            sender = msg.agent_id or "user"
            formatted.append(f"{sender}: {msg.content}")
        
        return "\n".join(formatted)
    
    def _initialize_components(self) -> None:
        """初始化组件"""
        # 初始化上下文变量
        for var_name, var_value in self.config.context_variables.items():
            self.context_engine.register_variable(var_name, var_value)
        
        # 确保消息队列存在
        if self.config.message_queue_id:
            self.message_manager.get_or_create_queue(
                self.config.message_queue_id,
                queue_type="memory"
            )
        else:
            # 自动创建消息队列
            self.config.message_queue_id = f"groupchat_{self.config.group_id}"
            self.message_manager.get_or_create_queue(
                self.config.message_queue_id,
                queue_type="memory"
            )
    
    def add_observer(self, observer: Callable[[str, Any], None]) -> None:
        """添加观察者
        
        Args:
            observer: 观察者函数
        """
        self._observers.append(observer)
    
    def remove_observer(self, observer: Callable[[str, Any], None]) -> None:
        """移除观察者
        
        Args:
            observer: 观察者函数
        """
        if observer in self._observers:
            self._observers.remove(observer)
    
    def _notify_observers(self, event: str, data: Any) -> None:
        """通知观察者
        
        Args:
            event: 事件类型
            data: 事件数据
        """
        for observer in self._observers:
            try:
                observer(event, data)
            except Exception as e:
                pass
    
    def get_status(self) -> Dict[str, Any]:
        """获取群聊状态
        
        Returns:
            状态字典
        """
        session_info = None
        if self.current_session:
            session_info = {
                "session_id": self.current_session.session_id,
                "current_round": self.current_session.current_round,
                "messages_in_round": self.current_session.messages_in_round,
                "last_speaker": self.current_session.last_speaker,
                "participants": self.current_session.participants,
                "is_active": self.current_session.is_active
            }
        
        return {
            "group_id": self.config.group_id,
            "name": self.config.name,
            "agent_count": len(self.agents),
            "current_session": session_info,
            "context_variables_count": len(self.context_engine.variables),
            "message_queue_available": self.config.message_queue_id is not None
        }


class GroupChatManager:
    """群聊管理器
    
    管理多个群聊实例，支持创建、配置和生命周期管理。
    """
    
    def __init__(self):
        self.group_chats: Dict[str, GroupChat] = {}
    
    @tracer.start_as_current_span("create_group_chat")
    def create_group_chat(self, config: GroupChatConfig) -> GroupChat:
        """创建群聊
        
        Args:
            config: 群聊配置
            
        Returns:
            群聊实例
        """
        span = trace.get_current_span()
        span.set_attribute("group_id", config.group_id)
        span.set_attribute("group_name", config.name)
        span.set_attribute("max_rounds", config.max_rounds)
        
        if config.group_id in self.group_chats:
            span.set_status(Status(StatusCode.ERROR, "GroupChat already exists"))
            raise GroupChatException(f"GroupChat {config.group_id} already exists")
        
        # 验证配置
        self._validate_config(config)
        
        group_chat = GroupChat(config)
        self.group_chats[config.group_id] = group_chat
        
        span.add_event("group_chat_created")
        
        return group_chat
    
    def get_group_chat(self, group_id: str) -> Optional[GroupChat]:
        """获取群聊
        
        Args:
            group_id: 群聊ID
            
        Returns:
            群聊实例，如果不存在则返回None
        """
        return self.group_chats.get(group_id)
    
    @tracer.start_as_current_span("remove_group_chat")
    def remove_group_chat(self, group_id: str) -> None:
        """移除群聊
        
        Args:
            group_id: 群聊ID
        """
        span = trace.get_current_span()
        span.set_attribute("group_id", group_id)
        
        if group_id in self.group_chats:
            group_chat = self.group_chats[group_id]
            
            # 结束当前会话
            if group_chat.current_session and group_chat.current_session.is_active:
                group_chat.end_session()
            
            del self.group_chats[group_id]
            
            span.add_event("group_chat_removed")
        else:
            span.add_event("group_chat_not_found")
    
    def list_group_chats(self) -> List[str]:
        """列出所有群聊ID
        
        Returns:
            群聊ID列表
        """
        return list(self.group_chats.keys())
    
    def get_group_chat_status(self, group_id: str) -> Optional[Dict[str, Any]]:
        """获取群聊状态
        
        Args:
            group_id: 群聊ID
            
        Returns:
            状态字典，如果群聊不存在则返回None
        """
        group_chat = self.get_group_chat(group_id)
        if group_chat:
            return group_chat.get_status()
        return None
    
    def get_all_group_chat_status(self) -> Dict[str, Dict[str, Any]]:
        """获取所有群聊状态
        
        Returns:
            群聊ID到状态字典的映射
        """
        status = {}
        for group_id, group_chat in self.group_chats.items():
            status[group_id] = group_chat.get_status()
        return status
    
    def _validate_config(self, config: GroupChatConfig) -> None:
        """验证群聊配置
        
        Args:
            config: 群聊配置
            
        Raises:
            ValidationException: 配置验证失败
        """
        if not config.group_id:
            raise ValidationException("Group ID is required")
        
        if not config.name:
            raise ValidationException("Group name is required")
        
        if config.max_rounds <= 0:
            raise ValidationException("Max rounds must be positive")
        
        if config.max_messages_per_round <= 0:
            raise ValidationException("Max messages per round must be positive")
    
    def get_manager_statistics(self) -> Dict[str, Any]:
        """获取管理器统计信息
        
        Returns:
            统计信息字典
        """
        active_sessions = sum(
            1 for gc in self.group_chats.values() 
            if gc.current_session and gc.current_session.is_active
        )
        
        return {
            "total_group_chats": len(self.group_chats),
            "active_sessions": active_sessions,
            "group_details": {
                group_id: {
                    "name": gc.config.name,
                    "agent_count": len(gc.agents),
                    "has_active_session": gc.current_session and gc.current_session.is_active
                }
                for group_id, gc in self.group_chats.items()
            }
        }


# 全局群聊管理器实例
group_chat_manager = GroupChatManager()


def get_group_chat_manager() -> GroupChatManager:
    """获取全局群聊管理器实例
    
    Returns:
        群聊管理器实例
    """
    return group_chat_manager 