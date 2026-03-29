# Game Maker Guide

Complete guide to creating games with the Universal Agent Platform's Godot game maker tools.

## Table of Contents

1. [Quick Start](#quick-start)
2. [Game Templates](#game-templates)
3. [Custom Games](#custom-games)
4. [Asset Creation](#asset-creation)
5. [AI Art Generation](#ai-art-generation)
6. [Debugging](#debugging)
7. [API Reference](#api-reference)
8. [Using the Game Agent](#using-the-game-agent)

---

## Quick Start

### Create a Game in 30 Seconds

```bash
# Using the API
curl -X POST http://localhost:8000/v1/games \
  -H "Content-Type: application/json" \
  -d '{
    "game_name": "MyPong",
    "game_type": "pong",
    "auto_export": true,
    "auto_serve": true
  }'

# Then open http://localhost:8888 in your browser
```

### Using Python

```python
from llm_router.tools.godot_tools import godot_create_from_template

# Create a complete Pong game
result = await godot_create_from_template(
    project_path="./data/games/my_pong",
    template_name="pong",
    game_name="MyPong",
    customizations={"colors": {"player1": "#ff0000", "player2": "#00ff00"}}
)

# Export to web
await godot_export_web("./data/games/my_pong")

# Serve locally
await godot_serve_game("./data/games/my_pong/export/html", port=8888)
```

### Using the Web Dashboard

1. Open http://localhost:8000/games
2. Click a template or "Create from Prompt"
3. Enter a game name
4. Click "Create Game"
5. Click "Play" when ready

---

## Game Templates

### Available Templates

| Template | Type | Description | Controls |
|----------|------|-------------|----------|
| **Pong** | pong | Classic two-player pong, first to 5 wins | W/S (P1), Up/Down (P2) |
| **Space Invaders** | space_invaders | Destroy all aliens before they reach you | A/D to move, Space to shoot |
| **Platformer** | platformer | Jump and run, collect coins | A/D to move, W/Space to jump |
| **Shooter** | shooter | Top-down survival shooter with waves | WASD to move, Space to shoot |
| **Puzzle** | puzzle | Match-3 puzzle game | Click to select, click to swap |

### Creating from Template

```python
from llm_router.tools.godot_tools import godot_create_from_template

result = await godot_create_from_template(
    project_path="./games/my_game",
    template_name="space_invaders",
    game_name="Space Blaster",
    customizations={
        "colors": {"player": "#00ff00", "enemies": "#ff0000"},
        "speed": 1.5,  # 50% faster
        "difficulty": "hard"
    }
)

print(f"Created: {result['files_created']}")
print(f"Controls: {result['controls']}")
```

### Template Customizations

| Option | Type | Description |
|--------|------|-------------|
| `colors` | dict | Override default colors (hex format) |
| `speed` | float | Game speed multiplier (1.0 = normal) |
| `difficulty` | string | "easy", "medium", or "hard" |

---

## Custom Games

### Building a Scene

Use `godot_build_scene` to create custom game scenes:

```python
from llm_router.tools.godot_tools import godot_build_scene

scene_config = {
    "root_type": "Node2D",
    "root_script": "Main.gd",
    "nodes": [
        {
            "name": "Player",
            "type": "CharacterBody2D",
            "script": "Player.gd",
            "position": [100, 300],
            "children": [
                {
                    "type": "CollisionShape2D",
                    "shape": "CircleShape2D",
                    "radius": 20
                },
                {
                    "type": "Sprite2D",
                    "texture": "res://player.png"
                }
            ]
        },
        {
            "name": "Enemy",
            "type": "Area2D",
            "position": [500, 300],
            "children": [
                {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [40, 40]}
            ]
        }
    ],
    "ui": {
        "labels": [
            {"name": "ScoreLabel", "text": "Score: 0", "position": [20, 20]},
            {"name": "HealthLabel", "text": "Health: 100", "position": [20, 50]}
        ]
    },
    "connections": [
        {"from": "Enemy", "signal": "body_entered", "to": ".", "method": "on_enemy_hit"}
    ]
}

result = await godot_build_scene(
    project_path="./games/custom_game",
    scene_name="Main",
    scene_config=scene_config
)
```

### Supported Node Types

- **2D Nodes**: Node2D, CharacterBody2D, StaticBody2D, RigidBody2D, Area2D
- **Visual**: Sprite2D, ColorRect, AnimatedSprite2D, Camera2D
- **Collision**: CollisionShape2D, CollisionShape3D
- **UI**: Label, Button, CanvasLayer
- **Logic**: Timer, AudioStreamPlayer
- **3D Nodes**: Node3D, CharacterBody3D, Camera3D, MeshInstance3D

### Adding Scripts

```python
from llm_router.tools.godot_tools import godot_add_script

script = '''extends CharacterBody2D

const SPEED: float = 200.0

func _physics_process(_delta: float) -> void:
    var direction: float = Input.get_axis("move_left", "move_right")
    velocity.x = direction * SPEED
    move_and_slide()
'''

result = await godot_add_script(
    project_path="./games/my_game",
    script_name="Player.gd",
    script_content=script,
    extends="CharacterBody2D"
)
```

---

## Asset Creation

### Creating Sprites

```python
from llm_router.tools.godot_assets import godot_create_sprite

# Simple rectangle sprite
await godot_create_sprite(
    project_path="./games/my_game",
    sprite_name="player",
    sprite_config={
        "type": "rectangle",
        "size": [32, 32],
        "color": "#4488ff"
    }
)

# Player ship sprite
await godot_create_sprite(
    project_path="./games/my_game",
    sprite_name="ship",
    sprite_config={
        "type": "player_ship",
        "size": [64, 64],
        "color": "#44ff44",
        "outline_color": "#ffffff",
        "outline_width": 2
    }
)
```

### Sprite Types

| Type | Description |
|------|-------------|
| `rectangle` | Simple rectangle |
| `circle` | Circle/ellipse |
| `triangle` | Triangle pointing up |
| `star` | 5-pointed star |
| `heart` | Heart shape |
| `arrow` | Arrow pointing right |
| `diamond` | Diamond/rhombus |
| `hexagon` | Regular hexagon |
| `player_ship` | Spaceship shape |
| `enemy` | Enemy ship (inverted triangle) |
| `bullet` | Small bullet/missile |
| `coin` | Collectible coin |
| `paddle` | Pong paddle |
| `ball` | Pong ball |

### Creating Sounds

```python
from llm_router.tools.godot_assets import godot_create_sound

# Jump sound
await godot_create_sound(
    project_path="./games/my_game",
    sound_name="jump",
    sound_config={
        "type": "jump",
        "frequency": 440,
        "duration": 0.2,
        "volume": 0.5
    }
)

# Explosion sound
await godot_create_sound(
    project_path="./games/my_game",
    sound_name="explosion",
    sound_config={
        "type": "explosion",
        "frequency": 100,
        "duration": 0.5,
        "volume": 0.7
    }
)
```

### Sound Types

| Type | Description |
|------|-------------|
| `beep`, `tone` | Simple sine wave |
| `square` | 8-bit style square wave |
| `noise` | White noise |
| `explosion` | Low rumble with noise |
| `jump` | Rising frequency sweep |
| `collect` | Two-tone pickup |
| `hit` | Quick impact |
| `powerup` | Rising arpeggio |
| `hurt` | Descending tone |
| `victory` | Triumphant fanfare |

---

## AI Art Generation

Requires `PIXAZO_API_KEY` environment variable.

### Generate AI Sprites

```python
from llm_router.tools.ai_art import generate_sprite_ai

result = await generate_sprite_ai(
    project_path="./games/my_game",
    sprite_name="dragon",
    sprite_config={
        "prompt": "A fierce red dragon, fantasy style",
        "size": [128, 128],
        "style": "pixel_art"  # or: cartoon, realistic, anime
    }
)
```

### Generate AI Textures

```python
from llm_router.tools.ai_art import generate_texture_ai

result = await generate_texture_ai(
    project_path="./games/my_game",
    texture_name="stone_floor",
    texture_config={
        "prompt": "Medieval stone floor texture",
        "size": [256, 256],
        "seamless": True
    }
)
```

### Generate AI Characters

```python
from llm_router.tools.ai_art import generate_character_ai

result = await generate_character_ai(
    project_path="./games/my_game",
    character_name="hero",
    character_config={
        "prompt": "Fantasy knight in golden armor",
        "animations": ["idle", "walk", "attack", "hurt"],
        "size": [64, 64]
    }
)
```

### Generate AI Music

```python
from llm_router.tools.ai_art import generate_music_ai

result = await generate_music_ai(
    project_path="./games/my_game",
    music_name="battle_theme",
    prompt="Epic orchestral battle music, fast tempo, drums and brass",
    duration=120,  # 2 minutes
    bpm=140,
    instrumental=True
)
```

---

## Tile Generation Workflow

A complete workflow for generating 2D game tiles with AI, including transparency handling, seamless tiling, and Godot resource creation.

### 1. Analyze Tile Needs

```python
from llm_router.tools.ai_art import analyze_tile_needs

# Analyze what tiles are needed for a game
manifest = analyze_tile_needs({
    "game_type": "platformer",
    "environment": "forest",
    "characters": ["player", "enemy"],
    "objects": ["coin", "heart"],
    "style": "pixel_art_32"
})

print(f"Background tiles: {manifest['background_tiles']}")
print(f"Decorations: {manifest['decoration_tiles']}")
print(f"Characters: {manifest['characters']}")
```

### 2. Generate Sprites with Alpha

```python
from llm_router.tools.ai_art import generate_sprite_with_alpha

# Generate a single sprite with clean transparency
result = await generate_sprite_with_alpha(
    project_path="./games/my_game",
    sprite_name="player_idle",
    sprite_config={
        "prompt": "fantasy knight character, front facing",
        "size": [32, 32],
        "style": "pixel_art_32",
        "remove_bg": True,  # Remove white background
        "seamless": False,
        "seed": 42
    }
)
```

### 3. Generate Complete Tileset

```python
from llm_router.tools.ai_art import generate_tileset_ai

# Generate a themed tileset
result = await generate_tileset_ai(
    project_path="./games/my_game",
    tileset_name="forest_tiles",
    tileset_config={
        "style": "pixel_art_32",
        "theme": "forest",
        "seed": 42,
        "seamless": True
    }
)

# Generated tiles are in: assets/tiles/forest_tiles/
```

### 4. Generate Animated Character

```python
from llm_router.tools.godot_assets import generate_animated_character

# Generate a complete animated character
result = await generate_animated_character(
    project_path="./games/my_game",
    character_name="hero",
    character_config={
        "prompt": "fantasy knight in golden armor",
        "animations": [
            {"name": "idle", "frame_count": 4, "speed": 5.0, "loop": True},
            {"name": "walk", "frame_count": 6, "speed": 10.0, "loop": True},
            {"name": "jump", "frame_count": 2, "speed": 8.0, "loop": False}
        ],
        "style": "pixel_art_32",
        "size": [32, 32],
        "seed": 42
    }
)

# Creates:
# - Individual sprite frames in assets/characters/hero/
# - Sprite sheet: assets/characters/hero/hero_spritesheet.png
# - Godot SpriteFrames: assets/animations/hero_frames.tres
```

### 5. Create TileSet Resource

```python
from llm_router.tools.godot_assets import create_tileset_resource

# Create a Godot TileSet resource
result = create_tileset_resource(
    project_path="./games/my_game",
    tileset_name="forest_tileset",
    tiles=[
        {"name": "grass", "texture_path": "res://assets/tiles/forest/grass.png"},
        {"name": "dirt", "texture_path": "res://assets/tiles/forest/dirt.png"},
        {"name": "stone", "texture_path": "res://assets/tiles/forest/stone.png", "shape": "rectangle"}
    ],
    tile_size=[32, 32]
)

# Use in Godot: load TileSet in TileMap node
```

### 6. Create SpriteFrames Resource

```python
from llm_router.tools.godot_assets import create_sprite_frames_resource

# Create SpriteFrames for AnimatedSprite2D
result = create_sprite_frames_resource(
    project_path="./games/my_game",
    frames_name="player",
    animations=[
        {
            "name": "idle",
            "frames": [
                "res://assets/characters/player/idle_00.png",
                "res://assets/characters/player/idle_01.png",
                "res://assets/characters/player/idle_02.png"
            ],
            "speed": 5.0,
            "loop": True
        },
        {
            "name": "walk",
            "frames": [
                "res://assets/characters/player/walk_00.png",
                "res://assets/characters/player/walk_01.png"
            ],
            "speed": 10.0,
            "loop": True
        }
    ]
)

# Use in Godot: assign to AnimatedSprite2D's frames property
```

### Available Themes

| Theme | Background Tiles | Decorations | Objects |
|-------|-----------------|-------------|----------|
| platformer | ground, grass, dirt, stone, wood_platform | bush, flower, rock, mushroom | coin, heart, star |
| dungeon | floor_stone, wall_stone, wall_brick, door, stairs | torch, chest, bones, cobweb | key, gem, potion |
| forest | grass, path, water, bridge, leaves_ground | tree, bush, flower, log, mushroom | acorn, berry, feather |
| desert | sand, sandstone, brick_adobe, cave_entrance | cactus, skull, tumbleweed, palm_tree | gem_ruby, scroll, lamp |
| ice | ice_floor, snow, ice_wall, frozen_water | icicle, snowman, pine_tree, crystal | gem_diamond, frozen_heart, snowflake |

### Available Styles

| Style | Size | Description |
|-------|------|-------------|
| pixel_art_16 | 16x16 | 16-bit pixel art, 4-8 colors, clean edges |
| pixel_art_32 | 32x32 | 32-bit pixel art, limited palette, clean edges |
| cartoon | 64x64 | Bold outlines, flat colors, game asset |
| realistic | 128x128 | Detailed, high quality texture |

---

## Debugging

### Validate Project

```python
from llm_router.tools.godot_debug import godot_validate_project

result = await godot_validate_project("./games/my_game")

print(f"Valid: {result['valid']}")
for issue in result['issues']:
    print(f"[{issue['severity']}] {issue['message']}")
    if 'fix' in issue:
        print(f"  Fix: {issue['fix']}")
```

### Run with Output Capture

```python
from llm_router.tools.godot_debug import godot_run_with_output

result = await godot_run_with_output("./games/my_game", timeout=30)

print(f"Exit code: {result['exit_code']}")
print(f"Errors: {result['error_count']}")
for error in result['errors']:
    print(f"  {error['file']}:{error['line']}: {error['message']}")
```

### Debug Scene Structure

```python
from llm_router.tools.godot_debug import godot_debug_scene

result = await godot_debug_scene("./games/my_game", "Main")

print(f"Nodes: {result['node_count']}")
for node in result['nodes']:
    print(f"  - {node['name']} ({node['type']})")
```

---

## API Reference

### Game Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/v1/games` | GET | List all games |
| `/v1/games` | POST | Create game from template |
| `/v1/games/templates` | GET | List available templates |
| `/v1/games/{id}` | GET | Get game details |
| `/v1/games/{id}/export` | POST | Export to web |
| `/v1/games/{id}/serve` | POST | Start HTTP server |
| `/v1/games/{id}/serve` | DELETE | Stop server |
| `/v1/games/{id}` | DELETE | Delete game |
| `/v1/games/{id}/validate` | GET | Validate for errors |
| `/v1/games/{id}/preview` | POST | Open in Godot editor |

### Create Game Request

```json
{
    "game_name": "MyGame",
    "game_type": "pong",
    "customizations": {
        "colors": {"player": "#ff0000"},
        "speed": 1.5
    },
    "auto_export": true,
    "auto_serve": false
}
```

### Game Response

```json
{
    "id": "my_game",
    "name": "MyGame",
    "game_type": "pong",
    "path": "./data/games/my_game",
    "status": "exported",
    "files": ["Main.gd", "Main.tscn", "project.godot"],
    "play_url": "http://localhost:8888",
    "export_path": "./data/games/my_game/export/html",
    "controls": "W/S to move paddle",
    "objective": "First to 5 points wins"
}
```

---

## Using the Game Agent

The Game Creator agent is optimized for game development:

```python
from llm_router.agent_framework import AgentRegistry, create_game_agent
from llm_router import LLMRouter

router = LLMRouter(config)
registry = AgentRegistry(router)

# Create game agent
game_agent = create_game_agent(router)

# Or register it
from llm_router.agent_framework import register_game_agent
register_game_agent(registry)

# Execute the agent
result = await registry.execute(
    "game-creator",
    "Create a Space Invaders clone with power-ups and 3 enemy types"
)
```

### Agent Capabilities

The Game Agent has access to all game creation tools:

- Project creation and configuration
- Scene building from templates or custom configs
- Script generation with proper GDScript syntax
- Asset creation (sprites, sounds, animations)
- AI art generation (requires API key)
- Debugging and validation
- Export and serving

### Best Practices

1. **Start with templates** when possible
2. **Validate early** to catch issues
3. **Export and test** frequently
4. **Use the web dashboard** for quick iterations

---

## Troubleshooting

### Common Issues

**Godot not found**
```
Error: Godot executable not found
```
Solution: Install Godot 4.x or set the path in `GODOT_PATHS`

**Export failed**
```
Error: Export timed out
```
Solution: Check Godot is installed with web export templates

**Port already in use**
```
Error: Port 8888 is already in use
```
Solution: Use a different port or stop the existing server

**PIXAZO_API_KEY not set**
```
Error: PIXAZO_API_KEY not set
```
Solution: `export PIXAZO_API_KEY=your_key_here`

---

## Examples

### Complete Game Creation Flow

```python
import asyncio
from llm_router.tools.godot_tools import (
    godot_create_from_template,
    godot_export_web,
    godot_serve_game
)
from llm_router.tools.godot_assets import godot_create_sprite, godot_create_sound

async def create_complete_game():
    # 1. Create game from template
    result = await godot_create_from_template(
        project_path="./games/my_shooter",
        template_name="shooter",
        game_name="Space Defender"
    )
    print(f"Created: {result['files_created']}")

    # 2. Add custom sprite
    await godot_create_sprite(
        project_path="./games/my_shooter",
        sprite_name="boss",
        sprite_config={
            "type": "enemy",
            "size": [128, 128],
            "color": "#ff0000"
        }
    )

    # 3. Add custom sound
    await godot_create_sound(
        project_path="./games/my_shooter",
        sound_name="boss_explosion",
        sound_config={
            "type": "explosion",
            "frequency": 80,
            "duration": 1.0
        }
    )

    # 4. Export to web
    export_result = await godot_export_web("./games/my_shooter")
    print(f"Exported to: {export_result['export_path']}")

    # 5. Serve locally
    serve_result = await godot_serve_game(
        export_result['export_path'],
        port=8888
    )
    print(f"Play at: {serve_result['url']}")

asyncio.run(create_complete_game())
```

---

## Resources

- [Godot Documentation](https://docs.godotengine.org/)
- [GDScript Reference](https://docs.godotengine.org/en/stable/tutorials/scripting/gdscript/index.html)
- [Godot Asset Library](https://godotengine.org/asset-library/)

---

*Generated by Universal Agent Platform - Game Maker Tools*
