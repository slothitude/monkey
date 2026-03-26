"""Built-in tools for the agent framework."""

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path
from typing import Any
import httpx

from llm_router.tools import ToolDefinition, ToolRegistry


# Web Search Tool
async def web_search(
    query: str,
    engine: str = "searxng",
    num_results: int = 5,
    searxng_url: str = "http://localhost:8888"
) -> dict:
    """
    Search the web using SearXNG or Brave Search.

    Args:
        query: Search query
        engine: Search engine to use (searxng, brave)
        num_results: Number of results to return
        searxng_url: URL for SearXNG instance

    Returns:
        Dict with search results
    """
    results = []

    try:
        if engine == "searxng":
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{searxng_url}/search",
                    params={"q": query, "format": "json"},
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("results", [])[:num_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("content", ""),
                    })

        elif engine == "brave":
            # Brave Search API (requires API key in environment)
            import os
            api_key = os.environ.get("BRAVE_API_KEY")
            if not api_key:
                return {"error": "BRAVE_API_KEY not set"}

            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    headers={"X-Subscription-Token": api_key},
                    params={"q": query, "count": num_results},
                    timeout=30.0
                )
                response.raise_for_status()
                data = response.json()

                for item in data.get("web", {}).get("results", []):
                    results.append({
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "snippet": item.get("description", ""),
                    })

        else:
            return {"error": f"Unknown search engine: {engine}"}

        return {"query": query, "results": results, "count": len(results)}

    except Exception as e:
        return {"error": str(e), "query": query, "results": []}


WEB_SEARCH_DEF = ToolDefinition(
    name="web_search",
    description="Search the web for information. Returns relevant search results with titles, URLs, and snippets.",
    parameters={
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "engine": {"type": "string", "enum": ["searxng", "brave"], "default": "searxng"},
            "num_results": {"type": "integer", "default": 5, "minimum": 1, "maximum": 20},
        },
        "required": ["query"],
    },
    function=web_search,
    category="research",
    examples=[
        "web_search(query='latest AI news 2024')",
        "web_search(query='Python asyncio tutorial', engine='brave')",
    ],
)


# File Operations Tool
async def file_read(
    path: str,
    encoding: str = "utf-8",
    max_size: int = 1000000  # 1MB max
) -> dict:
    """
    Read contents from a file.

    Args:
        path: Path to the file
        encoding: File encoding
        max_size: Maximum file size to read in bytes

    Returns:
        Dict with file contents or error
    """
    try:
        file_path = Path(path)
        if not file_path.exists():
            return {"error": f"File not found: {path}"}

        if file_path.stat().st_size > max_size:
            return {"error": f"File too large (max {max_size} bytes)"}

        content = file_path.read_text(encoding=encoding)
        return {
            "path": path,
            "content": content,
            "size": len(content),
            "lines": content.count("\n") + 1,
        }

    except Exception as e:
        return {"error": str(e), "path": path}


async def file_write(
    path: str,
    content: str,
    mode: str = "write",
    encoding: str = "utf-8"
) -> dict:
    """
    Write contents to a file.

    Args:
        path: Path to the file
        content: Content to write
        mode: 'write' to overwrite, 'append' to append
        encoding: File encoding

    Returns:
        Dict with result status
    """
    try:
        file_path = Path(path)

        # Create parent directories if needed
        file_path.parent.mkdir(parents=True, exist_ok=True)

        if mode == "append":
            with open(file_path, "a", encoding=encoding) as f:
                f.write(content)
        else:
            file_path.write_text(content, encoding=encoding)

        return {
            "success": True,
            "path": path,
            "bytes_written": len(content.encode(encoding)),
        }

    except Exception as e:
        return {"error": str(e), "path": path}


async def file_list(
    path: str = ".",
    pattern: str = "*",
    recursive: bool = False
) -> dict:
    """
    List files in a directory.

    Args:
        path: Directory path
        pattern: Glob pattern to filter files
        recursive: Whether to search recursively

    Returns:
        Dict with list of files
    """
    try:
        dir_path = Path(path)
        if not dir_path.exists():
            return {"error": f"Directory not found: {path}"}

        if recursive:
            files = list(dir_path.rglob(pattern))
        else:
            files = list(dir_path.glob(pattern))

        result = []
        for f in files:
            stat = f.stat() if f.is_file() else None
            result.append({
                "name": f.name,
                "path": str(f),
                "is_dir": f.is_dir(),
                "size": stat.st_size if stat else 0,
            })

        return {"path": path, "files": result, "count": len(result)}

    except Exception as e:
        return {"error": str(e), "path": path}


FILE_READ_DEF = ToolDefinition(
    name="file_read",
    description="Read contents from a file on the filesystem.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "encoding": {"type": "string", "default": "utf-8"},
            "max_size": {"type": "integer", "default": 1000000},
        },
        "required": ["path"],
    },
    function=file_read,
    category="file_ops",
    dangerous=True,
)

FILE_WRITE_DEF = ToolDefinition(
    name="file_write",
    description="Write contents to a file on the filesystem. Can create new files or append to existing ones.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Path to the file"},
            "content": {"type": "string", "description": "Content to write"},
            "mode": {"type": "string", "enum": ["write", "append"], "default": "write"},
            "encoding": {"type": "string", "default": "utf-8"},
        },
        "required": ["path", "content"],
    },
    function=file_write,
    category="file_ops",
    dangerous=True,
)

FILE_LIST_DEF = ToolDefinition(
    name="file_list",
    description="List files in a directory with optional pattern filtering.",
    parameters={
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": "."},
            "pattern": {"type": "string", "default": "*"},
            "recursive": {"type": "boolean", "default": False},
        },
    },
    function=file_list,
    category="file_ops",
)


# Code Execution Tool
async def code_exec(
    code: str,
    language: str = "python",
    timeout: int = 30,
    sandbox: bool = True
) -> dict:
    """
    Execute code in a sandboxed environment.

    Args:
        code: Code to execute
        language: Programming language (python, javascript, bash)
        timeout: Execution timeout in seconds
        sandbox: Whether to run in sandboxed mode

    Returns:
        Dict with execution results
    """
    try:
        if language == "python":
            # Execute Python code
            with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
                f.write(code)
                temp_path = f.name

            try:
                result = subprocess.run(
                    ["python", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                    cwd=tempfile.gettempdir(),
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                    "language": language,
                }
            finally:
                Path(temp_path).unlink(missing_ok=True)

        elif language == "javascript":
            # Execute JavaScript with Node.js
            with tempfile.NamedTemporaryFile(mode="w", suffix=".js", delete=False) as f:
                f.write(code)
                temp_path = f.name

            try:
                result = subprocess.run(
                    ["node", temp_path],
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                return {
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                    "returncode": result.returncode,
                    "language": language,
                }
            finally:
                Path(temp_path).unlink(missing_ok=True)

        elif language == "bash":
            # Execute bash commands (with restrictions in sandbox mode)
            if sandbox:
                # Block dangerous commands
                dangerous = ["rm -rf", "mkfs", "dd", ":(){", "chmod 777", "> /dev/"]
                for cmd in dangerous:
                    if cmd in code:
                        return {"error": f"Blocked dangerous command pattern: {cmd}"}

            result = subprocess.run(
                code,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return {
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode,
                "language": language,
            }

        else:
            return {"error": f"Unsupported language: {language}"}

    except subprocess.TimeoutExpired:
        return {"error": f"Execution timed out after {timeout} seconds"}
    except Exception as e:
        return {"error": str(e)}


CODE_EXEC_DEF = ToolDefinition(
    name="code_exec",
    description="Execute code in Python, JavaScript, or Bash. Results include stdout, stderr, and return code.",
    parameters={
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Code to execute"},
            "language": {"type": "string", "enum": ["python", "javascript", "bash"], "default": "python"},
            "timeout": {"type": "integer", "default": 30, "minimum": 1, "maximum": 300},
            "sandbox": {"type": "boolean", "default": True},
        },
        "required": ["code"],
    },
    function=code_exec,
    category="execution",
    dangerous=True,
    examples=[
        "code_exec(code='print(2+2)', language='python')",
        "code_exec(code='console.log(2+2)', language='javascript')",
    ],
)


# API Call Tool
async def api_call(
    url: str,
    method: str = "GET",
    headers: dict | None = None,
    params: dict | None = None,
    body: Any = None,
    timeout: int = 30
) -> dict:
    """
    Make HTTP API requests.

    Args:
        url: URL to request
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        headers: Request headers
        params: Query parameters
        body: Request body (for POST/PUT/PATCH)
        timeout: Request timeout in seconds

    Returns:
        Dict with response data
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method=method.upper(),
                url=url,
                headers=headers or {},
                params=params,
                json=body if body and method.upper() in ["POST", "PUT", "PATCH"] else None,
                timeout=timeout,
            )

            # Try to parse JSON response
            try:
                response_body = response.json()
            except Exception:
                response_body = response.text

            return {
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": response_body,
                "url": str(response.url),
            }

    except httpx.TimeoutException:
        return {"error": f"Request timed out after {timeout} seconds", "url": url}
    except Exception as e:
        return {"error": str(e), "url": url}


API_CALL_DEF = ToolDefinition(
    name="api_call",
    description="Make HTTP API requests to any URL. Supports GET, POST, PUT, DELETE, PATCH methods.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to request"},
            "method": {"type": "string", "enum": ["GET", "POST", "PUT", "DELETE", "PATCH"], "default": "GET"},
            "headers": {"type": "object", "description": "Request headers"},
            "params": {"type": "object", "description": "Query parameters"},
            "body": {"type": "object", "description": "Request body for POST/PUT/PATCH"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["url"],
    },
    function=api_call,
    category="network",
    examples=[
        "api_call(url='https://api.example.com/data')",
        "api_call(url='https://api.example.com/users', method='POST', body={'name': 'John'})",
    ],
)


# Database Query Tool (generic)
async def db_query(
    connection_string: str,
    query: str,
    params: list | None = None,
    database_type: str = "sqlite"
) -> dict:
    """
    Execute a database query.

    Args:
        connection_string: Database connection string or path
        query: SQL query to execute
        params: Query parameters
        database_type: Type of database (sqlite, postgres, mysql)

    Returns:
        Dict with query results
    """
    try:
        if database_type == "sqlite":
            import sqlite3
            conn = sqlite3.connect(connection_string)
            cursor = conn.cursor()
            cursor.execute(query, params or ())
            results = cursor.fetchall()
            columns = [desc[0] for desc in cursor.description] if cursor.description else []
            conn.commit()
            conn.close()

            return {
                "columns": columns,
                "rows": results,
                "row_count": len(results),
            }

        # For postgres/mysql, you would need asyncpg/aiomysql
        return {"error": f"Database type '{database_type}' not yet supported"}

    except Exception as e:
        return {"error": str(e)}


DB_QUERY_DEF = ToolDefinition(
    name="db_query",
    description="Execute SQL queries against a database. Supports SQLite, PostgreSQL, MySQL.",
    parameters={
        "type": "object",
        "properties": {
            "connection_string": {"type": "string", "description": "Database connection string or path"},
            "query": {"type": "string", "description": "SQL query to execute"},
            "params": {"type": "array", "description": "Query parameters"},
            "database_type": {"type": "string", "enum": ["sqlite", "postgres", "mysql"], "default": "sqlite"},
        },
        "required": ["connection_string", "query"],
    },
    function=db_query,
    category="database",
    dangerous=True,
)


# URL Fetch Tool
async def url_fetch(
    url: str,
    selector: str | None = None,
    timeout: int = 30
) -> dict:
    """
    Fetch and extract content from a URL.

    Args:
        url: URL to fetch
        selector: Optional CSS selector to extract specific elements
        timeout: Request timeout

    Returns:
        Dict with page content
    """
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(url, timeout=timeout, follow_redirects=True)
            response.raise_for_status()

            content = response.text

            # If selector provided, try to extract with BeautifulSoup
            if selector:
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(content, "html.parser")
                    elements = soup.select(selector)
                    extracted = [e.get_text(strip=True) for e in elements]
                    return {
                        "url": url,
                        "extracted": extracted,
                        "count": len(extracted),
                    }
                except ImportError:
                    pass

            return {
                "url": url,
                "content": content[:10000],  # Limit content size
                "content_length": len(content),
                "truncated": len(content) > 10000,
            }

    except Exception as e:
        return {"error": str(e), "url": url}


URL_FETCH_DEF = ToolDefinition(
    name="url_fetch",
    description="Fetch and extract content from a web page. Optionally extract specific elements using CSS selectors.",
    parameters={
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch"},
            "selector": {"type": "string", "description": "Optional CSS selector"},
            "timeout": {"type": "integer", "default": 30},
        },
        "required": ["url"],
    },
    function=url_fetch,
    category="research",
)


def register_builtin_tools(registry: ToolRegistry) -> None:
    """Register all built-in tools with a registry."""
    # Web tools
    registry.register(WEB_SEARCH_DEF)
    registry.register(URL_FETCH_DEF)

    # File tools
    registry.register(FILE_READ_DEF)
    registry.register(FILE_WRITE_DEF)
    registry.register(FILE_LIST_DEF)

    # Execution tools
    registry.register(CODE_EXEC_DEF)

    # Network tools
    registry.register(API_CALL_DEF)

    # Database tools
    registry.register(DB_QUERY_DEF)
