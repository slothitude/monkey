# Godot AI Complete Workflow

## Overview

The Godot AI agent has a complete automated workflow for creating, coding, exporting, serving, and publishing Godot 4.x games.

## Tools Available

### 1. godot_check_install()
Check if Godot is installed and get version info.
```json
{
  "installed": true,
  "path": "C:/Users/aaron/Godot/Godot_v4.6.1-stable_win64_console.exe",
  "version": "4.6.1.stable.official.14d19694e"
}
```

### 2. godot_create_project(project_path, project_name, godot_version)
Create a new Godot project with proper structure:
- project.godot
- icon.svg
- export_presets.cfg (for web export)
- .godot/ directory

### 3. godot_create_game(project_path, game_name, game_type, description)
Create a game from template:
- Types: shooter, platformer, puzzle
- Includes input mappings
- Creates basic scripts

### 4. godot_add_script(project_path, script_name, content, extends)
Add a GDScript file to the project:
- Automatically adds "extends" clause if missing
- Creates .gd file in project directory

### 5. godot_add_scene(project_path, scene_name, content)
Add a .tscn scene file.

### 6. godot_export_web(project_path, output_path)
Export to HTML5/WebAssembly:
- Creates index.html
- Creates .wasm file
- Creates .js and .pck files

### 7. godot_serve_game(export_path, port)
Start HTTP server for testing:
- Default port: 8888
- Auto-finds free port if busy
- Returns URL: http://localhost:PORT

### 8. godot_get_docs(topic, version)
Get Godot documentation URLs:
- Class reference
- Tutorials
- API docs

## itch.io Publishing Tools

### 9. itchio_setup()
Auto-download and install Butler CLI from GitHub releases.
- Installs to `~/butler/`
- Returns path and version

### 10. itchio_login()
Open browser for OAuth authentication.
- User completes login in browser
- Credentials stored in `~/.config/itch/butler_creds`

### 11. itchio_upload(game_path, username, game_slug, channel, version)
Upload game build to itch.io.
- Requires Butler installed and logged in
- Requires game page created manually

### 12. itchio_publish(game_path, username, game_name, channel)
Complete publishing workflow.

## Complete Workflow Example

```
User: "Create a Pong game"

Agent executes:
1. godot_check_install()
2. godot_create_project("./games/pong", "Pong")
3. godot_add_script("./games/pong", "Main.gd", main_code, "Node2D")
4. godot_add_script("./games/pong", "Player.gd", player_code, "CharacterBody2D")
5. godot_add_script("./games/pong", "Ball.gd", ball_code, "CharacterBody2D")
6. godot_export_web("./games/pong")
7. godot_serve_game("./games/pong/export/html", 8888)

Agent responds:
"Your Pong game is ready! Play at http://localhost:8888"
```

## Publishing to itch.io

```
User: "Publish this game to itch.io"

Agent executes:
1. itchio_setup()              # Auto-install Butler
2. itchio_login()              # Open browser for OAuth
3. [TELLS USER] "Create game page at https://itch.io/game/new"
4. [USER CONFIRMS] "Created at https://username.itch.io/game-slug"
5. itchio_upload("./games/pong/export/html", "username", "game-slug", "html5")

Agent responds:
"Game published! Play at https://username.itch.io/game-slug"
```

**IMPORTANT**: Game page must be created manually at https://itch.io/game/new because Cloudflare blocks automated creation.

## Agent Configuration

```json
{
  "id": "godot-ai",
  "name": "Godot AI",
  "tools": [
    "godot_check_install",
    "godot_create_project",
    "godot_create_game",
    "godot_add_script",
    "godot_add_scene",
    "godot_export_web",
    "godot_serve_game",
    "godot_get_docs",
    "itchio_setup",
    "itchio_login",
    "itchio_upload",
    "itchio_publish",
    "file_read",
    "file_write",
    "file_list",
    "web_search"
  ]
}
```

## Godot Installation

The tools look for Godot in these locations:

**Windows:**
- C:/Users/{USERNAME}/Godot/Godot_v4.6.1-stable_win64_console.exe
- C:/Program Files/Godot/

**Linux:**
- /usr/bin/godot4
- /usr/local/bin/godot4

**macOS:**
- /Applications/Godot.app/Contents/MacOS/Godot

## Butler Installation

Butler is auto-installed by `itchio_setup()` to:
- Windows: `C:/Users/{USERNAME}/butler/windows-amd64/butler.exe`
- macOS: `~/butler/darwin-amd64/butler`
- Linux: `~/butler/linux-amd64/butler`

## GDScript Style Guide (Godot 4.x)

```gdscript
extends CharacterBody2D

# Exports for inspector
@export var speed: float = 400.0
@export var jump_force: float = 500.0

# Type hints
var velocity: Vector2 = Vector2.ZERO
var is_grounded: bool = false

# Signals
signal died
signal score_changed(points: int)

func _ready() -> void:
    # Initialization
    pass

func _physics_process(delta: float) -> void:
    # Movement and physics
    pass

func _input(event: InputEvent) -> void:
    # Input handling
    pass
```

## Documentation Sources

- Official docs: https://docs.godotengine.org/en/stable/
- Class reference: https://docs.godotengine.org/en/stable/classes/
- Tutorials: https://docs.godotengine.org/en/stable/tutorials/

## API Endpoints

```bash
# Create agent
curl -X POST http://localhost:8000/v1/agents -d '{
  "id": "godot-ai",
  "name": "Godot AI",
  "tools": ["godot_check_install", "godot_create_project", ...]
}'

# Execute agent
curl -X POST http://localhost:8000/v1/agents/godot-ai/execute -d '{
  "prompt": "Create Space Invaders"
}'

# Stream execution
curl http://localhost:8000/v1/agents/godot-ai/stream?prompt=Create%20Pong
```
