import bpy

def is_newer_than(major, minor=0, patch=0):
    return bpy.app.version >= (major, minor, patch)

def is_online() -> bool:
    """Check if the internet is connected."""
    if not is_newer_than(4, 2):
        return True
    if not hasattr(bpy.app, 'online_access'):
        return False
    return bpy.app.online_access