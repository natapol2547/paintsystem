def addon_package() -> str:
    """Get the addon package name"""
    return __package__ or "paintsystem"

def get_preferences(context):
    """Get the Paint System preferences"""
    if context is None or context.preferences is None:
        return None
        
    ps = addon_package()
    try:
        prefs = context.preferences.addons[ps].preferences
        return prefs
    except KeyError:
        pass
    except RuntimeError:
        # Preferences might not be available yet
        return None
    
    # Fallback: try to find the addon by partial match
    try:
        for addon_key in context.preferences.addons:
            if 'paintsystem' in addon_key.lower():
                return context.preferences.addons[addon_key].preferences
    except (KeyError, RuntimeError, AttributeError):
        pass
    
    # Return None instead of raising - preferences might not be available yet
    return None