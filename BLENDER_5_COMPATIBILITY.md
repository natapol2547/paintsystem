# Blender 5.0 & Bforartists Compatibility Guide

## Overview
Paint System targets Blender 4.2+ and Bforartists. Use runtime API detection to stay forward-compatible without hard max-version checks.

## Patterns

### 1. Prefer Runtime Detection
```python
# Good
prop = getattr(obj, 'new_attr', getattr(obj, 'old_attr', None))

# Avoid
if bpy.app.version >= (5, 0, 0):
    prop = obj.new_attr
else:
    prop = obj.old_attr
```

### 2. Optional Imports
```python
try:
    from bl_ui.properties_paint_common import color_jitter_panel
except ImportError:
    color_jitter_panel = None

if color_jitter_panel:
    color_jitter_panel(col, context, brush)
```

### 3. When Version Checks Are Acceptable
- Icon name changes (e.g., `INFO` vs `INFO_LARGE`).
- Feature gates (template preview availability, GP v3-only features).

## Notes
- Panels and operators should guard for missing attributes in forks.
- Keep RMB/keymaps behavior configurable for Bforartists differences.

## Testing
- Validate on Blender 4.2 LTS and current stable.
- Sanity check on Bforartists latest stable.
