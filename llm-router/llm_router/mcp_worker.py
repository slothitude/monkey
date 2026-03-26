"""MCP Worker Tool - Exposes worker pool as callable tools for Claude Code.

This module provides MCP-compatible tools that allow Claude Code to:
1. Delegate tasks to specialized worker agents
2. Analyze and break down complex tasks
3. Spawn new workers with specific skills
4. Execute skills directly

Usage as MCP tool:
    from llm_router.mcp_worker import delegate_task, analyze_task, spawn_worker, execute_skill

    # Delegate a complex task
    result = delegate_task("Build a REST API for user management")

    # Analyze a task to see breakdown
    breakdown = analyze_task("Create a full-stack web application")

    # Spawn a specialized worker
    worker = spawn_worker("Code Reviewer", "Reviews code for bugs", ["code_review"])

    # Execute a skill
    result = execute_skill("code_review", code="def foo(): pass")
"""

import asyncio
import json
from typing import Any, Optional
from pathlib import Path

from llm_router import LLMRouter
from llm_router.config import load_config
from llm_router.agent_framework import AgentRegistry
from llm_router.worker_pool import WorkerPool, get_worker_pool


# Global instances
_router: Optional[LLMRouter] = None
_registry: Optional[AgentRegistry] = None
_pool: Optional[WorkerPool] = None


def initialize_worker_pool(config_path: str = "config.yaml") -> WorkerPool:
    """Initialize the worker pool with configuration.

    Args:
        config_path: Path to config.yaml file

    Returns:
        WorkerPool instance
    """
    global _router, _registry, _pool

    if _pool is not None:
        return _pool

    # Load config and create router
    config = load_config(config_path)
    _router = LLMRouter(config)

    # Create agent registry
    _registry = AgentRegistry(_router)

    # Create worker pool
    _pool = WorkerPool(
        router=_router,
        agent_registry=_registry,
        storage_path="./data/workers"
    )

    return _pool


def get_pool() -> WorkerPool:
    """Get the initialized worker pool."""
    if _pool is None:
        return initialize_worker_pool()
    return _pool


# Async implementations

async def delegate_task_async(
    task: str,
    spawn_missing: bool = True,
    context: Optional[str] = None
) -> dict:
    """Delegate a task to the worker pool.

    This is the main entry point for Claude Code to delegate work.
    The task will be analyzed, broken down, and executed by appropriate workers.

    Args:
        task: The task description to delegate
        spawn_missing: Whether to spawn new workers if needed
        context: Optional context information

    Returns:
        Dict with task_id, original_task, results, and summary
    """
    pool = get_pool()

    # Analyze the task
    breakdown = await pool.analyze_task(task)

    # Execute the breakdown
    result = await pool.execute_breakdown(breakdown, spawn_missing)

    # Generate summary if there are results
    if result.get("results"):
        summary_parts = []
        for subtask_id, subtask_result in result["results"].items():
            if subtask_result.get("success"):
                summary_parts.append(f"- {subtask_id}: {subtask_result.get('result', 'Completed')[:200]}")
            else:
                summary_parts.append(f"- {subtask_id}: FAILED - {subtask_result.get('error', 'Unknown error')}")

        result["summary"] = "\n".join(summary_parts)

    return result


async def analyze_task_async(task: str) -> dict:
    """Analyze a task and return breakdown without executing.

    Args:
        task: The task to analyze

    Returns:
        Dict with subtasks and reasoning
    """
    pool = get_pool()
    breakdown = await pool.analyze_task(task)

    return {
        "task_id": breakdown.task_id,
        "original_task": breakdown.original_task,
        "subtasks": breakdown.subtasks,
        "status": breakdown.status,
    }


async def spawn_worker_async(
    name: str,
    description: str,
    skills: list[str],
    model: str = "minimaxai/minimax-m2.5",
    system_prompt: Optional[str] = None
) -> dict:
    """Spawn a new worker with specific skills.

    Args:
        name: Worker name
        description: What this worker does
        skills: List of skill names this worker provides
        model: Model to use (default: minimax free model)
        system_prompt: Optional custom system prompt

    Returns:
        Dict with worker details
    """
    pool = get_pool()
    worker = await pool.spawn_worker(
        name=name,
        description=description,
        skills=skills,
        model=model,
        system_prompt=system_prompt
    )

    return {
        "id": worker.id,
        "name": worker.name,
        "description": worker.description,
        "skills": [s.name for s in worker.skills],
        "status": worker.status,
    }


async def execute_skill_async(skill_name: str, **kwargs) -> dict:
    """Execute a skill directly.

    Args:
        skill_name: Name of the skill to execute
        **kwargs: Arguments for the skill

    Returns:
        Dict with success, result, and error (if any)
    """
    pool = get_pool()
    return await pool.execute_skill(skill_name, **kwargs)


async def list_workers_async() -> list[dict]:
    """List all available workers.

    Returns:
        List of worker dicts
    """
    pool = get_pool()
    workers = pool.list_workers()

    return [
        {
            "id": w.id,
            "name": w.name,
            "description": w.description,
            "skills": [s.name for s in w.skills],
            "status": w.status,
            "use_count": w.use_count,
        }
        for w in workers
    ]


async def list_skills_async() -> list[dict]:
    """List all available skills.

    Returns:
        List of skill dicts
    """
    pool = get_pool()
    skills = pool.list_skills()

    return [
        {
            "id": s.id,
            "name": s.name,
            "description": s.description,
            "worker_id": s.worker_id,
            "use_count": s.use_count,
        }
        for s in skills
    ]


# Synchronous wrappers for MCP compatibility

def delegate_task(task: str, spawn_missing: bool = True, context: Optional[str] = None) -> dict:
    """Delegate a task to the worker pool (sync wrapper)."""
    return asyncio.run(delegate_task_async(task, spawn_missing, context))


def analyze_task(task: str) -> dict:
    """Analyze a task and return breakdown (sync wrapper)."""
    return asyncio.run(analyze_task_async(task))


def spawn_worker(name: str, description: str, skills: list[str], model: str = "minimaxai/minimax-m2.5") -> dict:
    """Spawn a new worker (sync wrapper)."""
    return asyncio.run(spawn_worker_async(name, description, skills, model))


def execute_skill(skill_name: str, **kwargs) -> dict:
    """Execute a skill directly (sync wrapper)."""
    return asyncio.run(execute_skill_async(skill_name, **kwargs))


def list_workers() -> list[dict]:
    """List all available workers (sync wrapper)."""
    return asyncio.run(list_workers_async())


def list_skills() -> list[dict]:
    """List all available skills (sync wrapper)."""
    return asyncio.run(list_skills_async())


# Tool definitions for MCP registration

TOOL_DEFINITIONS = [
    {
        "name": "delegate_task",
        "description": "Delegate a complex task to the worker pool. The task will be analyzed, broken down into subtasks, and executed by appropriate worker agents. Use this as your primary way to delegate work.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task description to delegate"
                },
                "spawn_missing": {
                    "type": "boolean",
                    "description": "Whether to spawn new workers if needed (default: true)"
                },
                "context": {
                    "type": "string",
                    "description": "Optional context information"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "analyze_task",
        "description": "Analyze a task and see how it would be broken down into subtasks without executing.",
        "parameters": {
            "type": "object",
            "properties": {
                "task": {
                    "type": "string",
                    "description": "The task to analyze"
                }
            },
            "required": ["task"]
        }
    },
    {
        "name": "spawn_worker",
        "description": "Spawn a new worker agent with specific skills.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Worker name"
                },
                "description": {
                    "type": "string",
                    "description": "What this worker does"
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of skill names this worker provides"
                },
                "model": {
                    "type": "string",
                    "description": "Model to use (default: minimaxai/minimax-m2.5)"
                }
            },
            "required": ["name", "description", "skills"]
        }
    },
    {
        "name": "execute_skill",
        "description": "Execute a specific skill directly.",
        "parameters": {
            "type": "object",
            "properties": {
                "skill_name": {
                    "type": "string",
                    "description": "Name of the skill to execute"
                }
            },
            "required": ["skill_name"]
        }
    },
    {
        "name": "list_workers",
        "description": "List all available workers in the pool.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    },
    {
        "name": "list_skills",
        "description": "List all available skills.",
        "parameters": {
            "type": "object",
            "properties": {}
        }
    }
]


# Tool function mapping
TOOL_FUNCTIONS = {
    "delegate_task": delegate_task,
    "analyze_task": analyze_task,
    "spawn_worker": spawn_worker,
    "execute_skill": execute_skill,
    "list_workers": list_workers,
    "list_skills": list_skills,
}


def get_mcp_tools() -> dict:
    """Get MCP tool definitions and functions.

    Returns:
        Dict with 'tools' (definitions) and 'functions' (callables)
    """
    return {
        "tools": TOOL_DEFINITIONS,
        "functions": TOOL_FUNCTIONS,
    }
