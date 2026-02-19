# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import bpy
from bpy.utils import register_submodule_factory
from .custom_icons import load_icons, unload_icons

# Ensure subpackages are available for extension loader expectations
from . import paintsystem as paintsystem
from . import panels as panels
from . import operators as operators
from . import keymaps as keymaps

# from .paintsystem.data import parse_context

bl_info = {
    "name": "Paint System",
    "author": "Tawan Sunflower, @blastframe",
    "description": "",
    "blender": (4, 2, 0),
    "version": (2, 1, 8),
    "location": "View3D > Sidebar > Paint System",
    "warning": "",
    "category": "Paint",
    'support': 'COMMUNITY',
    "tracker_url": "https://github.com/natapol2547/paintsystem"
}

bl_info_copy = bl_info.copy()

print("Paint System: Registering...")

submodules = [
    "paintsystem",
    "operators",
    "panels",
    "keymaps",
]

_register, _unregister = register_submodule_factory(__name__, submodules)

def register():
    """Register the addon with idempotent error handling for module reloads."""
    try:
        load_icons()
    except Exception as e:
        print(f"Paint System: Error loading icons: {e}")
    
    try:
        _register()
    except ValueError as e:
        # Handle case where classes are already registered (e.g., module reload in CI)
        if "already registered" in str(e):
            print(f"Paint System: Classes already registered (module reload), retrying clean register: {e}")
            try:
                _unregister()
            except Exception as cleanup_error:
                print(f"Paint System: Cleanup before re-register failed: {cleanup_error}")
            _register()
        else:
            raise
    except Exception as e:
        print(f"Paint System: Registration error: {e}")
        raise

    try:
        op = getattr(bpy.types, "PAINT_SYSTEM_OT_new_image_layer", None)
        needs_fix = op is None or not hasattr(op, "poll")
        if needs_fix:
            from .operators import layers_operators
            try:
                if op is not None:
                    bpy.utils.unregister_class(op)
            except Exception:
                pass
            try:
                bpy.utils.unregister_class(layers_operators.PAINTSYSTEM_OT_NewImage)
            except Exception:
                pass
            try:
                bpy.utils.register_class(layers_operators.PAINTSYSTEM_OT_NewImage)
            except ValueError as e:
                if "already registered" not in str(e):
                    raise
            if hasattr(bpy.types, "PAINT_SYSTEM_OT_new_image_layer"):
                print("Paint System: Registered new image layer operator (fallback)")
            else:
                print("Paint System: Failed to register new image layer operator")
    except Exception as e:
        print(f"Paint System: Fallback operator registration failed: {e}")
    
def unregister():
    """Unregister the addon with idempotent error handling."""
    try:
        _unregister()
    except Exception as e:
        print(f"Paint System: Unregister error: {e}")
    
    try:
        unload_icons()
    except Exception as e:
        print(f"Paint System: Error unloading icons: {e}")
    
    print("Paint System: Unregistered", __package__)