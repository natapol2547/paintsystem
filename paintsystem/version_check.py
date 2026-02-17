import bpy
import sys
import threading
from typing import Optional, Tuple
from .context import parse_context
from ..utils.version import is_newer_than, is_online
from .cache_utils import JsonFileCache

ADDON_ID = 'paint_system'

_version_cache = JsonFileCache("version_cache.json", label="version")


def _get_version_cache_max_age() -> float:
    """Compute the cache validity interval (in seconds) from user preferences.
    
    Returns 0 when caching should be bypassed.
    """
    try:
        ps_ctx = parse_context(bpy.context)
        if ps_ctx.ps_settings is None:
            return 0
        prefs = ps_ctx.ps_settings
        return (
            prefs.version_check_interval_days * 86400 +
            prefs.version_check_interval_hours * 3600 +
            prefs.version_check_interval_minutes * 60
        )
    except Exception:
        return 0


def save_version_cache(version: str) -> None:
    """Save version data to cache with timestamp."""
    _version_cache.save({"version": version})


def load_version_cache() -> Optional[str]:
    """Load version data from cache if valid based on user preferences."""
    max_age = _get_version_cache_max_age()
    if max_age == 0:
        return None
    cached = _version_cache.load(max_age)
    if cached is not None:
        return cached.get("version")
    return None


def thread_check_update():
    """Check for updates in a background thread - combines latest version check and update availability."""
    ps_ctx = parse_context(bpy.context)
    
    try:
        # Get current version first (doesn't require repo reading)
        current_version = _get_current_version_internal()
        
        # Get latest version and check if update is available in one go
        latest_version, update_available = _get_latest_version_and_check_update_internal(current_version)
        
        print(f"Latest version: {latest_version}, Update available: {update_available}")
        
        if latest_version is not None:
            save_version_cache(latest_version)
        
        # Update the state based on results
        if ps_ctx.ps_settings is not None:
            if latest_version is None:
                ps_ctx.ps_settings.update_state = 'UNAVAILABLE'
            elif update_available:
                ps_ctx.ps_settings.update_state = 'AVAILABLE'
            else:
                ps_ctx.ps_settings.update_state = 'UNAVAILABLE'
    except Exception as e:
        print(f"Error checking for updates: {e}", file=sys.stderr)
        if ps_ctx.ps_settings is not None:
            ps_ctx.ps_settings.update_state = 'ERROR'
    finally:
        if ps_ctx.ps_settings is not None and ps_ctx.ps_settings.update_state != 'ERROR':
            if ps_ctx.ps_settings.update_state == 'LOADING':
                ps_ctx.ps_settings.update_state = 'UNAVAILABLE'


def _get_latest_version_internal() -> Optional[str]:
    """
    Get the latest version number of the paint_system addon from the extension repository.
    
    Returns:
        The latest version string (e.g., "1.2.3") if found, None otherwise.
    """
    latest_version, _ = _get_latest_version_and_check_update_internal(None)
    return latest_version


def _get_latest_version_and_check_update_internal(current_version: Optional[str]) -> Tuple[Optional[str], bool]:
    """
    Get the latest version and check if update is available in one repository call.
    
    Args:
        current_version: Current installed version (if None, will be fetched from bl_info)
    
    Returns:
        Tuple of (latest_version, update_available)
        - latest_version: The latest version string (e.g., "1.2.3") if found, None otherwise
        - update_available: True if update is available, False otherwise
    """
    pkg_id = ADDON_ID
    
    # Get current version if not provided
    if current_version is None:
        current_version = _get_current_version_internal()
    
    try:
        from bl_pkg import bl_extension_ops as ext_op
        from bl_pkg import bl_extension_utils
    except ImportError:
        # Fallback for different Blender versions
        return None, False
    
    repos_all = ext_op.extension_repos_read(use_active_only=True)
    repo_cache_store = ext_op.repo_cache_store_ensure()
    
    repo_directory_supset = [repo_entry.directory for repo_entry in repos_all]
    
    if not repos_all:
        return None, False
    
    # Clear cache for repos that don't use cache
    for repo_item in repos_all:
        if repo_item.use_cache:
            continue
        bl_extension_utils.pkg_repo_cache_clear(repo_item.directory)
    
    pkg_manifest_local_all = list(repo_cache_store.pkg_manifest_from_local_ensure(
        error_fn=None,
        directory_subset=repo_directory_supset,
    ))
    
    for repo_index, pkg_manifest_remote in enumerate(repo_cache_store.pkg_manifest_from_remote_ensure(
        error_fn=None,
        directory_subset=repo_directory_supset,
    )):
        if pkg_manifest_remote is None:
            continue
        
        pkg_manifest_local = pkg_manifest_local_all[repo_index]
        if pkg_manifest_local is None:
            continue
        
        repo_item = repos_all[repo_index]
        for pkg_id_remote, item_remote in pkg_manifest_remote.items():
            if item_remote.block:
                # Blocked, skip.
                continue
            
            if pkg_id_remote == pkg_id:
                latest_version = item_remote.version
                # Check if update is available
                if current_version and latest_version:
                    comparison = _compare_versions(current_version, latest_version)
                    update_available = comparison < 0
                else:
                    update_available = False
                return latest_version, update_available
    
    return None, False


def get_latest_version() -> Optional[str]:
    """
    Get the latest version number of the paintsystem addon from the extension repository.
    Uses caching and thread support. Only checks online if is_online() is True.
    
    Returns:
        The latest version string (e.g., "1.2.3") if found, None otherwise.
    """
    import addon_utils
    from ..preferences import addon_package
    module_name = addon_package()
    if not is_newer_than(4, 2):
        return None
    
    if not is_online():
        return None
    
    is_extension = addon_utils.check_extension(module_name)
    if not is_extension:
        return None

    ps_ctx = parse_context(bpy.context)
    
    if ps_ctx.ps_settings is None:
        return None
    
    if ps_ctx.ps_settings.update_state == 'ERROR':
        return None
    
    # Check if already loading
    if ps_ctx.ps_settings.update_state == 'LOADING':
        # Try to return cached version while loading
        cached_version = load_version_cache()
        return cached_version
    
    # Try to load from cache first
    cached_version = load_version_cache()
    if cached_version is not None:
        return cached_version
    
    # Start background thread to check for updates (combines latest version and update check)
    ps_ctx.ps_settings.update_state = 'LOADING'
    threading.Thread(target=thread_check_update).start()
    
    return None


def reset_version_cache() -> None:
    """Reset the version cache."""
    _version_cache.reset()


def _get_current_version_internal() -> Optional[str]:
    """
    Get the current installed version number of the paintsystem addon.
    Optimized to avoid reading repos repeatedly - tries bl_info first.
    
    Returns:
        The current version string (e.g., "1.2.3") if found, None otherwise.
    """
    try:
        import addon_utils
        from ..preferences import addon_package
        
        # Get the current addon's module name
        module_name = addon_package()
        
        # First try to get version from bl_info (no repo reading required)
        # This works for both extensions and regular addons
        for mod in addon_utils.modules(refresh=False):
            if mod.__name__ == module_name:
                bl_info = addon_utils.module_bl_info(mod)
                if version := bl_info.get("version"):
                    return ".".join(str(x) for x in version)
        
        # If bl_info didn't work and it's an extension, try manifest
        # Only read repos as a last resort
        try:
            is_extension = addon_utils.check_extension(module_name)
            if is_extension:
                from bl_pkg import bl_extension_ops as ext_op
                from bl_pkg import repo_cache_store_ensure
                
                pkg_id = ADDON_ID
                repos_all = ext_op.extension_repos_read(use_active_only=True)
                repo_cache_store = repo_cache_store_ensure()
                
                if repos_all:
                    repo_directory_supset = [repo_entry.directory for repo_entry in repos_all]
                    
                    # Get local manifests - similar to Blender's addons_panel_draw_impl
                    pkg_manifest_local_all = list(repo_cache_store.pkg_manifest_from_local_ensure(
                        error_fn=None,
                        directory_subset=repo_directory_supset,
                    ))
                    
                    # Look for the package in local manifests
                    for pkg_manifest_local in pkg_manifest_local_all:
                        if pkg_manifest_local is None:
                            continue
                        
                        item_local = pkg_manifest_local.get(pkg_id)
                        if item_local is not None and item_local.type == "add-on":
                            return item_local.version
        except ImportError:
            pass
        except Exception:
            pass
        
    except ImportError:
        # Fallback: try to get version from bl_info
        try:
            import addon_utils
            from ..preferences import addon_package
            module_name = addon_package()
            for mod in addon_utils.modules(refresh=False):
                if mod.__name__ == module_name:
                    bl_info = addon_utils.module_bl_info(mod)
                    if version := bl_info.get("version"):
                        return ".".join(str(x) for x in version)
        except Exception:
            pass
        return None
    except Exception as e:
        print(f"Error getting current version: {e}", file=sys.stderr)
        return None
    
    return None


def get_current_version() -> Optional[str]:
    """
    Get the current installed version number of the paintsystem addon.
    
    Returns:
        The current version string (e.g., "1.2.3") if found, None otherwise.
    """
    return _get_current_version_internal()


def _compare_versions(version1: str, version2: str) -> int:
    """
    Compare two version strings.
    
    Args:
        version1: First version string (e.g., "2.1.1")
        version2: Second version string (e.g., "2.1.2")
    
    Returns:
        -1 if version1 < version2, 0 if equal, 1 if version1 > version2
    """
    def version_tuple(v: str) -> tuple:
        """Convert version string to tuple of integers."""
        parts = []
        for part in v.split('.'):
            try:
                parts.append(int(part))
            except ValueError:
                # Handle non-numeric parts (e.g., "2.1.1-beta")
                numeric_part = ''
                for char in part:
                    if char.isdigit():
                        numeric_part += char
                    else:
                        break
                if numeric_part:
                    parts.append(int(numeric_part))
                break
        return tuple(parts)
    
    v1_tuple = version_tuple(version1)
    v2_tuple = version_tuple(version2)
    
    # Pad shorter tuple with zeros
    max_len = max(len(v1_tuple), len(v2_tuple))
    v1_tuple = v1_tuple + (0,) * (max_len - len(v1_tuple))
    v2_tuple = v2_tuple + (0,) * (max_len - len(v2_tuple))
    
    if v1_tuple < v2_tuple:
        return -1
    elif v1_tuple > v2_tuple:
        return 1
    else:
        return 0


def is_update_available() -> Optional[bool]:
    """
    Check if an update is available by checking the update_state preference.
    This avoids duplicate repository calls by using the state set by the background thread.
    
    Returns:
        True if update is available, False if up to date, None if unable to determine.
    """
    ps_ctx = parse_context(bpy.context)
    if ps_ctx.ps_settings is None:
        return None
    
    # Trigger check if not already done
    get_latest_version()
    
    # Return based on update_state
    if ps_ctx.ps_settings.update_state == 'AVAILABLE':
        return True
    elif ps_ctx.ps_settings.update_state == 'UNAVAILABLE':
        return False
    else:  # LOADING
        return None

