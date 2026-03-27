"""
Game State Machine: Manages high-level game phases and transitions.
"""

from enum import Enum
from typing import List, Optional, Tuple

from ..vision.fast_detector import GameState


class GamePhase(Enum):
    """High-level game phases."""
    EXPLORE = "explore"
    COMBAT = "combat"
    HEALING = "healing"
    LOOTING = "looting"
    TRANSITIONING = "transitioning"  # Moving between floors
    GAME_OVER = "game_over"
    VICTORY = "victory"


class GameFSM:
    """
    Finite State Machine for game phase management.

    Transitions:
    - EXPLORE -> COMBAT (enemy detected)
    - EXPLORE -> HEALING (low health)
    - EXPLORE -> LOOTING (chest detected)
    - EXPLORE -> TRANSITIONING (stairs detected)
    - COMBAT -> EXPLORE (enemy dead)
    - COMBAT -> HEALING (low health in combat)
    - HEALING -> EXPLORE (health restored)
    - LOOTING -> EXPLORE (chest opened)
    - TRANSITIONING -> EXPLORE (floor changed)
    - * -> GAME_OVER (player died)
    - * -> VICTORY (won game)
    """

    def __init__(self, health_critical: float = 0.20, health_low: float = 0.30):
        self.phase = GamePhase.EXPLORE
        self.health_critical = health_critical
        self.health_low = health_low

        # Phase history for debugging
        self.phase_history: List[Tuple[GamePhase, GamePhase]] = []

    def update(self, state: GameState) -> GamePhase:
        """
        Update FSM based on current game state.

        Args:
            state: Current game state from vision detection

        Returns:
            Current phase after transitions
        """
        old_phase = self.phase

        # Check for terminal states first
        if state.game_over:
            self._transition(GamePhase.GAME_OVER)
            return self.phase

        if state.victory:
            self._transition(GamePhase.VICTORY)
            return self.phase

        # Phase-specific transitions
        if self.phase == GamePhase.EXPLORE:
            self._update_explore(state)

        elif self.phase == GamePhase.COMBAT:
            self._update_combat(state)

        elif self.phase == GamePhase.HEALING:
            self._update_healing(state)

        elif self.phase == GamePhase.LOOTING:
            self._update_looting(state)

        elif self.phase == GamePhase.TRANSITIONING:
            self._update_transitioning(state)

        # Record transition
        if old_phase != self.phase:
            self.phase_history.append((old_phase, self.phase))

        return self.phase

    def _transition(self, new_phase: GamePhase) -> None:
        """Transition to a new phase."""
        self.phase = new_phase

    def _update_explore(self, state: GameState) -> None:
        """Handle EXPLORE phase transitions."""
        # Priority: survival > combat > loot > explore
        if state.health_pct < self.health_critical:
            self._transition(GamePhase.HEALING)
        elif state.enemy_ahead:
            self._transition(GamePhase.COMBAT)
        elif state.chest_ahead and not state.enemy_ahead:
            self._transition(GamePhase.LOOTING)
        elif state.stairs_ahead and not state.enemy_ahead:
            self._transition(GamePhase.TRANSITIONING)

    def _update_combat(self, state: GameState) -> None:
        """Handle COMBAT phase transitions."""
        if state.health_pct < self.health_critical:
            self._transition(GamePhase.HEALING)
        elif not state.enemy_ahead:
            # Enemy defeated
            self._transition(GamePhase.EXPLORE)

    def _update_healing(self, state: GameState) -> None:
        """Handle HEALING phase transitions."""
        if state.health_pct >= 0.5:  # Restored to safe level
            self._transition(GamePhase.EXPLORE)
        elif state.game_over:
            self._transition(GamePhase.GAME_OVER)

    def _update_looting(self, state: GameState) -> None:
        """Handle LOOTING phase transitions."""
        if not state.chest_ahead:
            # Chest opened
            self._transition(GamePhase.EXPLORE)
        elif state.enemy_ahead:
            # Interrupted by enemy
            self._transition(GamePhase.COMBAT)

    def _update_transitioning(self, state: GameState) -> None:
        """Handle TRANSITIONING phase transitions."""
        # Always return to explore after transition
        # (floor number change would be detected by vision)
        self._transition(GamePhase.EXPLORE)

    def get_phase(self) -> GamePhase:
        """Get current phase."""
        return self.phase

    def reset(self) -> None:
        """Reset FSM to initial state."""
        self.phase = GamePhase.EXPLORE
        self.phase_history.clear()

    def is_active(self) -> bool:
        """Check if game is still active (not terminal state)."""
        return self.phase not in (GamePhase.GAME_OVER, GamePhase.VICTORY)
