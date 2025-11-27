# Paint System Add-on: Forward Compatibility Report

**Generated:** November 9, 2025  
**Current Min Version:** Blender 4.2.0  
**Target Platforms:** Bforartists 4.x/5.x, Blender 4.2+/5.0+

## Summary

The Paint System add-on demonstrates **good forward compatibility** with both Bforartists and mainline Blender. The codebase uses proper version checking and graceful fallbacks for API changes.

## ✅ Compatibility Strengths

### 1. **Version Detection System**
- Uses `is_newer_than()` utility function consistently
- Implements runtime version checks before using newer APIs
- Located in: `utils/version.py`

### 2. **API Evolution Handling**

#### Grease Pencil API (4.3+ → 5.0+)
```python
# panels/extras_panels.py:206
if is_newer_than(5,0):
    gpencil_brush_type = brush.gpencil_brush_type
else:
    gpencil_brush_type = brush.gpencil_tool
```
**Status:** ✅ Properly handles property rename

#### Asset System (4.3+)
```python
# operators/brushes/__init__.py:36
if bpy.app.version >= (4, 3, 0):
    for brush in bpy.data.brushes:
        if brush.name.startswith(BRUSH_PREFIX):
            brush.asset_mark()
```
**Status:** ✅ Conditionally marks assets only when supported

#### Color Jitter Panel (4.5+)
```python
# panels/extras_panels.py:259
if is_newer_than(4,5):
    try:
        from bl_ui.properties_paint_common import color_jitter_panel
    except Exception:
        color_jitter_panel = None
    if color_jitter_panel:
        color_jitter_panel(col, context, brush)
```
**Status:** ✅ Graceful fallback with try/except for Bforartists compatibility

### 3. **Node System Compatibility**
- Uses modern `ShaderNodeMix` (Blender 3.4+) consistently
- Uses `interface.new_socket()` API (Blender 4.0+) for node sockets
- No legacy `ShaderNodeMixRGB` usage detected

**Status:** ✅ Already using current APIs

### 4. **Handler Registration**
```python
# paintsystem/handlers.py:221
if hasattr(bpy.app.handlers, 'scene_update_pre'):
    bpy.app.handlers.scene_update_pre.append(paint_system_object_update)
else:
    bpy.app.handlers.depsgraph_update_post.append(paint_system_object_update)
```
**Status:** ✅ Handles deprecated `scene_update_pre` → `depsgraph_update_post` transition

### 5. **Manifest Configuration**
- Uses extension manifest system (Blender 4.2+)
- Minimum version set to 4.2.0
- No maximum version restriction (forward compatible by default)

**Status:** ✅ Proper manifest setup

## ⚠️ Potential Issues & Recommendations

### 1. **Pillow Wheel Configuration**
**Current State:**
```toml
platforms = ["windows-x64", "macos-x64"]
wheels = [
  "./wheels/pillow-12.0.0-cp311-cp311-macosx_11_0_arm64.whl",
]
```

**Issues:**
- Windows wheel commented out in manifest
- macOS ARM wheel specified but platform lists "macos-x64"
- Missing Linux support

**Recommendation:**
```toml
platforms = ["windows-x64", "macos-arm64", "linux-x64"]
wheels = [
  "./wheels/pillow-12.0.0-cp311-cp311-win_amd64.whl",
  "./wheels/pillow-12.0.0-cp311-cp311-macosx_11_0_arm64.whl",
  # Add Linux wheel when needed
]
```

### 2. **Python Version Dependency**
- Wheels built for CPython 3.11
- Blender 4.2-4.x uses Python 3.11
- Blender 5.0+ may use Python 3.12+

**Risk:** Medium  
**Impact:** Pillow wheel won't load in future Python versions

**Recommendation:**
- Add `blender_version_max = "4.9.0"` if staying with cp311 wheels
- OR prepare cp312 wheels for Blender 5.0+ support

### 3. **PropertyGroup API Usage**
Multiple uses of `bl_rna.properties` iteration:
- `operators/layers_operators.py:935`
- `paintsystem/handlers.py:73`
- `paintsystem/data.py:1024`

**Status:** ✅ Currently safe, but should monitor for deprecation warnings

### 4. **Socket Type String Names**
Uses string-based socket types extensively:
```python
socket_type="NodeSocketColor"
socket_type="NodeSocketFloat"
socket_type="NodeSocketVector"
```

**Status:** ✅ Safe - this is the stable API pattern
**Note:** Monitor for any future enum-based socket API changes

### 5. **Bforartists-Specific Considerations**

#### Differences Handled:
- ✅ Optional `color_jitter_panel` import with fallback
- ✅ Version detection works (Bforartists reports as Blender base version)

#### Potential Issues:
- Icon names may differ between Bforartists/Blender
- Custom keymap preferences (RMB menu override in `keymaps.py`)

**Current Status:**
```python
# keymaps.py:11
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = True  # For Bforartists compatibility
```
**Recommendation:** Continue testing RMB overrides in both environments

## 🔮 Future API Changes to Monitor

### Blender 5.0+ (Expected)
1. **Python 3.12 Migration**
   - Action: Rebuild Pillow wheels for cp312
   - Timeline: Monitor Blender 5.0 beta releases

2. **Grease Pencil 3.0 API**
   - Already handled in `panels/extras_panels.py:206`
   - Continue monitoring for additional property changes

3. **Asset Browser Evolution**
   - Current asset marking (4.3+) is stable
   - Watch for workflow changes in 5.x

### Deprecated APIs to Watch
1. `scene_update_pre` handler (already handled with fallback)
2. Direct property iteration via `bl_rna.properties` (currently safe)

## 🧪 Testing Recommendations

### Version Matrix
Test on:
- ✅ Blender 4.2 LTS
- ✅ Blender 4.3/4.4 (current stable)
- ⚠️ Blender 4.5+ (with color jitter panel)
- ⚠️ Blender 5.0 alpha/beta (when available)
- ✅ Bforartists 4.4.3 (current)
- ⚠️ Bforartists 5.0+ (when released)

### Critical Test Areas
1. Node tree compilation (especially ShaderNodeMix usage)
2. Socket creation/connection APIs
3. Handler registration/unregistration
4. Asset marking for brushes (4.3+)
5. Grease Pencil brush properties (4.3 vs 5.0)
6. Pillow wheel loading on all platforms

## 📝 Code Quality Notes

### Strong Patterns Used
1. ✅ Consistent use of `is_newer_than()` helper
2. ✅ Try/except blocks for optional features
3. ✅ `hasattr()` checks before using new APIs
4. ✅ Clear version-gated code blocks with comments

### Improvement Opportunities
1. Consider adding version compatibility matrix to README
2. Document minimum versions for optional features
3. Add CI/CD testing across Blender versions
4. Create version-specific test suites

## 🎯 Action Items

### High Priority
1. ✅ Fix syntax error in `layers_operators.py:947` (COMPLETED)
2. ⚠️ Resolve Pillow wheel platform mismatch in manifest
3. ⚠️ Add `blender_version_max` if not preparing Python 3.12 wheels

### Medium Priority
1. Test on Blender 5.0 alpha when available
2. Document Bforartists-specific features/workarounds
3. Add automated version compatibility tests

### Low Priority
1. Create compatibility test suite
2. Document version-specific feature availability
3. Add version badge to README

## Conclusion

**Overall Rating: GOOD** 🟢

The add-on demonstrates mature forward compatibility practices with:
- Proper version detection
- Graceful API fallbacks
- Modern API usage (ShaderNodeMix, interface.new_socket)
- Bforartists consideration

Main action needed: **Resolve Pillow wheel configuration** for proper cross-platform support.

The codebase is well-positioned for Blender 5.0+ with minimal changes expected, primarily around Python version updates for bundled wheels.
