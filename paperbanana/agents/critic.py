"""Critic Agent: Evaluates generated images and provides revision feedback."""

from __future__ import annotations

import json
from typing import Optional

import structlog

from paperbanana.agents.base import BaseAgent
from paperbanana.core.types import CritiqueResult, DiagramType
from paperbanana.core.utils import load_image
from paperbanana.providers.base import VLMProvider

logger = structlog.get_logger()


class CriticAgent(BaseAgent):
    """Evaluates generated diagrams and provides specific revision feedback.

    Compares the generated image against the source context to identify
    faithfulness, conciseness, readability, and aesthetic issues.
    """

    def __init__(self, vlm_provider: VLMProvider, prompt_dir: str = "prompts"):
        super().__init__(vlm_provider, prompt_dir)

    @property
    def agent_name(self) -> str:
        return "critic"

    async def run(
        self,
        image_path: str,
        description: str,
        source_context: str,
        caption: str,
        diagram_type: DiagramType = DiagramType.METHODOLOGY,
        user_feedback: Optional[str] = None,
    ) -> CritiqueResult:
        """Evaluate a generated image and provide revision feedback.

        Args:
            image_path: Path to the generated image.
            description: The description used to generate the image.
            source_context: Original methodology text.
            caption: Figure caption / communicative intent.
            diagram_type: Type of diagram.
            user_feedback: Optional user comments for the critic to consider.

        Returns:
            CritiqueResult with evaluation and optional revised description.
        """
        # Load the image
        image = load_image(image_path)

        prompt_type = "diagram" if diagram_type == DiagramType.METHODOLOGY else "plot"
        template = self.load_prompt(prompt_type)
        prompt = self.format_prompt(
            template,
            source_context=source_context,
            caption=caption,
            description=description,
        )

        if user_feedback:
            prompt += (
                f"\n\nAdditional user feedback to consider in your evaluation:\n{user_feedback}"
            )

        logger.info("Running critic agent", image_path=image_path)

        response = await self.vlm.generate(
            prompt=prompt,
            images=[image],
            temperature=0.3,
            max_tokens=4096,
            response_format="json",
        )

        critique = self._parse_response(response)
        logger.info(
            "Critic evaluation complete",
            needs_revision=critique.needs_revision,
            summary=critique.summary,
        )
        return critique

    def _parse_response(self, response: str) -> CritiqueResult:
        """Parse the VLM response into a CritiqueResult."""
        cleaned = response.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            if cleaned.lower().startswith("json"):
                cleaned = cleaned[4:].strip()

        # Try direct JSON parse first, then fallback to first object slice.
        candidates = [cleaned]
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidates.append(cleaned[start : end + 1])

        parsed: dict | None = None
        try:
            for candidate in candidates:
                try:
                    maybe = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(maybe, dict):
                    parsed = maybe
                    break
            if parsed is None:
                raise json.JSONDecodeError("No valid JSON object found", cleaned, 0)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse critic response", error=str(e))
            return CritiqueResult(
                critic_suggestions=[
                    "Critic output was not valid JSON; continue refining with a safer, simpler description."
                ],
                revised_description=None,
            )

        suggestions = parsed.get("critic_suggestions", [])
        if not isinstance(suggestions, list):
            suggestions = [str(suggestions)]
        normalized = [str(item).strip() for item in suggestions if str(item).strip()]

        revised = parsed.get("revised_description")
        if revised is not None:
            revised = str(revised).strip() or None

        return CritiqueResult(
            critic_suggestions=normalized,
            revised_description=revised,
        )
