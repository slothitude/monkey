"""Worker Pool - Dynamic agent workers that can be spawned, persisted, and used as tools."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from pydantic import BaseModel, Field
import uuid

from llm_router import LLMRouter
from llm_router.agent_framework import (
    Agent,
    AgentConfig,
    AgentRegistry,
    AgentStatus,
    AgentType,
)


class WorkerSkill(BaseModel):
    """A skill definition for a worker agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str
    worker_id: str  # The agent ID that implements this skill
    input_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {}})
    output_schema: dict = Field(default_factory=lambda: {"type": "object", "properties": {"result": {"type": "string"}}})
    examples: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_used: str | None = None
    use_count: int = 0


class WorkerDefinition(BaseModel):
    """Definition of a worker agent."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str
    skills: list[WorkerSkill] = Field(default_factory=list)
    agent_config: AgentConfig
    status: str = "idle"
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    last_used: str | None = None
    use_count: int = 0
    metadata: dict = Field(default_factory=dict)


class TaskBreakdown(BaseModel):
    """Breakdown of a complex task into subtasks."""
    task_id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    original_task: str
    subtasks: list[dict] = Field(default_factory=list)  # [{id, description, worker_type, dependencies}]
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    status: str = "pending"


class WorkerPool:
    """
    Manages a pool of worker agents that can be:
    1. Spawned dynamically based on task requirements
    2. Persisted to disk for restarts
    3. Used as callable tools/skills

    Example:
        pool = WorkerPool(router, storage_path="./workers")

        # Spawn a worker for a specific task type
        worker = await pool.spawn_worker(
            name="Code Reviewer",
            description="Reviews code for bugs and improvements",
            skills=["code_review", "suggest_fixes"]
        )

        # Use worker as a tool
        result = await pool.execute_skill("code_review", code="def foo(): pass")

        # Break down a complex task
        breakdown = await pool.analyze_task("Build a REST API")
        for subtask in breakdown.subtasks:
            worker = pool.get_worker_for_subtask(subtask)
            result = await worker.execute(subtask["description"])
    """

    def __init__(
        self,
        router: LLMRouter,
        agent_registry: AgentRegistry,
        storage_path: str = "./data/workers"
    ):
        self.router = router
        self.agent_registry = agent_registry
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

        self._workers: dict[str, WorkerDefinition] = {}
        self._skills: dict[str, WorkerSkill] = {}  # skill_name -> skill
        self._agents: dict[str, Agent] = {}  # worker_id -> Agent instance

        # Load persisted workers on init
        self._load_workers()

    def _load_workers(self) -> None:
        """Load persisted workers from disk."""
        workers_file = self.storage_path / "workers.json"
        if workers_file.exists():
            try:
                data = json.loads(workers_file.read_text())
                for worker_data in data.get("workers", []):
                    worker = WorkerDefinition(**worker_data)
                    self._workers[worker.id] = worker
                    for skill in worker.skills:
                        self._skills[skill.name] = skill
                print(f"Loaded {len(self._workers)} workers from disk")
            except Exception as e:
                print(f"Error loading workers: {e}")

    def _save_workers(self) -> None:
        """Persist workers to disk."""
        workers_file = self.storage_path / "workers.json"
        data = {
            "workers": [w.model_dump() for w in self._workers.values()],
            "saved_at": datetime.utcnow().isoformat()
        }
        workers_file.write_text(json.dumps(data, indent=2, default=str))

    async def spawn_worker(
        self,
        name: str,
        description: str,
        skills: list[str] | None = None,
        agent_type: str = "custom",
        model: str = "minimaxai/minimax-m2.5",  # Working free model
        system_prompt: str | None = None,
        tools: list[str] | None = None,
    ) -> WorkerDefinition:
        """
        Spawn a new worker agent with specified skills.

        Args:
            name: Worker name
            description: What this worker does
            skills: List of skill names this worker provides
            agent_type: Type of agent
            model: Model to use
            system_prompt: Custom system prompt
            tools: Built-in tools the worker can use

        Returns:
            WorkerDefinition
        """
        # Generate default system prompt if not provided
        if not system_prompt:
            system_prompt = f"""You are {name}. {description}

Your role is to complete tasks assigned to you efficiently and accurately.
You have access to specific skills: {', '.join(skills or [])}

Always:
1. Understand the task completely before starting
2. Break complex tasks into steps if needed
3. Provide clear, actionable results
4. Report any issues or blockers"""

        # Create agent config
        config = AgentConfig(
            name=name,
            description=description,
            agent_type=agent_type,
            model=model,
            system_prompt=system_prompt,
            tools=tools or [],
            memory_enabled=True,
        )

        # Create the agent
        agent = self.agent_registry.create_agent(config)

        # Create worker skills
        worker_skills = []
        for skill_name in (skills or []):
            skill = WorkerSkill(
                name=skill_name,
                description=f"Execute {skill_name} task",
                worker_id=agent.id,
            )
            worker_skills.append(skill)
            self._skills[skill_name] = skill

        # Create worker definition
        worker = WorkerDefinition(
            id=agent.id,
            name=name,
            description=description,
            skills=worker_skills,
            agent_config=config,
        )

        self._workers[worker.id] = worker
        self._agents[worker.id] = agent

        # Persist
        self._save_workers()

        return worker

    def get_worker(self, worker_id: str) -> WorkerDefinition | None:
        """Get a worker by ID."""
        return self._workers.get(worker_id)

    def get_worker_for_skill(self, skill_name: str) -> WorkerDefinition | None:
        """Get the worker that provides a specific skill."""
        skill = self._skills.get(skill_name)
        if skill:
            return self._workers.get(skill.worker_id)
        return None

    def list_workers(self) -> list[WorkerDefinition]:
        """List all workers."""
        return list(self._workers.values())

    def list_skills(self) -> list[WorkerSkill]:
        """List all available skills."""
        return list(self._skills.values())

    async def execute_skill(
        self,
        skill_name: str,
        **kwargs
    ) -> dict:
        """
        Execute a skill using the appropriate worker.

        Args:
            skill_name: Name of the skill to execute
            **kwargs: Arguments for the skill

        Returns:
            Dict with result
        """
        skill = self._skills.get(skill_name)
        if not skill:
            return {"error": f"Skill '{skill_name}' not found"}

        worker = self._workers.get(skill.worker_id)
        if not worker:
            return {"error": f"Worker '{skill.worker_id}' not found"}

        # Get or create agent
        if skill.worker_id not in self._agents:
            agent = self.agent_registry.create_agent(worker.agent_config)
            self._agents[skill.worker_id] = agent
        else:
            agent = self._agents[skill.worker_id]

        # Build prompt from kwargs
        prompt_parts = [f"Task: {skill_name}"]
        for key, value in kwargs.items():
            if isinstance(value, str) and len(value) > 100:
                prompt_parts.append(f"{key}:\n{value}")
            else:
                prompt_parts.append(f"{key}: {value}")

        prompt = "\n".join(prompt_parts)

        # Execute
        try:
            execution = await agent.execute(prompt)

            # Update stats
            skill.use_count += 1
            skill.last_used = datetime.utcnow().isoformat()
            worker.use_count += 1
            worker.last_used = datetime.utcnow().isoformat()
            self._save_workers()

            return {
                "success": execution.error is None,
                "result": execution.response,
                "error": execution.error,
                "tokens_used": execution.tokens_used,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def analyze_task(
        self,
        task: str,
        available_worker_types: list[str] | None = None
    ) -> TaskBreakdown:
        """
        Analyze a complex task and break it into subtasks.

        Uses an LLM to analyze the task and determine:
        1. What subtasks are needed
        2. What worker types are needed for each subtask
        3. Dependencies between subtasks

        Args:
            task: The task to analyze
            available_worker_types: Types of workers available (optional)

        Returns:
            TaskBreakdown with subtasks
        """
        worker_types = available_worker_types or [
            "research", "coding", "data_analysis", "automation", "writing", "review"
        ]

        analysis_prompt = f"""Analyze this task and break it into subtasks.

TASK: {task}

AVAILABLE WORKER TYPES: {', '.join(worker_types)}

Return a JSON object with this structure:
{{
    "subtasks": [
        {{
            "id": "subtask_1",
            "description": "What this subtask should accomplish",
            "worker_type": "one of the available types",
            "dependencies": ["ids of subtasks that must complete first"],
            "estimated_complexity": "low|medium|high"
        }}
    ],
    "reasoning": "Brief explanation of the breakdown"
}}

IMPORTANT: Return ONLY valid JSON, no other text."""

        try:
            response = await self.router.chat(
                messages=[{"role": "user", "content": analysis_prompt}],
                model="nvidia/llama-3.1-nemotron-70b-instruct",
                max_tokens=2000,
                temperature=0.3,
            )

            content = response.choices[0].message.content if response.choices else "{}"

            # Extract JSON from response
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]

            data = json.loads(content.strip())

            breakdown = TaskBreakdown(
                original_task=task,
                subtasks=data.get("subtasks", []),
                status="analyzed"
            )

            return breakdown

        except Exception as e:
            # Fallback: single subtask
            return TaskBreakdown(
                original_task=task,
                subtasks=[{
                    "id": "subtask_1",
                    "description": task,
                    "worker_type": "general",
                    "dependencies": [],
                    "estimated_complexity": "medium"
                }],
                status="fallback"
            )

    async def execute_breakdown(
        self,
        breakdown: TaskBreakdown,
        spawn_missing_workers: bool = True
    ) -> dict:
        """
        Execute a task breakdown, spawning workers as needed.

        Args:
            breakdown: TaskBreakdown to execute
            spawn_missing_workers: Whether to spawn workers for missing types

        Returns:
            Dict with results from all subtasks
        """
        results = {}
        completed = set()

        # Sort subtasks by dependencies (topological sort)
        subtasks = self._sort_subtasks(breakdown.subtasks)

        for subtask in subtasks:
            subtask_id = subtask["id"]
            worker_type = subtask.get("worker_type", "general")

            # Check dependencies
            deps = subtask.get("dependencies", [])
            dep_results = {d: results.get(d) for d in deps if d in results}

            # Get or spawn worker
            worker = self.get_worker_for_skill(f"{worker_type}_execute")

            if not worker and spawn_missing_workers:
                # Spawn a new worker for this type
                worker = await self.spawn_worker(
                    name=f"{worker_type.title()} Worker",
                    description=f"Handles {worker_type} tasks",
                    skills=[f"{worker_type}_execute"],
                    agent_type=worker_type,
                    model="minimaxai/minimax-m2.5",  # Use working free model
                )

            if worker:
                # Build prompt with context from dependencies
                prompt = subtask["description"]
                if dep_results:
                    context = "\n\n".join([
                        f"Result from {d}: {r.get('result', 'No result')}"
                        for d, r in dep_results.items()
                        if r.get("success")
                    ])
                    if context:
                        prompt = f"{prompt}\n\nContext from previous steps:\n{context}"

                # Execute
                result = await self.execute_skill(f"{worker_type}_execute", task=prompt)
                results[subtask_id] = result
                completed.add(subtask_id)
            else:
                results[subtask_id] = {"success": False, "error": f"No worker for type {worker_type}"}

        breakdown.status = "completed"
        return {
            "task_id": breakdown.task_id,
            "original_task": breakdown.original_task,
            "results": results,
            "completed_subtasks": list(completed),
        }

    def _sort_subtasks(self, subtasks: list[dict]) -> list[dict]:
        """Topological sort of subtasks based on dependencies."""
        sorted_tasks = []
        visited = set()
        temp_visited = set()

        def visit(task_id: str):
            if task_id in temp_visited:
                raise ValueError("Circular dependency detected")
            if task_id in visited:
                return

            temp_visited.add(task_id)

            task = next((t for t in subtasks if t["id"] == task_id), None)
            if task:
                for dep in task.get("dependencies", []):
                    visit(dep)

            temp_visited.remove(task_id)
            visited.add(task_id)
            if task:
                sorted_tasks.append(task)

        for task in subtasks:
            visit(task["id"])

        return sorted_tasks

    def delete_worker(self, worker_id: str) -> bool:
        """Delete a worker and its associated skills."""
        if worker_id not in self._workers:
            return False

        worker = self._workers[worker_id]

        # Remove skills
        for skill in worker.skills:
            self._skills.pop(skill.name, None)

        # Remove agent
        self._agents.pop(worker_id, None)
        self.agent_registry.delete_agent(worker_id)

        # Remove worker
        del self._workers[worker_id]

        # Persist
        self._save_workers()

        return True

    def get_tool_definitions(self) -> list[dict]:
        """
        Get tool definitions for all worker skills.

        These can be registered as tools with the agent framework
        so other agents can use workers as tools.
        """
        tools = []
        for skill in self._skills.values():
            tools.append({
                "type": "function",
                "function": {
                    "name": skill.name,
                    "description": skill.description,
                    "parameters": skill.input_schema,
                }
            })
        return tools

    def get_tool_functions(self) -> dict[str, Callable]:
        """
        Get callable functions for all worker skills.

        Returns a dict mapping skill_name -> async function
        """
        functions = {}
        for skill_name in self._skills.keys():
            # Create a closure to capture the skill_name
            def make_executor(name):
                async def execute(**kwargs):
                    return await self.execute_skill(name, **kwargs)
                return execute
            functions[skill_name] = make_executor(skill_name)
        return functions


# Singleton instance
_worker_pool: WorkerPool | None = None


def get_worker_pool(
    router: LLMRouter | None = None,
    agent_registry: AgentRegistry | None = None,
    storage_path: str = "./data/workers"
) -> WorkerPool:
    """Get or create the worker pool singleton."""
    global _worker_pool
    if _worker_pool is None:
        if router is None or agent_registry is None:
            raise ValueError("router and agent_registry required for first initialization")
        _worker_pool = WorkerPool(router, agent_registry, storage_path)
    return _worker_pool
