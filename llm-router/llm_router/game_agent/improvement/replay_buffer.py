"""
Replay Buffer: Store and sample game experiences for learning.
"""

import json
import random
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from ..vision.fast_detector import GameState


@dataclass
class Experience:
    """A single game experience (state, action, reward, next_state)."""
    state: dict  # Discretized state
    action: str
    reward: float
    next_state: dict
    done: bool  # Terminal state
    timestamp: str = ""

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = datetime.now().isoformat()


class ReplayBuffer:
    """
    Circular buffer for storing game experiences.

    Used for:
    - Storing experiences during gameplay
    - Sampling batches for Q-learning
    - Analyzing gameplay patterns
    """

    def __init__(self, capacity: int = 10000, save_path: Optional[Path] = None):
        self.capacity = capacity
        self.buffer: List[Experience] = []
        self.position = 0
        self.save_path = save_path

        if save_path and save_path.exists():
            self.load(save_path)

    def push(
        self,
        state: GameState,
        action: str,
        reward: float,
        next_state: GameState,
        done: bool
    ) -> None:
        """Add an experience to the buffer."""
        experience = Experience(
            state=discretize_state(state),
            action=action,
            reward=reward,
            next_state=discretize_state(next_state),
            done=done
        )

        if len(self.buffer) < self.capacity:
            self.buffer.append(experience)
        else:
            self.buffer[self.position] = experience

        self.position = (self.position + 1) % self.capacity

    def sample(self, batch_size: int) -> List[Experience]:
        """Sample a random batch of experiences."""
        return random.sample(self.buffer, min(batch_size, len(self.buffer)))

    def get_recent(self, n: int) -> List[Experience]:
        """Get the n most recent experiences."""
        if len(self.buffer) <= n:
            return self.buffer.copy()
        # Handle circular buffer wraparound
        if self.position >= n:
            return self.buffer[self.position - n:self.position]
        else:
            return self.buffer[-(n - self.position):] + self.buffer[:self.position]

    def get_all(self) -> List[Experience]:
        """Get all experiences."""
        return self.buffer.copy()

    def clear(self) -> None:
        """Clear the buffer."""
        self.buffer.clear()
        self.position = 0

    def __len__(self) -> int:
        return len(self.buffer)

    def save(self, path: Optional[Path] = None) -> None:
        """Save buffer to file."""
        path = path or self.save_path
        if not path:
            return

        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump([asdict(e) for e in self.buffer], f, indent=2)

    def load(self, path: Path) -> int:
        """Load buffer from file."""
        try:
            with open(path, "r") as f:
                data = json.load(f)
            self.buffer = [Experience(**e) for e in data]
            self.position = len(self.buffer) % self.capacity
            return len(self.buffer)
        except (json.JSONDecodeError, IOError):
            return 0

    def get_statistics(self) -> dict:
        """Get statistics about stored experiences."""
        if not self.buffer:
            return {"count": 0}

        rewards = [e.reward for e in self.buffer]
        actions = [e.action for e in self.buffer]

        return {
            "count": len(self.buffer),
            "avg_reward": sum(rewards) / len(rewards),
            "max_reward": max(rewards),
            "min_reward": min(rewards),
            "action_counts": {a: actions.count(a) for a in set(actions)},
            "terminal_count": sum(1 for e in self.buffer if e.done)
        }


def discretize_state(state: GameState) -> dict:
    """
    Convert continuous game state to discrete representation for Q-table.

    This reduces the state space from infinite to manageable.
    """
    return {
        # Health bucketed into 4 levels
        "health_bucket": int(state.health_pct * 4),  # 0-4

        # Mana bucketed into 4 levels
        "mana_bucket": int(state.mana_pct * 4),  # 0-4

        # Binary flags
        "enemy_ahead": int(state.enemy_ahead),
        "stairs_ahead": int(state.stairs_ahead),
        "chest_ahead": int(state.chest_ahead),
        "door_ahead": int(state.door_ahead),
        "potion_ahead": int(state.potion_ahead),

        # Floor (discrete already)
        "floor": state.floor,

        # Keys (capped at 3+)
        "keys_bucket": min(state.keys, 3),

        # Enemy type hash (if enemy present)
        "enemy_type_hash": hash(state.enemy_type) % 10 if state.enemy_ahead else -1,

        # Game status
        "game_over": int(state.game_over),
        "victory": int(state.victory),
    }


def state_to_key(state: dict) -> str:
    """Convert discrete state dict to hashable string key."""
    return json.dumps(state, sort_keys=True)
