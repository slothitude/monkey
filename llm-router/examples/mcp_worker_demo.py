#!/usr/bin/env python3
"""
Example: Using the MCP Worker Pool from Python

This demonstrates how to use the worker pool as callable tools.
"""

from llm_router.mcp_worker import (
    initialize_worker_pool,
    delegate_task,
    analyze_task,
    spawn_worker,
    execute_skill,
    list_workers,
    list_skills,
)
import json


def main():
    # Initialize the worker pool
    print("Initializing worker pool...")
    initialize_worker_pool()

    # List existing workers
    print("\n=== Existing Workers ===")
    workers = list_workers()
    for w in workers:
        print(f"  - {w['name']}: {w['skills']}")

    # List existing skills
    print("\n=== Available Skills ===")
    skills = list_skills()
    for s in skills:
        print(f"  - {s['name']}: {s['description']}")

    # Analyze a task
    print("\n=== Analyzing Task ===")
    task = "Build a simple REST API with endpoints for users and posts"
    analysis = analyze_task(task)
    print(f"Task: {analysis['original_task']}")
    print(f"Subtasks:")
    for st in analysis.get("subtasks", []):
        print(f"  - {st['id']}: {st['description']} ({st['worker_type']})")

    # Delegate the task
    print("\n=== Delegating Task ===")
    result = delegate_task(task)
    print(f"Task ID: {result['task_id']}")
    print(f"Completed: {result['completed_subtasks']}")
    print(f"\nSummary:\n{result.get('summary', 'No summary')}")

    # Spawn a new worker
    print("\n=== Spawning New Worker ===")
    new_worker = spawn_worker(
        name="Code Reviewer",
        description="Reviews code for bugs, security issues, and improvements",
        skills=["code_review", "suggest_improvements"],
    )
    print(f"Spawned: {new_worker['name']} (ID: {new_worker['id']})")
    print(f"Skills: {new_worker['skills']}")

    # Execute a skill
    print("\n=== Executing Skill ===")
    skill_result = execute_skill(
        skill_name="code_review",
        code="def add(a, b): return a + b",
    )
    print(f"Success: {skill_result.get('success')}")
    print(f"Result: {skill_result.get('result', skill_result.get('error'))}")


if __name__ == "__main__":
    main()
