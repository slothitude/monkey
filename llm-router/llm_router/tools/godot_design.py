"""Game design prompt templates for Claude Code.

Encodes proven game design principles into structured prompts that guide
the AI to create games following best practices from the industry.

Based on:
- Sid Meier: "A game is a series of interesting decisions"
- Vlambeer: "Juice It or Lose It"
- Csikszentmihalyi: Flow theory
- Celeste postmortem: One mechanic, explored deeply
- Hades postmortem: Failure as design material
"""

from llm_router.tools import ToolDefinition, ToolRegistry


# =============================================================================
# Game Design Prompt Templates
# =============================================================================

DESIGN_PROMPTS = {
    "core_loop": {
        "name": "Core Loop Design",
        "description": "Design a game around a compelling core loop: action -> reward -> progression -> next action. The core loop must be fun within 60 seconds.",
        "prompt": """Design a game with a compelling core loop following this structure:

CORE LOOP: action -> reward -> progression -> next action

Requirements:
1. The core action must be immediately satisfying (fun within 60 seconds)
2. Every action presents a meaningful choice with clear trade-offs (Sid Meier principle)
3. Rewards are visible and create anticipation for the next action
4. Progression gives a sense of forward momentum

Output format:
- CORE ACTION: What the player does moment-to-moment
- REWARD: What they get for doing it well
- PROGRESSION: How the game changes as they improve
- FAILURE STATE: What happens when they fail (make it a teaching moment, not punishment)
- 60-SECOND TEST: Describe exactly what a new player experiences in their first minute
- FIRST DECISION: The first meaningful choice the player makes (must not be obvious)
- JUICE PLAN: What feedback effects amplify the core action (screen shake, particles, sounds)
""",
    },

    "one_mechanic": {
        "name": "One Mechanic, Explored Deeply",
        "description": "Design a game around a single mechanic explored through increasingly complex situations. Like Braid (time reversal), Celeste (dash + climb), Undertale (spare or kill).",
        "prompt": """Design a game around ONE core mechanic, explored deeply through 10 levels.

Design principle: Do one thing better than anyone else.

Requirements:
1. Choose ONE mechanic. Not two. Not three. ONE.
2. Level 1: Introduce the mechanic in its simplest form (no distractions)
3. Level 2-3: Add one twist per level (new context, not new mechanics)
4. Level 4-5: Combine previously learned applications
5. Level 6-7: Subvert expectations (the mechanic works differently in a new context)
6. Level 8-9: Mastery challenges (require precise execution of learned skills)
7. Level 10: Grand finale that tests everything

Output format:
- MECHANIC: The single core mechanic (one sentence)
- WHY IT WORKS: Why this mechanic creates interesting decisions
- LEVEL PROGRESSION: For each of 10 levels:
  - Level N: What new situation/context is introduced
  - Player learns: What understanding this level builds
  - Difficulty source: Where the challenge comes from (not just "harder")
- SKILL CEILING: How the mechanic supports expert play
- FLOW CHANNEL: How you keep players between boredom and anxiety (match challenge to skill)
- DEATH DESIGN: How failure works (fast restart, encouraging, teaches something)
""",
    },

    "arcade_score": {
        "name": "Arcade Score Attack",
        "description": "Design a score-based arcade game with escalating difficulty, risk/reward, and replayability. Think Tetris, Spelunky, Vampire Survivors.",
        "prompt": """Design an arcade score-attack game with infinite replayability.

Core principle: Easy to learn, hard to master. The game never ends - you just get better.

Requirements:
1. Controls: Maximum 2-3 inputs (arrow keys + 1 button)
2. Score is the primary motivator (display it prominently)
3. Difficulty escalates continuously but predictably
4. Risk/reward: Player chooses between safe low-score and risky high-score plays
5. Near-miss excitement: Game should frequently create "I almost died!" moments
6. Each run is 3-10 minutes (short enough to try again)

Output format:
- CONCEPT: One-sentence game concept
- CONTROLS: Exact key bindings
- CORE LOOP: The second-to-second gameplay
- SCORING: How score is calculated (with multipliers/combos)
- RISK/REWARD: 3 specific situations where the player must choose safety vs. points
- DIFFICULTY RAMP: How the game gets harder over time (specific parameters that change)
- ENEMY TYPES: 3-5 enemy types that create different tactical situations
- POWER-UPS: 3-5 power-ups that change how the game feels temporarily
- JUICE: What visual/audio effects make scoring feel amazing
- HIGH SCORE HOOK: What makes the player want "just one more run"
""",
    },

    "platformer": {
        "name": "2D Platformer",
        "description": "Design a 2D platformer with tight controls, fair challenges, and satisfying movement. Think Celeste, Super Meat Boy, Hollow Knight.",
        "prompt": """Design a 2D platformer with tight, satisfying movement.

Core principle: Movement itself should feel good before any level design happens.

Requirements:
1. Player physics: Responsive, predictable, with air control
2. Coyote time: Allow jumping briefly after leaving a platform
3. Jump buffer: Queue a jump if pressed slightly before landing
4. Variable jump height: Tap for short hop, hold for full jump
5. Every death is the player's fault and immediately obvious why
6. Respawn is instant (within 1 second)

Output format:
- PLAYER ABILITIES: Movement mechanics (max 3 - dash is allowed)
- PHYSICS: Exact values for gravity, jump force, max speed, acceleration
- LEVEL 1 (Tutorial): Step-by-step what the player learns in the first screen
- LEVEL PROGRESSION: How 5 levels introduce new situations
- OBSTACLE TYPES: 4-6 obstacle types that create different challenges
- ENEMY TYPES: 2-3 enemies that interact with the platforming differently
- CHECKPOINT PLACEMENT: Rules for where checkpoints go
- COYOTE TIME: Frames of grace period (recommend 6)
- JUICE: Movement feedback (squash on land, stretch on jump, particles on dash)
- DEATH ANIMATION: Fast, encouraging, teaches the player
""",
    },

    "shooter": {
        "name": "Space/Arcade Shooter",
        "description": "Design a top-down or side-scrolling shooter with satisfying weapons, enemy patterns, and escalating action. Think Geometry Wars, Enter the Gungeon.",
        "prompt": """Design a shooter where every pull of the trigger feels satisfying.

Core principle: The weapon is the star. Everything else supports the fantasy of power.

Requirements:
1. Weapon must feel powerful from the first shot (sound, visual, screen shake)
2. Enemies telegraph attacks (player can always see danger coming)
3. Bullet patterns are readable (player can see gaps to navigate through)
4. Every enemy type teaches the player something new
5. Boss fights are the exam on everything learned so far

Output format:
- CONCEPT: Ship/character concept and theme
- WEAPON: Primary weapon mechanics (fire rate, spread, damage feel)
- MOVEMENT: How the player moves (speed, dodge/dash ability)
- ENEMY TYPES: 5 enemy types, each serving a purpose:
  - Name, behavior, what it teaches the player, threat level
- BULLET PATTERNS: 3-4 patterns enemies use (with gaps for dodging)
- WAVE DESIGN: How 5 waves escalate difficulty
- BOSS: Phase-based boss fight design
- POWER-UPS: What the player can collect and how it changes gameplay
- SCORING: Combo system or multiplier mechanics
- JUICE: Hit effects, kill effects, combo celebrations
- DIFFICULTY CURVE: How parameters change per wave
""",
    },

    "puzzle": {
        "name": "Puzzle Game",
        "description": "Design a puzzle game where the player discovers rules through play. Think Portal, Baba Is You, The Witness.",
        "prompt": """Design a puzzle game where understanding IS the gameplay.

Core principle: The puzzle should teach its own rules. No tutorials, no text.

Requirements:
1. First puzzle is trivially easy and teaches one rule
2. Each puzzle adds exactly one new idea
3. Solution should feel like an insight, not trial-and-error
4. Player should have an 'aha!' moment in each puzzle
5. Failed attempts still teach something about the rules

Output format:
- CORE MECHANIC: The single rule/system the player manipulates
- RULE DISCOVERY: How the first 3 puzzles teach the rules without words
- PUZZLE PROGRESSION: 8 puzzles, each building on the last:
  - Puzzle N: What new idea this puzzle introduces
  - Hint: What the player should notice
  - AHA moment: The insight needed to solve it
- FAILURE STATES: What happens when the player gets it wrong
- FEEDBACK: How the game communicates success/failure without text
- SKILL COMPONENT: Is there a time/movement limit or is it pure logic?
- DIFFICULTY SPIKE PREVENTION: How to help stuck players
""",
    },

    "roguelike": {
        "name": "Roguelike Run",
        "description": "Design a roguelike with procedural generation, permadeath, and run-defining choices. Think Hades, Slay the Spire, Dead Cells.",
        "prompt": """Design a roguelike where every run tells a different story.

Core principle: Death is a feature, not a bug. Make dying interesting.

Requirements:
1. Runs are 15-30 minutes
2. Every run offers different strategic choices
3. Permadeath is permanent but progress feels earned
4. The player should always feel like they're learning
5. Meta-progression: Something carries between runs (not power, but options)

Output format:
- CORE LOOP: What happens in a single run
- ROOM TYPES: 5-6 room types that create different situations
- ENEMY VARIETY: How enemies scale and introduce new threats
- BUILD DIVERSITY: 3 distinct playstyles the player can pursue
- CHOICE POINTS: Where the player makes run-defining decisions
- DEATH REWARD: What the player gets for dying (narrative, unlocks, knowledge)
- META PROGRESSION: What carries between runs
- PROCEDURAL RULES: How levels are generated to ensure fairness
- DIFFICULTY SCALING: How the run gets harder over time
- BALANCE: How to make every build viable but different in playstyle
""",
    },
}


def godot_design_game(
    game_type: str,
    theme: str = "",
    constraints: str = "",
    reference_game: str = "",
) -> dict:
    """
    Get a structured game design prompt based on proven design principles.

    These prompts encode industry best practices from GDC talks and postmortems.
    They force the AI to follow good design patterns rather than generic game generation.

    Game types:
    - core_loop: Design around action->reward->progression loop
    - one_mechanic: One mechanic explored through 10 levels (Celeste approach)
    - arcade_score: Score-attack with escalating difficulty
    - platformer: 2D platformer with tight movement
    - shooter: Space/arcade shooter with satisfying weapons
    - puzzle: Puzzle game with rule discovery
    - roguelike: Roguelike with permadeath and run variety

    Args:
        game_type: Type of game design prompt to generate
        theme: Optional theme/flavor to guide the design
        constraints: Optional constraints (e.g., "no combat", "mouse only")
        reference_game: Optional game to use as reference point

    Returns:
        Dict with the structured design prompt
    """
    if game_type not in DESIGN_PROMPTS:
        available = ", ".join(DESIGN_PROMPTS.keys())
        return {"error": f"Unknown game type '{game_type}'. Available: {available}"}

    template = DESIGN_PROMPTS[game_type]

    prompt = template["prompt"]

    # Add theme if specified
    if theme:
        prompt = f"Theme: {theme}\n\n{prompt}"

    # Add constraints if specified
    if constraints:
        prompt += f"""

ADDITIONAL CONSTRAINTS:
{constraints}
"""

    # Add reference if specified
    if reference_game:
        prompt += f"""

REFERENCE GAME: {reference_game}
Use this as inspiration. Do not copy it, but learn from what makes it work.
"""

    return {
        "game_type": game_type,
        "template_name": template["name"],
        "description": template["description"],
        "prompt": prompt,
        "principles": {
            "interesting_decisions": "Every moment should present a meaningful choice with clear trade-offs (Sid Meier)",
            "juice_matters": "Screen shake, particles, sounds change perception without changing gameplay (Vlambeer)",
            "flow_channel": "Match challenge to skill - not too easy (boring), not too hard (anxiety) (Csikszentmihalyi)",
            "explore_deeply": "One mechanic explored deeply beats many mechanics explored shallowly (Celeste)",
            "fun_first": "If core mechanic isn't fun in 5 minutes, pivot. No amount of art fixes unfun mechanics.",
        },
    }


def godot_list_design_prompts() -> dict:
    """
    List all available game design prompt templates.

    Returns:
        Dict with all available templates
    """
    templates = {}
    for key, value in DESIGN_PROMPTS.items():
        templates[key] = {
            "name": value["name"],
            "description": value["description"],
        }

    return {
        "templates": templates,
        "count": len(templates),
        "usage": "Use godot_design_game(game_type='core_loop', theme='space', reference_game='Geometry Wars') to get a structured prompt",
    }


def godot_design_review(
    game_description: str,
) -> dict:
    """
    Review a game design against proven design principles.

    Checks for common design mistakes and suggests improvements.

    Args:
        game_description: Description of the game to review

    Returns:
        Dict with design review feedback
    """
    review = {
        "principles": [],
        "warnings": [],
        "suggestions": [],
    }

    desc_lower = game_description.lower()

    # Check for interesting decisions
    if any(word in desc_lower for word in ["click", "tap", "auto", "idle", "incremental"]):
        if "choice" not in desc_lower and "decision" not in desc_lower:
            review["warnings"].append(
                "LOW DECISION DENSITY: If the player's optimal move is always obvious "
                "(e.g., always click), there are no interesting decisions. "
                "Add trade-offs: clicking A helps short-term but hurts long-term."
            )

    # Check for juice
    if not any(word in desc_lower for word in ["shake", "particle", "flash", "sound", "effect", "juice"]):
        review["suggestions"].append(
            "NO JUICE MENTIONED: Add screen shake, particles, hit flashes, squash-and-stretch. "
            "Same mechanics + juice = dramatically different feel. (Vlambeer)"
        )

    # Check for failure design
    if not any(word in desc_lower for word in ["death", "fail", "lose", "game over", "restart"]):
        review["warnings"].append(
            "NO FAILURE STATE: What happens when the player makes mistakes? "
            "Failure is design material - Hades made death a narrative reward, "
            "Celeste made death fast and encouraging."
        )
    else:
        review["principles"].append("Has a failure state - good.")

    # Check for difficulty curve
    if not any(word in desc_lower for word in ["difficulty", "harder", "level", "wave", "progress"]):
        review["warnings"].append(
            "NO DIFFICULTY PROGRESSION: Games need escalating challenge to maintain flow. "
            "Too easy = boredom, too hard = anxiety. Use a curve that matches player skill growth."
        )

    # Check for core loop clarity
    if any(word in desc_lower for word in ["loop", "cycle", "repeat"]):
        review["principles"].append("Core loop is mentioned - good foundation.")
    else:
        review["suggestions"].append(
            "CORE LOOP UNCLEAR: Define the core loop: action -> reward -> progression -> next action. "
            "If this loop isn't fun in 60 seconds, nothing else matters."
        )

    # Check for too many mechanics
    mechanic_words = ["mechanic", "system", "feature", "ability", "power", "skill"]
    mechanic_count = sum(1 for w in mechanic_words if w in desc_lower)
    if mechanic_count >= 4:
        review["warnings"].append(
            "TOO MANY MECHANICS: Consider focusing on ONE mechanic explored deeply. "
            "Braid (time reversal), Celeste (dash), Undertale (spare/kill). "
            "More mechanics != more fun. Depth > breadth."
        )

    # Check for player feedback
    if not any(word in desc_lower for word in ["feedback", "visual", "audio", "sound", "animation"]):
        review["suggestions"].append(
            "NO FEEDBACK PLAN: Every player action needs immediate, visible feedback. "
            "Jump -> squash/stretch. Hit -> flash + shake. Score -> particle burst + sound."
        )

    return {
        "review": review,
        "score": {
            "principles_met": len(review["principles"]),
            "warnings": len(review["warnings"]),
            "suggestions": len(review["suggestions"]),
        },
        "summary": f"Found {len(review['principles'])} strengths, {len(review['warnings'])} warnings, {len(review['suggestions'])} suggestions",
    }


# =============================================================================
# Tool Definitions
# =============================================================================

GODOT_DESIGN_GAME_DEF = ToolDefinition(
    name="godot_design_game",
    description="Get a structured game design prompt based on proven design principles. These prompts encode industry best practices (Sid Meier, Vlambeer, Csikszentmihalyi). Types: core_loop, one_mechanic, arcade_score, platformer, shooter, puzzle, roguelike.",
    parameters={
        "type": "object",
        "required": ["game_type"],
        "properties": {
            "game_type": {
                "type": "string",
                "description": "Type: core_loop, one_mechanic, arcade_score, platformer, shooter, puzzle, roguelike",
                "enum": ["core_loop", "one_mechanic", "arcade_score", "platformer", "shooter", "puzzle", "roguelike"],
            },
            "theme": {"type": "string", "description": "Optional theme to guide the design (e.g., 'space', 'underwater')"},
            "constraints": {"type": "string", "description": "Optional constraints (e.g., 'mouse only', 'no combat')"},
            "reference_game": {"type": "string", "description": "Optional game to use as reference"},
        },
    },
    function=godot_design_game,
    category="godot",
    examples=[
        'godot_design_game(game_type="platformer", theme="haunted mansion")',
        'godot_design_game(game_type="arcade_score", reference_game="Geometry Wars")',
        'godot_design_game(game_type="one_mechanic", constraints="no combat, puzzle-focused")',
    ],
)

GODOT_LIST_DESIGN_DEF = ToolDefinition(
    name="godot_list_design_prompts",
    description="List all available game design prompt templates with descriptions.",
    parameters={
        "type": "object",
        "properties": {},
    },
    function=godot_list_design_prompts,
    category="godot",
)

GODOT_DESIGN_REVIEW_DEF = ToolDefinition(
    name="godot_design_review",
    description="Review a game design description against proven design principles. Checks for common mistakes like low decision density, missing juice, unclear core loop.",
    parameters={
        "type": "object",
        "required": ["game_description"],
        "properties": {
            "game_description": {"type": "string", "description": "Description of the game to review"},
        },
    },
    function=godot_design_review,
    category="godot",
)


def register_godot_design_tools(registry: ToolRegistry) -> None:
    """Register game design tools with a registry."""
    registry.register(GODOT_DESIGN_GAME_DEF)
    registry.register(GODOT_LIST_DESIGN_DEF)
    registry.register(GODOT_DESIGN_REVIEW_DEF)
