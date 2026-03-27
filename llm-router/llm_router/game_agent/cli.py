#!/usr/bin/env python
"""
CLI entry point for the Game-Playing Agent.

Usage:
    python -m llm_router.game_agent play [--url URL] [--train N]
    python -m llm_router.game_agent learn
    python -m llm_router.game_agent detect --image PATH
    python -m llm_router.game_agent templates
"""

import argparse
import asyncio
import json
import logging
from pathlib import Path

from .config import GameAgentConfig
from .player import GamePlayer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


async def play_game(args):
    """Play the game."""
    config = GameAgentConfig(game_url=args.url or "http://localhost:8888")

    async with GamePlayer(config=config, use_q_learning=not args.no_learning) as player:
        # Initial learning if needed
        if args.learn_first:
            logger.info("Running initial template learning...")
            results = await player.initial_learning()
            logger.info(f"Templates learned: {list(results.keys())}")

        if args.train:
            # Training mode
            logger.info(f"Training for {args.train} games...")
            results = await player.train(num_games=args.train)

            wins = sum(1 for r in results if r.victory)
            logger.info(f"Training complete: {wins}/{args.train} wins ({wins/args.train*100:.0f}%)")

            for i, result in enumerate(results):
                logger.info(
                    f"Game {i+1}: Victory={result.victory}, "
                    f"Floor={result.stats.floors_reached}, "
                    f"Duration={result.stats.duration_seconds:.1f}s"
                )
        else:
            # Single game
            logger.info("Starting game...")
            result = await player.play_game(use_rules=True, explore=not args.no_explore)

            print("\n" + "="*50)
            print("GAME OVER" if not result.victory else "VICTORY!")
            print("="*50)
            print(f"Duration: {result.stats.duration_seconds:.1f}s")
            print(f"Frames: {result.stats.frames_processed}")
            print(f"Actions: {result.stats.actions_taken}")
            print(f"Floor: {result.stats.floors_reached}")
            print(f"Enemies Killed: {result.stats.enemies_killed}")
            print(f"Chests Opened: {result.stats.chests_opened}")
            if result.error:
                print(f"Error: {result.error}")


async def learn_templates(args):
    """Learn templates from the game."""
    config = GameAgentConfig(game_url=args.url or "http://localhost:8888")

    async with GamePlayer(config=config) as player:
        logger.info("Starting template learning...")
        results = await player.initial_learning()

        print("\nTemplates learned:")
        for name, path in results.items():
            print(f"  {name}: {path}")


def detect_state(args):
    """Detect game state from an image file."""
    from .vision.fast_detector import FastDetector

    config = GameAgentConfig()
    detector = FastDetector(config)

    logger.info(f"Detecting state from: {args.image}")
    state = detector.detect_from_file(args.image)

    print("\nDetected State:")
    print(f"  Health: {state.health_pct*100:.0f}%")
    print(f"  Mana: {state.mana_pct*100:.0f}%")
    print(f"  Floor: {state.floor}")
    print(f"  Enemy: {state.enemy_ahead} ({state.enemy_type})")
    print(f"  Stairs: {state.stairs_ahead}")
    print(f"  Chest: {state.chest_ahead}")
    print(f"  Game Over: {state.game_over}")
    print(f"  Victory: {state.victory}")
    print(f"\nDetection time: {state.detection_time_ms:.1f}ms")


def list_templates(args):
    """List all learned templates."""
    from .vision.template_manager import TemplateManager

    config = GameAgentConfig()
    manager = TemplateManager(config)

    templates = manager.list_templates()

    if not templates:
        print("No templates found.")
        return

    print(f"\nTemplates ({len(templates)}):")
    for name, meta in templates.items():
        print(f"  {name}:")
        print(f"    Path: {meta.get('path', 'N/A')}")
        print(f"    Threshold: {meta.get('match_threshold', 'N/A')}")
        print(f"    Description: {meta.get('description', 'N/A')}")


def main():
    parser = argparse.ArgumentParser(
        description="Game-Playing Agent for Dungeon Crawler"
    )
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Play command
    play_parser = subparsers.add_parser("play", help="Play the game")
    play_parser.add_argument("--url", help="Game URL")
    play_parser.add_argument("--train", type=int, help="Number of training games")
    play_parser.add_argument("--no-learning", action="store_true", help="Disable Q-learning")
    play_parser.add_argument("--no-explore", action="store_true", help="Disable exploration")
    play_parser.add_argument("--learn-first", action="store_true", help="Run template learning first")

    # Learn command
    learn_parser = subparsers.add_parser("learn", help="Learn templates from game")
    learn_parser.add_argument("--url", help="Game URL")

    # Detect command
    detect_parser = subparsers.add_parser("detect", help="Detect state from image")
    detect_parser.add_argument("image", help="Path to image file")

    # Templates command
    subparsers.add_parser("templates", help="List learned templates")

    args = parser.parse_args()

    if args.command == "play":
        asyncio.run(play_game(args))
    elif args.command == "learn":
        asyncio.run(learn_templates(args))
    elif args.command == "detect":
        detect_state(args)
    elif args.command == "templates":
        list_templates(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
