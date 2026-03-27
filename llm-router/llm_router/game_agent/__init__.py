"""
Game-Playing Agent for Dungeon Crawler

A fast game-playing agent that uses:
- Vision model sparingly (only for template learning)
- OpenCV template matching for fast detection (~5ms)
- Q-learning for improvement over time

Usage:
    python -m llm_router.game_agent play --url http://localhost:8888
    python -m llm_router.game_agent learn
    python -m llm_router.game_agent detect --image screenshot.png
"""

from .config import GameAgentConfig
from .player import GamePlayer, GameResult, GameStats
from .browser import BrowserController, KEYS
from .vision.fast_detector import FastDetector, GameState, Detection
from .vision.template_manager import TemplateManager
from .decision.state_machine import GameFSM, GamePhase
from .decision.rules import RuleEngine, Rule
from .improvement.q_learner import QLearner, calculate_reward
from .improvement.replay_buffer import ReplayBuffer, Experience

__all__ = [
    # Main classes
    "GameAgentConfig",
    "GamePlayer",
    "GameResult",
    "GameStats",
    "BrowserController",
    "KEYS",

    # Vision
    "FastDetector",
    "GameState",
    "Detection",
    "TemplateManager",

    # Decision
    "GameFSM",
    "GamePhase",
    "RuleEngine",
    "Rule",

    # Learning
    "QLearner",
    "calculate_reward",
    "ReplayBuffer",
    "Experience",
]
