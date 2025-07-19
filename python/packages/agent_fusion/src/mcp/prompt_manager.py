#!/usr/bin/env python3
"""
MCP (Model Context Protocol) Server Example - Prompt Manager

This is an example MCP server that provides prompt management capabilities.
It demonstrates how to create tools, resources, and prompts using the MCP protocol.
"""

import asyncio
import json
from typing import Any, Dict, List, Optional
from mcp import McpServer, types
from mcp.server.stdio import stdio_server


class PromptManager:
    def __init__(self):
        self.prompts: Dict[str, Dict[str, Any]] = {
            "code_review": {
                "name": "code_review",
                "description": "A prompt for conducting thorough code reviews",
                "arguments": [
                    {
                        "name": "code",
                        "description": "The code to review",
                        "required": True
                    },
                    {
                        "name": "language",
                        "description": "Programming language of the code",
                        "required": False
                    }
                ],
                "template": """Please review the following {language} code:

{code}

Focus on:
- Code quality and readability
- Security vulnerabilities
- Performance optimizations
- Best practices
- Potential bugs

Provide constructive feedback with specific suggestions for improvement."""
            },
            "sql_query": {
                "name": "sql_query",
                "description": "A prompt for generating SQL queries",
                "arguments": [
                    {
                        "name": "requirements",
                        "description": "Description of what the query should accomplish",
                        "required": True
                    },
                    {
                        "name": "schema",
                        "description": "Database schema information",
                        "required": False
                    }
                ],
                "template": """Generate a SQL query based on the following requirements:

{requirements}

{schema}

Provide:
1. The SQL query
2. Explanation of what the query does
3. Any assumptions made
4. Performance considerations if applicable"""
            },
            "debug_assistant": {
                "name": "debug_assistant",
                "description": "A prompt for debugging code issues",
                "arguments": [
                    {
                        "name": "error_message",
                        "description": "The error message or issue description",
                        "required": True
                    },
                    {
                        "name": "code_context",
                        "description": "Relevant code context",
                        "required": False
                    }
                ],
                "template": """Help debug this issue:

Error: {error_message}

Code Context:
{code_context}

Please provide:
1. Analysis of the error
2. Possible causes
3. Step-by-step debugging approach
4. Suggested fixes
5. Prevention strategies"""
            }
        }

    async def list_prompts(self) -> List[types.Prompt]:
        """List all available prompts"""
        return [
            types.Prompt(
                name=prompt_data["name"],
                description=prompt_data["description"],
                arguments=[
                    types.PromptArgument(
                        name=arg["name"],
                        description=arg["description"],
                        required=arg["required"]
                    )
                    for arg in prompt_data["arguments"]
                ]
            )
            for prompt_data in self.prompts.values()
        ]

    async def get_prompt(self, name: str, arguments: Dict[str, Any]) -> types.GetPromptResult:
        """Get a specific prompt with arguments filled in"""
        if name not in self.prompts:
            raise ValueError(f"Prompt '{name}' not found")

        prompt_data = self.prompts[name]
        template = prompt_data["template"]

        # Fill in the template with provided arguments
        filled_template = template.format(**arguments)

        return types.GetPromptResult(
            description=prompt_data["description"],
            messages=[
                types.PromptMessage(
                    role="user",
                    content=types.TextContent(
                        type="text",
                        text=filled_template
                    )
                )
            ]
        )


async def main():
    """Main entry point for the MCP server"""
    prompt_manager = PromptManager()
    
    # Create the MCP server
    server = McpServer("prompt-manager")

    @server.list_prompts()
    async def handle_list_prompts() -> List[types.Prompt]:
        """Handle list_prompts requests"""
        return await prompt_manager.list_prompts()

    @server.get_prompt()
    async def handle_get_prompt(
        name: str, 
        arguments: Optional[Dict[str, str]] = None
    ) -> types.GetPromptResult:
        """Handle get_prompt requests"""
        if arguments is None:
            arguments = {}
        return await prompt_manager.get_prompt(name, arguments)

    @server.list_tools()
    async def handle_list_tools() -> List[types.Tool]:
        """List available tools"""
        return [
            types.Tool(
                name="create_prompt",
                description="Create a new prompt template",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the prompt"
                        },
                        "description": {
                            "type": "string",
                            "description": "Description of the prompt"
                        },
                        "template": {
                            "type": "string",
                            "description": "Prompt template with placeholders"
                        },
                        "arguments": {
                            "type": "array",
                            "description": "List of argument definitions",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "required": {"type": "boolean"}
                                }
                            }
                        }
                    },
                    "required": ["name", "description", "template"]
                }
            ),
            types.Tool(
                name="delete_prompt",
                description="Delete an existing prompt",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "name": {
                            "type": "string",
                            "description": "Name of the prompt to delete"
                        }
                    },
                    "required": ["name"]
                }
            )
        ]

    @server.call_tool()
    async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[types.TextContent]:
        """Handle tool calls"""
        if name == "create_prompt":
            prompt_name = arguments["name"]
            prompt_data = {
                "name": prompt_name,
                "description": arguments["description"],
                "template": arguments["template"],
                "arguments": arguments.get("arguments", [])
            }
            prompt_manager.prompts[prompt_name] = prompt_data
            return [types.TextContent(
                type="text",
                text=f"Prompt '{prompt_name}' created successfully"
            )]
        
        elif name == "delete_prompt":
            prompt_name = arguments["name"]
            if prompt_name in prompt_manager.prompts:
                del prompt_manager.prompts[prompt_name]
                return [types.TextContent(
                    type="text",
                    text=f"Prompt '{prompt_name}' deleted successfully"
                )]
            else:
                return [types.TextContent(
                    type="text",
                    text=f"Prompt '{prompt_name}' not found"
                )]
        
        else:
            raise ValueError(f"Unknown tool: {name}")

    @server.list_resources()
    async def handle_list_resources() -> List[types.Resource]:
        """List available resources"""
        return [
            types.Resource(
                uri="prompt://templates",
                name="Prompt Templates",
                description="Collection of all prompt templates",
                mimeType="application/json"
            )
        ]

    @server.read_resource()
    async def handle_read_resource(uri: str) -> str:
        """Read a resource"""
        if uri == "prompt://templates":
            return json.dumps(prompt_manager.prompts, indent=2)
        else:
            raise ValueError(f"Unknown resource: {uri}")

    # Run the server
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())