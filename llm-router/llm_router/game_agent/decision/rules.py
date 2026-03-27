"""
Rule Engine: Rule-based decision making for game actions.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..vision.fast_detector import GameState
from .state_machine import GamePhase


@dataclass
class Rule:
    """A single decision rule."""
    name: str
    condition: Callable[[GameState, GamePhase], bool]
    action: str
    priority: int = 0  # Higher = more important

    def evaluate(self, state: GameState, phase: GamePhase) -> Optional[str]:
        """Evaluate rule and return action if condition met."""
        if self.condition(state, phase):
            return self.action
        return None


class RuleEngine:
    """
    Rule-based decision engine for game actions.

    Rules are evaluated in priority order (highest first).
    First matching rule's action is returned.
    """

    def __init__(self):
        self.rules: List[Rule] = []
        self._setup_default_rules()

    def _setup_default_rules(self) -> None:
        """Set up default game rules."""
        # Survival rules (highest priority)
        self.add_rule(Rule(
            name="critical_health_potion",
            condition=lambda s, p: s.health_pct < 0.15,  # Has potion check would be added
            action="use_potion",
            priority=100
        ))

        self.add_rule(Rule(
            name="low_health_heal",
            condition=lambda s, p: s.health_pct < 0.30 and s.mana_pct >= 0.15 and p != GamePhase.HEALING,
            action="cast_heal",
            priority=95
        ))

        # Combat rules
        self.add_rule(Rule(
            name="combat_fireball",
            condition=lambda s, p: s.enemy_ahead and s.mana_pct >= 0.20 and p == GamePhase.COMBAT,
            action="cast_fireball",
            priority=80
        ))

        self.add_rule(Rule(
            name="combat_attack",
            condition=lambda s, p: s.enemy_ahead and p == GamePhase.COMBAT,
            action="attack",
            priority=70
        ))

        # Loot rules
        self.add_rule(Rule(
            name="open_chest",
            condition=lambda s, p: s.chest_ahead and not s.enemy_ahead and p == GamePhase.LOOTING,
            action="interact",
            priority=60
        ))

        # Progress rules
        self.add_rule(Rule(
            name="take_stairs",
            condition=lambda s, p: s.stairs_ahead and not s.enemy_ahead and p == GamePhase.TRANSITIONING,
            action="move_forward",
            priority=50
        ))

        # Exploration rules (lowest priority)
        self.add_rule(Rule(
            name="explore_forward",
            condition=lambda s, p: p == GamePhase.EXPLORE,
            action="move_forward",
            priority=10
        ))

        # Fallback
        self.add_rule(Rule(
            name="fallback_wait",
            condition=lambda s, p: True,  # Always matches
            action="wait",
            priority=0
        ))

    def add_rule(self, rule: Rule) -> None:
        """Add a rule to the engine."""
        self.rules.append(rule)
        # Sort by priority (highest first)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> bool:
        """Remove a rule by name."""
        for i, rule in enumerate(self.rules):
            if rule.name == name:
                self.rules.pop(i)
                return True
        return False

    def decide(self, state: GameState, phase: GamePhase) -> Tuple[str, str]:
        """
        Decide what action to take based on current state.

        Returns:
            (action, rule_name) tuple
        """
        for rule in self.rules:
            action = rule.evaluate(state, phase)
            if action:
                return action, rule.name

        # Should never reach here due to fallback rule
        return "wait", "fallback"

    def get_rules_for_phase(self, phase: GamePhase) -> List[Rule]:
        """Get all rules that could apply to a phase."""
        return [r for r in self.rules if self._rule_applies_to_phase(r, phase)]

    def _rule_applies_to_phase(self, rule: Rule, phase: GamePhase) -> bool:
        """Check if a rule could apply to a phase (heuristic)."""
        # This is a simple heuristic - in practice, rules might apply to multiple phases
        if "explore" in rule.name.lower():
            return phase == GamePhase.EXPLORE
        if "combat" in rule.name.lower():
            return phase == GamePhase.COMBAT
        if "heal" in rule.name.lower():
            return phase in (GamePhase.HEALING, GamePhase.COMBAT, GamePhase.EXPLORE)
        if "loot" in rule.name.lower() or "chest" in rule.name.lower():
            return phase == GamePhase.LOOTING
        if "stairs" in rule.name.lower() or "transition" in rule.name.lower():
            return phase == GamePhase.TRANSITIONING
        return True  # Rules like fallback apply everywhere


# Pre-defined action sequences for common scenarios
ACTION_SEQUENCES = {
    "combat_basic": ["attack", "attack", "attack"],
    "combat_ranged": ["cast_fireball", "attack", "attack"],
    "heal_and_attack": ["cast_heal", "attack", "attack"],
    "loot_room": ["interact", "move_forward"],
    "descend": ["move_forward", "interact"],
}


def get_action_sequence(name: str) -> List[str]:
    """Get a named action sequence."""
    return ACTION_SEQUENCES.get(name, [])
