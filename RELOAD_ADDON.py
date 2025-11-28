"""
Quick script to reload the Paint System addon in Blender/Bforartists
Run this in Blender's Python console or Text Editor to reload after code changes
"""

import bpy
import sys
import importlib

# Addon module name
addon_module = "bl_ext.vscode_development.paintsystem"

# Disable the addon
try:
    bpy.ops.preferences.addon_disable(module=addon_module)
    print(f"Disabled {addon_module}")
except:
    print(f"Addon {addon_module} was not enabled")

# Remove all cached modules
modules_to_remove = []
for module_name in sys.modules:
    if addon_module in module_name:
        modules_to_remove.append(module_name)

for module_name in modules_to_remove:
    del sys.modules[module_name]
    print(f"Removed cached module: {module_name}")

# Re-enable the addon
try:
    bpy.ops.preferences.addon_enable(module=addon_module)
    print(f"\n✓ Successfully reloaded {addon_module}")
except Exception as e:
    print(f"\n✗ Error reloading addon: {e}")
