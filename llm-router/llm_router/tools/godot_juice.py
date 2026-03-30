"""Game juice effects library for Godot - screen shake, hit flash, squash & stretch, particles.

"Juice changes everything." - Vlambeer

These tools add professional game feel to any Godot project with a single call.
Each effect is a self-contained GDScript that can be attached to any node.
"""

from pathlib import Path
from typing import Optional

from llm_router.tools import ToolDefinition, ToolRegistry


# =============================================================================
# GDScript Juice Effect Templates
# =============================================================================

CAMERA_SHAKE_SCRIPT = '''extends Camera2D
## Camera Shake - adds screen shake on demand.
## Usage: Camera2D.add_child(CameraShake.new()) or set as script on Camera2D.
## Call shake() from anywhere: get_viewport().get_camera_2d().shake()

@export var decay: float = 0.9          ## How quickly shaking stops (0-1, higher = longer)
@export var max_offset: Vector2 = Vector2(10, 8)  ## Max horizontal/vertical shake in pixels
@export var max_roll: float = 0.05      ## Max rotation in radians

var _trauma: float = 0.0
var _noise: FastNoiseLite
var _noise_y: int = 0

var _initial_offset: Vector2 = offset
var _initial_rotation: float = rotation


func _ready() -> void:
    _noise = FastNoiseLite.new()
    _noise.seed = randi()
    _noise.frequency = 2.0
    randomize()


func _process(delta: float) -> void:
    if _trauma > 0:
        _trauma = max(_trauma - decay * delta, 0)
        _shake()


func shake(amount: float = 0.5) -> void:
    """Trigger a shake. amount: 0.0 to 1.0 intensity."""
    _trauma = min(_trauma + amount, 1.0)


func _shake() -> void:
    var amount = _trauma * _trauma  # Quadratic falloff
    offset.x = _initial_offset.x + max_offset.x * amount * _get_noise(0, _noise_y)
    offset.y = _initial_offset.y + max_offset.y * amount * _get_noise(0, _noise_y + 100)
    rotation = _initial_rotation + max_roll * amount * _get_noise(0, _noise_y + 200)
    _noise_y += 1


func _get_noise(x: int, y: int) -> float:
    return _noise.get_noise_2d(x, y)
'''

HIT_FLASH_SCRIPT = '''extends CanvasItem
## Hit Flash - flashes the node white on hit for instant feedback.
## Usage: Add as child to any CanvasItem. Call flash() when hit.

@export var flash_color: Color = Color.WHITE
@export var flash_duration: float = 0.1
@export var flash_count: int = 1

var _flash_timer: float = 0.0
var _flashing: bool = false
var _original_modulate: Color
var _current_flash: int = 0


func _ready() -> void:
    _original_modulate = modulate


func _process(delta: float) -> void:
    if _flashing:
        _flash_timer -= delta
        if _flash_timer <= 0:
            _current_flash += 1
            if _current_flash >= flash_count * 2:
                _flashing = false
                modulate = _original_modulate
            else:
                modulate = flash_color if _current_flash % 2 == 0 else _original_modulate
                _flash_timer = flash_duration


func flash(count: int = -1, duration: float = -1.0) -> void:
    """Trigger a hit flash. Optionally override count and duration."""
    _flashing = true
    _current_flash = 0
    _flash_timer = 0.0
    if count > 0:
        flash_count = count
    if duration > 0:
        flash_duration = duration
    modulate = flash_color
'''

SPAWN_ANIMATION_SCRIPT = '''extends Node2D
## Spawn Animation - scale-in effect when an object appears.
## Usage: Add as child or set as script. Auto-plays on _ready().

@export var scale_from: float = 0.0
@export var scale_to: float = 1.0
@export var duration: float = 0.3
@export var ease_type: int = Tween.EASE_OUT
@export var transition_type: int = Tween.TRANS_BACK
@export var auto_play: bool = true

var _tween: Tween


func _ready() -> void:
    if auto_play:
        play()


func play() -> void:
    """Play the spawn animation."""
    if _tween:
        _tween.kill()
    scale = Vector2(scale_from, scale_from)
    _tween = create_tween()
    _tween.tween_property(self, "scale", Vector2(scale_to, scale_to), duration) \
        .set_ease(ease_type).set_trans(transition_type)


func despawn() -> void:
    """Play a reverse animation (shrink to nothing)."""
    if _tween:
        _tween.kill()
    _tween = create_tween()
    _tween.tween_property(self, "scale", Vector2.ZERO, duration * 0.5) \
        .set_ease(Tween.EASE_IN).set_trans(Tween.TRANS_BACK)
'''

SQUASH_STRETCH_SCRIPT = '''extends Node2D
## Squash & Stretch - classic animation principle for juicy movement.
## Usage: Add as child to any Node2D. Call squash() or stretch().

@export var squash_amount: float = 0.3
@export var stretch_amount: float = 0.2
@export var duration: float = 0.15
@export var return_duration: float = 0.1

var _original_scale: Vector2 = Vector2.ONE
var _tween: Tween


func _ready() -> void:
    _original_scale = scale


func squash(intensity: float = -1.0) -> void:
    """Squash (flatten) animation. Good for landing/impacts."""
    if _tween:
        _tween.kill()
    var amt = intensity if intensity > 0 else squash_amount
    var squash_scale = Vector2(_original_scale.x * (1.0 + amt), _original_scale.y * (1.0 - amt))
    _tween = create_tween()
    _tween.tween_property(self, "scale", squash_scale, duration).set_ease(Tween.EASE_OUT)
    _tween.tween_property(self, "scale", _original_scale, return_duration).set_ease(Tween.EASE_IN_OUT)


func stretch(intensity: float = -1.0) -> void:
    """Stretch (elongate) animation. Good for jumping/launching."""
    if _tween:
        _tween.kill()
    var amt = intensity if intensity > 0 else stretch_amount
    var stretch_scale = Vector2(_original_scale.x * (1.0 - amt * 0.5), _original_scale.y * (1.0 + amt))
    _tween = create_tween()
    _tween.tween_property(self, "scale", stretch_scale, duration).set_ease(Tween.EASE_OUT)
    _tween.tween_property(self, "scale", _original_scale, return_duration).set_ease(Tween.EASE_IN_OUT)


func impact(direction: Vector2 = Vector2.DOWN, intensity: float = -1.0) -> void:
    """Squash in the direction of impact."""
    if _tween:
        _tween.kill()
    var amt = intensity if intensity > 0 else squash_amount
    var squash = Vector2(
        _original_scale.x * (1.0 + amt * abs(direction.x)),
        _original_scale.y * (1.0 + amt * abs(direction.y)),
    )
    # Counter-squash the other axis
    if abs(direction.x) > abs(direction.y):
        squash.y = _original_scale.y * (1.0 - amt * 0.5)
    else:
        squash.x = _original_scale.x * (1.0 - amt * 0.5)
    _tween = create_tween()
    _tween.tween_property(self, "scale", squash, duration).set_ease(Tween.EASE_OUT)
    _tween.tween_property(self, "scale", _original_scale, return_duration).set_ease(Tween.EASE_IN_OUT)
'''

PARTICLE_TRAIL_SCRIPT = '''extends Node2D
## Particle Trail - leaves a trail of fading particles behind a moving object.
## Usage: Add as child to any moving Node2D. Auto-emits based on velocity.

@export var emit_rate: float = 30.0       ## Particles per second
@export var particle_lifetime: float = 0.5
@export var particle_size: float = 4.0
@export var particle_color: Color = Color(1, 1, 1, 0.8)
@export var spread: float = 5.0
@export var fade_speed: float = 2.0
@export var min_speed: float = 10.0       ## Min parent speed to emit

var _particles: Array = []
var _emit_timer: float = 0.0
var _prev_position: Vector2 = Vector2.ZERO


func _ready() -> void:
    _prev_position = global_position


func _process(delta: float) -> void:
    var velocity = (global_position - _prev_position) / max(delta, 0.001)
    _prev_position = global_position

    # Emit new particles
    if velocity.length() > min_speed:
        _emit_timer += delta
        var interval = 1.0 / emit_rate
        while _emit_timer >= interval:
            _emit_timer -= interval
            _spawn_particle()

    # Update existing particles
    var i = _particles.size() - 1
    while i >= 0:
        var p = _particles[i]
        p["age"] += delta
        if p["age"] >= particle_lifetime:
            _particles.remove_at(i)
            continue
        p["position"] += p["velocity"] * delta
        p["velocity"] *= 0.95
        i -= 1

    queue_redraw()


func _spawn_particle() -> void:
    _particles.append({
        "position": global_position + Vector2(randf_range(-spread, spread), randf_range(-spread, spread)),
        "velocity": Vector2(randf_range(-10, 10), randf_range(-10, 10)),
        "age": 0.0,
        "size": particle_size * randf_range(0.5, 1.0),
    })


func _draw() -> void:
    for p in _particles:
        var alpha = 1.0 - (p["age"] / particle_lifetime)
        var color = Color(particle_color.r, particle_color.g, particle_color.b, alpha * particle_color.a)
        var size = p["size"] * (1.0 - p["age"] / particle_lifetime)
        draw_circle(to_local(p["position"]), size, color)
'''

FREEZE_FRAME_SCRIPT = '''extends Node
## Freeze Frame (Hit Stop) - pauses the game for a few frames on impact.
## Usage: Call hitstop() when a hit lands for that crunchy feel.
## This is a singleton-style autoload. Add to autoloads or use directly.

var _freeze_time: float = 0.0
var _frozen: bool = false


func _ready() -> void:
    process_mode = Node.PROCESS_MODE_ALWAYS  # Always process so we can unfreeze


func _process(delta: float) -> void:
    if _frozen:
        _freeze_time -= get_process_delta_time()
        if _freeze_time <= 0:
            _frozen = false
            get_tree().paused = false


func hitstop(frames: float = 4.0) -> void:
    """Pause the game for N frames (at 60fps). E.g., 4 frames = 0.067 seconds."""
    var duration = frames / 60.0
    _freeze_time = duration
    _frozen = true
    get_tree().paused = true
'''

COLOR_FLASH_SCRIPT = '''extends CanvasItem
## Color Flash - flashes a specific color with configurable patterns.
## More flexible than HitFlash. Supports patterns: solid, pulse, rainbow.

@export var default_color: Color = Color.RED
@export var default_duration: float = 0.3
@export var pattern: String = "solid"  ## solid, pulse, rainbow

var _flash_tween: Tween
var _original_modulate: Color


func _ready() -> void:
    _original_modulate = modulate


func flash(color: Color = Color(), duration: float = -1.0) -> void:
    """Flash the node a color."""
    if color == Color():
        color = default_color
    if duration < 0:
        duration = default_duration

    if _flash_tween:
        _flash_tween.kill()

    match pattern:
        "solid":
            modulate = color
            _flash_tween = create_tween()
            _flash_tween.tween_property(self, "modulate", _original_modulate, duration)
        "pulse":
            _flash_tween = create_tween()
            _flash_tween.tween_property(self, "modulate", color, duration * 0.3)
            _flash_tween.tween_property(self, "modulate", _original_modulate, duration * 0.3)
            _flash_tween.tween_property(self, "modulate", color, duration * 0.3)
            _flash_tween.tween_property(self, "modulate", _original_modulate, duration * 0.3)
        "rainbow":
            _flash_tween = create_tween()
            _flash_tween.tween_property(self, "modulate", Color.RED, duration * 0.2)
            _flash_tween.tween_property(self, "modulate", Color.YELLOW, duration * 0.2)
            _flash_tween.tween_property(self, "modulate", Color.GREEN, duration * 0.2)
            _flash_tween.tween_property(self, "modulate", Color.CYAN, duration * 0.2)
            _flash_tween.tween_property(self, "modulate", _original_modulate, duration * 0.2)


func stop() -> void:
    """Stop any active flash."""
    if _flash_tween:
        _flash_tween.kill()
    modulate = _original_modulate
'''

# Effect name -> (filename, GDScript content, description)
JUICE_EFFECTS = {
    "camera_shake": {
        "filename": "camera_shake.gd",
        "script": CAMERA_SHAKE_SCRIPT,
        "description": "Screen shake on demand. Attach to Camera2D, call shake(intensity).",
        "target_type": "Camera2D",
    },
    "hit_flash": {
        "filename": "hit_flash.gd",
        "script": HIT_FLASH_SCRIPT,
        "description": "White flash on hit. Attach to any CanvasItem, call flash().",
        "target_type": "CanvasItem",
    },
    "spawn_animation": {
        "filename": "spawn_animation.gd",
        "script": SPAWN_ANIMATION_SCRIPT,
        "description": "Scale-in effect when objects appear. Auto-plays on ready.",
        "target_type": "Node2D",
    },
    "squash_stretch": {
        "filename": "squash_stretch.gd",
        "script": SQUASH_STRETCH_SCRIPT,
        "description": "Squash/stretch animation for movement. Call squash(), stretch(), or impact().",
        "target_type": "Node2D",
    },
    "particle_trail": {
        "filename": "particle_trail.gd",
        "script": PARTICLE_TRAIL_SCRIPT,
        "description": "Fading particle trail behind moving objects. Auto-emits based on velocity.",
        "target_type": "Node2D",
    },
    "freeze_frame": {
        "filename": "freeze_frame.gd",
        "script": FREEZE_FRAME_SCRIPT,
        "description": "Hit-stop effect. Pauses game for N frames on impact for crunchy feel.",
        "target_type": "Node",
    },
    "color_flash": {
        "filename": "color_flash.gd",
        "script": COLOR_FLASH_SCRIPT,
        "description": "Color flash with patterns (solid, pulse, rainbow). More flexible than hit_flash.",
        "target_type": "CanvasItem",
    },
}


def godot_add_juice(
    project_path: str,
    effect: str,
    target_node: str = None,
    intensity: float = 0.5,
    auto_attach: bool = True,
) -> dict:
    """
    Add a juice effect to a Godot game project.

    Available effects:
    - camera_shake: Screen shake. Attach to Camera2D, call shake(intensity).
    - hit_flash: White flash on hit. Attach to any CanvasItem.
    - spawn_animation: Scale-in on appear. Auto-plays on ready.
    - squash_stretch: Squash/stretch for movement impacts.
    - particle_trail: Fading trail behind moving objects.
    - freeze_frame: Hit-stop effect for impactful moments.
    - color_flash: Color flash with patterns (solid/pulse/rainbow).

    Args:
        project_path: Path to the Godot project
        effect: Name of the juice effect to add
        target_node: Node path to attach the effect to (e.g., "Camera2D", "Player")
        intensity: Effect intensity 0.0-1.0 (adjusts default parameters)
        auto_attach: If True, attempts to modify the scene to include the effect

    Returns:
        Dict with the effect info and script path
    """
    if effect not in JUICE_EFFECTS:
        available = ", ".join(JUICE_EFFECTS.keys())
        return {"error": f"Unknown effect '{effect}'. Available: {available}"}

    project_dir = Path(project_path)
    if not project_dir.exists():
        return {"error": f"Project directory not found: {project_path}"}

    effect_info = JUICE_EFFECTS[effect]

    # Create juice_scripts directory
    juice_dir = project_dir / "juice"
    juice_dir.mkdir(exist_ok=True)

    script_path = juice_dir / effect_info["filename"]
    script_content = effect_info["script"]

    # Adjust intensity-dependent parameters
    if effect == "camera_shake" and intensity != 0.5:
        max_offset = int(10 * intensity * 2)
        max_roll = round(0.05 * intensity * 2, 3)
        decay = round(max(0.5, 0.9 - intensity * 0.4), 2)
        script_content = script_content.replace(
            '@export var max_offset: Vector2 = Vector2(10, 8)',
            f'@export var max_offset: Vector2 = Vector2({max_offset}, {int(max_offset * 0.8)})'
        )
        script_content = script_content.replace(
            '@export var max_roll: float = 0.05',
            f'@export var max_roll: float = {max_roll}'
        )
        script_content = script_content.replace(
            '@export var decay: float = 0.9',
            f'@export var decay: float = {decay}'
        )
    elif effect == "hit_flash" and intensity != 0.5:
        duration = round(max(0.05, 0.1 * (1.0 - intensity * 0.5)), 3)
        count = max(1, int(intensity * 4))
        script_content = script_content.replace(
            '@export var flash_duration: float = 0.1',
            f'@export var flash_duration: float = {duration}'
        )
        script_content = script_content.replace(
            '@export var flash_count: int = 1',
            f'@export var flash_count: int = {count}'
        )

    script_path.write_text(script_content)

    result = {
        "success": True,
        "effect": effect,
        "description": effect_info["description"],
        "target_type": effect_info["target_type"],
        "script_path": str(script_path),
        "project_path": str(project_dir),
        "usage": {},
    }

    # Provide usage instructions based on effect type
    if effect == "camera_shake":
        result["usage"] = {
            "attach_to": "Camera2D node",
            "gdscript": f'var shaker = get_node("{target_node or "Camera2D"}")\nshaker.shake({intensity})',
            "tip": "Call shake(0.3) for light shake, shake(0.8) for heavy impacts",
        }
    elif effect == "hit_flash":
        result["usage"] = {
            "attach_to": "Any CanvasItem (Sprite2D, AnimatedSprite2D, etc.)",
            "gdscript": f'get_node("{target_node or "enemy"}").get_node("HitFlash").flash()',
            "tip": "Add as child node, call flash() in _on_hit() handler",
        }
    elif effect == "spawn_animation":
        result["usage"] = {
            "attach_to": "Any Node2D that spawns (enemies, pickups, effects)",
            "gdscript": "# Auto-plays on _ready(). Call play() to replay, despawn() for death animation",
        }
    elif effect == "squash_stretch":
        result["usage"] = {
            "attach_to": "Any Node2D that moves (player, enemies, projectiles)",
            "gdscript": f'# On jump: get_node("SquashStretch").stretch()\n# On land: get_node("SquashStretch").squash()',
        }
    elif effect == "particle_trail":
        result["usage"] = {
            "attach_to": "Any moving Node2D",
            "gdscript": "# Auto-emits when parent moves. Adjust emit_rate and min_speed in inspector",
        }
    elif effect == "freeze_frame":
        result["usage"] = {
            "attach_to": "Autoload or add to scene root",
            "gdscript": f'# On heavy hit: get_node("FreezeFrame").hitstop(6)\n# On light hit: get_node("FreezeFrame").hitstop(2)',
            "tip": "2-4 frames for light hits, 5-8 for heavy, 10+ for supers",
        }
    elif effect == "color_flash":
        result["usage"] = {
            "attach_to": "Any CanvasItem",
            "gdscript": f'get_node("{target_node or "enemy"}").get_node("ColorFlash").flash(Color.RED)',
            "tip": "Set pattern in inspector: solid, pulse, or rainbow",
        }

    return result


def godot_add_juice_pack(
    project_path: str,
    pack: str = "essentials",
) -> dict:
    """
    Add a pack of juice effects to a project.

    Packs:
    - essentials: camera_shake, hit_flash, spawn_animation (most games need these)
    - movement: squash_stretch, particle_trail, spawn_animation (for platformers)
    - combat: camera_shake, hit_flash, freeze_frame, color_flash (for action games)
    - all: every juice effect

    Args:
        project_path: Path to the Godot project
        pack: Name of the juice pack to add

    Returns:
        Dict with all added effects
    """
    packs = {
        "essentials": ["camera_shake", "hit_flash", "spawn_animation"],
        "movement": ["squash_stretch", "particle_trail", "spawn_animation"],
        "combat": ["camera_shake", "hit_flash", "freeze_frame", "color_flash"],
        "all": list(JUICE_EFFECTS.keys()),
    }

    if pack not in packs:
        return {"error": f"Unknown pack '{pack}'. Available: {', '.join(packs.keys())}"}

    effects = packs[pack]
    results = []
    for effect_name in effects:
        result = godot_add_juice(project_path, effect_name)
        results.append(result)

    return {
        "success": True,
        "pack": pack,
        "effects_added": [r["effect"] for r in results if r.get("success")],
        "results": results,
        "count": len(results),
    }


def godot_list_juice_effects() -> dict:
    """
    List all available juice effects with descriptions and usage info.

    Returns:
        Dict with all available effects
    """
    effects = {}
    for name, info in JUICE_EFFECTS.items():
        effects[name] = {
            "description": info["description"],
            "target_type": info["target_type"],
            "filename": info["filename"],
        }

    return {
        "effects": effects,
        "packs": {
            "essentials": "camera_shake, hit_flash, spawn_animation - most games need these",
            "movement": "squash_stretch, particle_trail, spawn_animation - for platformers",
            "combat": "camera_shake, hit_flash, freeze_frame, color_flash - for action games",
            "all": "Every available juice effect",
        },
        "count": len(effects),
    }


# =============================================================================
# Tool Definitions
# =============================================================================

GODOT_ADD_JUICE_DEF = ToolDefinition(
    name="godot_add_juice",
    description="Add a game juice effect to a Godot project. Effects: camera_shake, hit_flash, spawn_animation, squash_stretch, particle_trail, freeze_frame, color_flash. These add professional game feel with screen shake, flashes, animations, and particles.",
    parameters={
        "type": "object",
        "required": ["project_path", "effect"],
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "effect": {
                "type": "string",
                "description": "Effect name: camera_shake, hit_flash, spawn_animation, squash_stretch, particle_trail, freeze_frame, color_flash",
                "enum": ["camera_shake", "hit_flash", "spawn_animation", "squash_stretch", "particle_trail", "freeze_frame", "color_flash"],
            },
            "target_node": {"type": "string", "description": "Node path to attach the effect to (e.g., Camera2D, Player)"},
            "intensity": {"type": "number", "description": "Effect intensity 0.0-1.0 (default: 0.5)", "default": 0.5},
            "auto_attach": {"type": "boolean", "description": "Auto-attach to target node in scene (default: true)", "default": True},
        },
    },
    function=godot_add_juice,
    category="godot",
    examples=[
        'godot_add_juice(project_path="./games/MyGame", effect="camera_shake", intensity=0.7)',
        'godot_add_juice(project_path="./games/MyGame", effect="hit_flash", target_node="Player")',
    ],
)

GODOT_ADD_JUICE_PACK_DEF = ToolDefinition(
    name="godot_add_juice_pack",
    description="Add a pack of complementary juice effects to a Godot project. Packs: essentials (camera_shake + hit_flash + spawn), movement (squash + trail + spawn), combat (shake + flash + freeze + color), all.",
    parameters={
        "type": "object",
        "required": ["project_path"],
        "properties": {
            "project_path": {"type": "string", "description": "Path to the Godot project"},
            "pack": {
                "type": "string",
                "description": "Pack name: essentials, movement, combat, all (default: essentials)",
                "enum": ["essentials", "movement", "combat", "all"],
                "default": "essentials",
            },
        },
    },
    function=godot_add_juice_pack,
    category="godot",
    examples=[
        'godot_add_juice_pack(project_path="./games/MyGame", pack="combat")',
    ],
)

GODOT_LIST_JUICE_DEF = ToolDefinition(
    name="godot_list_juice_effects",
    description="List all available game juice effects with descriptions.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=godot_list_juice_effects,
    category="godot",
)


def register_godot_juice_tools(registry: ToolRegistry) -> None:
    """Register juice effect tools with a registry."""
    registry.register(GODOT_ADD_JUICE_DEF)
    registry.register(GODOT_ADD_JUICE_PACK_DEF)
    registry.register(GODOT_LIST_JUICE_DEF)
