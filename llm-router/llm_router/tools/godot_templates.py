"""Complete game templates for Godot game creation."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class GameTemplate:
    """Complete game template definition."""
    name: str
    game_type: str
    description: str
    difficulty: str = "medium"

    # Scene configuration for scene builder
    scene_config: dict = field(default_factory=dict)

    # Scripts (filename -> content)
    scripts: dict = field(default_factory=dict)

    # Input mappings
    input_mappings: dict = field(default_factory=dict)

    # Project settings overrides
    project_settings: dict = field(default_factory=dict)

    # Game info
    controls: str = ""
    objective: str = ""


# =============================================================================
# PONG TEMPLATE - Classic two-player pong game
# =============================================================================

PONG_TEMPLATE = GameTemplate(
    name="Pong",
    game_type="pong",
    description="Classic two-player pong game - first to 5 points wins",
    difficulty="easy",
    controls="W/S to move left paddle, Up/Down for right paddle",
    objective="Score 5 points to win",
    input_mappings={
        "p1_up": ["W"],
        "p1_down": ["S"],
        "p2_up": ["UP"],
        "p2_down": ["DOWN"],
    },
    scene_config={
        "root_type": "Node2D",
        "root_script": "Main.gd",
        "nodes": [
            {
                "name": "Player1",
                "type": "CharacterBody2D",
                "script": "Paddle.gd",
                "position": [50, 300],
                "properties": {"paddle_speed": 500, "is_player1": True},
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [20, 80]},
                    {"type": "ColorRect", "rect": [-10, -40, 20, 80], "properties": {"color": "#4488ff"}}
                ]
            },
            {
                "name": "Player2",
                "type": "CharacterBody2D",
                "script": "Paddle.gd",
                "position": [590, 300],
                "properties": {"paddle_speed": 500, "is_player1": False},
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [20, 80]},
                    {"type": "ColorRect", "rect": [-10, -40, 20, 80], "properties": {"color": "#ff4444"}}
                ]
            },
            {
                "name": "Ball",
                "type": "CharacterBody2D",
                "script": "Ball.gd",
                "position": [320, 240],
                "children": [
                    {"type": "CollisionShape2D", "shape": "CircleShape2D", "radius": 10},
                    {"type": "ColorRect", "rect": [-10, -10, 20, 20], "properties": {"color": "#ffffff"}}
                ]
            },
            {
                "name": "TopWall",
                "type": "StaticBody2D",
                "position": [320, 0],
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [640, 20]},
                    {"type": "ColorRect", "rect": [-320, 0, 640, 20], "properties": {"color": "#333333"}}
                ]
            },
            {
                "name": "BottomWall",
                "type": "StaticBody2D",
                "position": [320, 480],
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [640, 20]},
                    {"type": "ColorRect", "rect": [-320, -20, 640, 20], "properties": {"color": "#333333"}}
                ]
            },
            {
                "name": "LeftGoal",
                "type": "Area2D",
                "position": [0, 240],
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [20, 480]}
                ]
            },
            {
                "name": "RightGoal",
                "type": "Area2D",
                "position": [640, 240],
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [20, 480]}
                ]
            },
            {
                "name": "CenterLine",
                "type": "ColorRect",
                "position": [318, 0],
                "properties": {"color": "#444444"},
                "children": []
            }
        ],
        "ui": {
            "labels": [
                {"name": "Player1Score", "text": "0", "position": [160, 40], "font_size": 48},
                {"name": "Player2Score", "text": "0", "position": [480, 40], "font_size": 48},
                {"name": "WinLabel", "text": "Player 1 Wins!", "position": [200, 200], "font_size": 32}
            ]
        },
        "connections": [
            {"from": "LeftGoal", "signal": "body_entered", "to": ".", "method": "on_left_goal"},
            {"from": "RightGoal", "signal": "body_entered", "to": ".", "method": "on_right_goal"}
        ]
    },
    scripts={
        "Main.gd": '''extends Node2D

# Pong - Classic two-player pong game
# First to 5 points wins

@onready var ball: CharacterBody2D = $Ball
@onready var p1_score_label: Label = $UI/Player1Score
@onready var p2_score_label: Label = $UI/Player2Score
@onready var win_label: Label = $UI/WinLabel

var player1_score: int = 0
var player2_score: int = 0
const WIN_SCORE: int = 5
var game_over: bool = false

func _ready() -> void:
    win_label.visible = false
    reset_ball()

func reset_ball() -> void:
    ball.position = Vector2(320, 240)
    var direction: float = 1.0 if randf() > 0.5 else -1.0
    var angle: float = randf_range(-0.3, 0.3)
    ball.velocity = Vector2(direction * 300, sin(angle) * 300)

func on_left_goal(body: Node2D) -> void:
    if game_over:
        return
    if body == ball:
        player2_score += 1
        p2_score_label.text = str(player2_score)
        check_win()
        if not game_over:
            reset_ball()

func on_right_goal(body: Node2D) -> void:
    if game_over:
        return
    if body == ball:
        player1_score += 1
        p1_score_label.text = str(player1_score)
        check_win()
        if not game_over:
            reset_ball()

func check_win() -> void:
    if player1_score >= WIN_SCORE:
        game_over = true
        win_label.text = "Player 1 Wins!"
        win_label.visible = true
    elif player2_score >= WIN_SCORE:
        game_over = true
        win_label.text = "Player 2 Wins!"
        win_label.visible = true

func _input(event: InputEvent) -> void:
    if game_over and event.is_action_pressed("ui_accept"):
        restart_game()

func restart_game() -> void:
    player1_score = 0
    player2_score = 0
    game_over = false
    p1_score_label.text = "0"
    p2_score_label.text = "0"
    win_label.visible = false
    reset_ball()
''',

        "Paddle.gd": '''extends CharacterBody2D

# Paddle controller for both players

@export var paddle_speed: float = 500.0
@export var is_player1: bool = true

const TOP_LIMIT: float = 60.0
const BOTTOM_LIMIT: float = 460.0

func _physics_process(_delta: float) -> void:
    var direction: float = 0.0

    if is_player1:
        if Input.is_action_pressed("p1_up"):
            direction = -1.0
        elif Input.is_action_pressed("p1_down"):
            direction = 1.0
    else:
        if Input.is_action_pressed("p2_up"):
            direction = -1.0
        elif Input.is_action_pressed("p2_down"):
            direction = 1.0

    velocity.y = direction * paddle_speed
    move_and_slide()

    # Clamp position
    position.y = clamp(position.y, TOP_LIMIT, BOTTOM_LIMIT)
''',

        "Ball.gd": '''extends CharacterBody2D

# Ball physics for Pong

const SPEED_INCREMENT: float = 10.0
const MAX_SPEED: float = 800.0

func _physics_process(delta: float) -> void:
    var collision: KinematicCollision2D = move_and_collide(velocity * delta)

    if collision:
        var normal: Vector2 = collision.get_normal()
        velocity = velocity.bounce(normal)

        # Speed up on paddle hit
        var collider: Node = collision.get_collider()
        if collider and (collider.name == "Player1" or collider.name == "Player2"):
            var speed: float = velocity.length()
            speed = min(speed + SPEED_INCREMENT, MAX_SPEED)
            velocity = velocity.normalized() * speed

            # Add some angle based on where ball hit paddle
            var paddle_pos: float = collider.position.y
            var hit_offset: float = (position.y - paddle_pos) / 40.0
            velocity.y += hit_offset * 100

            # Keep speed consistent
            velocity = velocity.normalized() * speed
'''
    },
    project_settings={
        "display/window/size/viewport_width": 640,
        "display/window/size/viewport_height": 480,
    }
)


# =============================================================================
# SPACE INVADERS TEMPLATE
# =============================================================================

SPACE_INVADERS_TEMPLATE = GameTemplate(
    name="Space Invaders",
    game_type="space_invaders",
    description="Classic space invaders - destroy all aliens before they reach you",
    difficulty="medium",
    controls="A/D or Left/Right to move, Space to shoot",
    objective="Destroy all aliens, avoid their bombs",
    input_mappings={
        "move_left": ["A", "LEFT"],
        "move_right": ["D", "RIGHT"],
        "shoot": ["SPACE"],
    },
    scene_config={
        "root_type": "Node2D",
        "root_script": "Main.gd",
        "nodes": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "script": "Player.gd",
                "position": [320, 440],
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [40, 20]},
                    {"type": "ColorRect", "rect": [-20, -10, 40, 20], "properties": {"color": "#44ff44"}}
                ]
            },
            {
                "name": "Aliens",
                "type": "Node2D",
                "script": "AlienSwarm.gd",
                "children": []
            },
            {
                "name": "Bullets",
                "type": "Node2D",
                "children": []
            },
            {
                "name": "AlienBombs",
                "type": "Node2D",
                "children": []
            },
            {
                "name": "ShootCooldown",
                "type": "Timer",
                "properties": {"wait_time": 0.3, "one_shot": True}
            }
        ],
        "ui": {
            "labels": [
                {"name": "ScoreLabel", "text": "Score: 0", "position": [20, 20]},
                {"name": "LivesLabel", "text": "Lives: 3", "position": [520, 20]},
                {"name": "GameOverLabel", "text": "GAME OVER\\nPress Space to restart", "position": [220, 200]}
            ]
        }
    },
    scripts={
        "Main.gd": '''extends Node2D

# Space Invaders - Destroy all aliens!

@onready var player: CharacterBody2D = $Player
@onready var aliens: Node2D = $Aliens
@onready var bullets: Node2D = $Bullets
@onready var alien_bombs: Node2D = $AlienBombs
@onready var shoot_cooldown: Timer = $ShootCooldown
@onready var score_label: Label = $UI/ScoreLabel
@onready var lives_label: Label = $UI/LivesLabel
@onready var game_over_label: Label = $UI/GameOverLabel

var score: int = 0
var lives: int = 3
var game_over: bool = false
var can_shoot: bool = true

const ALIEN_SCENE: PackedScene = preload("res://Alien.tscn")
const BULLET_SCENE: PackedScene = preload("res://Bullet.tscn")
const BOMB_SCENE: PackedScene = preload("res://AlienBomb.tscn")

func _ready() -> void:
    game_over_label.visible = false
    spawn_aliens()

func spawn_aliens() -> void:
    for row in range(5):
        for col in range(10):
            var alien: Node2D = ALIEN_SCENE.instantiate()
            alien.position = Vector2(80 + col * 50, 60 + row * 40)
            alien.points = 10 + (4 - row) * 5  # Higher rows worth more
            aliens.add_child(alien)

func _process(_delta: float) -> void:
    if game_over:
        if Input.is_action_just_pressed("shoot"):
            restart_game()
        return

    # Check win condition
    if aliens.get_child_count() == 0:
        game_over = true
        game_over_label.text = "YOU WIN!\\nPress Space to restart"
        game_over_label.visible = true

func shoot_bullet(pos: Vector2) -> void:
    if not can_shoot or game_over:
        return
    var bullet: Node2D = BULLET_SCENE.instantiate()
    bullet.position = pos
    bullets.add_child(bullet)
    can_shoot = false
    shoot_cooldown.start()

func _on_shoot_cooldown_timeout() -> void:
    can_shoot = true

func add_score(points: int) -> void:
    score += points
    score_label.text = "Score: %d" % score

func player_hit() -> void:
    lives -= 1
    lives_label.text = "Lives: %d" % lives
    if lives <= 0:
        game_over = true
        game_over_label.visible = true

func restart_game() -> void:
    # Clear everything
    for child in aliens.get_children():
        child.queue_free()
    for child in bullets.get_children():
        child.queue_free()
    for child in alien_bombs.get_children():
        child.queue_free()

    score = 0
    lives = 3
    game_over = false
    score_label.text = "Score: 0"
    lives_label.text = "Lives: 3"
    game_over_label.visible = false
    player.position = Vector2(320, 440)

    spawn_aliens()
''',

        "Player.gd": '''extends CharacterBody2D

# Player ship controller

const SPEED: float = 300.0
const LEFT_LIMIT: float = 20.0
const RIGHT_LIMIT: float = 620.0

signal shoot(pos: Vector2)

func _physics_process(_delta: float) -> void:
    var direction: float = Input.get_axis("move_left", "move_right")
    velocity.x = direction * SPEED
    move_and_slide()
    position.x = clamp(position.x, LEFT_LIMIT, RIGHT_LIMIT)

    if Input.is_action_just_pressed("shoot"):
        shoot.emit(position - Vector2(0, 15))
''',

        "AlienSwarm.gd": '''extends Node2D

# Controls the alien swarm movement

var direction: float = 1.0
var speed: float = 50.0
var drop_amount: float = 20.0

func _process(delta: float) -> void:
    var should_drop: bool = false
    var left_most: float = 1000.0
    var right_most: float = 0.0

    for alien in get_children():
        if alien.position.x < left_most:
            left_most = alien.position.x
        if alien.position.x > right_most:
            right_most = alien.position.x

    # Check if we need to drop and reverse
    if right_most > 600 and direction > 0:
        should_drop = true
        direction = -1.0
    elif left_most < 40 and direction < 0:
        should_drop = true
        direction = 1.0

    # Move all aliens
    for alien in get_children():
        if should_drop:
            alien.position.y += drop_amount
        alien.position.x += direction * speed * delta

        # Random bomb drop
        if randf() < 0.001:
            var main: Node = get_tree().current_scene
            if main.has_method("spawn_bomb"):
                main.spawn_bomb(alien.position)
''',

        "Alien.gd": '''extends Area2D

# Individual alien

@export var points: int = 10

signal destroyed(points: int)

func _ready() -> void:
    # Create visual representation
    var rect: ColorRect = ColorRect.new()
    rect.color = Color("#ff8844")
    rect.position = Vector2(-15, -10)
    rect.size = Vector2(30, 20)
    add_child(rect)

    # Add collision
    var collision: CollisionShape2D = CollisionShape2D.new()
    var shape: RectangleShape2D = RectangleShape2D.new()
    shape.size = Vector2(30, 20)
    collision.shape = shape
    add_child(collision)

func _on_body_entered(body: Node2D) -> void:
    if body.is_in_group("bullets"):
        body.queue_free()
        destroyed.emit(points)
        queue_free()
''',

        "Bullet.gd": '''extends Area2D

# Player bullet

const SPEED: float = 500.0

func _ready() -> void:
    add_to_group("bullets")
    # Create visual
    var rect: ColorRect = ColorRect.new()
    rect.color = Color("#ffff44")
    rect.position = Vector2(-2, -8)
    rect.size = Vector2(4, 16)
    add_child(rect)

    # Add collision
    var collision: CollisionShape2D = CollisionShape2D.new()
    var shape: RectangleShape2D = RectangleShape2D.new()
    shape.size = Vector2(4, 16)
    collision.shape = shape
    add_child(collision)

func _process(delta: float) -> void:
    position.y -= SPEED * delta
    if position.y < -20:
        queue_free()
''',

        "AlienBomb.gd": '''extends Area2D

# Alien bomb

const SPEED: float = 200.0

func _ready() -> void:
    add_to_group("bombs")
    var rect: ColorRect = ColorRect.new()
    rect.color = Color("#ff4444")
    rect.position = Vector2(-3, -6)
    rect.size = Vector2(6, 12)
    add_child(rect)

    var collision: CollisionShape2D = CollisionShape2D.new()
    var shape: RectangleShape2D = RectangleShape2D.new()
    shape.size = Vector2(6, 12)
    collision.shape = shape
    add_child(collision)

func _process(delta: float) -> void:
    position.y += SPEED * delta
    if position.y > 500:
        queue_free()
'''
    },
    project_settings={
        "display/window/size/viewport_width": 640,
        "display/window/size/viewport_height": 480,
    }
)


# =============================================================================
# PLATFORMER TEMPLATE
# =============================================================================

PLATFORMER_TEMPLATE = GameTemplate(
    name="Platformer",
    game_type="platformer",
    description="Jump and run platformer - collect coins, avoid spikes",
    difficulty="medium",
    controls="A/D or Left/Right to move, W/Space/Up to jump",
    objective="Collect all coins and reach the goal",
    input_mappings={
        "move_left": ["A", "LEFT"],
        "move_right": ["D", "RIGHT"],
        "jump": ["W", "SPACE", "UP"],
    },
    scene_config={
        "root_type": "Node2D",
        "root_script": "Main.gd",
        "nodes": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "script": "Player.gd",
                "position": [100, 300],
                "children": [
                    {"type": "CollisionShape2D", "shape": "RectangleShape2D", "size": [30, 40]},
                    {"type": "ColorRect", "rect": [-15, -20, 30, 40], "properties": {"color": "#4488ff"}}
                ]
            },
            {
                "name": "Level",
                "type": "TileMap",
                "children": []
            },
            {
                "name": "Coins",
                "type": "Node2D",
                "children": []
            },
            {
                "name": "Camera2D",
                "type": "Camera2D",
                "position": [320, 240],
                "properties": {"zoom": [1, 1], "limit_left": 0, "limit_top": 0}
            }
        ],
        "ui": {
            "labels": [
                {"name": "CoinLabel", "text": "Coins: 0", "position": [20, 20]},
                {"name": "LivesLabel", "text": "Lives: 3", "position": [520, 20]}
            ]
        }
    },
    scripts={
        "Main.gd": '''extends Node2D

# Platformer - Collect coins, avoid hazards!

@onready var player: CharacterBody2D = $Player
@onready var coin_label: Label = $UI/CoinLabel
@onready var lives_label: Label = $UI/LivesLabel

var coins: int = 0
var lives: int = 3
var spawn_point: Vector2 = Vector2(100, 300)

const COIN_SCENE: PackedScene = preload("res://Coin.tscn")

func _ready() -> void:
    spawn_coins()

func spawn_coins() -> void:
    var coin_positions: Array[Vector2] = [
        Vector2(200, 200), Vector2(300, 200), Vector2(400, 150),
        Vector2(500, 250), Vector2(600, 100), Vector2(150, 350)
    ]

    for pos in coin_positions:
        var coin: Node2D = COIN_SCENE.instantiate()
        coin.position = pos
        $Coins.add_child(coin)

func collect_coin() -> void:
    coins += 1
    coin_label.text = "Coins: %d" % coins

func player_died() -> void:
    lives -= 1
    lives_label.text = "Lives: %d" % lives
    if lives > 0:
        player.position = spawn_point
    else:
        # Game over
        lives = 3
        coins = 0
        lives_label.text = "Lives: 3"
        coin_label.text = "Coins: 0"
        player.position = spawn_point
        # Respawn coins
        for coin in $Coins.get_children():
            coin.queue_free()
        spawn_coins()
''',

        "Player.gd": '''extends CharacterBody2D

# Player character with jump and run

const SPEED: float = 200.0
const JUMP_FORCE: float = 400.0
const GRAVITY: float = 1000.0

var velocity_y: float = 0.0

func _physics_process(delta: float) -> void:
    # Horizontal movement
    var direction: float = Input.get_axis("move_left", "move_right")
    velocity.x = direction * SPEED

    # Gravity
    if not is_on_floor():
        velocity_y += GRAVITY * delta
    else:
        velocity_y = 0

    # Jump
    if Input.is_action_just_pressed("jump") and is_on_floor():
        velocity_y = -JUMP_FORCE

    velocity.y = velocity_y
    move_and_slide()

func _on_area_entered(area: Area2D) -> void:
    if area.is_in_group("coins"):
        var main: Node = get_tree().current_scene
        if main.has_method("collect_coin"):
            main.collect_coin()
        area.queue_free()
    elif area.is_in_group("hazards"):
        var main: Node = get_tree().current_scene
        if main.has_method("player_died"):
            main.player_died()
''',

        "Coin.gd": '''extends Area2D

# Collectible coin

func _ready() -> void:
    add_to_group("coins")
    # Visual
    var circle: Node2D = Node2D.new()
    # Simple coin as yellow circle using ColorRect approximation
    var rect: ColorRect = ColorRect.new()
    rect.color = Color("#ffdd00")
    rect.position = Vector2(-10, -10)
    rect.size = Vector2(20, 20)
    add_child(rect)

    # Collision
    var collision: CollisionShape2D = CollisionShape2D.new()
    var shape: CircleShape2D = CircleShape2D.new()
    shape.radius = 10
    collision.shape = shape
    add_child(collision)
'''
    },
    project_settings={
        "display/window/size/viewport_width": 640,
        "display/window/size/viewport_height": 480,
    }
)


# =============================================================================
# SHOOTER TEMPLATE (Top-down)
# =============================================================================

SHOOTER_TEMPLATE = GameTemplate(
    name="Top-Down Shooter",
    game_type="shooter",
    description="Top-down shooter - survive waves of enemies",
    difficulty="hard",
    controls="WASD to move, Mouse to aim, Click to shoot",
    objective="Survive as long as possible, defeat enemies",
    input_mappings={
        "move_up": ["W"],
        "move_down": ["S"],
        "move_left": ["A"],
        "move_right": ["D"],
        "shoot": ["SPACE"],
    },
    scene_config={
        "root_type": "Node2D",
        "root_script": "Main.gd",
        "nodes": [
            {
                "name": "Player",
                "type": "CharacterBody2D",
                "script": "Player.gd",
                "position": [320, 240],
                "children": [
                    {"type": "CollisionShape2D", "shape": "CircleShape2D", "radius": 15},
                    {"type": "ColorRect", "rect": [-15, -15, 30, 30], "properties": {"color": "#44ff44"}}
                ]
            },
            {
                "name": "Enemies",
                "type": "Node2D",
                "children": []
            },
            {
                "name": "Bullets",
                "type": "Node2D",
                "children": []
            },
            {
                "name": "SpawnTimer",
                "type": "Timer",
                "properties": {"wait_time": 2.0, "autostart": True}
            },
            {
                "name": "Camera2D",
                "type": "Camera2D",
                "position": [320, 240]
            }
        ],
        "ui": {
            "labels": [
                {"name": "ScoreLabel", "text": "Score: 0", "position": [20, 20]},
                {"name": "HealthLabel", "text": "Health: 100", "position": [20, 50]},
                {"name": "WaveLabel", "text": "Wave: 1", "position": [520, 20]}
            ]
        },
        "connections": [
            {"from": "SpawnTimer", "signal": "timeout", "to": ".", "method": "spawn_enemy"}
        ]
    },
    scripts={
        "Main.gd": '''extends Node2D

# Top-Down Shooter - Survive the waves!

@onready var player: CharacterBody2D = $Player
@onready var spawn_timer: Timer = $SpawnTimer

var score: int = 0
var wave: int = 1
var enemies_killed: int = 0
var enemies_per_wave: int = 5

const ENEMY_SCENE: PackedScene = preload("res://Enemy.tscn")
const BULLET_SCENE: PackedScene = preload("res://Bullet.tscn")

func _ready() -> void:
    pass

func spawn_enemy() -> void:
    var enemy: Node2D = ENEMY_SCENE.instantiate()
    # Spawn at random edge
    var side: int = randi() % 4
    match side:
        0: enemy.position = Vector2(randf_range(0, 640), 0)
        1: enemy.position = Vector2(640, randf_range(0, 480))
        2: enemy.position = Vector2(randf_range(0, 640), 480)
        3: enemy.position = Vector2(0, randf_range(0, 480))

    enemy.speed = 50 + wave * 10
    $Enemies.add_child(enemy)

func add_score(points: int) -> void:
    score += points
    enemies_killed += 1
    $UI/ScoreLabel.text = "Score: %d" % score

    # Check for wave completion
    if enemies_killed >= enemies_per_wave:
        wave += 1
        enemies_killed = 0
        enemies_per_wave += 2
        spawn_timer.wait_time = max(0.5, spawn_timer.wait_time - 0.1)
        $UI/WaveLabel.text = "Wave: %d" % wave

func spawn_bullet(pos: Vector2, dir: Vector2) -> void:
    var bullet: Node2D = BULLET_SCENE.instantiate()
    bullet.position = pos
    bullet.direction = dir.normalized()
    $Bullets.add_child(bullet)

func player_hit(damage: int) -> void:
    player.health -= damage
    $UI/HealthLabel.text = "Health: %d" % player.health
    if player.health <= 0:
        game_over()

func game_over() -> void:
    get_tree().reload_current_scene()
''',

        "Player.gd": '''extends CharacterBody2D

# Player controller

const SPEED: float = 200.0
var health: int = 100

func _physics_process(_delta: float) -> void:
    var input_dir: Vector2 = Input.get_vector("move_left", "move_right", "move_up", "move_down")
    velocity = input_dir * SPEED
    move_and_slide()

    # Shoot with space
    if Input.is_action_just_pressed("shoot"):
        var main: Node = get_tree().current_scene
        if main.has_method("spawn_bullet"):
            main.spawn_bullet(position, get_global_mouse_position() - position)
''',

        "Enemy.gd": '''extends CharacterBody2D

# Enemy that chases player

@export var speed: float = 60.0
@export var damage: int = 10
@export var points: int = 100

func _physics_process(delta: float) -> void:
    var player: Node2D = get_tree().current_scene.get_node_or_null("Player")
    if not player:
        return

    var direction: Vector2 = (player.position - position).normalized()
    velocity = direction * speed
    move_and_slide()

func _on_area_entered(area: Area2D) -> void:
    if area.is_in_group("bullets"):
        var main: Node = get_tree().current_scene
        if main.has_method("add_score"):
            main.add_score(points)
        area.queue_free()
        queue_free()

func _on_body_entered(body: Node2D) -> void:
    if body.name == "Player":
        var main: Node = get_tree().current_scene
        if main.has_method("player_hit"):
            main.player_hit(damage)
        queue_free()
''',

        "Bullet.gd": '''extends Area2D

# Player bullet

@export var speed: float = 500.0
var direction: Vector2 = Vector2.RIGHT

func _ready() -> void:
    add_to_group("bullets")
    var rect: ColorRect = ColorRect.new()
    rect.color = Color("#ffff00")
    rect.position = Vector2(-4, -2)
    rect.size = Vector2(8, 4)
    add_child(rect)

    var collision: CollisionShape2D = CollisionShape2D.new()
    var shape: CircleShape2D = CircleShape2D.new()
    shape.radius = 4
    collision.shape = shape
    add_child(collision)

func _process(delta: float) -> void:
    position += direction * speed * delta
    if position.x < -50 or position.x > 690 or position.y < -50 or position.y > 530:
        queue_free()
'''
    },
    project_settings={
        "display/window/size/viewport_width": 640,
        "display/window/size/viewport_height": 480,
    }
)


# =============================================================================
# PUZZLE TEMPLATE (Match-3 style)
# =============================================================================

PUZZLE_TEMPLATE = GameTemplate(
    name="Puzzle Match",
    game_type="puzzle",
    description="Match-3 puzzle game - swap tiles to match colors",
    difficulty="easy",
    controls="Click to select tile, click adjacent tile to swap",
    objective="Match 3 or more same-colored tiles to score",
    input_mappings={
        "select": ["SPACE", "ENTER"],
    },
    scene_config={
        "root_type": "Node2D",
        "root_script": "Main.gd",
        "nodes": [
            {
                "name": "Grid",
                "type": "Node2D",
                "script": "Grid.gd",
                "position": [120, 60],
                "children": []
            }
        ],
        "ui": {
            "labels": [
                {"name": "ScoreLabel", "text": "Score: 0", "position": [20, 20]},
                {"name": "MovesLabel", "text": "Moves: 30", "position": [20, 50]}
            ]
        }
    },
    scripts={
        "Main.gd": '''extends Node2D

# Match-3 Puzzle Game

@onready var grid: Node2D = $Grid

var score: int = 0
var moves: int = 30

const GRID_SIZE: int = 8
const TILE_SIZE: int = 50
const COLORS: Array[Color] = [
    Color("#ff4444"), Color("#44ff44"), Color("#4444ff"),
    Color("#ffff44"), Color("#ff44ff")
]

func _ready() -> void:
    grid.init_grid()

func add_score(points: int) -> void:
    score += points
    $UI/ScoreLabel.text = "Score: %d" % score

func use_move() -> void:
    moves -= 1
    $UI/MovesLabel.text = "Moves: %d" % moves
    if moves <= 0:
        game_over()

func game_over() -> void:
    # Could show game over screen
    pass
''',

        "Grid.gd": '''extends Node2D

# Match-3 grid controller

const GRID_SIZE: int = 8
const TILE_SIZE: int = 50

var tiles: Array = []
var selected_tile: Node2D = null

const COLORS: Array[Color] = [
    Color("#ff4444"), Color("#44ff44"), Color("#4444ff"),
    Color("#ffff44"), Color("#ff44ff")
]

func init_grid() -> void:
    for y in range(GRID_SIZE):
        tiles.append([])
        for x in range(GRID_SIZE):
            var tile: ColorRect = ColorRect.new()
            tile.color = COLORS[randi() % COLORS.size()]
            tile.position = Vector2(x * TILE_SIZE, y * TILE_SIZE)
            tile.size = Vector2(TILE_SIZE - 2, TILE_SIZE - 2)
            tile.set_meta("grid_x", x)
            tile.set_meta("grid_y", y)
            add_child(tile)
            tiles[y].append(tile)

func _input(event: InputEvent) -> void:
    if event is InputEventMouseButton and event.pressed:
        var local_pos: Vector2 = make_input_local(event).position
        var grid_x: int = int(local_pos.x / TILE_SIZE)
        var grid_y: int = int(local_pos.y / TILE_SIZE)

        if grid_x >= 0 and grid_x < GRID_SIZE and grid_y >= 0 and grid_y < GRID_SIZE:
            handle_click(grid_x, grid_y)

func handle_click(x: int, y: int) -> void:
    var clicked: ColorRect = tiles[y][x]

    if selected_tile == null:
        selected_tile = clicked
        # Highlight selected
        clicked.size = Vector2(TILE_SIZE - 4, TILE_SIZE - 4)
    else:
        # Check if adjacent
        var sel_x: int = selected_tile.get_meta("grid_x")
        var sel_y: int = selected_tile.get_meta("grid_y")

        if abs(x - sel_x) + abs(y - sel_y) == 1:
            # Swap tiles
            swap_tiles(sel_x, sel_y, x, y)
            # Check for matches
            if not check_matches():
                # Swap back if no match
                swap_tiles(sel_x, sel_y, x, y)
            else:
                var main: Node = get_tree().current_scene
                if main.has_method("use_move"):
                    main.use_move()
                # Fill empty spaces
                await get_tree().create_timer(0.2).timeout
                fill_empty()

        # Reset selection
        selected_tile.size = Vector2(TILE_SIZE - 2, TILE_SIZE - 2)
        selected_tile = null

func swap_tiles(x1: int, y1: int, x2: int, y2: int) -> void:
    var temp: Color = tiles[y1][x1].color
    tiles[y1][x1].color = tiles[y2][x2].color
    tiles[y2][x2].color = temp

func check_matches() -> bool:
    var matched: bool = false

    # Check horizontal matches
    for y in range(GRID_SIZE):
        for x in range(GRID_SIZE - 2):
            if tiles[y][x].color == tiles[y][x+1].color == tiles[y][x+2].color:
                # Found match
                tiles[y][x].color = Color("#00000000")
                tiles[y][x+1].color = Color("#00000000")
                tiles[y][x+2].color = Color("#00000000")
                matched = true
                var main: Node = get_tree().current_scene
                if main.has_method("add_score"):
                    main.add_score(100)

    # Check vertical matches
    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE - 2):
            if tiles[y][x].color == tiles[y+1][x].color == tiles[y+2][x].color:
                tiles[y][x].color = Color("#00000000")
                tiles[y+1][x].color = Color("#00000000")
                tiles[y+2][x].color = Color("#00000000")
                matched = true
                var main: Node = get_tree().current_scene
                if main.has_method("add_score"):
                    main.add_score(100)

    return matched

func fill_empty() -> void:
    # Drop tiles down and fill top
    for x in range(GRID_SIZE):
        for y in range(GRID_SIZE - 1, -1, -1):
            if tiles[y][x].color == Color("#00000000"):
                # Find tile above to drop
                for above in range(y - 1, -1, -1):
                    if tiles[above][x].color != Color("#00000000"):
                        tiles[y][x].color = tiles[above][x].color
                        tiles[above][x].color = Color("#00000000")
                        break
                # If still empty, add new tile
                if tiles[y][x].color == Color("#00000000"):
                    tiles[y][x].color = COLORS[randi() % COLORS.size()]
'''
    },
    project_settings={
        "display/window/size/viewport_width": 640,
        "display/window/size/viewport_height": 480,
    }
)


# =============================================================================
# TEMPLATE REGISTRY
# =============================================================================

GAME_TEMPLATES: dict[str, GameTemplate] = {
    "pong": PONG_TEMPLATE,
    "space_invaders": SPACE_INVADERS_TEMPLATE,
    "platformer": PLATFORMER_TEMPLATE,
    "shooter": SHOOTER_TEMPLATE,
    "puzzle": PUZZLE_TEMPLATE,
}


def get_template(template_name: str) -> Optional[GameTemplate]:
    """Get a template by name."""
    return GAME_TEMPLATES.get(template_name.lower())


def list_templates() -> list[dict]:
    """List all available templates with info."""
    return [
        {
            "name": t.name,
            "type": t.game_type,
            "description": t.description,
            "difficulty": t.difficulty,
            "controls": t.controls,
            "objective": t.objective,
        }
        for t in GAME_TEMPLATES.values()
    ]


def create_game_from_template(project_dir: Path, template: GameTemplate, game_name: str) -> list[str]:
    """
    Create a complete game from a template.

    Returns list of created files.
    """
    files_created = []

    # Create scripts
    for script_name, script_content in template.scripts.items():
        script_path = project_dir / script_name
        script_path.write_text(script_content)
        files_created.append(script_name)

    # Create main scene using the scene builder
    from llm_router.tools.godot_tools import build_scene_from_config
    scene_content = build_scene_from_config(game_name, template.scene_config)
    scene_path = project_dir / f"{game_name}.tscn"
    scene_path.write_text(scene_content)
    files_created.append(f"{game_name}.tscn")

    return files_created
