"""OpenTelemetry使用示例

展示OpenTelemetry在各种场景下的使用方法。
"""

import time
import asyncio
import sqlite3
import requests
from typing import Dict, List, Any
from opentelemetry import trace
from opentelemetry.trace import Status, StatusCode
from opentelemetry.propagate import inject, extract
from .opentelemetry_config import get_tracer


class BasicTraceExample:
    """基础追踪示例"""
    
    def __init__(self):
        self.tracer = get_tracer(__name__)
    
    def simple_operation(self, user_id: str):
        """简单操作示例"""
        with self.tracer.start_as_current_span("simple_operation") as span:
            # 设置属性
            span.set_attribute("user.id", user_id)
            span.set_attribute("operation.type", "user_processing")
            
            # 模拟工作
            time.sleep(0.1)
            
            # 添加事件
            span.add_event("Processing started")
            
            # 模拟更多工作
            result = self._process_data(user_id)
            
            span.add_event("Processing completed", {
                "result.length": len(result)
            })
            
            return result
    
    def _process_data(self, user_id: str) -> str:
        """内部处理方法"""
        with self.tracer.start_as_current_span("process_data") as span:
            span.set_attribute("internal.operation", "data_processing")
            time.sleep(0.05)
            return f"processed_data_for_{user_id}"


class HTTPTraceExample:
    """HTTP请求追踪示例"""
    
    def __init__(self):
        self.tracer = get_tracer(__name__)
    
    def make_api_call(self, url: str, method: str = "GET", data: Dict = None):
        """API调用示例"""
        with self.tracer.start_as_current_span("api_call") as span:
            span.set_attribute("http.url", url)
            span.set_attribute("http.method", method)
            
            # 准备传播头
            headers = {"User-Agent": "AgentFusion/1.0"}
            inject(headers)
            
            try:
                if method.upper() == "GET":
                    response = requests.get(url, headers=headers, timeout=10)
                elif method.upper() == "POST":
                    response = requests.post(url, json=data, headers=headers, timeout=10)
                else:
                    raise ValueError(f"Unsupported method: {method}")
                
                span.set_attribute("http.status_code", response.status_code)
                span.set_attribute("http.response_size", len(response.content))
                
                if response.status_code < 400:
                    span.set_status(Status(StatusCode.OK))
                else:
                    span.set_status(Status(StatusCode.ERROR, f"HTTP {response.status_code}"))
                
                return response.json() if response.headers.get('content-type', '').startswith('application/json') else response.text
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def chain_api_calls(self, urls: List[str]):
        """链式API调用示例"""
        with self.tracer.start_as_current_span("chain_api_calls") as span:
            span.set_attribute("api.call_count", len(urls))
            
            results = []
            for i, url in enumerate(urls):
                with self.tracer.start_as_current_span(f"api_call_{i}") as call_span:
                    call_span.set_attribute("api.call_index", i)
                    call_span.set_attribute("api.url", url)
                    
                    try:
                        result = self.make_api_call(url)
                        results.append(result)
                        call_span.add_event("API call successful")
                    except Exception as e:
                        call_span.add_event("API call failed", {"error": str(e)})
                        # 继续处理其他URL
                        results.append(None)
            
            successful_calls = sum(1 for r in results if r is not None)
            span.set_attribute("api.successful_calls", successful_calls)
            span.add_event("All API calls completed", {
                "total_calls": len(urls),
                "successful_calls": successful_calls
            })
            
            return results


class DatabaseTraceExample:
    """数据库操作追踪示例"""
    
    def __init__(self, db_path: str = ":memory:"):
        self.tracer = get_tracer(__name__)
        self.db_path = db_path
        self._init_database()
    
    def _init_database(self):
        """初始化数据库"""
        with self.tracer.start_as_current_span("init_database") as span:
            span.set_attribute("db.path", self.db_path)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    name TEXT,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    message TEXT,
                    response TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (id)
                )
            """)
            
            conn.commit()
            conn.close()
            
            span.add_event("Database initialized")
    
    def create_user(self, user_id: str, name: str, email: str):
        """创建用户"""
        with self.tracer.start_as_current_span("create_user") as span:
            span.set_attribute("db.operation", "INSERT")
            span.set_attribute("db.table", "users")
            span.set_attribute("user.id", user_id)
            span.set_attribute("user.name", name)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    "INSERT INTO users (id, name, email) VALUES (?, ?, ?)",
                    (user_id, name, email)
                )
                conn.commit()
                span.add_event("User created successfully")
                return True
            except sqlite3.IntegrityError as e:
                span.set_status(Status(StatusCode.ERROR, f"User already exists: {e}"))
                span.record_exception(e)
                return False
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                conn.close()
    
    def get_user(self, user_id: str):
        """获取用户"""
        with self.tracer.start_as_current_span("get_user") as span:
            span.set_attribute("db.operation", "SELECT")
            span.set_attribute("db.table", "users")
            span.set_attribute("user.id", user_id)
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
                result = cursor.fetchone()
                
                if result:
                    span.add_event("User found")
                    return {
                        "id": result[0],
                        "name": result[1],
                        "email": result[2],
                        "created_at": result[3]
                    }
                else:
                    span.add_event("User not found")
                    return None
            finally:
                conn.close()
    
    def save_conversation(self, conversation_id: str, user_id: str, message: str, response: str):
        """保存对话"""
        with self.tracer.start_as_current_span("save_conversation") as span:
            span.set_attribute("db.operation", "INSERT")
            span.set_attribute("db.table", "conversations")
            span.set_attribute("conversation.id", conversation_id)
            span.set_attribute("user.id", user_id)
            span.set_attribute("message.length", len(message))
            span.set_attribute("response.length", len(response))
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            try:
                cursor.execute(
                    "INSERT INTO conversations (id, user_id, message, response) VALUES (?, ?, ?, ?)",
                    (conversation_id, user_id, message, response)
                )
                conn.commit()
                span.add_event("Conversation saved")
                return True
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
            finally:
                conn.close()


class AgentTraceExample:
    """Agent交互追踪示例"""
    
    def __init__(self):
        self.tracer = get_tracer(__name__)
        self.db_example = DatabaseTraceExample()
        self.http_example = HTTPTraceExample()
    
    def process_user_message(self, user_id: str, message: str, agent_config: Dict[str, Any]):
        """处理用户消息的完整流程"""
        with self.tracer.start_as_current_span("process_user_message") as main_span:
            main_span.set_attribute("user.id", user_id)
            main_span.set_attribute("message.length", len(message))
            main_span.set_attribute("agent.model", agent_config.get("model", "unknown"))
            main_span.set_attribute("agent.temperature", agent_config.get("temperature", 0.7))
            
            try:
                # 1. 预处理消息
                processed_message = self._preprocess_message(message)
                
                # 2. 获取用户上下文
                user_context = self._get_user_context(user_id)
                
                # 3. 调用LLM
                llm_response = self._call_llm(processed_message, user_context, agent_config)
                
                # 4. 后处理响应
                final_response = self._postprocess_response(llm_response)
                
                # 5. 保存对话
                conversation_id = f"conv_{int(time.time())}"
                self._save_conversation(conversation_id, user_id, message, final_response)
                
                main_span.add_event("Message processing completed successfully")
                return {
                    "conversation_id": conversation_id,
                    "response": final_response,
                    "user_context": user_context
                }
                
            except Exception as e:
                main_span.set_status(Status(StatusCode.ERROR, str(e)))
                main_span.record_exception(e)
                raise
    
    def _preprocess_message(self, message: str) -> str:
        """预处理消息"""
        with self.tracer.start_as_current_span("preprocess_message") as span:
            span.set_attribute("preprocessing.type", "text_cleaning")
            span.set_attribute("original.length", len(message))
            
            # 模拟预处理
            time.sleep(0.01)
            processed = message.strip().lower()
            
            span.set_attribute("processed.length", len(processed))
            span.add_event("Message preprocessed")
            return processed
    
    def _get_user_context(self, user_id: str) -> Dict[str, Any]:
        """获取用户上下文"""
        with self.tracer.start_as_current_span("get_user_context") as span:
            span.set_attribute("user.id", user_id)
            
            # 从数据库获取用户信息
            user_info = self.db_example.get_user(user_id)
            
            if user_info:
                span.add_event("User context retrieved")
                return {
                    "user_info": user_info,
                    "has_history": True
                }
            else:
                span.add_event("New user, no context")
                return {
                    "user_info": None,
                    "has_history": False
                }
    
    def _call_llm(self, message: str, context: Dict[str, Any], config: Dict[str, Any]) -> str:
        """调用LLM"""
        with self.tracer.start_as_current_span("call_llm") as span:
            span.set_attribute("llm.model", config.get("model", "unknown"))
            span.set_attribute("llm.temperature", config.get("temperature", 0.7))
            span.set_attribute("llm.max_tokens", config.get("max_tokens", 1000))
            span.set_attribute("message.length", len(message))
            span.set_attribute("has_context", bool(context.get("has_history")))
            
            try:
                # 模拟LLM调用
                time.sleep(0.5)  # 模拟网络延迟
                
                # 模拟token使用
                estimated_tokens = len(message) // 4 + 100  # 简单估算
                span.set_attribute("llm.tokens_used", estimated_tokens)
                
                response = f"AI response to: {message}"
                span.set_attribute("response.length", len(response))
                span.add_event("LLM call completed")
                return response
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def _postprocess_response(self, response: str) -> str:
        """后处理响应"""
        with self.tracer.start_as_current_span("postprocess_response") as span:
            span.set_attribute("postprocessing.type", "response_formatting")
            span.set_attribute("original.length", len(response))
            
            # 模拟后处理
            time.sleep(0.01)
            processed = response.capitalize()
            
            span.set_attribute("processed.length", len(processed))
            span.add_event("Response postprocessed")
            return processed
    
    def _save_conversation(self, conversation_id: str, user_id: str, message: str, response: str):
        """保存对话"""
        with self.tracer.start_as_current_span("save_conversation") as span:
            span.set_attribute("conversation.id", conversation_id)
            
            # 使用数据库示例保存对话
            self.db_example.save_conversation(conversation_id, user_id, message, response)
            
            span.add_event("Conversation saved to database")


class AsyncTraceExample:
    """异步操作追踪示例"""
    
    def __init__(self):
        self.tracer = get_tracer(__name__)
    
    async def async_agent_operation(self, message: str) -> Dict[str, Any]:
        """异步Agent操作"""
        with self.tracer.start_as_current_span("async_agent_operation") as span:
            span.set_attribute("message.length", len(message))
            
            # 并发执行多个分析任务
            tasks = [
                self.analyze_sentiment(message),
                self.extract_entities(message),
                self.generate_keywords(message),
                self.classify_intent(message)
            ]
            
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # 处理结果
            processed_results = {}
            for i, (task_name, result) in enumerate(zip(
                ["sentiment", "entities", "keywords", "intent"], results
            )):
                if isinstance(result, Exception):
                    span.add_event(f"Task {task_name} failed", {"error": str(result)})
                    processed_results[task_name] = None
                else:
                    processed_results[task_name] = result
            
            span.add_event("All async tasks completed")
            return processed_results
    
    async def analyze_sentiment(self, message: str) -> str:
        """分析情感"""
        with self.tracer.start_as_current_span("analyze_sentiment") as span:
            span.set_attribute("analysis.type", "sentiment")
            span.set_attribute("message.length", len(message))
            
            await asyncio.sleep(0.1)  # 模拟异步处理
            
            # 简单的情感分析模拟
            sentiment = "positive" if "good" in message.lower() else "neutral"
            span.set_attribute("sentiment.result", sentiment)
            span.add_event("Sentiment analysis completed")
            return sentiment
    
    async def extract_entities(self, message: str) -> List[str]:
        """提取实体"""
        with self.tracer.start_as_current_span("extract_entities") as span:
            span.set_attribute("analysis.type", "entities")
            span.set_attribute("message.length", len(message))
            
            await asyncio.sleep(0.2)  # 模拟异步处理
            
            # 简单的实体提取模拟
            entities = [word for word in message.split() if word.istitle()]
            span.set_attribute("entities.count", len(entities))
            span.add_event("Entity extraction completed")
            return entities
    
    async def generate_keywords(self, message: str) -> List[str]:
        """生成关键词"""
        with self.tracer.start_as_current_span("generate_keywords") as span:
            span.set_attribute("analysis.type", "keywords")
            span.set_attribute("message.length", len(message))
            
            await asyncio.sleep(0.15)  # 模拟异步处理
            
            # 简单的关键词生成模拟
            keywords = [word for word in message.split() if len(word) > 3][:5]
            span.set_attribute("keywords.count", len(keywords))
            span.add_event("Keyword generation completed")
            return keywords
    
    async def classify_intent(self, message: str) -> str:
        """分类意图"""
        with self.tracer.start_as_current_span("classify_intent") as span:
            span.set_attribute("analysis.type", "intent")
            span.set_attribute("message.length", len(message))
            
            await asyncio.sleep(0.12)  # 模拟异步处理
            
            # 简单的意图分类模拟
            if "?" in message:
                intent = "question"
            elif "help" in message.lower():
                intent = "help_request"
            else:
                intent = "general"
            
            span.set_attribute("intent.result", intent)
            span.add_event("Intent classification completed")
            return intent


class DistributedTraceExample:
    """分布式追踪示例"""
    
    def __init__(self):
        self.tracer = get_tracer(__name__)
    
    def service_a_operation(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """服务A操作（发送方）"""
        with self.tracer.start_as_current_span("service_a_operation") as span:
            span.set_attribute("service.name", "service-a")
            span.set_attribute("operation.type", "external_call")
            span.set_attribute("data.size", len(str(data)))
            
            # 准备调用服务B
            headers = {"Content-Type": "application/json"}
            inject(headers)  # 注入追踪上下文
            
            try:
                # 模拟HTTP调用到服务B
                response = self._simulate_http_call_to_service_b(data, headers)
                
                span.set_attribute("response.status", "success")
                span.add_event("Service B call completed")
                return response
                
            except Exception as e:
                span.set_status(Status(StatusCode.ERROR, str(e)))
                span.record_exception(e)
                raise
    
    def service_b_operation(self, request_headers: Dict[str, str], data: Dict[str, Any]) -> Dict[str, Any]:
        """服务B操作（接收方）"""
        # 从HTTP头中提取追踪上下文
        parent_context = extract(request_headers)
        
        with self.tracer.start_as_current_span("service_b_operation", context=parent_context) as span:
            span.set_attribute("service.name", "service-b")
            span.set_attribute("data.size", len(str(data)))
            
            # 模拟处理
            time.sleep(0.1)
            
            # 调用内部服务
            internal_result = self._internal_processing(data)
            
            result = {
                "processed": True,
                "data": data,
                "internal_result": internal_result,
                "timestamp": time.time()
            }
            
            span.add_event("Data processed successfully")
            return result
    
    def _simulate_http_call_to_service_b(self, data: Dict[str, Any], headers: Dict[str, str]) -> Dict[str, Any]:
        """模拟HTTP调用到服务B"""
        with self.tracer.start_as_current_span("http_call_to_service_b") as span:
            span.set_attribute("http.method", "POST")
            span.set_attribute("http.url", "http://service-b:8080/process")
            
            # 模拟网络延迟
            time.sleep(0.05)
            
            # 模拟服务B的响应
            response = self.service_b_operation(headers, data)
            
            span.set_attribute("http.status_code", 200)
            span.add_event("HTTP call completed")
            return response
    
    def _internal_processing(self, data: Dict[str, Any]) -> str:
        """内部处理"""
        with self.tracer.start_as_current_span("internal_processing") as span:
            span.set_attribute("processing.type", "data_transformation")
            
            # 模拟内部处理
            time.sleep(0.02)
            
            result = f"processed_{len(str(data))}_items"
            span.set_attribute("processing.result", result)
            span.add_event("Internal processing completed")
            return result


# 示例运行函数
def run_basic_example():
    """运行基础示例"""
    basic = BasicTraceExample()
    result = basic.simple_operation("user_123")
    print(f"Basic example result: {result}")


def run_http_example():
    """运行HTTP示例"""
    http = HTTPTraceExample()
    try:
        # 使用公共API进行测试
        result = http.make_api_call("https://httpbin.org/json")
        print(f"HTTP example result: {result}")
    except Exception as e:
        print(f"HTTP example error: {e}")


def run_database_example():
    """运行数据库示例"""
    db = DatabaseTraceExample()
    
    # 创建用户
    db.create_user("user_123", "Alice", "alice@example.com")
    
    # 获取用户
    user = db.get_user("user_123")
    print(f"Database example user: {user}")
    
    # 保存对话
    db.save_conversation("conv_123", "user_123", "Hello", "Hi there!")


def run_agent_example():
    """运行Agent示例"""
    agent = AgentTraceExample()
    
    # 首先创建用户
    agent.db_example.create_user("user_456", "Bob", "bob@example.com")
    
    # 处理消息
    result = agent.process_user_message(
        "user_456",
        "Hello, how are you?",
        {"model": "gpt-4", "temperature": 0.7, "max_tokens": 1000}
    )
    print(f"Agent example result: {result}")


async def run_async_example():
    """运行异步示例"""
    async_example = AsyncTraceExample()
    result = await async_example.async_agent_operation("Hello, this is a Good message!")
    print(f"Async example result: {result}")


def run_distributed_example():
    """运行分布式示例"""
    distributed = DistributedTraceExample()
    
    data = {"message": "Hello from service A", "timestamp": time.time()}
    result = distributed.service_a_operation(data)
    print(f"Distributed example result: {result}")


if __name__ == "__main__":
    print("Running OpenTelemetry Examples...")
    
    # 运行各种示例
    print("\n1. Basic Example:")
    run_basic_example()
    
    print("\n2. HTTP Example:")
    run_http_example()
    
    print("\n3. Database Example:")
    run_database_example()
    
    print("\n4. Agent Example:")
    run_agent_example()
    
    print("\n5. Async Example:")
    asyncio.run(run_async_example())
    
    print("\n6. Distributed Example:")
    run_distributed_example()
    
    print("\nAll examples completed!") 