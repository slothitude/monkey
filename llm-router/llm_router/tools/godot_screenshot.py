"""Visual feedback tools for Godot games - screenshot capture and analysis.

Enables Claude to see running games for visual debugging and iteration.
Uses Playwright for browser-based screenshot capture of served web exports.
"""

import asyncio
import base64
import os
import time
from pathlib import Path
from typing import Optional

from llm_router.tools import ToolDefinition, ToolRegistry


async def godot_screenshot(
    game_url: str,
    output_path: str = "game_screenshot.png",
    wait_seconds: float = 2.0,
    click_to_focus: bool = True,
    full_page: bool = False,
    selector: str = None,
) -> dict:
    """
    Capture a screenshot of a running Godot web game for visual feedback.

    Opens the game URL in a headless browser, waits for it to load, and captures
    a screenshot. Returns the path to the saved image so it can be analyzed.

    Args:
        game_url: URL of the served game (e.g., http://localhost:8888)
        output_path: Where to save the screenshot PNG
        wait_seconds: Seconds to wait for game to load before capture (default: 2.0)
        click_to_focus: Click the canvas to ensure focus (default: True)
        full_page: Capture the full page instead of just the canvas (default: False)
        selector: CSS selector to capture specific element (default: canvas)

    Returns:
        Dict with screenshot info including path and dimensions
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "error": "Playwright not installed. Run: pip install playwright && playwright install chromium",
            "screenshot_path": None,
        }

    try:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})

            await page.goto(game_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(int(wait_seconds * 1000))

            if click_to_focus:
                canvas = await page.query_selector("canvas")
                if canvas:
                    box = await canvas.bounding_box()
                    if box:
                        await page.mouse.click(
                            box["x"] + box["width"] / 2,
                            box["y"] + box["height"] / 2,
                        )
                        await page.wait_for_timeout(500)

            # Capture screenshot
            if full_page:
                await page.screenshot(path=str(output_file), full_page=True, type="png")
                dimensions = {"width": 1280, "height": 720}
            elif selector:
                element = await page.query_selector(selector)
                if element:
                    await element.screenshot(path=str(output_file), type="png")
                    box = await element.bounding_box()
                    dimensions = {"width": int(box["width"]), "height": int(box["height"])}
                else:
                    await page.screenshot(path=str(output_file), type="png")
                    dimensions = {"width": 1280, "height": 720}
            else:
                # Default: capture canvas element
                canvas = await page.query_selector("canvas")
                if canvas:
                    await canvas.screenshot(path=str(output_file), type="png")
                    box = await canvas.bounding_box()
                    dimensions = {"width": int(box["width"]), "height": int(box["height"])}
                else:
                    await page.screenshot(path=str(output_file), type="png")
                    dimensions = {"width": 1280, "height": 720}

            await browser.close()

        file_size = output_file.stat().st_size

        return {
            "success": True,
            "screenshot_path": str(output_file.absolute()),
            "dimensions": dimensions,
            "file_size_bytes": file_size,
            "game_url": game_url,
            "message": f"Screenshot saved to {output_file.absolute()}. View this image to see the current game state.",
        }

    except Exception as e:
        return {
            "error": f"Failed to capture screenshot: {e}",
            "screenshot_path": None,
        }


async def godot_screenshot_sequence(
    game_url: str,
    output_dir: str = "game_screenshots",
    num_screenshots: int = 3,
    interval_seconds: float = 2.0,
    wait_seconds: float = 3.0,
    actions: list = None,
) -> dict:
    """
    Capture a sequence of screenshots while optionally performing actions.

    Useful for seeing game progression, animations, or the result of specific inputs.

    Args:
        game_url: URL of the served game
        output_dir: Directory to save screenshots
        num_screenshots: Number of screenshots to capture (default: 3)
        interval_seconds: Seconds between screenshots (default: 2.0)
        wait_seconds: Seconds to wait for game to load (default: 3.0)
        actions: Optional list of actions between screenshots.
                 Each action is a dict: {"type": "key_press", "key": "space"}
                 or {"type": "mouse_click", "x": 640, "y": 360}

    Returns:
        Dict with paths to all captured screenshots
    """
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        return {
            "error": "Playwright not installed. Run: pip install playwright && playwright install chromium",
        }

    try:
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        screenshots = []

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            page = await browser.new_page(viewport={"width": 1280, "height": 720})

            await page.goto(game_url, wait_until="domcontentloaded", timeout=15000)
            await page.wait_for_timeout(int(wait_seconds * 1000))

            # Click to focus
            canvas = await page.query_selector("canvas")
            canvas_box = None
            if canvas:
                canvas_box = await canvas.bounding_box()
                if canvas_box:
                    await page.mouse.click(
                        canvas_box["x"] + canvas_box["width"] / 2,
                        canvas_box["y"] + canvas_box["height"] / 2,
                    )
                    await page.wait_for_timeout(500)

            for i in range(num_screenshots):
                # Perform action if specified
                if actions and i < len(actions):
                    action = actions[i]
                    if action.get("type") == "key_press":
                        await page.keyboard.press(action.get("key", "Space"))
                    elif action.get("type") == "key_down":
                        await page.keyboard.down(action.get("key", "ArrowRight"))
                        await page.wait_for_timeout(int(action.get("duration_ms", 500)))
                        await page.keyboard.up(action.get("key", "ArrowRight"))
                    elif action.get("type") == "mouse_click":
                        await page.mouse.click(action.get("x", 640), action.get("y", 360))

                    await page.wait_for_timeout(int(interval_seconds * 500))

                # Capture screenshot
                filename = f"screenshot_{i+1:03d}.png"
                filepath = output_path / filename

                if canvas and canvas_box:
                    await canvas.screenshot(path=str(filepath), type="png")
                else:
                    await page.screenshot(path=str(filepath), type="png")

                screenshots.append(str(filepath.absolute()))
                await page.wait_for_timeout(int(interval_seconds * 1000))

            await browser.close()

        return {
            "success": True,
            "screenshots": screenshots,
            "count": len(screenshots),
            "output_dir": str(output_path.absolute()),
            "message": f"Captured {len(screenshots)} screenshots in {output_path.absolute()}",
        }

    except Exception as e:
        return {"error": f"Failed to capture screenshots: {e}"}


async def godot_compare_screenshots(
    screenshot_before: str,
    screenshot_after: str,
    output_path: str = "comparison.png",
) -> dict:
    """
    Compare two screenshots to highlight visual differences.

    Useful for verifying that a change had the expected visual effect.

    Args:
        screenshot_before: Path to the 'before' screenshot
        screenshot_after: Path to the 'after' screenshot
        output_path: Where to save the comparison image

    Returns:
        Dict with comparison results
    """
    try:
        from PIL import Image, ImageChops, ImageDraw
    except ImportError:
        return {"error": "PIL not installed. Run: pip install Pillow"}

    try:
        before = Image.open(screenshot_before)
        after = Image.open(screenshot_after)

        # Resize to match if needed
        if before.size != after.size:
            after = after.resize(before.size)

        # Compute difference
        diff = ImageChops.difference(before, after)

        # Count different pixels
        diff_pixels = 0
        total_pixels = before.size[0] * before.size[1]
        for pixel in diff.getdata():
            if sum(pixel[:3]) > 30:  # Threshold for visible difference
                diff_pixels += 1

        change_percent = (diff_pixels / total_pixels) * 100

        # Create side-by-side comparison
        comparison = Image.new("RGB", (before.size[0] * 3, before.size[1] + 30), "white")
        draw = ImageDraw.Draw(comparison)
        comparison.paste(before, (0, 30))
        comparison.paste(after, (before.size[0], 30))
        comparison.paste(diff, (before.size[0] * 2, 30))

        draw.text((5, 5), "BEFORE", fill="black")
        draw.text((before.size[0] + 5, 5), "AFTER", fill="black")
        draw.text((before.size[0] * 2 + 5, 5), f"DIFF ({change_percent:.1f}% changed)", fill="red" if change_percent > 5 else "green")

        comparison.save(output_path)

        return {
            "success": True,
            "comparison_path": str(Path(output_path).absolute()),
            "change_percent": round(change_percent, 2),
            "diff_pixels": diff_pixels,
            "total_pixels": total_pixels,
            "dimensions": {"width": before.size[0], "height": before.size[1]},
            "significant_change": change_percent > 1.0,
            "message": f"Comparison saved. {change_percent:.1f}% of pixels changed.",
        }

    except Exception as e:
        return {"error": f"Failed to compare screenshots: {e}"}


# =============================================================================
# Tool Definitions
# =============================================================================

GODOT_SCREENSHOT_DEF = ToolDefinition(
    name="godot_screenshot",
    description="Capture a screenshot of a running Godot web game for visual feedback. Use this to see what the game currently looks like after making changes. Returns the path to the saved image.",
    parameters={
        "type": "object",
        "required": ["game_url"],
        "properties": {
            "game_url": {"type": "string", "description": "URL of the served game (e.g., http://localhost:8888)"},
            "output_path": {"type": "string", "description": "Where to save the screenshot (default: game_screenshot.png)", "default": "game_screenshot.png"},
            "wait_seconds": {"type": "number", "description": "Seconds to wait for game to load (default: 2.0)", "default": 2.0},
            "click_to_focus": {"type": "boolean", "description": "Click the canvas to ensure focus (default: true)", "default": True},
            "full_page": {"type": "boolean", "description": "Capture full page instead of just the canvas (default: false)", "default": False},
            "selector": {"type": "string", "description": "CSS selector to capture specific element (default: canvas)"},
        },
    },
    function=godot_screenshot,
    category="godot",
    examples=[
        'godot_screenshot(game_url="http://localhost:8888")',
        'godot_screenshot(game_url="http://localhost:8080", output_path="my_game_state.png")',
    ],
)

GODOT_SCREENSHOT_SEQUENCE_DEF = ToolDefinition(
    name="godot_screenshot_sequence",
    description="Capture a sequence of screenshots while performing actions on a running game. Use to see game progression, animations, or results of specific inputs.",
    parameters={
        "type": "object",
        "required": ["game_url"],
        "properties": {
            "game_url": {"type": "string", "description": "URL of the served game"},
            "output_dir": {"type": "string", "description": "Directory to save screenshots (default: game_screenshots)", "default": "game_screenshots"},
            "num_screenshots": {"type": "integer", "description": "Number of screenshots to capture (default: 3)", "default": 3},
            "interval_seconds": {"type": "number", "description": "Seconds between screenshots (default: 2.0)", "default": 2.0},
            "wait_seconds": {"type": "number", "description": "Seconds to wait for game to load (default: 3.0)", "default": 3.0},
            "actions": {
                "type": "array",
                "items": {"type": "object"},
                "description": "Actions between screenshots: [{\"type\": \"key_press\", \"key\": \"Space\"}, {\"type\": \"key_down\", \"key\": \"ArrowRight\", \"duration_ms\": 500}]",
            },
        },
    },
    function=godot_screenshot_sequence,
    category="godot",
    examples=[
        'godot_screenshot_sequence(game_url="http://localhost:8888", num_screenshots=5)',
        'godot_screenshot_sequence(game_url="http://localhost:8888", actions=[{"type": "key_press", "key": "Space"}])',
    ],
)

GODOT_COMPARE_SCREENSHOTS_DEF = ToolDefinition(
    name="godot_compare_screenshots",
    description="Compare two game screenshots to highlight visual differences. Useful for verifying that a code change had the expected visual effect.",
    parameters={
        "type": "object",
        "required": ["screenshot_before", "screenshot_after"],
        "properties": {
            "screenshot_before": {"type": "string", "description": "Path to the 'before' screenshot"},
            "screenshot_after": {"type": "string", "description": "Path to the 'after' screenshot"},
            "output_path": {"type": "string", "description": "Where to save the comparison image (default: comparison.png)", "default": "comparison.png"},
        },
    },
    function=godot_compare_screenshots,
    category="godot",
    examples=[
        'godot_compare_screenshots(screenshot_before="before.png", screenshot_after="after.png")',
    ],
)


def register_godot_screenshot_tools(registry: ToolRegistry) -> None:
    """Register screenshot tools with a registry."""
    registry.register(GODOT_SCREENSHOT_DEF)
    registry.register(GODOT_SCREENSHOT_SEQUENCE_DEF)
    registry.register(GODOT_COMPARE_SCREENSHOTS_DEF)
