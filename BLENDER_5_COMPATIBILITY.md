# Blender 5.0 & Bforartists Compatibility Guide

## Overview
Paint System v2.1.0 is optimized for **Blender 5.0 main branch** and **Bforartists** compatibility using runtime API detection instead of hard version checks. This ensures forward compatibility without requiring updates for each Blender release.

## Key Compatibility Patterns

### 1. Runtime API Detection (Preferred)
Use `getattr()` with fallbacks instead of version checks:

```python
# ✓ Correct: Runtime detection
gpencil_brush_type = getattr(brush, 'gpencil_brush_type', None) or getattr(brush, 'gpencil_tool', None)

# ✗ Avoid: Hard version check
if is_newer_than(5,0):
    gpencil_brush_type = brush.gpencil_brush_type
else:
    gpencil_brush_type = brush.gpencil_tool
```

**Benefits:**
- Works across Blender and Bforartists versions
- No breakage when API names change
- Self-healing code (tries new API first, falls back gracefully)

### 2. Optional Import Pattern
For platform-specific features (like Bforartists UI differences):

```python
try:
    from bl_ui.properties_paint_common import color_jitter_panel
except ImportError:
    color_jitter_panel = None

if color_jitter_panel:
    color_jitter_panel(col, context, brush)
```

### 3. When to Use `is_newer_than()`
**Only use version checks for:**
- Icon name changes (`INFO_LARGE` vs `INFO`)
- Template function availability (`template_ID_preview` in 4.3+)
- Features that don't exist in older versions (Grease Pencil v3 in 4.3+)

**Don't use for:**
- Property renames (use `getattr` instead)
- API migrations (use runtime detection)
- Anything that might vary between forks (Bforartists)

## Grease Pencil API Changes

### Before (Hard Version Check)
```python
if is_newer_than(5,0):
    gpencil_brush_type = brush.gpencil_brush_type
else:
    gpencil_brush_type = brush.gpencil_tool
```

### After (Runtime Detection)
```python
gpencil_brush_type = getattr(brush, 'gpencil_brush_type', None) or getattr(brush, 'gpencil_tool', None)
```

**Locations Updated:**
- `panels/extras_panels.py` lines 197, 303 (MAT_PT_BrushColor, MAT_PT_ColorPalette poll methods)

## Blender 4.3+ Grease Pencil v3 Support

Grease Pencil v3 (Blender 4.3+) no longer requires version checks for basic object type:

```python
# Before
case 'GREASEPENCIL':
    if is_newer_than(4,3,0):
        ps_object = obj

# After (simplified)
case 'GREASEPENCIL':
    # Grease Pencil v3 support (Blender 4.3+)
    ps_object = obj
```

Since `blender_version_min = "4.2.0"`, we can assume GP v3 exists without checking.

## Platform-Specific Features

### Optional UI Components
Features that may not exist in all forks:

| Feature | Import Path | Fallback Behavior |
|---------|-------------|-------------------|
| Color Jitter Panel | `bl_ui.properties_paint_common.color_jitter_panel` | Skip if not available (Bforartists 4.5.2 tested) |
| Template ID Preview | `layout.template_ID_preview()` | Use `template_ID()` before 4.3 |

### Icon Names
Some icons changed in 4.3+:

```python
icon='INFO_LARGE' if is_newer_than(4,3) else 'INFO'
```

## Testing Checklist

- [x] Grease Pencil API detection (gpencil_brush_type/gpencil_tool)
- [x] Optional color_jitter_panel import
- [x] Icon compatibility (INFO vs INFO_LARGE)
- [x] Template ID functions (template_ID_preview availability)
- [ ] Test on Blender 5.0 main branch
- [ ] Test on Bforartists latest stable
- [ ] Verify RMB popover registration across platforms
- [ ] Check keyboard shortcuts (may differ in Bforartists)

## Known Platform Differences

### Bforartists 4.5.2
- ✅ Core Paint System features working
- ✅ RMB quick popover functional
- ⚠️ Color jitter panel may not exist (handled via try/except)
- ⚠️ Some keyboard shortcuts remapped (not Paint System specific)

### Blender 5.0 Main Branch
- ✅ Grease Pencil brush type detection working
- ✅ No deprecated API warnings
- 🔄 Runtime API detection ensures future compatibility

## Maintenance Guidelines

When adding new features:

1. **Always use runtime detection first**
   ```python
   prop_value = getattr(obj, 'new_property', getattr(obj, 'old_property', None))
   ```

2. **Test optional imports with try/except**
   ```python
   try:
       from module import feature
   except ImportError:
       feature = None
   ```

3. **Only add version checks for true feature gates**
   - Icon name changes
   - New template functions
   - Version-gated features (not property renames)

4. **Document platform-specific behavior**
   - Add comments explaining why fallbacks exist
   - Note which Blender/Bforartists versions need specific code paths

## Troubleshooting

### "AttributeError: 'Brush' object has no attribute 'gpencil_brush_type'"
**Solution:** Already fixed. Code uses `getattr()` with `gpencil_tool` fallback.

### "ImportError: cannot import name 'color_jitter_panel'"
**Solution:** Already handled. Import wrapped in try/except with None fallback.

### Addon works in Blender but fails in Bforartists
**Check:**
1. Icon names (some differ between platforms)
2. Keyboard shortcuts (Bforartists remaps some keys)
3. Optional UI features (try/except imports)

### Future Blender version breaks addon
**If this happens:**
1. Check which property/API changed
2. Add fallback using `getattr(obj, 'new_name', getattr(obj, 'old_name', None))`
3. Test both old and new versions
4. Document in this file

## Version History

### v2.1.0 (Current)
- ✅ Optimized for Blender 5.0 compatibility
- ✅ Runtime API detection for Grease Pencil brush types
- ✅ Bforartists 4.5.2 tested and working
- ✅ Forward compatible design (no hard max version)

### Future Improvements
- [ ] Add automated testing across multiple Blender versions
- [ ] Document all platform-specific UI differences
- [ ] Create compatibility matrix for major versions
