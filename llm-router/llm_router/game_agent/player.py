"""
Game Player: Main game loop orchestrating all components.
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from .browser import BrowserController, KEYS
from .config import GameAgentConfig
from .decision.rules import RuleEngine
from .decision.state_machine import GameFSM, GamePhase
from .improvement.q_learner import QLearner, calculate_reward
from .improvement.replay_buffer import ReplayBuffer
from .vision.fast_detector import FastDetector, GameState
from .vision.template_manager import TemplateManager

logger = logging.getLogger(__name__)


@dataclass
class GameStats:
    """Statistics for a game run."""
    start_time: float = 0.0
    end_time: float = 0.0
    frames_processed: int = 0
    actions_taken: int = 0
    floors_reached: int = 1
    enemies_killed: int = 0
    chests_opened: int = 0
    vision_calls: int = 0
    victory: bool = False

    @property
    def duration_seconds(self) -> float:
        return self.end_time - self.start_time if self.end_time else 0

    @property
    def fps(self) -> float:
        if self.duration_seconds <= 0:
            return 0
        return self.frames_processed / self.duration_seconds


@dataclass
class GameResult:
    """Result of a game run."""
    victory: bool
    stats: GameStats
    final_state: Optional[GameState] = None
    error: Optional[str] = None


class GamePlayer:
    """
    Main game-playing agent that coordinates all components.

    Flow:
    1. Browser takes screenshot
    2. FastDetector extracts game state (no AI)
    3. FSM determines current phase
    4. RuleEngine or QLearner chooses action
    5. Browser executes action
    6. Experience stored for learning
    7. Repeat until game over or victory
    """

    def __init__(
        self,
        config: Optional[GameAgentConfig] = None,
        llm_client: Any = None,
        use_q_learning: bool = True
    ):
        self.config = config or GameAgentConfig()
        self.llm_client = llm_client

        # Components
        self.browser = BrowserController(self.config)
        self.template_manager = TemplateManager(self.config, llm_client)
        self.detector = FastDetector(self.config, self.template_manager)
        self.fsm = GameFSM(
            health_critical=self.config.health_critical,
            health_low=self.config.health_low
        )
        self.rule_engine = RuleEngine()

        # Learning components (optional)
        self.use_q_learning = use_q_learning
        if use_q_learning:
            self.q_learner = QLearner(self.config)
            self.replay_buffer = ReplayBuffer(save_path=self.config.replay_file)
        else:
            self.q_learner = None
            self.replay_buffer = None

        # State
        self.running = False
        self.paused = False
        self.stats = GameStats()
        self.prev_state: Optional[GameState] = None
        self.last_action = ""

        # Callbacks for external monitoring
        self.on_state_change: Optional[Callable[[GameState, GamePhase, str], None]] = None
        self.on_frame: Optional[Callable[[np.ndarray, GameState], None]] = None

    async def start(self) -> None:
        """Start the browser and navigate to game."""
        await self.browser.start()
        await self.browser.navigate()

    async def stop(self) -> None:
        """Stop the game and close browser."""
        self.running = False
        await self.browser.close()

    async def initial_learning(self) -> Dict[str, str]:
        """
        Run initial template learning phase.

        Uses vision model to identify UI elements and create templates.
        This should be called once for a new game.
        """
        if not self.llm_client:
            raise ValueError("LLM client required for initial learning")

        logger.info("Starting initial template learning...")
        self.stats.vision_calls = 0

        # Wait for game to load
        await asyncio.sleep(2)

        # Take initial screenshot
        screenshot = await self.browser.take_screenshot()

        # Identify UI layout
        logger.info("Identifying UI layout...")
        ui_layout = await self.template_manager.identify_ui_layout(screenshot)
        self.stats.vision_calls += 1

        results = {}

        # Learn each UI element
        for element_name, region in ui_layout.items():
            try:
                logger.info(f"Learning template: {element_name}")
                template_path = await self.template_manager.learn_template_with_vision(
                    screenshot,
                    tuple(region),
                    element_name
                )
                results[element_name] = template_path
                self.stats.vision_calls += 1
            except Exception as e:
                logger.warning(f"Failed to learn {element_name}: {e}")
                results[element_name] = f"error: {e}"

        # Reload templates in detector
        self.detector.clear_cache()

        logger.info(f"Initial learning complete. Vision calls: {self.stats.vision_calls}")
        return results

    async def play_game(
        self,
        max_frames: int = 10000,
        use_rules: bool = True,
        explore: bool = True
    ) -> GameResult:
        """
        Play a complete game run.

        Args:
            max_frames: Maximum frames before stopping
            use_rules: Use rule engine (vs pure Q-learning)
            explore: Allow exploration in Q-learning

        Returns:
            GameResult with outcome and statistics
        """
        self.running = True
        self.paused = False
        self.stats = GameStats()
        self.stats.start_time = time.time()
        self.fsm.reset()
        self.prev_state = None
        self.last_action = ""

        try:
            while self.running and self.stats.frames_processed < max_frames:
                # Handle pause
                while self.paused:
                    await asyncio.sleep(0.1)

                # Step through one frame
                state = await self.step(use_rules=use_rules, explore=explore)

                # Check for terminal state
                if state.game_over or state.victory:
                    self.stats.victory = state.victory
                    break

                # Frame delay
                await asyncio.sleep(self.config.frame_delay_ms / 1000)

        except Exception as e:
            logger.error(f"Game error: {e}")
            self.stats.end_time = time.time()
            return GameResult(
                victory=False,
                stats=self.stats,
                error=str(e)
            )

        self.stats.end_time = time.time()

        # Save learning data
        if self.use_q_learning and self.q_learner:
            self.q_learner.save()
        if self.replay_buffer:
            self.replay_buffer.save()

        return GameResult(
            victory=self.stats.victory,
            stats=self.stats,
            final_state=self.prev_state
        )

    async def step(self, use_rules: bool = True, explore: bool = True) -> GameState:
        """
        Execute one game step (screenshot -> detect -> decide -> act).

        Returns:
            Current game state after action
        """
        # 1. Take screenshot
        screenshot = await self.browser.take_screenshot()
        self.stats.frames_processed += 1

        # Call frame callback if set
        if self.on_frame:
            self.on_frame(screenshot, None)  # State not known yet

        # 2. Detect game state (FAST - no AI)
        state = self.detector.detect_state(screenshot)

        # Update frame callback with state
        if self.on_frame:
            self.on_frame(screenshot, state)

        # 3. Update FSM
        phase = self.fsm.update(state)

        # 4. Choose action
        if use_rules or not self.q_learner:
            action, rule_name = self.rule_engine.decide(state, phase)
        else:
            # Pure Q-learning
            action, was_explore = self.q_learner.choose_action(state, explore=explore)

        # 5. Execute action
        await self.execute_action(action)
        self.last_action = action
        self.stats.actions_taken += 1

        # 6. Learning update (if we have previous state)
        if self.prev_state is not None and self.use_q_learning:
            reward = calculate_reward(self.prev_state, action, state, self.config)

            # Store experience
            if self.replay_buffer:
                self.replay_buffer.push(
                    self.prev_state,
                    action,
                    reward,
                    state,
                    state.game_over or state.victory
                )

            # Update Q-values
            if self.q_learner:
                self.q_learner.update(
                    self.prev_state,
                    action,
                    reward,
                    state,
                    state.game_over or state.victory
                )

            # Track stats
            if reward > 5:
                self.stats.enemies_killed += 1
            if reward > 1 and action == "interact":
                self.stats.chests_opened += 1

        # 7. Update floor tracking
        if state.floor > self.stats.floors_reached:
            self.stats.floors_reached = state.floor

        # 8. Callback
        if self.on_state_change:
            self.on_state_change(state, phase, action)

        # Store for next iteration
        self.prev_state = state

        return state

    async def execute_action(self, action: str) -> None:
        """Execute an action by pressing the corresponding key."""
        key = KEYS.get(action)
        if key:
            await self.browser.press_key(key)
        else:
            logger.warning(f"Unknown action: {action}")

    def pause(self) -> None:
        """Pause the game loop."""
        self.paused = True

    def resume(self) -> None:
        """Resume the game loop."""
        self.paused = False

    def stop_game(self) -> None:
        """Signal the game to stop."""
        self.running = False

    async def train(self, num_games: int = 10, save_every: int = 5) -> List[GameResult]:
        """
        Train the agent by playing multiple games.

        Args:
            num_games: Number of games to play
            save_every: Save Q-table every N games

        Returns:
            List of game results
        """
        results = []

        for game_num in range(num_games):
            logger.info(f"Starting training game {game_num + 1}/{num_games}")

            # Start fresh
            await self.start()

            # Play game
            result = await self.play_game(use_rules=True, explore=True)
            results.append(result)

            # Decay exploration
            if self.q_learner:
                self.q_learner.decay_exploration()

            # Save periodically
            if (game_num + 1) % save_every == 0:
                if self.q_learner:
                    self.q_learner.save()
                if self.replay_buffer:
                    self.replay_buffer.save()

            # Log progress
            logger.info(
                f"Game {game_num + 1}: Victory={result.victory}, "
                f"Floor={result.stats.floors_reached}, "
                f"Duration={result.stats.duration_seconds:.1f}s"
            )

            await self.stop()

        return results

    def get_status(self) -> Dict[str, Any]:
        """Get current agent status."""
        return {
            "running": self.running,
            "paused": self.paused,
            "frames_processed": self.stats.frames_processed,
            "actions_taken": self.stats.actions_taken,
            "floors_reached": self.stats.floors_reached,
            "last_action": self.last_action,
            "phase": self.fsm.phase.value if self.fsm else None,
            "q_learner_stats": self.q_learner.get_statistics() if self.q_learner else None,
        }

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop()
