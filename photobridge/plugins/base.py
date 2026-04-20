"""
Base class for all photobridge destination plugins.

To add a new destination:
1. Create photobridge/plugins/<name>.py
2. Subclass BasePlugin and implement upload()
3. Add an instance to the PLUGINS list in main.py

Each plugin reads its own enable/tag config from environment variables:
  PLUGIN_<NAME>_ENABLED      true/false   (default: true)
  PLUGIN_<NAME>_REQUIRE_TAG  true/false   (default: false — process all photos)
  PLUGIN_<NAME>_TAG          e.g. #instagram  (default: #<name>)

When REQUIRE_TAG is false, all photos are sent to this destination.
When REQUIRE_TAG is true, only photos whose caption contains TAG are sent.
"""

import logging
import os
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)


class BasePlugin(ABC):
    # Subclasses must set this — used for config env var names and logging
    name: str = ""

    # Lower priority runs first. WordPress=10, Drive=10, Instagram=20.
    # Instagram is higher because it depends on the WordPress public URL.
    priority: int = 10

    def __init__(self, settings):
        self._settings = settings

    # --- Config helpers (read PLUGIN_<NAME>_* env vars) ---

    def _env(self, suffix: str, default: str = "") -> str:
        key = f"PLUGIN_{self.name.upper()}_{suffix}"
        return os.getenv(key, default)

    @property
    def enabled(self) -> bool:
        return self._env("ENABLED", "true").lower() == "true"

    @property
    def require_tag(self) -> bool:
        return self._env("REQUIRE_TAG", "false").lower() == "true"

    @property
    def tag(self) -> str:
        return self._env("TAG", f"#{self.name.lower()}")

    # --- Processing gate ---

    def should_process(self, caption: str) -> bool:
        """Return True if this plugin should handle this photo."""
        if not self.enabled:
            return False
        if self.require_tag:
            return self.tag.lower() in caption.lower()
        return True

    # --- Interface ---

    @abstractmethod
    def upload(
        self,
        image_bytes: bytes,
        filename: str,
        mime_type: str,
        caption: str,
        context: dict,
    ) -> str:
        """
        Upload the image and return a public URL (or empty string).

        context: dict accumulating results from higher-priority plugins,
                 keyed by plugin name. e.g. context['wordpress'] = 'https://...'
        """
        ...
