"""
Configuration for the Game-Playing Agent.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def _get_data_dir() -> Path:
    """Get the data directory for persistent storage."""
    return Path(__file__).parent / "data"


@dataclass
class GameAgentConfig:
    """Settings and thresholds for the game agent."""

    # Game settings
    game_url: str = "http://localhost:8888"
    max_floor: int = 5

    # Timing (milliseconds)
    frame_delay_ms: int = 100  # Time between frames
    action_delay_ms: int = 150  # Time after action before next frame
    load_wait_ms: int = 3000  # Wait for game to load

    # Template matching thresholds
    template_threshold: float = 0.75  # Default match threshold
    enemy_threshold: float = 0.70  # Lower for enemies (more variation)
    ui_threshold: float = 0.85  # Higher for UI elements (more static)

    # Vision model settings
    vision_model: str = "claude-sonnet-4-6-20250929"
    max_vision_calls_per_game: int = 10  # Limit vision model usage

    # Decision thresholds
    health_critical: float = 0.20  # Health % considered critical
    health_low: float = 0.30  # Health % considered low
    mana_for_heal: int = 15  # Mana cost for heal spell
    mana_for_fireball: int = 20  # Mana cost for fireball

    # Q-learning settings
    learning_rate: float = 0.1
    discount_factor: float = 0.95
    exploration_rate: float = 0.2
    exploration_decay: float = 0.995

    # Paths (use field with default_factory for mutable defaults)
    data_dir: Path = field(default_factory=_get_data_dir)
    templates_dir: Optional[Path] = None
    cache_file: Optional[Path] = None
    q_table_file: Optional[Path] = None
    replay_file: Optional[Path] = None

    # Rewards
    reward_floor_advance: float = 10.0
    reward_enemy_kill: float = 5.0
    reward_chest_open: float = 2.0
    reward_victory: float = 100.0
    reward_death: float = -50.0
    reward_health_change_mult: float = 0.1

    def __post_init__(self):
        # Ensure data_dir is a Path
        self.data_dir = Path(self.data_dir)

        # Set up paths relative to data_dir
        if self.templates_dir is None:
            self.templates_dir = self.data_dir / "templates"
        if self.cache_file is None:
            self.cache_file = self.data_dir / "template_cache.json"
        if self.q_table_file is None:
            self.q_table_file = self.data_dir / "q_table.json"
        if self.replay_file is None:
            self.replay_file = self.data_dir / "replay_buffer.json"

        # Ensure paths are Path objects
        self.templates_dir = Path(self.templates_dir)
        self.cache_file = Path(self.cache_file)
        self.q_table_file = Path(self.q_table_file)
        self.replay_file = Path(self.replay_file)

        # Create directories
        self.templates_dir.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
