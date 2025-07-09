通过跑通应用的过程中完善agent工具链，终极目标是实现一个
#agent融合体
通过对话的形式和agent交互，agent根据对话内容和任务需求，调用工具链，完成任务
##这个需要用到autogen库
其中有个需要做的是使用autogen_agentchat.agents.BaseChatAgent去实现一些基础常用的多模态agent,
比如：
- 文字转图片， 直接调大模型生成图片，并将图片存进图库中，这里的数据库需要选型，需要支持图片的存储和查询，并自动打标签，（这里你需要输出一个数据库选型报告），这里图片还需要有一个唯一id对应
- 图片入库，通过embedding模型 转文字后直接用文字向量存入数据库（这里直接用向量数据库即可，其中需要保持图片id和第一个的一致）
- 图库mcp，可以通过文字直接查询向量数据库，并找出id，搜索图库中的图片，并返回图片，也可支持标签的方式
...
##agent切换
需要一个agent切换的机制，比如：
一开始用户输入，帮我写一个ui交互设计稿，他会自动意图匹配来选择正确的agent并切换至该agent
大概实现是通过切换autogen中TaskRunner，然后调用run或者run_stream方法
TaskRunner派生类几乎所有交互的类如AssistantAgent, UserProxyAgent, GroupChat等
结束时会回到原来的模式
这里需要注意的是要通过mcp根据从agent元数据数据库中获取的agent信息，来动态加载需要的agent
这些信息的格式可以参考python/packages/agent-fusion/src/dataclass/*.py
这里有三个概念
agent 单体agent
group_chat 多个agent聊天，目前只支持selector_group_chat，即通过selector_prompt来选择下一个发言者agent
graph_flow 多个agent以固定工作流的方式来完成任务

这里可以直接用has-a的方式动态加载需要的agent

##原始应用 1：
设计一个名为idea spark 的TODO应用，
首先我需要用agent工具链来帮我生成一个idea spark 应用的PRD文档

然后根据这个PRD文档，我需要用agent工具链来帮我生成一个idea spark 应用的架构设计

其次我们需要用agent工具链来帮我生成一个idea spark 应用的UI设计稿（目前我在这里）


##附加应用2：
使用group_chat来实现论文数据分割载入，并通过rag agent查询知识点


#TODO
1.用户鉴权
2.记忆功能
3.多agent切换



