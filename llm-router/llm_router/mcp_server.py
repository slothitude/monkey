"""MCP Server for Worker Pool - Allows Claude Code to delegate tasks.

This creates an MCP (Model Context Protocol) server that exposes the worker pool
as callable tools for Claude Code to use as a project manager.

Run this server:
    python -m llm_router.mcp_server

Or configure in Claude Code settings:
    {
        "mcpServers": {
            "worker-pool": {
                "command": "python",
                "args": ["-m", "llm_router.mcp_server"],
                "cwd": "/path/to/llm-router"
            }
        }
    }
"""

import asyncio
import json
import sys
from typing import Any

# Initialize worker pool on import
from llm_router.mcp_worker import (
    initialize_worker_pool,
    delegate_task_async,
    analyze_task_async,
    spawn_worker_async,
    execute_skill_async,
    list_workers_async,
    list_skills_async,
    TOOL_DEFINITIONS,
)


class MCPServer:
    """Simple MCP server implementation."""

    def __init__(self):
        self.running = False
        # Initialize pool
        initialize_worker_pool()

    async def handle_request(self, request: dict) -> dict:
        """Handle an MCP request."""
        method = request.get("method")
        params = request.get("params", {})
        request_id = request.get("id")

        try:
            if method == "initialize":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {
                            "tools": {}
                        },
                        "serverInfo": {
                            "name": "worker-pool",
                            "version": "1.0.0"
                        }
                    }
                }

            elif method == "tools/list":
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "tools": TOOL_DEFINITIONS
                    }
                }

            elif method == "tools/call":
                tool_name = params.get("name")
                arguments = params.get("arguments", {})

                if tool_name == "delegate_task":
                    result = await delegate_task_async(
                        task=arguments.get("task"),
                        spawn_missing=arguments.get("spawn_missing", True),
                        context=arguments.get("context")
                    )
                elif tool_name == "analyze_task":
                    result = await analyze_task_async(task=arguments.get("task"))
                elif tool_name == "spawn_worker":
                    result = await spawn_worker_async(
                        name=arguments.get("name"),
                        description=arguments.get("description"),
                        skills=arguments.get("skills", []),
                        model=arguments.get("model", "minimaxai/minimax-m2.5")
                    )
                elif tool_name == "execute_skill":
                    result = await execute_skill_async(
                        skill_name=arguments.get("skill_name"),
                        **{k: v for k, v in arguments.items() if k != "skill_name"}
                    )
                elif tool_name == "list_workers":
                    result = await list_workers_async()
                elif tool_name == "list_skills":
                    result = await list_skills_async()
                else:
                    return {
                        "jsonrpc": "2.0",
                        "id": request_id,
                        "error": {
                            "code": -32601,
                            "message": f"Unknown tool: {tool_name}"
                        }
                    }

                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2, default=str)
                            }
                        ]
                    }
                }

            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Unknown method: {method}"
                    }
                }

        except Exception as e:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(e)
                }
            }

    async def run(self):
        """Run the MCP server, reading from stdin and writing to stdout."""
        self.running = True

        while self.running:
            try:
                line = await asyncio.get_event_loop().run_in_executor(
                    None, sys.stdin.readline
                )

                if not line:
                    break

                line = line.strip()
                if not line:
                    continue

                try:
                    request = json.loads(line)
                    response = await self.handle_request(request)
                    print(json.dumps(response), flush=True)
                except json.JSONDecodeError as e:
                    print(json.dumps({
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {
                            "code": -32700,
                            "message": f"Parse error: {e}"
                        }
                    }), flush=True)

            except KeyboardInterrupt:
                break
            except Exception as e:
                print(json.dumps({
                    "jsonrpc": "2.0",
                    "id": None,
                    "error": {
                        "code": -32603,
                        "message": str(e)
                    }
                }), flush=True)


def main():
    """Main entry point."""
    server = MCPServer()
    asyncio.run(server.run())


if __name__ == "__main__":
    main()
