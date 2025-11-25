import bpy
import json
import sys
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
from .data import parse_context
import threading
from ..utils.version import is_online
try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

def get_cache_path() -> str:
    """Get the path to the cache file in the addon root directory."""
    # Go up one level from this file's directory (paintsystem/paintsystem/ -> paintsystem/)
    addon_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(addon_root, "donation_cache.json")


def save_donation_cache(data: Dict[str, Any]) -> None:
    """Save donation data to cache with timestamp."""
    cache_path = get_cache_path()
    cache_data = {
        "timestamp": time.time(),
        "data": data
    }
    try:
        with open(cache_path, 'w') as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print(f"Error saving donation cache: {e}", file=sys.stderr)


def load_donation_cache() -> Optional[Dict[str, Any]]:
    """Load donation data from cache if valid (less than 10 minutes old)."""
    cache_path = get_cache_path()
    if not os.path.exists(cache_path):
        return None
    
    try:
        with open(cache_path, 'r') as f:
            cache_data = json.load(f)
            
        timestamp = cache_data.get("timestamp", 0)
        # Check if cache is older than 10 minutes (600 seconds)
        if time.time() - timestamp > 600:
            return None
            
        return cache_data.get("data")
    except Exception as e:
        print(f"Error loading donation cache: {e}", file=sys.stderr)
        return None

def thread_request_donation_info(base_url: str = "https://paintsystem-backend.vercel.app"):
    print(f"Requesting donation info...")
    ps_ctx = parse_context(bpy.context)
    ps_ctx.ps_settings.loading_donations = True
    try:
        url = f"{base_url}/api/donation-info"
        response = requests.get(url, timeout=10)
        response.raise_for_status()  # Raise an exception for bad status codes
        
        data = response.json()
        # sort recentDonations by timestamp
        data['recentDonations'].sort(key=lambda x: datetime.fromisoformat(x['timestamp']), reverse=True)
        save_donation_cache(data)
        ps_ctx.ps_settings.loading_donations = False
    
    except requests.exceptions.RequestException as e:
        print(f"Error fetching donation info: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"Error details: {error_data}", file=sys.stderr)
            except:
                print(f"Status code: {e.response.status_code}", file=sys.stderr)
        ps_ctx.ps_settings.loading_donations = False
        return None
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON response: {e}", file=sys.stderr)
        ps_ctx.ps_settings.loading_donations = False
        return None

def get_donation_info(base_url: str = "https://paintsystem-backend.vercel.app") -> Optional[Dict[str, Any]]:
    """
    Fetch donation info from the API endpoint.
    
    Args:
        base_url: Base URL of the API server (default: localhost:5173)
    
    Returns:
        Dictionary containing recentDonations and totalSales, or None if error
    """
    ps_ctx = parse_context(bpy.context)
    if not is_online():
        return None
    
    if ps_ctx.ps_settings is None or ps_ctx.ps_settings.loading_donations:
        return None
    
    # Try to load from cache first
    cached_data = load_donation_cache()
    if cached_data is not None:
        return cached_data

    ps_ctx.ps_settings.loading_donations = True
    if not REQUESTS_AVAILABLE:
        print("Error: requests library is not available", file=sys.stderr)
        return None
    
    threading.Thread(target=lambda: thread_request_donation_info(base_url)).start()

def reset_donation_cache() -> None:
    """Reset the donation cache."""
    cache_path = get_cache_path()
    if os.path.exists(cache_path):
        os.remove(cache_path)
    print("Donation cache reset")
    get_donation_info()