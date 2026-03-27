"""
Space Shooter Game Adapter.

Adapts the game agent for the simple space shooter game.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
import cv2
import numpy as np
import time

from ...config import GameAgentConfig


@dataclass
class SpaceShooterState:
    """Game state for the space shooter."""
    # Player
    player_x: int = 0
    player_y: int = 0
    player_found: bool = False

    # Stats (from text)
    score: int = 0
    health: int = 100
    wave: int = 1

    # Enemies
    enemies: List[Tuple[int, int]] = field(default_factory=list)
    enemy_count: int = 0

    # Projectiles
    bullets: List[Tuple[int, int]] = field(default_factory=list)

    # Game state
    game_over: bool = False
    victory: bool = False

    # Timing
    detection_time_ms: float = 0.0


class SpaceShooterDetector:
    """
    Fast detector for the space shooter game.

    Uses simple color detection:
    - Green = player
    - Red = enemies
    - Yellow = bullets (if any)
    """

    def __init__(self, config: Optional[GameAgentConfig] = None):
        self.config = config or GameAgentConfig()

        # Color ranges (HSV)
        self.player_color = {
            "lower": np.array([35, 100, 100]),   # Green
            "upper": np.array([85, 255, 255])
        }
        self.enemy_color = {
            "lower": np.array([0, 100, 100]),    # Red (lower range)
            "upper": np.array([10, 255, 255])
        }
        self.enemy_color2 = {
            "lower": np.array([170, 100, 100]),  # Red (upper range)
            "upper": np.array([180, 255, 255])
        }

    def detect_state(self, screenshot: np.ndarray) -> SpaceShooterState:
        """
        Detect game state from screenshot.

        Target: < 5ms
        """
        start_time = time.perf_counter()

        state = SpaceShooterState()

        # Convert to HSV
        hsv = cv2.cvtColor(screenshot, cv2.COLOR_BGR2HSV)

        # Detect player (green)
        player_mask = cv2.inRange(hsv, self.player_color["lower"], self.player_color["upper"])
        player_coords = np.where(player_mask > 0)
        if len(player_coords[0]) > 0:
            state.player_found = True
            state.player_y = int(np.mean(player_coords[0]))
            state.player_x = int(np.mean(player_coords[1]))

        # Detect enemies (red)
        enemy_mask1 = cv2.inRange(hsv, self.enemy_color["lower"], self.enemy_color["upper"])
        enemy_mask2 = cv2.inRange(hsv, self.enemy_color2["lower"], self.enemy_color2["upper"])
        enemy_mask = cv2.bitwise_or(enemy_mask1, enemy_mask2)

        # Find enemy contours
        contours, _ = cv2.findContours(enemy_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            if cv2.contourArea(contour) > 50:  # Filter noise
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    state.enemies.append((cx, cy))

        state.enemy_count = len(state.enemies)

        # Try to read text (score, health, wave) - simplified for now
        # In production, would use OCR or template matching

        state.detection_time_ms = (time.perf_counter() - start_time) * 1000
        return state


# Actions for space shooter
SPACE_SHOOTER_ACTIONS = [
    "move_left",
    "move_right",
    "move_up",
    "move_down",
    "shoot",
    "wait",
]

# Key mappings
SPACE_SHOOTER_KEYS = {
    "move_left": "ArrowLeft",
    "move_right": "ArrowRight",
    "move_up": "ArrowUp",
    "move_down": "ArrowDown",
    "shoot": " ",  # Space
    "wait": ".",
}
