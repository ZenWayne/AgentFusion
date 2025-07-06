# Create server parameters for stdio connection
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import os
import litellm
from litellm import experimental_mcp_client
import asyncio
import json

async def main():
    server_params = StdioServerParameters(
        command="node",
        args=[
            "C:\\Users\\73448\\AppData\\Roaming\\npm\\node_modules\\@modelcontextprotocol\\server-filesystem\\dist\\index.js", 
            "./"
        ],
        env={}
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # Initialize the connection
            await session.initialize()

            # Get tools
            tools = await experimental_mcp_client.load_mcp_tools(session=session, format="openai")
            print("MCP TOOLS: ", tools)

            messages = [{"role": "user", "content": "list all files in the current directory"}]
            llm_response = await litellm.acompletion(
                model="gpt-4o",
                api_key=os.getenv("OPENAI_API_KEY"),
                messages=messages,
                tools=tools,
            )
            print("LLM RESPONSE: ", json.dumps(llm_response, indent=4, default=str))

            openai_tool = llm_response["choices"][0]["message"]["tool_calls"][0]
            # Call the tool using MCP client
            call_result = await experimental_mcp_client.call_openai_tool(
                session=session,
                openai_tool=openai_tool,
            )
            print("MCP TOOL CALL RESULT: ", call_result)

            # send the tool result to the LLM
            messages.append(llm_response["choices"][0]["message"])
            messages.append(
                {
                    "role": "tool",
                    "content": str(call_result.content[0].text),
                    "tool_call_id": openai_tool["id"],
                }
            )
            print("final messages with tool result: ", messages)
            llm_response = await litellm.acompletion(
                model="gpt-4o",
                api_key=os.getenv("OPENAI_API_KEY"),
                messages=messages,
                tools=tools,
            )
            print(
                "FINAL LLM RESPONSE: ", json.dumps(llm_response, indent=4, default=str)
            )

if __name__ == "__main__":
    asyncio.run(main())