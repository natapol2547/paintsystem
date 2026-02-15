"""Shared JSON file caching utilities for the Paint System addon."""

import json
import os
import sys
import time
from typing import Any, Dict, Optional


def _get_addon_root() -> str:
    """Get the addon root directory (one level up from this file's directory)."""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class JsonFileCache:
    """A simple JSON file cache with timestamp-based expiration.
    
    Args:
        filename: Name of the cache file (stored in the addon root directory).
        label: Human-readable label used in log messages (e.g. "donation", "version").
    """

    def __init__(self, filename: str, label: str = "cache"):
        self._filename = filename
        self._label = label

    @property
    def path(self) -> str:
        return os.path.join(_get_addon_root(), self._filename)

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
            print(f"Error saving {self._label} cache: {e}", file=sys.stderr)

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
            print(f"Error loading {self._label} cache: {e}", file=sys.stderr)
            return None

    def reset(self) -> None:
        """Delete the cache file if it exists."""
        if os.path.exists(self.path):
            os.remove(self.path)
        print(f"{self._label.capitalize()} cache reset")
