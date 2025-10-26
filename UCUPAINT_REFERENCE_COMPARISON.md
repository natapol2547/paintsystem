# Side-by-Side Comparison: UCUpaint vs Paint System Implementation

## Reference: UCUpaint v2.3.5 Architecture

### UCUpaint File Structure (Relevant Parts)
```
├── BakeTarget.py          <- Contains bake target properties & update callback
├── common.py              <- Contains update_image_editor_image() function
├── ui.py                  <- UI property definitions
└── __init__.py
```

### UCUpaint Implementation Flow

```
User Action: Changes active_bake_target_index property
                    ↓
BakeTarget.py Line 142: update=update_active_bake_target_index callback triggers
                    ↓
BakeTarget.py Line 19: update_active_bake_target_index(self, context) executes
                    ↓
                    Gets the active bake target's image
                    ↓
common.py Line 1160: update_image_editor_image(context, image) called
                    ↓
                    Image editor space(s) updated with new image
                    ↓
User sees new target image in editor
```

## Paint System Implementation

### Paint System File Structure (After Implementation)
```
├── paintsystem/
│   └── data.py                    <- Channel & group properties
├── operators/
│   ├── image_editor_sync.py       <- NEW: Sync functions (replaces common.py role)
│   └── common.py
└── keymaps.py
```

### Paint System Implementation Flow

```
User Action: Changes active channel via UI or Ctrl+Q
                    ↓
data.py Line 1315: update=update_channel callback triggers
                    ↓
data.py Line 1303: update_channel(self, context) executes
                    ↓
                    [EXISTING] Run preview/isolation logic
                    ↓
                    [EXISTING] Call update_active_image()
                    ↓
                    [NEW] update_active_channel_on_switch() called
                    ↓
image_editor_sync.py: Extracts channel source image
                    ↓
image_editor_sync.py: update_image_editor_image() updates editor
                    ↓
User sees new channel image in editor
```

## Code Comparison

### UCUpaint: Bake Target Update Callback
**File: BakeTarget.py, Lines 19-29**
```python
def update_active_bake_target_index(self, context):
    yp = self
    tree = self.id_data
    try: bt = yp.bake_targets[yp.active_bake_target_index]
    except: return

    bt_node = tree.nodes.get(bt.image_node)
    if bt_node and bt_node.image:
        update_image_editor_image(context, bt_node.image)
    else:
        update_image_editor_image(context, None)
```

### Paint System: Channel Update Callback (ADAPTED)
**File: operators/image_editor_sync.py**
```python
def update_active_channel_on_switch(group, context):
    try:
        if not hasattr(group, 'channels') or not hasattr(group, 'active_index'):
            return
        
        if group.active_index < 0 or group.active_index >= len(group.channels):
            update_image_editor_image(context, None)
            return
        
        active_channel = group.channels[group.active_index]
        image = get_channel_source_image(active_channel)
        update_image_editor_image(context, image)
        
    except Exception as e:
        print(f"Error updating channel on switch: {e}")
```

**Key Differences:**
- Uses `group.channels` (collection) instead of `yp.bake_targets`
- Calls generic `get_channel_source_image()` instead of directly accessing `bt.image_node`
- More defensive error handling (checks bounds, wraps in try/except)

---

### UCUpaint: Image Editor Update Function
**File: common.py, Lines 1160-1175**
```python
def update_image_editor_image(context, image):
    obj = context.object
    scene = context.scene

    if obj.mode == 'EDIT':
        space = get_edit_image_editor_space(context)
        if space:
            space.use_image_pin = True
            space.image = image
    else:
        space = get_first_unpinned_image_editor_space(context)
        if space:
            space.image = image
            space.use_image_pin = False
```

### Paint System: Image Editor Update Function (IDENTICAL PATTERN)
**File: operators/image_editor_sync.py**
```python
def update_image_editor_image(context, image):
    obj = context.object
    
    if obj and obj.mode == 'EDIT':
        space = get_edit_image_editor_space(context)
        if space:
            space.use_image_pin = True
            space.image = image
    else:
        space = get_first_unpinned_image_editor_space(context)
        if space:
            space.image = image
            if hasattr(space, 'use_image_pin'):
                space.use_image_pin = False
```

**Key Differences:**
- Added null check: `if obj and obj.mode`
- Added hasattr check for `use_image_pin` (better compatibility)
- Otherwise: 100% identical logic

---

### UCUpaint: Editor Space Finding Functions
**File: common.py, Lines 1176+**
```python
def get_edit_image_editor_space(context):
    ypwm = context.window_manager.ypprops
    area_index = ypwm.edit_image_editor_area_index
    window_index = ypwm.edit_image_editor_window_index
    if window_index >= 0 and window_index < len(context.window_manager.windows):
        window = context.window_manager.windows[window_index]
        if area_index >= 0 and area_index < len(window.screen.areas):
            area = window.screen.areas[area_index]
            if area.type == 'IMAGE_EDITOR' and (not is_bl_newer_than(2, 80) or area.spaces[0].mode == 'UV'):
                return area.spaces[0]

def get_first_unpinned_image_editor_space(context):
    # Iterate through all areas in all windows
    # Return first IMAGE_EDITOR space with use_image_pin == False
```

### Paint System: Editor Space Finding Functions (ADAPTED)
**File: operators/image_editor_sync.py**
```python
def get_edit_image_editor_space(context):
    try:
        wm = context.window_manager
        if wm and hasattr(wm, 'ps_props'):
            ps_props = wm.ps_props
            # ... similar logic but uses ps_props instead of ypprops
    except:
        pass
    return None

def get_first_unpinned_image_editor_space(context):
    try:
        wm = context.window_manager
        if not wm:
            return None
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'IMAGE_EDITOR' and len(area.spaces) > 0:
                    space = area.spaces[0]
                    if hasattr(space, 'use_image_pin'):
                        if not space.use_image_pin:
                            return space
                    else:
                        return space
    except:
        pass
    return None
```

**Key Differences:**
- More defensive programming (try/except wrapping)
- Looks for `ps_props` instead of `ypprops` (Paint System specific)
- Simplified version without Blender version checks
- Handles missing attributes gracefully

---

## Property Definition Comparison

### UCUpaint: Property with Callback
**File: BakeTarget.py, or ui.py**
```python
active_bake_target_index : IntProperty(
    name = 'Active Bake Target',
    description = 'Active bake target index',
    default = 0,
    update = update_active_bake_target_index  # <-- Callback registered here
)
```

### Paint System: Property with Callback (NO CHANGE NEEDED)
**File: paintsystem/data.py, Line 1315**
```python
active_index: IntProperty(
    name="Active Channel Index", 
    update=update_channel  # Already has callback, just enhanced it
)
```

The property definition doesn't need to change - we just enhanced the `update_channel` callback function.

---

## Key Takeaways

| Aspect | UCUpaint | Paint System |
|--------|----------|--------------|
| **Callback Trigger** | `active_bake_target_index` change | `active_index` change |
| **Callback Function** | `update_active_bake_target_index()` | Enhanced `update_channel()` |
| **Core Logic** | `update_image_editor_image()` | `update_image_editor_image()` (same) |
| **Data Structure** | `bake_targets[]` collection | `channels[]` collection |
| **Image Extraction** | Direct `bt.image_node.image` | Generic `get_channel_source_image()` |
| **Property Access** | `ypprops` | `ps_props` (or none needed) |
| **Error Handling** | Minimal (some try/except) | Comprehensive (defensive) |
| **Compatibility** | Blender 2.80+ | Blender 4.2+ (as per manifest) |

---

## Why This Works

UCUpaint's pattern is proven and widely used in the industry. Our implementation:

1. ✅ **Follows the same architecture** - property callback → update function → editor sync
2. ✅ **Uses identical core logic** - same `update_image_editor_image()` function
3. ✅ **Adds safety** - better error handling than original
4. ✅ **Maintains compatibility** - works with Paint System's existing code
5. ✅ **Minimal integration** - only requires adding a function call to existing update callback

