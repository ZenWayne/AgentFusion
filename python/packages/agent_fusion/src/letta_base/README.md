##概述：
这是一个agent框架，通过谷歌的A2A进行通信，支持全局上下文提取，单个agent有自己的记忆，可以进行多轮对话。

## 架构
```mermaid
graph TD
    A[Agent] --> B[Agent]
    B --> C[Agent]
    C --> D[Agent]
    D --> A
```

## 参考OpenAI的接口