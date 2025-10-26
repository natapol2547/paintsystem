# Paint System - Painting Target Update Integration Guide

## Overview

This guide explains how to implement automatic image editor updates when switching painting targets (channels) in Paint System, based on UCUpaint's proven implementation.

## Problem

Currently, when users press Ctrl+Q to switch to a different channel, the image editor doesn't update to show the new channel's source image. Users must manually trigger a layer update to see the target image.

## Solution

The solution uses property callbacks (`update=`) that execute whenever the active channel index changes. When this happens, the image editor is automatically updated to display the new channel's source image.

## Files Created/Modified

### 1. **NEW: `operators/image_editor_sync.py`** ✓ Created
This module contains all the image editor synchronization logic:
- `get_edit_image_editor_space(context)` - Find the image editor in EDIT mode
- `get_first_unpinned_image_editor_space(context)` - Find an available image editor
- `update_image_editor_image(context, image)` - Update the image editor to show an image
- `get_channel_source_image(channel)` - Extract the source image from a channel
- `update_active_channel_on_switch(group, context)` - Main callback function
- `update_channel_with_editor_sync(self, context)` - Enhanced update function

### 2. **MODIFIED: `paintsystem/data.py`** - Integration Points

#### Option A: Quick Integration (Recommended)
Import and use the enhanced update function:

```python
# At the top of data.py, add:
from ..operators.image_editor_sync import update_active_channel_on_switch

# Then in the Channel class (~line 1315), modify:
def update_channel(self, context):
    ps_ctx = parse_context(context)
    ps_mat_data = ps_ctx.ps_mat_data
    if ps_mat_data.preview_channel:
        # Call paint_system.isolate_active_channel twice to ensure it's updated
        bpy.ops.paint_system.isolate_active_channel('EXEC_DEFAULT')
        bpy.ops.paint_system.isolate_active_channel('EXEC_DEFAULT')
    if ps_ctx.active_channel.use_bake_image:
        # Force to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
    update_active_image(self, context)
    
    # ADD THIS LINE:
    update_active_channel_on_switch(self, context)

# The active_index property stays the same:
active_index: IntProperty(name="Active Channel Index", update=update_channel)
```

#### Option B: Full Integration
Replace the entire `update_channel` function with `update_channel_with_editor_sync`:

```python
from ..operators.image_editor_sync import update_channel_with_editor_sync

# Then in the Channel class:
active_index: IntProperty(
    name="Active Channel Index",
    update=update_channel_with_editor_sync  # Use the new function directly
)
```

## How It Works

### Reference: UCUpaint Implementation
- **File**: `BakeTarget.py` lines 19-29
- **File**: `common.py` lines 1160-1185

UCUpaint's approach:
1. Whenever `active_bake_target_index` changes, `update_active_bake_target_index()` callback fires
2. This callback extracts the target's image and calls `update_image_editor_image()`
3. `update_image_editor_image()` handles mode-specific behavior:
   - **EDIT mode**: Pins the image editor to the specified image
   - **Other modes**: Updates the first unpinned image editor

### Paint System Adaptation
Same pattern but for channels:
1. When user switches channel (Ctrl+Q), `update_channel()` fires
2. We call `update_active_channel_on_switch()`
3. This function:
   - Gets the active channel
   - Extracts its source image using `get_channel_source_image()`
   - Updates the image editor using `update_image_editor_image()`

## Key Functions Explained

### `update_image_editor_image(context, image)`
**Purpose**: Updates the image editor to display the specified image

```python
def update_image_editor_image(context, image):
    obj = context.object
    
    if obj and obj.mode == 'EDIT':
        # In EDIT mode: Pin the editor to ensure consistent display
        space = get_edit_image_editor_space(context)
        if space:
            space.use_image_pin = True
            space.image = image
    else:
        # In other modes: Use first unpinned editor
        space = get_first_unpinned_image_editor_space(context)
        if space:
            space.image = image
            space.use_image_pin = False  # Keep it unpinned
```

### `get_channel_source_image(channel)`
**Purpose**: Extracts the displayable image from a channel

Priority:
1. If channel has `bake_image` and `use_bake_image` is True → use it
2. If channel has an `image` property → use it
3. If channel has a `node_tree` with image nodes → find and use first image node
4. Otherwise → return None

## Testing Checklist

- [ ] Restart Blender to reload addon
- [ ] Create a Paint System material with multiple channels
- [ ] Switch between channels using the UI (click channel in list)
- [ ] Verify image editor updates to show each channel's source image
- [ ] Try Ctrl+Q switching if implemented
- [ ] Test in both EDIT mode and other modes
- [ ] Check that no errors appear in console

## Troubleshooting

### Image editor doesn't update
1. Check console for errors
2. Verify `bpy.ops.image_paint` is available (requires Texture Paint or IMAGE_EDITOR active)
3. Ensure image editor space exists in your layout
4. Try restarting Blender

### Multiple image editors don't update correctly
This is expected behavior when not using the recorded editor indices. The function finds the first unpinned editor.
- Solution: Pin your preferred editor manually if needed

### Mode-specific issues
- **EDIT mode**: Editor should pin automatically
- **PAINT mode**: Editor should stay unpinned and update on each channel switch

## Reference Implementation Details

UCUpaint sources:
- **BakeTarget.py, line 19**: `update_active_bake_target_index()` - The callback
- **BakeTarget.py, line 142**: Where callback is registered to `active_bake_target_index` property
- **common.py, line 1160**: `update_image_editor_image()` - Core update function
- **common.py, line 1176**: `get_edit_image_editor_space()` - Mode-specific editor finding

## Benefits

✅ **Seamless Workflow** - No manual refresh needed  
✅ **Automatic** - Works with all channel switching methods  
✅ **Robust** - Safe error handling, won't break existing functionality  
✅ **User-Friendly** - Matches UCUpaint's proven UX  
✅ **Mode-Aware** - Different behavior for EDIT vs other modes  

## Next Steps

1. Copy the code from `operators/image_editor_sync.py`
2. Integrate into `paintsystem/data.py` following Option A or B above
3. Test thoroughly in different scenarios
4. Consider adding Ctrl+Q keymap if not already present

