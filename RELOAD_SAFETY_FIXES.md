# Reload Safety Fixes

## Overview

This change converts all operator modules from `register_classes_factory()` to a
defensive `_safe_unregister_class` / `_get_registered_class` pattern to prevent
errors when reloading the addon (e.g. during development or CI testing).

## Problem

When Blender reloads an addon (e.g. via F8 or `bpy.ops.preferences.addon_enable`),
classes that were previously registered may still be present in `bpy.types`. Calling
`register_classes_factory` in this situation raises a `ValueError: already registered`
error, crashing the reload.

## Solution

Each operator module now defines two helper functions:

- `_get_registered_class(cls)` — looks up whether a class is already registered in
  `bpy.types` by class name or `bl_idname`.
- `_safe_unregister_class(cls)` — silently unregisters a class, swallowing any errors.

The `register()` function first clears any stale registrations, then registers each
class fresh. The `unregister()` function always cleans up without raising errors.

## Files Changed

- `__init__.py` — retry-on-conflict logic in addon `register()`
- `operators/bake_operators.py`
- `operators/channel_operators.py`
- `operators/group_operators.py`
- `operators/image_operators.py`
- `operators/layers_operators.py`
- `operators/quick_edit.py`
- `operators/shader_editor.py`
- `operators/versioning_operators.py`
- `paintsystem/data.py`
