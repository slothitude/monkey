"""
Template Manager: Uses vision model to learn and create OpenCV templates.

The vision model is called SPARINGLY - only to create new templates.
Once created, FastDetector uses OpenCV for quick detection.
"""

import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

from ..config import GameAgentConfig


class TemplateManager:
    """Manages template creation using vision model and caching."""

    def __init__(self, config: Optional[GameAgentConfig] = None, llm_client: Any = None):
        self.config = config or GameAgentConfig()
        self.llm_client = llm_client
        self.template_cache: Dict[str, Dict] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load template cache from file."""
        if self.config.cache_file.exists():
            try:
                with open(self.config.cache_file, "r") as f:
                    self.template_cache = json.load(f)
            except (json.JSONDecodeError, IOError):
                self.template_cache = {}

    def _save_cache(self) -> None:
        """Save template cache to file."""
        self.config.cache_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config.cache_file, "w") as f:
            json.dump(self.template_cache, f, indent=2)

    def get_template(self, name: str) -> Optional[np.ndarray]:
        """Load a template image by name."""
        if name not in self.template_cache:
            # Try to load directly from templates directory
            template_path = self.config.templates_dir / f"{name}.png"
            if template_path.exists():
                template = cv2.imread(str(template_path))
                if template is not None:
                    self.template_cache[name] = {
                        "path": str(template_path),
                        "match_threshold": self.config.template_threshold,
                        "learned_at": datetime.now().isoformat()
                    }
                    self._save_cache()
                    return template
            return None

        cache_entry = self.template_cache[name]
        template_path = Path(cache_entry["path"])
        if template_path.exists():
            return cv2.imread(str(template_path))
        return None

    def save_template(
        self,
        name: str,
        image: np.ndarray,
        region: Optional[Tuple[int, int, int, int]] = None,
        description: str = "",
        threshold: Optional[float] = None
    ) -> str:
        """
        Save an image region as a template.

        Args:
            name: Template name (e.g., "health_bar", "enemy_goblin")
            image: Full screenshot or cropped image
            region: Optional (x, y, width, height) to crop from image
            description: What this template represents
            threshold: Match threshold override

        Returns:
            Path to saved template
        """
        # Crop if region provided
        if region:
            x, y, w, h = region
            template_img = image[y:y+h, x:x+w]
        else:
            template_img = image

        # Save template image
        template_path = self.config.templates_dir / f"{name}.png"
        cv2.imwrite(str(template_path), template_img)

        # Update cache
        self.template_cache[name] = {
            "path": str(template_path),
            "description": description,
            "match_threshold": threshold or self.config.template_threshold,
            "learned_at": datetime.now().isoformat()
        }
        self._save_cache()

        return str(template_path)

    async def learn_template_with_vision(
        self,
        screenshot: np.ndarray,
        region: Tuple[int, int, int, int],
        template_name: str,
        prompt: Optional[str] = None
    ) -> str:
        """
        Use vision model to understand and create a template.

        This is the "slow path" - only called when learning new elements.

        Args:
            screenshot: Full screenshot
            region: (x, y, width, height) of region to learn
            template_name: Name for the template
            prompt: Custom prompt for vision model

        Returns:
            Path to saved template
        """
        if not self.llm_client:
            raise ValueError("LLM client required for vision-based learning")

        x, y, w, h = region
        region_img = screenshot[y:y+h, x:x+w]

        # Convert to base64 for vision model
        _, buffer = cv2.imencode('.png', region_img)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        # Ask vision model what this is
        default_prompt = (
            f"Describe this game element. What is it? What does it represent in the game? "
            f"Be concise - one sentence max."
        )

        description = await self._call_vision_model(img_base64, prompt or default_prompt)

        # Determine threshold based on type
        threshold = self.config.template_threshold
        if "enemy" in template_name or "monster" in template_name:
            threshold = self.config.enemy_threshold
        elif any(ui in template_name for ui in ["bar", "button", "label"]):
            threshold = self.config.ui_threshold

        return self.save_template(template_name, screenshot, region, description, threshold)

    async def identify_ui_layout(self, screenshot: np.ndarray) -> Dict[str, Tuple[int, int, int, int]]:
        """
        Use vision model to identify UI element locations.

        Returns:
            Dict mapping element names to (x, y, width, height) regions
        """
        if not self.llm_client:
            raise ValueError("LLM client required for UI identification")

        # Convert to base64
        _, buffer = cv2.imencode('.png', screenshot)
        img_base64 = base64.b64encode(buffer).decode('utf-8')

        prompt = (
            "Identify and describe the locations of UI elements in this game screenshot. "
            "Return a JSON object where keys are element names (health_bar, mana_bar, "
            "floor_indicator, minimap, game_message_area, main_viewport) and values are "
            "[x, y, width, height] arrays representing bounding boxes. "
            "Only include elements you can clearly identify. Return ONLY valid JSON."
        )

        response = await self._call_vision_model(img_base64, prompt)

        # Parse JSON from response
        try:
            # Try to extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                layout = json.loads(json_match.group())
                # Convert lists to tuples
                return {k: tuple(v) for k, v in layout.items()}
        except (json.JSONDecodeError, TypeError):
            pass

        return {}

    async def _call_vision_model(self, image_base64: str, prompt: str) -> str:
        """Call vision model with image and prompt."""
        # This integrates with the llm-router's vision capabilities
        # The actual implementation depends on how llm-router handles vision

        if hasattr(self.llm_client, 'chat'):
            # Using llm-router client
            response = await self.llm_client.chat(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{image_base64}"
                            }
                        }
                    ]
                }],
                model=self.config.vision_model
            )
            return response.get("content", [{}])[0].get("text", "")

        raise NotImplementedError("LLM client must support vision input")

    def list_templates(self) -> Dict[str, Dict]:
        """List all known templates with their metadata."""
        return dict(self.template_cache)

    def delete_template(self, name: str) -> bool:
        """Delete a template."""
        if name in self.template_cache:
            template_path = Path(self.template_cache[name]["path"])
            if template_path.exists():
                template_path.unlink()
            del self.template_cache[name]
            self._save_cache()
            return True
        return False

    def update_threshold(self, name: str, threshold: float) -> bool:
        """Update match threshold for a template."""
        if name in self.template_cache:
            self.template_cache[name]["match_threshold"] = threshold
            self._save_cache()
            return True
        return False
