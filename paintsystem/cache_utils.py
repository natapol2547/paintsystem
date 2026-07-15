"""Shared JSON file caching utilities for the Paint System addon."""

import bpy
import json
import os
import time
from typing import Any, Dict, Optional

from ..utils.logging import get_logger

logger = get_logger(__name__)


def _get_cache_dir() -> str:
    # (bl_ext.<repo>.<pkg>). __package__ here is the nested submodule
    # (bl_ext.<repo>.<pkg>.paintsystem), so trim it back to the extension root.
    extension_package = ".".join(__package__.split(".")[:3])
    return bpy.utils.extension_path_user(extension_package, path="", create=True)



class JsonFileCache:
    """A simple JSON file cache with timestamp-based expiration.
    
    Args:
        filename: Name of the cache file (stored in the addon root directory).
        label: Human-readable label used in log messages (e.g. "version").
    """

    def __init__(self, filename: str, label: str = "cache"):
        self._filename = filename
        self._label = label

    @property
    def path(self) -> str:
        return os.path.join(_get_cache_dir(), self._filename)

    def save(self, data: Dict[str, Any]) -> None:
        """Save *data* to the cache file, stamped with the current time."""
        cache_data = {
            "timestamp": time.time(),
            "data": data,
        }
        try:
            with open(self.path, 'w') as f:
                json.dump(cache_data, f, indent=2)
        except Exception as e:
            logger.error(f"Error saving {self._label} cache: {e}")

    def load(self, max_age_seconds: float) -> Optional[Dict[str, Any]]:
        """Load cached data if the file exists and is younger than *max_age_seconds*.
        
        Returns:
            The cached data dict, or ``None`` if the cache is missing, expired, or corrupt.
        """
        if not os.path.exists(self.path):
            return None

        try:
            with open(self.path, 'r') as f:
                cache_data = json.load(f)

            timestamp = cache_data.get("timestamp", 0)
            if max_age_seconds > 0 and (time.time() - timestamp) > max_age_seconds:
                return None

            return cache_data.get("data")
        except Exception as e:
            logger.error(f"Error loading {self._label} cache: {e}")
            return None

    def reset(self) -> None:
        """Delete the cache file if it exists."""
        if os.path.exists(self.path):
            os.remove(self.path)
        logger.info(f"{self._label.capitalize()} cache reset")
