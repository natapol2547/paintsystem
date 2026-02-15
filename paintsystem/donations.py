import bpy
import json
import sys
from datetime import datetime
from typing import Dict, Any, Optional
from .context import parse_context
import threading
from ..utils.version import is_online
from .cache_utils import JsonFileCache

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

_donation_cache = JsonFileCache("donation_cache.json", label="donation")

# Cache validity: 10 minutes
_DONATION_CACHE_MAX_AGE = 600


def thread_request_donation_info(base_url: str = "https://paintsystem-backend.vercel.app"):
    """Fetch donation info in a background thread.
    
    Note: Blender context access is not fully thread-safe. State updates
    to ps_settings are wrapped in try/except as a precaution.
    """
    print(f"Requesting donation info...")
    ps_ctx = parse_context(bpy.context)
    
    def _set_loading(value):
        try:
            if ps_ctx.ps_settings is not None:
                ps_ctx.ps_settings.loading_donations = value
        except Exception:
            pass
    
    _set_loading(True)
    try:
        url = f"{base_url}/api/donation-info"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        # sort recentDonations by timestamp
        data['recentDonations'].sort(key=lambda x: datetime.fromisoformat(x['timestamp']), reverse=True)
        _donation_cache.save(data)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching donation info: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"Error details: {error_data}", file=sys.stderr)
            except Exception:
                print(f"Status code: {e.response.status_code}", file=sys.stderr)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
    finally:
        _set_loading(False)

def get_donation_info(base_url: str = "https://paintsystem-backend.vercel.app") -> Optional[Dict[str, Any]]:
    """
    Fetch donation info from the API endpoint.
    
    Args:
        base_url: Base URL of the API server
    
    Returns:
        Dictionary containing recentDonations and totalSales, or None if error
    """
    ps_ctx = parse_context(bpy.context)
    if not is_online():
        return None
    
    if ps_ctx.ps_settings is None or ps_ctx.ps_settings.loading_donations:
        return None
    
    # Try to load from cache first
    cached_data = _donation_cache.load(_DONATION_CACHE_MAX_AGE)
    if cached_data is not None:
        return cached_data

    ps_ctx.ps_settings.loading_donations = True
    if not REQUESTS_AVAILABLE:
        print("Error: requests library is not available", file=sys.stderr)
        return None
    
    threading.Thread(target=lambda: thread_request_donation_info(base_url)).start()

def reset_donation_cache() -> None:
    """Reset the donation cache."""
    _donation_cache.reset()
    get_donation_info()