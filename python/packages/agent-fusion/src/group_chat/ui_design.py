from base.utils import AgentBuilder
from model_client import label, ModelClient
from os.path import join, dirname, abspath
import asyncio

async def ui_design():
    model_client = label.deepseek_chat_DeepSeek 
    prompt_file_path = lambda agent_name : \
        join(
            dirname(abspath(__file__)), "prompt", f"{agent_name}_pt.md"
            )

    agent = AgentBuilder("ui_design_agent", "UI设计代理，负责生成和优化用户界面设计方案", model_client, prompt_file_path("ui_design"))

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(ui_design())
