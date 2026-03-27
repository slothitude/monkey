"""
Q-Learner: Learn optimal actions through experience.

Uses tabular Q-learning with discretized states.
"""

import json
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from ..config import GameAgentConfig
from ..vision.fast_detector import GameState
from .replay_buffer import ReplayBuffer, discretize_state, state_to_key


# All possible actions
ACTIONS = [
    "move_forward",
    "move_backward",
    "turn_left",
    "turn_right",
    "attack",
    "cast_fireball",
    "cast_heal",
    "interact",
    "use_potion",
    "wait",
]


class QLearner:
    """
    Tabular Q-Learning agent.

    Q(s, a) represents the expected future reward for taking action a in state s.
    """

    def __init__(self, config: Optional[GameAgentConfig] = None):
        self.config = config or GameAgentConfig()

        # Q-table: state_key -> action -> value
        self.q_table: Dict[str, Dict[str, float]] = defaultdict(lambda: defaultdict(float))

        # Learning parameters
        self.learning_rate = self.config.learning_rate
        self.discount_factor = self.config.discount_factor
        self.exploration_rate = self.config.exploration_rate
        self.exploration_decay = self.config.exploration_decay

        # Statistics
        self.total_updates = 0
        self.total_decisions = 0

        # Load existing Q-table if available
        if self.config.q_table_file.exists():
            self.load(self.config.q_table_file)

    def get_q_value(self, state: GameState, action: str) -> float:
        """Get Q-value for a state-action pair."""
        state_key = state_to_key(discretize_state(state))
        return self.q_table[state_key][action]

    def get_all_q_values(self, state: GameState) -> Dict[str, float]:
        """Get Q-values for all actions in a state."""
        state_key = state_to_key(discretize_state(state))
        return dict(self.q_table[state_key])

    def choose_action(
        self,
        state: GameState,
        available_actions: Optional[List[str]] = None,
        explore: bool = True
    ) -> Tuple[str, bool]:
        """
        Choose an action using epsilon-greedy policy.

        Args:
            state: Current game state
            available_actions: Actions to choose from (default: all)
            explore: Whether to allow exploration

        Returns:
            (action, was_exploration) tuple
        """
        self.total_decisions += 1
        available_actions = available_actions or ACTIONS

        state_key = state_to_key(discretize_state(state))

        # Exploration: random action
        if explore and random.random() < self.exploration_rate:
            action = random.choice(available_actions)
            return action, True

        # Exploitation: best known action
        q_values = {a: self.q_table[state_key][a] for a in available_actions}

        if not q_values:
            return random.choice(available_actions), True

        # Find max Q-value action
        max_q = max(q_values.values())
        best_actions = [a for a, q in q_values.items() if q == max_q]

        # Break ties randomly
        action = random.choice(best_actions)
        return action, False

    def update(
        self,
        state: GameState,
        action: str,
        reward: float,
        next_state: GameState,
        done: bool
    ) -> float:
        """
        Update Q-value using Q-learning update rule.

        Q(s, a) = Q(s, a) + α * (r + γ * max(Q(s', a')) - Q(s, a))

        Returns:
            TD error (for logging)
        """
        self.total_updates += 1

        state_key = state_to_key(discretize_state(state))
        next_state_key = state_to_key(discretize_state(next_state))

        # Current Q-value
        current_q = self.q_table[state_key][action]

        # Max Q-value for next state
        if done:
            max_next_q = 0
        else:
            max_next_q = max(self.q_table[next_state_key].values()) if self.q_table[next_state_key] else 0

        # TD target and error
        td_target = reward + self.discount_factor * max_next_q
        td_error = td_target - current_q

        # Update Q-value
        self.q_table[state_key][action] = current_q + self.learning_rate * td_error

        return td_error

    def update_from_batch(self, experiences: List, batch_size: int = 32) -> float:
        """
        Update Q-values from a batch of experiences.

        Returns:
            Average TD error
        """
        if len(experiences) < batch_size:
            batch = experiences
        else:
            batch = random.sample(experiences, batch_size)

        total_td_error = 0
        for exp in batch:
            # Reconstruct state objects (simplified)
            state = GameState(**exp.state)
            next_state = GameState(**exp.next_state)

            td_error = self.update(state, exp.action, exp.reward, next_state, exp.done)
            total_td_error += td_error

        return total_td_error / len(batch) if batch else 0

    def decay_exploration(self) -> float:
        """Decay exploration rate."""
        self.exploration_rate *= self.exploration_decay
        return self.exploration_rate

    def train_from_replay_buffer(
        self,
        buffer: ReplayBuffer,
        epochs: int = 10,
        batch_size: int = 32
    ) -> List[float]:
        """
        Train on experiences from replay buffer.

        Returns:
            List of average TD errors per epoch
        """
        if len(buffer) < batch_size:
            return []

        td_errors = []
        for _ in range(epochs):
            experiences = buffer.sample(batch_size)
            avg_td_error = self.update_from_batch(experiences, batch_size)
            td_errors.append(avg_td_error)

        return td_errors

    def get_best_action(self, state: GameState, available_actions: Optional[List[str]] = None) -> str:
        """Get best action without exploration."""
        action, _ = self.choose_action(state, available_actions, explore=False)
        return action

    def save(self, path: Optional[Path] = None) -> None:
        """Save Q-table to file."""
        path = path or self.config.q_table_file
        path.parent.mkdir(parents=True, exist_ok=True)

        # Convert defaultdict to regular dict for JSON
        data = {
            "q_table": {k: dict(v) for k, v in self.q_table.items()},
            "exploration_rate": self.exploration_rate,
            "total_updates": self.total_updates,
            "total_decisions": self.total_decisions,
        }

        with open(path, "w") as f:
            json.dump(data, f, indent=2)

    def load(self, path: Path) -> bool:
        """Load Q-table from file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)

            self.q_table = defaultdict(lambda: defaultdict(float))
            for state_key, actions in data.get("q_table", {}).items():
                for action, value in actions.items():
                    self.q_table[state_key][action] = value

            self.exploration_rate = data.get("exploration_rate", self.config.exploration_rate)
            self.total_updates = data.get("total_updates", 0)
            self.total_decisions = data.get("total_decisions", 0)

            return True
        except (json.JSONDecodeError, IOError):
            return False

    def get_statistics(self) -> dict:
        """Get Q-learner statistics."""
        return {
            "states_known": len(self.q_table),
            "total_actions_learned": sum(len(v) for v in self.q_table.values()),
            "exploration_rate": self.exploration_rate,
            "total_updates": self.total_updates,
            "total_decisions": self.total_decisions,
        }

    def reset(self) -> None:
        """Reset Q-table and statistics."""
        self.q_table.clear()
        self.exploration_rate = self.config.exploration_rate
        self.total_updates = 0
        self.total_decisions = 0


def calculate_reward(
    prev_state: GameState,
    action: str,
    new_state: GameState,
    config: Optional[GameAgentConfig] = None
) -> float:
    """
    Calculate reward for a state transition.

    Reward function shaped to encourage:
    - Surviving (health management)
    - Progressing (floor advancement)
    - Killing enemies
    - Opening chests
    - Winning the game
    """
    config = config or GameAgentConfig()
    reward = 0.0

    # Health change reward
    health_change = new_state.health_pct - prev_state.health_pct
    reward += health_change * config.reward_health_change_mult * 100

    # Floor advancement (big reward)
    if new_state.floor > prev_state.floor:
        reward += config.reward_floor_advance

    # Enemy killed (assume enemy disappeared after combat action)
    if prev_state.enemy_ahead and not new_state.enemy_ahead:
        if action in ["attack", "cast_fireball"]:
            reward += config.reward_enemy_kill

    # Chest opened
    if prev_state.chest_ahead and not new_state.chest_ahead:
        if action == "interact":
            reward += config.reward_chest_open

    # Victory
    if new_state.victory and not prev_state.victory:
        reward += config.reward_victory

    # Death
    if new_state.game_over and not prev_state.game_over:
        reward += config.reward_death

    # Small penalty for waiting (encourage action)
    if action == "wait":
        reward -= 0.1

    return reward


# Alias for backwards compatibility
def get_reward(prev_state: GameState, action: str, new_state: GameState, config: Optional[GameAgentConfig] = None) -> float:
    """Alias for calculate_reward."""
    return calculate_reward(prev_state, action, new_state, config)
