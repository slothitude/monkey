"""
Browser control using Playwright for game interaction.
"""

import asyncio
import base64
import io
from typing import Optional, Tuple

import numpy as np
from PIL import Image

from .config import GameAgentConfig


class BrowserController:
    """Controls a browser for playing the game using Playwright."""

    def __init__(self, config: Optional[GameAgentConfig] = None):
        self.config = config or GameAgentConfig()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def start(self) -> None:
        """Start the browser."""
        from playwright.async_api import async_playwright

        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=False,  # Visible for debugging
            args=["--disable-web-security", "--disable-features=IsolateOrigins,site-per-process"]
        )
        self._context = await self._browser.new_context()
        self._page = await self._context.new_page()

        # Set viewport size
        await self._page.set_viewport_size({"width": 1024, "height": 768})

    async def navigate(self, url: Optional[str] = None) -> None:
        """Navigate to the game URL."""
        url = url or self.config.game_url
        await self._page.goto(url, wait_until="networkidle")
        await asyncio.sleep(self.config.load_wait_ms / 1000)

    async def take_screenshot(self) -> np.ndarray:
        """Take a screenshot and return as numpy array."""
        screenshot_bytes = await self._page.screenshot(type="png")
        image = Image.open(io.BytesIO(screenshot_bytes))
        return np.array(image)

    async def take_screenshot_base64(self) -> str:
        """Take a screenshot and return as base64 string."""
        screenshot_bytes = await self._page.screenshot(type="png")
        return base64.b64encode(screenshot_bytes).decode("utf-8")

    async def press_key(self, key: str) -> None:
        """Press a key."""
        await self._page.keyboard.press(key)
        await asyncio.sleep(self.config.action_delay_ms / 1000)

    async def send_keys(self, text: str) -> None:
        """Type text."""
        await self._page.keyboard.type(text)
        await asyncio.sleep(self.config.action_delay_ms / 1000)

    async def click(self, x: int, y: int) -> None:
        """Click at coordinates."""
        await self._page.mouse.click(x, y)
        await asyncio.sleep(self.config.action_delay_ms / 1000)

    async def evaluate(self, script: str) -> any:
        """Execute JavaScript in the page."""
        return await self._page.evaluate(script)

    async def get_game_state_js(self) -> dict:
        """Try to extract game state from JavaScript (if available)."""
        try:
            result = await self._page.evaluate("""
                () => {
                    if (window.gameState) return window.gameState;
                    if (window.game && window.game.state) return window.game.state;
                    if (window.player) return {
                        health: window.player.health,
                        mana: window.player.mana,
                        floor: window.player.floor
                    };
                    return null;
                }
            """)
            return result
        except Exception:
            return None

    async def close(self) -> None:
        """Close the browser."""
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()
        self._page = None
        self._context = None
        self._browser = None
        self._playwright = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()


# Key mappings for common actions
KEYS = {
    "move_forward": "ArrowUp",
    "move_backward": "ArrowDown",
    "turn_left": "ArrowLeft",
    "turn_right": "ArrowRight",
    "attack": " ",  # Space
    "interact": "e",
    "cast_fireball": "1",
    "cast_heal": "2",
    "use_potion": "3",
    "pause": "Escape",
    "wait": ".",  # Period key for waiting
}
