"""Difficulty curve tools for Godot games.

Provides parameterized difficulty scaling so games can ramp challenge smoothly.
Generates GDScript autoloads that other scripts query for current difficulty.
"""

import math
from pathlib import Path
from typing import Optional

from llm_router.tools import ToolDefinition, ToolRegistry


# Difficulty curve functions
def _linear(level: int, start: float, ramp: float) -> float:
    return start + ramp * level

def _exponential(level: int, start: float, ramp: float) -> float:
    return start * math.pow(1 + ramp, level)

def _logarithmic(level: int, start: float, ramp: float) -> float:
    return start + ramp * math.log(level + 1)

def _step(level: int, start: float, ramp: float, step_size: int = 5) -> float:
    tier = level // step_size
    return start + ramp * tier

def _sigmoid(level: int, start: float, ramp: float, midpoint: int = 10) -> float:
    x = (level - midpoint) / max(midpoint * 0.3, 1)
    return start + ramp / (1 + math.exp(-x))


def _generate_difficulty_script(
    curve: str,
    start: float,
    ramp: float,
    max_level: int,
    parameters: dict,
) -> str:
    """Generate a GDScript difficulty manager autoload."""

    # What to scale
    enemy_speed_mult = parameters.get("enemy_speed_mult", True)
    enemy_health_mult = parameters.get("enemy_health_mult", True)
    spawn_rate_mult = parameters.get("spawn_rate_mult", True)
    enemy_damage_mult = parameters.get("enemy_damage_mult", False)
    pickup_reduction = parameters.get("pickup_reduction", True)

    # Curve-specific GDScript
    curve_funcs = {
        "linear": f"""
func _get_curve_value(level: int) -> float:
    return {start} + {ramp} * level""",
        "exponential": f"""
func _get_curve_value(level: int) -> float:
    return {start} * pow({1 + ramp}, level)""",
        "logarithmic": f"""
func _get_curve_value(level: int) -> float:
    return {start} + {ramp} * log(level + 1)""",
        "step": f"""
func _get_curve_value(level: int) -> float:
    var tier = level / {parameters.get('step_size', 5)}
    return {start} + {ramp} * tier""",
        "sigmoid": f"""
func _get_curve_value(level: int) -> float:
    var midpoint = {max_level} / 2.0
    var x = (level - midpoint) / max(midpoint * 0.3, 1.0)
    return {start} + {ramp} / (1.0 + exp(-x))""",
    }

    curve_func = curve_funcs.get(curve, curve_funcs["linear"])

    return f'''extends Node
## Difficulty Manager - Automatically scales game parameters as levels progress.
## Curve: {curve} | Start: {start} | Ramp: {ramp} | Max Level: {max_level}
##
## Usage: Query difficulty from any script:
##   var diff = DifficultyManager.get_difficulty()
##   speed *= diff.enemy_speed
##   health *= diff.enemy_health

signal difficulty_changed(level: int, difficulty: float)

var current_level: int = 0
var current_difficulty: float = {start}
var max_level: int = {max_level}
{curve_func}


func _ready() -> void:
    set_level(0)


func set_level(level: int) -> void:
    """Set the current level and recalculate difficulty."""
    current_level = clamp(level, 0, max_level)
    current_difficulty = _get_curve_value(current_level)
    difficulty_changed.emit(current_level, current_difficulty)


func advance_level() -> void:
    """Move to the next level."""
    set_level(current_level + 1)


func get_difficulty() -> Dictionary:
    """Get current difficulty multipliers."""
    var d = current_difficulty
    return {{
        "raw_value": d,
        "level": current_level,
        "progress": current_level / float(max_level) if max_level > 0 else 0.0,
{f'        "enemy_speed": 1.0 + (d - {start}) * 0.5,' if enemy_speed_mult else '        "enemy_speed": 1.0,'}
{f'        "enemy_health": 1.0 + (d - {start}) * 0.3,' if enemy_health_mult else '        "enemy_health": 1.0,'}
{f'        "spawn_rate": 1.0 + (d - {start}) * 0.4,' if spawn_rate_mult else '        "spawn_rate": 1.0,'}
{f'        "enemy_damage": 1.0 + (d - {start}) * 0.2,' if enemy_damage_mult else '        "enemy_damage": 1.0,'}
{f'        "pickup_chance": max(0.2, 1.0 - (d - {start}) * 0.3),' if pickup_reduction else '        "pickup_chance": 1.0,'}
    }}


func get_curve_points(num_points: int = 20) -> Array:
    """Get difficulty values at evenly spaced levels (for visualization)."""
    var points = []
    for i in range(num_points + 1):
        var level = int(i * max_level / float(num_points))
        points.append({{"level": level, "difficulty": _get_curve_value(level)}})
    return points
'''


def godot_set_difficulty(
    project_path: str,
    curve: str = "exponential",
    start: float = 1.0,
    ramp: float = 0.15,
    max_level: int = 20,
    step_size: int = 5,
    enemy_speed_mult: bool = True,
    enemy_health_mult: bool = True,
    spawn_rate_mult: bool = True,
    enemy_damage_mult: bool = False,
    pickup_reduction: bool = True,
) -> dict:
    """
    Add a parameterized difficulty curve to a Godot game.

    Creates a DifficultyManager autoload that other scripts can query for
    current difficulty multipliers. Call set_level(n) or advance_level() to progress.

    Curves:
    - linear: Steady increase (start + ramp * level). Good for casual games.
    - exponential: Accelerating difficulty. Good for arcade/score-attack.
    - logarithmic: Fast early, plateaus later. Good for games with skill ceilings.
    - step: Jump every N levels. Good for wave/tier-based games.
    - sigmoid: S-curve, slow start and end, fast middle. Good for story-driven games.

    Args:
        project_path: Path to the Godot project
        curve: Curve type: linear, exponential, logarithmic, step, sigmoid
        start: Starting difficulty value (default: 1.0)
        ramp: How fast difficulty increases (default: 0.15)
        max_level: Maximum level before capping (default: 20)
        step_size: Levels between difficulty jumps (for step curve, default: 5)
        enemy_speed_mult: Scale enemy speed with difficulty (default: True)
        enemy_health_mult: Scale enemy health with difficulty (default: True)
        spawn_rate_mult: Scale spawn rate with difficulty (default: True)
        enemy_damage_mult: Scale enemy damage with difficulty (default: False)
        pickup_reduction: Reduce pickup spawns at higher difficulty (default: True)

    Returns:
        Dict with the difficulty curve info
    """
    valid_curves = ["linear", "exponential", "logarithmic", "step", "sigmoid"]
    if curve not in valid_curves:
        return {"error": f"Unknown curve '{curve}'. Valid: {', '.join(valid_curves)}"}

    project_dir = Path(project_path)
    if not project_dir.exists():
        return {"error": f"Project directory not found: {project_path}"}

    parameters = {
        "enemy_speed_mult": enemy_speed_mult,
        "enemy_health_mult": enemy_health_mult,
        "spawn_rate_mult": spawn_rate_mult,
        "enemy_damage_mult": enemy_damage_mult,
        "pickup_reduction": pickup_reduction,
        "step_size": step_size,
    }

    script_content = _generate_difficulty_script(curve, start, ramp, max_level, parameters)

    # Write the script
    script_path = project_dir / "difficulty_manager.gd"
    script_path.write_text(script_content)

    # Generate preview points
    curve_func = {
        "linear": lambda l: _linear(l, start, ramp),
        "exponential": lambda l: _exponential(l, start, ramp),
        "logarithmic": lambda l: _logarithmic(l, start, ramp),
        "step": lambda l: _step(l, start, ramp, step_size),
        "sigmoid": lambda l: _sigmoid(l, start, ramp, max_level // 2),
    }[curve]

    preview_points = []
    for i in range(0, min(max_level + 1, 11)):
        level = int(i * max_level / 10)
        preview_points.append({"level": level, "difficulty": round(curve_func(level), 3)})

    # Update project.godot to add autoload
    project_godot = project_dir / "project.godot"
    autoload_registered = False
    if project_godot.exists():
        content = project_godot.read_text()
        if "DifficultyManager" not in content:
            # Add autoload section
            if "[autoload]" not in content:
                content += '\n\n[autoload]\n\nDifficultyManager="*res://difficulty_manager.gd"\n'
            else:
                content = content.replace(
                    "[autoload]",
                    '[autoload]\n\nDifficultyManager="*res://difficulty_manager.gd"'
                )
            project_godot.write_text(content)
            autoload_registered = True

    return {
        "success": True,
        "curve": curve,
        "start": start,
        "ramp": ramp,
        "max_level": max_level,
        "script_path": str(script_path),
        "autoload_registered": autoload_registered,
        "preview": preview_points,
        "usage": {
            "query": "var diff = DifficultyManager.get_difficulty()",
            "advance": "DifficultyManager.advance_level()",
            "set": "DifficultyManager.set_level(5)",
            "example": "enemy.speed = base_speed * DifficultyManager.get_difficulty().enemy_speed",
        },
    }


def godot_preview_difficulty(
    curve: str = "exponential",
    start: float = 1.0,
    ramp: float = 0.15,
    max_level: int = 20,
    step_size: int = 5,
) -> dict:
    """
    Preview a difficulty curve without modifying any project files.

    Returns data points for all curve types so you can compare and choose.

    Args:
        curve: Curve type to preview (or 'all' for comparison)
        start: Starting difficulty value
        ramp: How fast difficulty increases
        max_level: Maximum level
        step_size: Step size for step curve

    Returns:
        Dict with difficulty values at each level
    """
    curves = {
        "linear": lambda l: _linear(l, start, ramp),
        "exponential": lambda l: _exponential(l, start, ramp),
        "logarithmic": lambda l: _logarithmic(l, start, ramp),
        "step": lambda l: _step(l, start, ramp, step_size),
        "sigmoid": lambda l: _sigmoid(l, start, ramp, max_level // 2),
    }

    if curve == "all":
        # Compare all curves
        points = {}
        for name, func in curves.items():
            values = []
            for i in range(min(max_level + 1, 21)):
                values.append({"level": i, "difficulty": round(func(i), 3)})
            points[name] = values
        return {"curves": points, "parameters": {"start": start, "ramp": ramp, "max_level": max_level}}

    if curve not in curves:
        return {"error": f"Unknown curve '{curve}'. Valid: {', '.join(curves.keys())}, 'all'"}

    func = curves[curve]
    points = []
    for i in range(min(max_level + 1, 21)):
        points.append({"level": i, "difficulty": round(func(i), 3)})

    return {
        "curve": curve,
        "parameters": {"start": start, "ramp": ramp, "max_level": max_level},
        "points": points,
        "range": {"min": round(func(0), 3), "max": round(func(max_level), 3)},
        "recommendations": {
            "linear": "Casual games, puzzles, games for younger audiences",
            "exponential": "Arcade games, score-attack, roguelikes",
            "logarithmic": "Games with skill ceilings, RPGs",
            "step": "Wave-based games, tier/arena games",
            "sigmoid": "Story-driven games, tutorial-heavy games",
        },
    }


# =============================================================================
# Tool Definitions
# =============================================================================

GODOT_SET_DIFFICULTY_DEF = ToolDefinition(
    name="godot_set_difficulty",
    description="Add a parameterized difficulty curve to a Godot game. Creates a DifficultyManager autoload that scales enemy speed, health, spawn rate, and more as levels progress. Curves: linear, exponential, logarithmic, step, sigmoid.",
    parameters={
        "type": "object",
        "required": ["project_path"],
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "curve": {
                "type": "string",
                "description": "Curve type: linear, exponential, logarithmic, step, sigmoid",
                "enum": ["linear", "exponential", "logarithmic", "step", "sigmoid"],
                "default": "exponential",
            },
            "start": {"type": "number", "description": "Starting difficulty value (default: 1.0)", "default": 1.0},
            "ramp": {"type": "number", "description": "How fast difficulty increases (default: 0.15)", "default": 0.15},
            "max_level": {"type": "integer", "description": "Maximum level before capping (default: 20)", "default": 20},
            "step_size": {"type": "integer", "description": "Levels between jumps for step curve (default: 5)", "default": 5},
            "enemy_speed_mult": {"type": "boolean", "description": "Scale enemy speed (default: true)", "default": True},
            "enemy_health_mult": {"type": "boolean", "description": "Scale enemy health (default: true)", "default": True},
            "spawn_rate_mult": {"type": "boolean", "description": "Scale spawn rate (default: true)", "default": True},
            "enemy_damage_mult": {"type": "boolean", "description": "Scale enemy damage (default: false)", "default": False},
            "pickup_reduction": {"type": "boolean", "description": "Reduce pickups at higher difficulty (default: true)", "default": True},
        },
    },
    function=godot_set_difficulty,
    category="godot",
    examples=[
        'godot_set_difficulty(project_path="./games/MyGame", curve="exponential", ramp=0.2)',
        'godot_set_difficulty(project_path="./games/MyGame", curve="step", step_size=5, max_level=30)',
    ],
)

GODOT_PREVIEW_DIFFICULTY_DEF = ToolDefinition(
    name="godot_preview_difficulty",
    description="Preview difficulty curve values without modifying any files. Pass curve='all' to compare all curves side by side.",
    parameters={
        "type": "object",
        "properties": {
            "curve": {
                "type": "string",
                "description": "Curve type or 'all' for comparison (default: all)",
                "default": "all",
            },
            "start": {"type": "number", "description": "Starting difficulty (default: 1.0)", "default": 1.0},
            "ramp": {"type": "number", "description": "Ramp rate (default: 0.15)", "default": 0.15},
            "max_level": {"type": "integer", "description": "Max level (default: 20)", "default": 20},
            "step_size": {"type": "integer", "description": "Step size for step curve (default: 5)", "default": 5},
        },
    },
    function=godot_preview_difficulty,
    category="godot",
)


def register_godot_difficulty_tools(registry: ToolRegistry) -> None:
    """Register difficulty curve tools with a registry."""
    registry.register(GODOT_SET_DIFFICULTY_DEF)
    registry.register(GODOT_PREVIEW_DIFFICULTY_DEF)
