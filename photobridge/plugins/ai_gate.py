"""
AI content gate plugin.

Uses Google Cloud Vision SafeSearch to screen images before they reach
Instagram. Sets context flags that Instagram (and any future gated plugin)
reads to decide whether to proceed.

Configurable likelihood threshold — any SafeSearch category at or above
the threshold causes rejection. Default is POSSIBLE which catches all but
very unlikely detections.
"""

import logging
import os

from google.cloud import vision

from photobridge.plugins.base import BasePlugin

logger = logging.getLogger(__name__)

# Maps Vision SafeSearch likelihood enum values to comparable integers
LIKELIHOOD_SCORE = {
    "UNKNOWN": 0,
    "VERY_UNLIKELY": 1,
    "UNLIKELY": 2,
    "POSSIBLE": 3,
    "LIKELY": 4,
    "VERY_LIKELY": 5,
}


class AIGatePlugin(BasePlugin):
    name = "ai_gate"
    priority = 15

    def __init__(self, settings):
        super().__init__(settings)
        self._client = None
        threshold_name = os.getenv("PLUGIN_AI_GATE_THRESHOLD", "POSSIBLE").upper()
        self._threshold = LIKELIHOOD_SCORE.get(threshold_name, 3)

    def _get_client(self):
        if self._client is None:
            self._client = vision.ImageAnnotatorClient()
        return self._client

    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str,
        context: dict,
    ) -> str:
        client = self._get_client()
        image = vision.Image(content=image_bytes)
        response = client.safe_search_detection(image=image)

        if response.error.message:
            logger.warning("Vision API error for %s: %s", filename, response.error.message)
            return ""

        safe = response.safe_search_annotation
        checks = {
            "adult content": safe.adult,
            "violent content": safe.violence,
            "racy content": safe.racy,
        }

        violations = []
        for label, likelihood in checks.items():
            score = int(likelihood)
            if score >= self._threshold:
                likelihood_name = likelihood.name if hasattr(likelihood, "name") else str(likelihood)
                violations.append(f"{label} ({likelihood_name.lower().replace('_', ' ')})")

        if violations:
            reason = "Image flagged for: " + ", ".join(violations)
            context["ai_gate_rejected"] = True
            context["ai_gate_reason"] = reason
            logger.info("AI gate rejected %s: %s", filename, reason)
        else:
            logger.info("AI gate approved %s", filename)

        return ""
