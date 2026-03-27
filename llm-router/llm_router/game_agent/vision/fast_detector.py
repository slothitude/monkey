"""
Fast Detector: OpenCV-only detection for real-time game state.

NO vision model calls here - only fast template matching and image analysis.
Target: < 10ms per frame.
"""

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

from ..config import GameAgentConfig
from .template_manager import TemplateManager


@dataclass
class Detection:
    """Result of a template detection."""
    name: str
    found: bool
    confidence: float = 0.0
    location: Tuple[int, int] = (0, 0)  # Top-left corner
    size: Tuple[int, int] = (0, 0)  # Width, height
    center: Tuple[int, int] = (0, 0)


@dataclass
class GameState:
    """Current game state extracted from screenshot."""
    # Player stats
    health_pct: float = 0.0  # 0.0 - 1.0
    mana_pct: float = 0.0  # 0.0 - 1.0
    floor: int = 1
    keys: int = 0

    # Enemy detection
    enemy_ahead: bool = False
    enemy_type: str = ""
    enemy_health_pct: float = 0.0
    enemy_location: Tuple[int, int] = (0, 0)

    # Interactive elements
    stairs_ahead: bool = False
    chest_ahead: bool = False
    door_ahead: bool = False
    potion_ahead: bool = False

    # Game status
    game_over: bool = False
    victory: bool = False
    paused: bool = False

    # Raw detections for debugging
    detections: List[Detection] = field(default_factory=list)

    # Timing
    detection_time_ms: float = 0.0


class FastDetector:
    """
    Fast OpenCV-only game state detector.

    Uses template matching and color analysis - NO AI calls.
    """

    # Known enemy types
    ENEMY_TYPES = ["rat", "goblin", "skeleton", "orc", "demon", "dragon", "slime", "bat"]

    # UI element templates
    UI_ELEMENTS = ["health_bar", "mana_bar", "floor_label", "minimap"]

    # Interactive elements
    INTERACTIVE = ["stairs", "chest", "door", "potion", "key"]

    # Status screens
    STATUS_SCREENS = ["game_over", "victory", "paused", "death_screen"]

    def __init__(self, config: Optional[GameAgentConfig] = None, template_manager: Optional[TemplateManager] = None):
        self.config = config or GameAgentConfig()
        self.template_manager = template_manager or TemplateManager(self.config)

        # Cache loaded templates
        self._template_cache: Dict[str, np.ndarray] = {}
        self._threshold_cache: Dict[str, float] = {}

        # Color ranges for bar detection (HSV)
        self.health_color_range = {
            "lower": np.array([0, 100, 100]),   # Red
            "upper": np.array([10, 255, 255])
        }
        self.mana_color_range = {
            "lower": np.array([100, 100, 100]),  # Blue
            "upper": np.array([130, 255, 255])
        }

    def _load_template(self, name: str) -> Optional[np.ndarray]:
        """Load and cache a template."""
        if name in self._template_cache:
            return self._template_cache[name]

        template = self.template_manager.get_template(name)
        if template is not None:
            self._template_cache[name] = template
            # Get threshold from cache
            cache = self.template_manager.template_cache.get(name, {})
            self._threshold_cache[name] = cache.get("match_threshold", self.config.template_threshold)

        return template

    def template_match(
        self,
        screenshot: np.ndarray,
        template_name: str,
        threshold: Optional[float] = None
    ) -> Detection:
        """
        Perform template matching on screenshot.

        Args:
            screenshot: Game screenshot as numpy array (BGR)
            template_name: Name of template to match
            threshold: Override threshold

        Returns:
            Detection result
        """
        template = self._load_template(template_name)
        if template is None:
            return Detection(name=template_name, found=False)

        # Get threshold
        if threshold is None:
            threshold = self._threshold_cache.get(template_name, self.config.template_threshold)

        # Perform template matching
        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

        if max_val >= threshold:
            h, w = template.shape[:2]
            return Detection(
                name=template_name,
                found=True,
                confidence=float(max_val),
                location=max_loc,
                size=(w, h),
                center=(max_loc[0] + w // 2, max_loc[1] + h // 2)
            )

        return Detection(name=template_name, found=False)

    def multi_template_match(
        self,
        screenshot: np.ndarray,
        template_name: str,
        threshold: Optional[float] = None
    ) -> List[Detection]:
        """
        Find all occurrences of a template.

        Returns:
            List of all detections
        """
        template = self._load_template(template_name)
        if template is None:
            return []

        if threshold is None:
            threshold = self._threshold_cache.get(template_name, self.config.template_threshold)

        result = cv2.matchTemplate(screenshot, template, cv2.TM_CCOEFF_NORMED)
        locations = np.where(result >= threshold)

        detections = []
        h, w = template.shape[:2]

        for pt in zip(*locations[::-1]):
            detections.append(Detection(
                name=template_name,
                found=True,
                confidence=float(result[pt[1], pt[0]]),
                location=pt,
                size=(w, h),
                center=(pt[0] + w // 2, pt[1] + h // 2)
            ))

        return detections

    def analyze_bar_fill(
        self,
        screenshot: np.ndarray,
        bar_region: Tuple[int, int, int, int],
        color: str = "red"
    ) -> float:
        """
        Analyze a health/mana bar to determine fill percentage.

        Args:
            screenshot: Full screenshot
            bar_region: (x, y, width, height) of the bar
            color: "red" for health, "blue" for mana

        Returns:
            Fill percentage (0.0 - 1.0)
        """
        x, y, w, h = bar_region
        # Ensure bounds are valid
        h_img, w_img = screenshot.shape[:2]
        x1, y1 = max(0, x), max(0, y)
        x2, y2 = min(w_img, x + w), min(h_img, y + h)
        bar_img = screenshot[y1:y2, x1:x2]

        if bar_img.size == 0:
            return 0.0

        # Convert to HSV for color detection
        hsv = cv2.cvtColor(bar_img, cv2.COLOR_BGR2HSV)

        # Select color range
        if color in ("blue", "mana"):
            lower = self.mana_color_range["lower"]
            upper = self.mana_color_range["upper"]
        else:  # red/health
            lower = self.health_color_range["lower"]
            upper = self.health_color_range["upper"]

        # Create mask for the color
        mask = cv2.inRange(hsv, lower, upper)

        # Calculate fill percentage
        filled_pixels = cv2.countNonZero(mask)
        total_pixels = bar_img.shape[0] * bar_img.shape[1]

        return min(1.0, filled_pixels / total_pixels if total_pixels > 0 else 0.0)

    def detect_enemies(self, screenshot: np.ndarray) -> Tuple[bool, str, Tuple[int, int]]:
        """
        Detect enemies in the screenshot.

        Returns:
            (found, enemy_type, location)
        """
        for enemy_type in self.ENEMY_TYPES:
            detection = self.template_match(
                screenshot,
                f"enemy_{enemy_type}",
                threshold=self.config.enemy_threshold
            )
            if detection.found:
                return True, enemy_type, detection.center

        return False, "", (0, 0)

    def detect_state(self, screenshot: np.ndarray) -> GameState:
        """
        Full game state detection. This is the main method.

        Target: < 10ms execution time.
        """
        start_time = time.perf_counter()

        state = GameState()
        detections = []

        # 1. Detect UI elements (health/mana bars)
        for element in self.UI_ELEMENTS:
            det = self.template_match(screenshot, element)
            if det.found:
                detections.append(det)

        # 2. Analyze bar fill if templates found
        health_det = next((d for d in detections if d.name == "health_bar"), None)
        if health_det and health_det.found:
            # Use detected location for fill analysis
            x, y = health_det.location
            w, h = health_det.size
            state.health_pct = self.analyze_bar_fill(
                screenshot, (x, y, w, h), color="red"
            )

        mana_det = next((d for d in detections if d.name == "mana_bar"), None)
        if mana_det and mana_det.found:
            x, y = mana_det.location
            w, h = mana_det.size
            state.mana_pct = self.analyze_bar_fill(
                screenshot, (x, y, w, h), color="blue"
            )

        # 3. Detect enemies
        enemy_found, enemy_type, enemy_loc = self.detect_enemies(screenshot)
        state.enemy_ahead = enemy_found
        state.enemy_type = enemy_type
        state.enemy_location = enemy_loc

        # 4. Detect interactive elements
        for element in self.INTERACTIVE:
            det = self.template_match(screenshot, element)
            if det.found:
                detections.append(det)
                if element == "stairs":
                    state.stairs_ahead = True
                elif element == "chest":
                    state.chest_ahead = True
                elif element == "door":
                    state.door_ahead = True
                elif element == "potion":
                    state.potion_ahead = True

        # 5. Detect status screens
        for screen in self.STATUS_SCREENS:
            det = self.template_match(screenshot, screen)
            if det.found:
                detections.append(det)
                if screen == "game_over":
                    state.game_over = True
                elif screen == "victory":
                    state.victory = True
                elif screen == "paused":
                    state.paused = True

        state.detections = detections
        state.detection_time_ms = (time.perf_counter() - start_time) * 1000

        return state

    def detect_from_file(self, image_path: str) -> GameState:
        """Convenience method to detect from image file."""
        screenshot = cv2.imread(image_path)
        if screenshot is None:
            raise ValueError(f"Could not load image: {image_path}")
        return self.detect_state(screenshot)

    def clear_cache(self) -> None:
        """Clear template cache."""
        self._template_cache.clear()
        self._threshold_cache.clear()
