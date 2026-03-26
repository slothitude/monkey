"""Workflow orchestration for multi-agent execution."""

import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, AsyncGenerator, Optional
from pydantic import BaseModel, Field

from llm_router.agent_framework import Agent, AgentRegistry, AgentExecution, AgentStatus


class WorkflowStatus(str, Enum):
    """Workflow execution status."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class WorkflowMode(str, Enum):
    """Workflow execution modes."""
    SINGLE = "single"  # One agent, one task
    PARALLEL = "parallel"  # Multiple agents, same prompt
    SEQUENTIAL = "sequential"  # Chain of agents
    DAG = "dag"  # Complex dependency graph


@dataclass
class WorkflowNode:
    """A node in the workflow DAG."""
    id: str
    agent_id: str
    prompt: str | None = None  # If None, uses input from previous node
    dependencies: list[str] = field(default_factory=list)  # Node IDs this depends on
    status: AgentStatus = AgentStatus.IDLE
    execution: AgentExecution | None = None
    result: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "prompt": self.prompt,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "result": self.result,
        }


@dataclass
class WorkflowEdge:
    """An edge in the workflow DAG."""
    from_node: str
    to_node: str
    transform: str | None = None  # Optional transformation on output


class WorkflowConfig(BaseModel):
    """Configuration for a workflow."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4())[:8])
    name: str
    description: str = ""
    mode: WorkflowMode = WorkflowMode.SINGLE
    nodes: list[dict] = Field(default_factory=list)  # Node configurations
    edges: list[dict] = Field(default_factory=list)  # Edge configurations
    input_prompt: str = ""  # Default input prompt
    max_parallel: int = 5  # Max parallel executions
    timeout: int = 300  # Total workflow timeout in seconds
    metadata: dict[str, Any] = Field(default_factory=dict)

    class Config:
        use_enum_values = True


@dataclass
class WorkflowExecution:
    """Represents a workflow execution."""
    id: str
    workflow_id: str
    status: WorkflowStatus
    input_prompt: str
    nodes: dict[str, WorkflowNode] = field(default_factory=dict)
    results: dict[str, str] = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "input_prompt": self.input_prompt,
            "nodes": {nid: node.to_dict() for nid, node in self.nodes.items()},
            "results": self.results,
            "errors": self.errors,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "metadata": self.metadata,
        }


class Workflow:
    """
    A workflow that orchestrates multiple agents.

    Supports:
    - Single: One agent execution
    - Parallel: Multiple agents with same input
    - Sequential: Chain of agents, output feeds next
    - DAG: Complex dependency graph

    Example:
        workflow = Workflow(
            config=WorkflowConfig(
                name="Research Pipeline",
                mode=WorkflowMode.SEQUENTIAL,
                nodes=[
                    {"id": "search", "agent_id": "researcher"},
                    {"id": "summarize", "agent_id": "summarizer"},
                ]
            ),
            registry=agent_registry
        )

        result = await workflow.execute("What is quantum computing?")
    """

    def __init__(self, config: WorkflowConfig, registry: AgentRegistry):
        self.config = config
        self.registry = registry
        self._nodes: dict[str, WorkflowNode] = {}
        self._edges: list[WorkflowEdge] = []
        self._execution: WorkflowExecution | None = None
        self._initialize_graph()

    def _initialize_graph(self) -> None:
        """Initialize the workflow graph from config."""
        # Create nodes
        for node_config in self.config.nodes:
            node = WorkflowNode(
                id=node_config["id"],
                agent_id=node_config["agent_id"],
                prompt=node_config.get("prompt"),
                dependencies=node_config.get("dependencies", []),
            )
            self._nodes[node.id] = node

        # Create edges
        for edge_config in self.config.edges:
            edge = WorkflowEdge(
                from_node=edge_config["from"],
                to_node=edge_config["to"],
                transform=edge_config.get("transform"),
            )
            self._edges.append(edge)

    @property
    def id(self) -> str:
        return self.config.id

    @property
    def name(self) -> str:
        return self.config.name

    async def execute(
        self,
        prompt: str,
        **kwargs
    ) -> WorkflowExecution:
        """
        Execute the workflow with a prompt.

        Args:
            prompt: Input prompt for the workflow
            **kwargs: Additional parameters

        Returns:
            WorkflowExecution with results
        """
        execution_id = str(uuid.uuid4())[:8]
        execution = WorkflowExecution(
            id=execution_id,
            workflow_id=self.id,
            status=WorkflowStatus.RUNNING,
            input_prompt=prompt,
            nodes={nid: WorkflowNode(**node.__dict__) for nid, node in self._nodes.items()},
        )
        self._execution = execution

        try:
            if self.config.mode == WorkflowMode.SINGLE:
                await self._execute_single(execution, prompt, **kwargs)
            elif self.config.mode == WorkflowMode.PARALLEL:
                await self._execute_parallel(execution, prompt, **kwargs)
            elif self.config.mode == WorkflowMode.SEQUENTIAL:
                await self._execute_sequential(execution, prompt, **kwargs)
            elif self.config.mode == WorkflowMode.DAG:
                await self._execute_dag(execution, prompt, **kwargs)

            execution.status = WorkflowStatus.COMPLETED

        except asyncio.CancelledError:
            execution.status = WorkflowStatus.CANCELLED
            raise
        except Exception as e:
            execution.status = WorkflowStatus.FAILED
            execution.errors.append(str(e))
        finally:
            execution.completed_at = datetime.utcnow()

        return execution

    async def execute_stream(
        self,
        prompt: str,
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """
        Execute workflow with streaming updates.

        Yields:
            Dict with current status and partial results
        """
        execution_id = str(uuid.uuid4())[:8]
        execution = WorkflowExecution(
            id=execution_id,
            workflow_id=self.id,
            status=WorkflowStatus.RUNNING,
            input_prompt=prompt,
            nodes={nid: WorkflowNode(**node.__dict__) for nid, node in self._nodes.items()},
        )
        self._execution = execution

        yield {"type": "start", "execution_id": execution_id, "status": "running"}

        try:
            if self.config.mode == WorkflowMode.SEQUENTIAL:
                async for update in self._execute_sequential_stream(execution, prompt, **kwargs):
                    yield update
            else:
                # Fall back to non-streaming for other modes
                result = await self.execute(prompt, **kwargs)
                yield {"type": "complete", "execution": result.to_dict()}

        except Exception as e:
            yield {"type": "error", "error": str(e)}

    async def _execute_single(
        self,
        execution: WorkflowExecution,
        prompt: str,
        **kwargs
    ) -> None:
        """Execute single agent."""
        if not self._nodes:
            raise ValueError("No nodes in workflow")

        node = list(self._nodes.values())[0]
        agent = self.registry.get_agent(node.agent_id)
        if not agent:
            raise ValueError(f"Agent not found: {node.agent_id}")

        node.status = AgentStatus.RUNNING
        execution.nodes[node.id].status = AgentStatus.RUNNING

        result = await agent.execute(prompt=node.prompt or prompt, **kwargs)
        node.execution = result
        node.result = result.response
        node.status = result.status

        execution.nodes[node.id].execution = result
        execution.nodes[node.id].result = result.response
        execution.nodes[node.id].status = result.status
        execution.results[node.id] = result.response or ""

    async def _execute_parallel(
        self,
        execution: WorkflowExecution,
        prompt: str,
        **kwargs
    ) -> None:
        """Execute multiple agents in parallel with same input."""
        semaphore = asyncio.Semaphore(self.config.max_parallel)

        async def run_node(node: WorkflowNode) -> tuple[str, AgentExecution]:
            async with semaphore:
                agent = self.registry.get_agent(node.agent_id)
                if not agent:
                    raise ValueError(f"Agent not found: {node.agent_id}")

                node.status = AgentStatus.RUNNING
                execution.nodes[node.id].status = AgentStatus.RUNNING

                result = await agent.execute(prompt=node.prompt or prompt, **kwargs)
                return node.id, result

        tasks = [run_node(node) for node in self._nodes.values()]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for item in results:
            if isinstance(item, Exception):
                execution.errors.append(str(item))
            else:
                node_id, result = item
                self._nodes[node_id].execution = result
                self._nodes[node_id].result = result.response
                self._nodes[node_id].status = result.status
                execution.nodes[node_id].execution = result
                execution.nodes[node_id].result = result.response
                execution.nodes[node_id].status = result.status
                execution.results[node_id] = result.response or ""

    async def _execute_sequential(
        self,
        execution: WorkflowExecution,
        prompt: str,
        **kwargs
    ) -> None:
        """Execute agents in sequence, output feeds next."""
        current_input = prompt

        # Get nodes in order (by dependencies)
        ordered_nodes = self._topological_sort()

        for node in ordered_nodes:
            agent = self.registry.get_agent(node.agent_id)
            if not agent:
                raise ValueError(f"Agent not found: {node.agent_id}")

            node.status = AgentStatus.RUNNING
            execution.nodes[node.id].status = AgentStatus.RUNNING

            # Use node prompt or current input from previous node
            node_prompt = node.prompt or current_input

            result = await agent.execute(prompt=node_prompt, **kwargs)
            node.execution = result
            node.result = result.response
            node.status = result.status

            execution.nodes[node.id].execution = result
            execution.nodes[node.id].result = result.response
            execution.nodes[node.id].status = result.status
            execution.results[node.id] = result.response or ""

            # Feed output to next node
            if result.response:
                current_input = result.response

    async def _execute_sequential_stream(
        self,
        execution: WorkflowExecution,
        prompt: str,
        **kwargs
    ) -> AsyncGenerator[dict, None]:
        """Execute sequentially with streaming."""
        current_input = prompt
        ordered_nodes = self._topological_sort()

        for node in ordered_nodes:
            agent = self.registry.get_agent(node.agent_id)
            if not agent:
                yield {"type": "error", "node_id": node.id, "error": f"Agent not found: {node.agent_id}"}
                continue

            yield {"type": "node_start", "node_id": node.id, "agent_id": node.agent_id}

            node.status = AgentStatus.RUNNING
            node_prompt = node.prompt or current_input

            # Stream the agent execution
            full_response = ""
            async for chunk in agent.execute_stream(prompt=node_prompt, **kwargs):
                full_response += chunk
                yield {
                    "type": "chunk",
                    "node_id": node.id,
                    "content": chunk,
                }

            node.result = full_response
            node.status = AgentStatus.COMPLETED
            execution.results[node.id] = full_response

            yield {
                "type": "node_complete",
                "node_id": node.id,
                "result": full_response,
            }

            current_input = full_response

        yield {"type": "complete", "results": execution.results}

    async def _execute_dag(
        self,
        execution: WorkflowExecution,
        prompt: str,
        **kwargs
    ) -> None:
        """Execute DAG with dependencies."""
        completed: set[str] = set()
        failed: set[str] = set()

        while len(completed) + len(failed) < len(self._nodes):
            # Find nodes ready to execute (all dependencies met)
            ready = []
            for node_id, node in self._nodes.items():
                if node_id in completed or node_id in failed:
                    continue
                if all(dep in completed for dep in node.dependencies):
                    ready.append(node)

            if not ready:
                # No progress possible - there's a cycle or all remaining failed
                remaining = set(self._nodes.keys()) - completed - failed
                if remaining:
                    execution.errors.append(f"Cannot make progress. Remaining nodes: {remaining}")
                break

            # Execute ready nodes in parallel (up to max_parallel)
            semaphore = asyncio.Semaphore(self.config.max_parallel)

            async def run_node(node: WorkflowNode) -> tuple[str, AgentExecution | Exception]:
                async with semaphore:
                    agent = self.registry.get_agent(node.agent_id)
                    if not agent:
                        return node.id, Exception(f"Agent not found: {node.agent_id}")

                    node.status = AgentStatus.RUNNING
                    execution.nodes[node.id].status = AgentStatus.RUNNING

                    # Build prompt from dependencies' results
                    node_prompt = node.prompt or prompt
                    if node.dependencies:
                        dep_results = [execution.results.get(d, "") for d in node.dependencies]
                        if any(dep_results):
                            node_prompt += f"\n\nPrevious results:\n" + "\n".join(dep_results)

                    try:
                        result = await agent.execute(prompt=node_prompt, **kwargs)
                        return node.id, result
                    except Exception as e:
                        return node.id, e

            tasks = [run_node(node) for node in ready]
            results = await asyncio.gather(*tasks)

            for node_id, result in results:
                if isinstance(result, Exception):
                    failed.add(node_id)
                    execution.errors.append(f"Node {node_id} failed: {result}")
                    self._nodes[node_id].status = AgentStatus.ERROR
                    execution.nodes[node_id].status = AgentStatus.ERROR
                else:
                    completed.add(node_id)
                    self._nodes[node_id].execution = result
                    self._nodes[node_id].result = result.response
                    self._nodes[node_id].status = result.status
                    execution.nodes[node_id].execution = result
                    execution.nodes[node_id].result = result.response
                    execution.nodes[node_id].status = result.status
                    execution.results[node_id] = result.response or ""

    def _topological_sort(self) -> list[WorkflowNode]:
        """Sort nodes by dependencies."""
        sorted_nodes = []
        visited = set()
        temp_visited = set()

        def visit(node_id: str):
            if node_id in temp_visited:
                raise ValueError("Cycle detected in workflow")
            if node_id in visited:
                return

            temp_visited.add(node_id)
            node = self._nodes.get(node_id)
            if node:
                for dep in node.dependencies:
                    visit(dep)
                temp_visited.remove(node_id)
                visited.add(node_id)
                sorted_nodes.append(node)

        for node_id in self._nodes:
            visit(node_id)

        return sorted_nodes

    def pause(self) -> None:
        """Pause the workflow."""
        if self._execution and self._execution.status == WorkflowStatus.RUNNING:
            self._execution.status = WorkflowStatus.PAUSED

    def resume(self) -> None:
        """Resume a paused workflow."""
        if self._execution and self._execution.status == WorkflowStatus.PAUSED:
            self._execution.status = WorkflowStatus.RUNNING

    def cancel(self) -> None:
        """Cancel the workflow."""
        if self._execution:
            self._execution.status = WorkflowStatus.CANCELLED
            self._execution.completed_at = datetime.utcnow()

    def to_dict(self) -> dict:
        """Serialize workflow to dict."""
        return {
            "id": self.id,
            "name": self.name,
            "config": self.config.model_dump(),
            "nodes": {nid: node.to_dict() for nid, node in self._nodes.items()},
            "edges": [{"from": e.from_node, "to": e.to_node, "transform": e.transform} for e in self._edges],
        }


class WorkflowRegistry:
    """
    Registry for managing workflows.

    Example:
        registry = WorkflowRegistry(agent_registry)

        # Create workflow
        workflow = registry.create_workflow(WorkflowConfig(
            name="Research Pipeline",
            mode=WorkflowMode.SEQUENTIAL,
            nodes=[
                {"id": "search", "agent_id": "researcher"},
                {"id": "summarize", "agent_id": "summarizer"},
            ]
        ))

        # Execute
        result = await registry.execute(workflow.id, "What is AI?")
    """

    def __init__(self, agent_registry: AgentRegistry):
        self.agent_registry = agent_registry
        self._workflows: dict[str, Workflow] = {}
        self._executions: dict[str, WorkflowExecution] = {}

    def create_workflow(self, config: WorkflowConfig) -> Workflow:
        """Create and register a new workflow."""
        workflow = Workflow(config, self.agent_registry)
        self._workflows[workflow.id] = workflow
        return workflow

    def get_workflow(self, workflow_id: str) -> Workflow | None:
        """Get a workflow by ID."""
        return self._workflows.get(workflow_id)

    def list_workflows(self) -> list[Workflow]:
        """List all workflows."""
        return list(self._workflows.values())

    def delete_workflow(self, workflow_id: str) -> bool:
        """Delete a workflow."""
        if workflow_id in self._workflows:
            del self._workflows[workflow_id]
            return True
        return False

    async def execute(self, workflow_id: str, prompt: str, **kwargs) -> WorkflowExecution:
        """Execute a workflow by ID."""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        execution = await workflow.execute(prompt, **kwargs)
        self._executions[execution.id] = execution
        return execution

    async def execute_stream(self, workflow_id: str, prompt: str, **kwargs) -> AsyncGenerator[dict, None]:
        """Execute a workflow with streaming."""
        workflow = self.get_workflow(workflow_id)
        if not workflow:
            raise ValueError(f"Workflow not found: {workflow_id}")

        async for update in workflow.execute_stream(prompt, **kwargs):
            yield update

    def get_execution(self, execution_id: str) -> WorkflowExecution | None:
        """Get an execution by ID."""
        return self._executions.get(execution_id)

    def list_executions(self, workflow_id: str | None = None, limit: int = 50) -> list[WorkflowExecution]:
        """List executions, optionally filtered by workflow."""
        executions = list(self._executions.values())
        if workflow_id:
            executions = [e for e in executions if e.workflow_id == workflow_id]
        return executions[-limit:]

    def to_dict(self) -> dict:
        """Serialize registry to dict."""
        return {
            "workflows": {wid: wf.to_dict() for wid, wf in self._workflows.items()},
            "executions": {eid: ex.to_dict() for eid, ex in self._executions.items()},
        }
