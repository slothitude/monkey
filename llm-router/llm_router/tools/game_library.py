"""Game Library - Unified game management across multiple directories.

Provides:
- Scanning multiple directories for Godot projects
- Persistent metadata storage (survives server restarts)
- Search and filter capabilities
- MCP tools and API endpoints
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel


class GameMetadata(BaseModel):
    """Metadata for a game in the library."""
    id: str                          # directory name (unique identifier)
    name: str                        # display name from project.godot
    path: str                        # absolute path to project directory
    game_type: str | None = None     # pong, platformer, etc.
    godot_version: str | None = None # from project.godot features
    status: str = "created"          # created, exported, serving
    controls: str | None = None
    objective: str | None = None
    export_path: str | None = None
    play_url: str | None = None
    port: int | None = None
    created_at: str
    last_played: str | None = None
    source_dir: str                  # which configured dir it came from

    class Config:
        extra = "allow"  # Allow additional fields


class GameLibraryConfig(BaseModel):
    """Configuration for the game library."""
    directories: list[str] = ["./data/games", "./games"]
    library_path: str = "./data/game_library.json"
    auto_scan: bool = True


class GameLibrary:
    """
    Unified game library that scans multiple directories and persists metadata.

    Usage:
        library = GameLibrary("./config.yaml")
        games = library.scan()  # Scan all configured directories
        games = library.list(filter_type="pong")
        game = library.get("my_game")
        library.update_status("my_game", "exported", export_path="/path/to/export")
    """

    def __init__(self, config_path: str = "./config.yaml"):
        self._games: dict[str, GameMetadata] = {}
        self._servers: dict[str, int] = {}  # game_id -> port
        self._config = self._load_config(config_path)
        self._library_path = self._config.library_path
        self._loaded = False

        # Load persisted library on init
        self._load_library()

        # Auto-scan if configured
        if self._config.auto_scan:
            self.scan()

    def _load_config(self, config_path: str) -> GameLibraryConfig:
        """Load configuration from YAML file."""
        try:
            import yaml
            config_file = Path(config_path)
            if config_file.exists():
                with open(config_file) as f:
                    data = yaml.safe_load(f) or {}
                library_config = data.get("game_library", {})
                return GameLibraryConfig(**library_config)
        except Exception as e:
            print(f"Warning: Could not load game_library config: {e}")

        return GameLibraryConfig()

    def _parse_project_godot(self, project_path: Path) -> dict[str, Any]:
        """Extract metadata from project.godot file."""
        project_file = project_path / "project.godot"
        if not project_file.exists():
            return {}

        content = project_file.read_text(encoding="utf-8", errors="ignore")
        metadata: dict[str, Any] = {}

        # Parse INI-style format
        current_section = None
        for line in content.split("\n"):
            line = line.strip()

            # Skip comments and empty lines
            if not line or line.startswith(";"):
                # Check for special metadata comments
                if "# GAME_TYPE:" in line:
                    metadata["game_type"] = line.split("# GAME_TYPE:")[1].strip()
                elif "# CONTROLS:" in line:
                    metadata["controls"] = line.split("# CONTROLS:")[1].strip()
                elif "# OBJECTIVE:" in line:
                    metadata["objective"] = line.split("# OBJECTIVE:")[1].strip()
                continue

            # Section header
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1]
                continue

            # Key-value pair
            if "=" in line:
                key, value = line.split("=", 1)

                # Parse config/name
                if key == "config/name":
                    # Remove quotes
                    metadata["name"] = value.strip().strip('"')

                # Parse Godot version from features
                elif key == "config/features":
                    # Extract version from PackedStringArray("4.2", ...)
                    match = re.search(r'"(\d+\.\d+)', value)
                    if match:
                        metadata["godot_version"] = match.group(1)

                # Parse main scene
                elif key == "run/main_scene":
                    metadata["main_scene"] = value.strip().strip('"')

                # Parse input controls
                elif current_section == "input":
                    if "controls" not in metadata:
                        metadata["controls"] = ""
                    # Add input action name
                    if not key.startswith("events"):
                        metadata["controls"] += f"{key}, "

        # Clean up controls string
        if "controls" in metadata:
            metadata["controls"] = metadata["controls"].strip().rstrip(",")

        return metadata

    def _detect_game_type(self, path: Path, name: str) -> str | None:
        """Detect game type from directory name or project name."""
        name_lower = (path.name + " " + name).lower()

        type_keywords = {
            "pong": ["pong"],
            "platformer": ["platformer", "platform"],
            "space_invaders": ["space_invader", "spaceinvader", "invader"],
            "shooter": ["shooter", "shoot"],
            "puzzle": ["puzzle"],
            "dungeon_crawler": ["dungeon", "crawler"],
        }

        for game_type, keywords in type_keywords.items():
            for keyword in keywords:
                if keyword in name_lower:
                    return game_type

        return None

    def _get_default_controls(self, game_type: str | None) -> str | None:
        """Get default controls for a game type."""
        controls_map = {
            "pong": "W/S or Arrow Up/Down to move paddle",
            "platformer": "A/D or Arrow Left/Right to move, W/Space/Arrow Up to jump",
            "space_invaders": "Arrow Left/Right to move, Space to shoot",
            "shooter": "WASD to move, Mouse to aim, Click to shoot",
            "puzzle": "Click or Arrow keys to interact",
            "dungeon_crawler": "WASD to move, Space to attack",
        }
        return controls_map.get(game_type) if game_type else None

    def _get_default_objective(self, game_type: str | None) -> str | None:
        """Get default objective for a game type."""
        objectives_map = {
            "pong": "Score points by getting the ball past your opponent's paddle",
            "platformer": "Navigate through levels, avoid obstacles, reach the goal",
            "space_invaders": "Destroy all alien invaders before they reach you",
            "shooter": "Defeat enemies and survive as long as possible",
            "puzzle": "Solve puzzles to progress through the game",
            "dungeon_crawler": "Explore the dungeon, defeat monsters, find treasure",
        }
        return objectives_map.get(game_type) if game_type else None

    def scan(self) -> list[GameMetadata]:
        """Scan all configured directories for games."""
        discovered: dict[str, GameMetadata] = {}

        for dir_path in self._config.directories:
            games_dir = Path(dir_path)
            if not games_dir.exists():
                continue

            for game_dir in games_dir.iterdir():
                if not game_dir.is_dir():
                    continue

                # Check for project.godot
                if not (game_dir / "project.godot").exists():
                    continue

                game_id = game_dir.name

                # Parse project file
                project_meta = self._parse_project_godot(game_dir)

                # Detect game type
                game_type = project_meta.get("game_type") or self._detect_game_type(
                    game_dir, project_meta.get("name", game_id)
                )

                # Get or create metadata
                existing = self._games.get(game_id)

                created_at = existing.created_at if existing else datetime.now().isoformat()

                metadata = GameMetadata(
                    id=game_id,
                    name=project_meta.get("name", game_id.replace("_", " ").title()),
                    path=str(game_dir.absolute()),
                    game_type=game_type,
                    godot_version=project_meta.get("godot_version"),
                    status=existing.status if existing else "created",
                    controls=project_meta.get("controls") or self._get_default_controls(game_type),
                    objective=project_meta.get("objective") or self._get_default_objective(game_type),
                    export_path=existing.export_path if existing else None,
                    play_url=existing.play_url if existing else None,
                    port=existing.port if existing else None,
                    created_at=created_at,
                    last_played=existing.last_played if existing else None,
                    source_dir=dir_path,
                )

                # Check for export directory
                export_dir = game_dir / "export" / "html"
                if export_dir.exists() and (export_dir / "index.html").exists():
                    metadata.status = existing.status if existing and existing.status in ["serving", "exported"] else "exported"
                    metadata.export_path = str(export_dir)

                discovered[game_id] = metadata

        # Update internal state
        self._games = discovered
        self._save_library()

        return list(self._games.values())

    def list(
        self,
        filter_type: str | None = None,
        filter_status: str | None = None,
    ) -> list[GameMetadata]:
        """List games with optional filters."""
        games = list(self._games.values())

        if filter_type:
            games = [g for g in games if g.game_type == filter_type]

        if filter_status:
            games = [g for g in games if g.status == filter_status]

        return sorted(games, key=lambda g: g.name.lower())

    def get(self, game_id: str) -> GameMetadata | None:
        """Get a specific game by ID."""
        return self._games.get(game_id)

    def search(self, query: str) -> list[GameMetadata]:
        """Search games by name, type, or ID."""
        query_lower = query.lower()
        results = []

        for game in self._games.values():
            if (
                query_lower in game.name.lower()
                or query_lower in game.id.lower()
                or (game.game_type and query_lower in game.game_type.lower())
            ):
                results.append(game)

        return sorted(results, key=lambda g: g.name.lower())

    def register(
        self,
        path: str,
        game_type: str | None = None,
        **kwargs: Any,
    ) -> GameMetadata:
        """Register a new game or update existing."""
        game_path = Path(path)
        if not game_path.exists():
            raise ValueError(f"Path does not exist: {path}")

        game_id = game_path.name

        # Parse project metadata
        project_meta = self._parse_project_godot(game_path)

        # Determine game type
        detected_type = game_type or project_meta.get("game_type") or self._detect_game_type(
            game_path, project_meta.get("name", game_id)
        )

        # Get existing or create new
        existing = self._games.get(game_id)
        created_at = existing.created_at if existing else datetime.now().isoformat()

        metadata = GameMetadata(
            id=game_id,
            name=kwargs.get("name") or project_meta.get("name", game_id.replace("_", " ").title()),
            path=str(game_path.absolute()),
            game_type=detected_type,
            godot_version=project_meta.get("godot_version"),
            status=kwargs.get("status", existing.status if existing else "created"),
            controls=kwargs.get("controls") or project_meta.get("controls") or self._get_default_controls(detected_type),
            objective=kwargs.get("objective") or project_meta.get("objective") or self._get_default_objective(detected_type),
            export_path=kwargs.get("export_path", existing.export_path if existing else None),
            play_url=kwargs.get("play_url", existing.play_url if existing else None),
            port=kwargs.get("port", existing.port if existing else None),
            created_at=created_at,
            last_played=kwargs.get("last_played", existing.last_played if existing else None),
            source_dir=kwargs.get("source_dir", str(game_path.parent)),
        )

        self._games[game_id] = metadata
        self._save_library()

        return metadata

    def update_status(
        self,
        game_id: str,
        status: str,
        **kwargs: Any,
    ) -> GameMetadata | None:
        """Update game status (exported, serving, etc.)."""
        game = self._games.get(game_id)
        if not game:
            return None

        # Update status
        game.status = status

        # Update optional fields
        for field in ["export_path", "play_url", "port", "last_played", "controls", "objective", "game_type"]:
            if field in kwargs:
                setattr(game, field, kwargs[field])

        self._save_library()

        return game

    def unregister(self, game_id: str) -> bool:
        """Remove a game from the library."""
        if game_id in self._games:
            del self._games[game_id]
            self._save_library()
            return True
        return False

    def _save_library(self) -> None:
        """Persist library to JSON."""
        try:
            library_file = Path(self._library_path)
            library_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "version": 1,
                "updated_at": datetime.now().isoformat(),
                "games": {gid: game.model_dump() for gid, game in self._games.items()},
            }

            with open(library_file, "w") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            print(f"Warning: Could not save game library: {e}")

    def _load_library(self) -> None:
        """Load library from JSON on startup."""
        if self._loaded:
            return

        try:
            library_file = Path(self._library_path)
            if not library_file.exists():
                self._loaded = True
                return

            with open(library_file) as f:
                data = json.load(f)

            # Load games
            games_data = data.get("games", {})
            for gid, gdata in games_data.items():
                try:
                    self._games[gid] = GameMetadata(**gdata)
                except Exception as e:
                    print(f"Warning: Could not load game {gid}: {e}")

            self._loaded = True
        except Exception as e:
            print(f"Warning: Could not load game library: {e}")
            self._loaded = True

    def get_server_port(self, game_id: str) -> int | None:
        """Get the port a game is being served on."""
        return self._servers.get(game_id)

    def set_server_port(self, game_id: str, port: int | None) -> None:
        """Set or clear the port a game is being served on."""
        if port is None:
            self._servers.pop(game_id, None)
        else:
            self._servers[game_id] = port

    def get_stats(self) -> dict[str, Any]:
        """Get library statistics."""
        games = list(self._games.values())
        types: dict[str, int] = {}
        statuses: dict[str, int] = {}

        for game in games:
            if game.game_type:
                types[game.game_type] = types.get(game.game_type, 0) + 1
            statuses[game.status] = statuses.get(game.status, 0) + 1

        return {
            "total_games": len(games),
            "by_type": types,
            "by_status": statuses,
            "serving": len(self._servers),
        }


# Global instance
_library: GameLibrary | None = None


def get_game_library(config_path: str = "./config.yaml") -> GameLibrary:
    """Get the global game library instance."""
    global _library
    if _library is None:
        _library = GameLibrary(config_path)
    return _library


# MCP Tool functions
async def library_scan() -> dict:
    """Scan all directories for games."""
    library = get_game_library()
    games = library.scan()
    return {
        "success": True,
        "games": [g.model_dump() for g in games],
        "count": len(games),
        "stats": library.get_stats(),
    }


async def library_list(
    filter_type: str | None = None,
    filter_status: str | None = None,
) -> dict:
    """List all games with optional filters."""
    library = get_game_library()
    games = library.list(filter_type=filter_type, filter_status=filter_status)
    return {
        "games": [g.model_dump() for g in games],
        "count": len(games),
        "stats": library.get_stats(),
    }


async def library_get(game_id: str) -> dict:
    """Get detailed info for a specific game."""
    library = get_game_library()
    game = library.get(game_id)
    if not game:
        return {"error": f"Game not found: {game_id}"}
    return {"game": game.model_dump()}


async def library_search(query: str) -> dict:
    """Search games by name or type."""
    library = get_game_library()
    games = library.search(query)
    return {
        "games": [g.model_dump() for g in games],
        "count": len(games),
        "query": query,
    }


async def library_register(
    path: str,
    game_type: str | None = None,
    **kwargs: Any,
) -> dict:
    """Manually register a game."""
    library = get_game_library()
    try:
        game = library.register(path, game_type=game_type, **kwargs)
        return {"success": True, "game": game.model_dump()}
    except Exception as e:
        return {"error": str(e)}


def register_game_library_tools(registry) -> None:
    """Register game library tools with the tool registry."""
    from llm_router.tools import ToolDefinition

    registry.register(ToolDefinition(
        name="library_scan",
        description="Scan all configured directories for Godot games and update the library.",
        parameters={"type": "object", "properties": {}},
        function=library_scan,
        category="game_library",
    ))

    registry.register(ToolDefinition(
        name="library_list",
        description="List all games in the library with optional filters.",
        parameters={
            "type": "object",
            "properties": {
                "filter_type": {"type": "string", "description": "Filter by game type (pong, platformer, etc.)"},
                "filter_status": {"type": "string", "description": "Filter by status (created, exported, serving)"},
            },
        },
        function=library_list,
        category="game_library",
    ))

    registry.register(ToolDefinition(
        name="library_get",
        description="Get detailed info for a specific game.",
        parameters={
            "type": "object",
            "properties": {
                "game_id": {"type": "string", "description": "The game ID (directory name)"},
            },
            "required": ["game_id"],
        },
        function=library_get,
        category="game_library",
    ))

    registry.register(ToolDefinition(
        name="library_search",
        description="Search games by name or type.",
        parameters={
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"},
            },
            "required": ["query"],
        },
        function=library_search,
        category="game_library",
    ))

    registry.register(ToolDefinition(
        name="library_register",
        description="Manually register a game directory in the library.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Path to the game directory"},
                "game_type": {"type": "string", "description": "Optional game type"},
            },
            "required": ["path"],
        },
        function=library_register,
        category="game_library",
    ))
