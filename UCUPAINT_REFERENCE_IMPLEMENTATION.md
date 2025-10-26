# UCUpaint Reference Implementation: Painting Target Updates on Switch

## Problem Being Solved
When switching the painting target (Ctrl+Q), the UI doesn't update the image editor to show the newly selected target image. Users have to manually trigger a layer update to see the new target.

## Reference Implementation from UCUpaint v2.3.5

### Core Concept
UCUpaint uses a property update callback that automatically refreshes the image editor whenever the active bake target index changes.

### Key Files & Functions

#### 1. **BakeTarget.py** - Update Callback Definition
```python
def update_active_bake_target_index(self, context):
    """
    Called whenever the active_bake_target_index property changes.
    This ensures the image editor displays the currently selected target.
    
    Args:
        self: The object containing the active_bake_target_index property
        context: Blender context
    """
    yp = self  # In this case, 'self' is the root property group
    tree = self.id_data  # Get the associated node tree
    
    try: 
        bt = yp.bake_targets[yp.active_bake_target_index]
    except: 
        return  # Safe exit if index is invalid

    # Get the image node associated with this bake target
    bt_node = tree.nodes.get(bt.image_node)
    if bt_node and bt_node.image:
        # Call the image editor update function with the target image
        update_image_editor_image(context, bt_node.image)
    else:
        # If no image, clear the image editor
        update_image_editor_image(context, None)
```

#### 2. **common.py** - Image Editor Update Function
```python
def update_image_editor_image(context, image):
    """
    Updates the image editor to display the specified image.
    Handles both EDIT mode and other modes differently.
    
    Args:
        context: Blender context
        image: The image to display (can be None)
    """
    obj = context.object
    scene = context.scene

    if obj.mode == 'EDIT':
        # In EDIT mode: Pin the image editor to the specified image
        space = get_edit_image_editor_space(context)
        if space:
            space.use_image_pin = True
            space.image = image
    else:
        # In other modes: Use first unpinned image editor
        space = get_first_unpinned_image_editor_space(context)
        if space:
            space.image = image
            # Hack for Blender 2.8 which keeps pinning image automatically
            space.use_image_pin = False

def get_edit_image_editor_space(context):
    """
    Retrieves the image editor space that was previously recorded
    as the edit image editor (for EDIT mode).
    
    Returns:
        The image editor space, or None if not found
    """
    ypwm = context.window_manager.ypprops
    area_index = ypwm.edit_image_editor_area_index
    window_index = ypwm.edit_image_editor_window_index
    
    if window_index >= 0 and window_index < len(context.window_manager.windows):
        window = context.window_manager.windows[window_index]
        if area_index >= 0 and area_index < len(window.screen.areas):
            area = window.screen.areas[area_index]
            if area.type == 'IMAGE_EDITOR' and (not is_bl_newer_than(2, 80) or area.spaces[0].mode == 'UV'):
                return area.spaces[0]
    
    return None

def get_first_unpinned_image_editor_space(context):
    """
    Finds the first image editor space that is not pinned.
    
    Returns:
        The first unpinned image editor space, or None if not found
    """
    # Implementation would iterate through all areas in all windows
    # and find the first IMAGE_EDITOR space with use_image_pin == False
    pass
```

#### 3. **Root.py or UI Property Definition** - Property with Update Callback
```python
# In the Root property group class definition:
active_bake_target_index : IntProperty(
    name = 'Active Bake Target',
    description = 'Active bake target index',
    default = 0,
    update = update_active_bake_target_index  # <-- KEY: This callback is crucial
)
```

## Adaptation for Paint System

### Step 1: Create Update Function in `common.py`
Similar to UCUpaint, create functions to:
1. Find the active channel's source image
2. Update the image editor to display it

### Step 2: Add Update Callback to Channel Properties
In your channel data class, add the `update` parameter to the active channel index property:

```python
active_index : IntProperty(
    name = 'Active Channel',
    update = update_active_channel_index  # Add this
)
```

### Step 3: Implement the Update Callback
```python
def update_active_channel_index(self, context):
    """
    Called when active channel is switched (e.g., via Ctrl+Q).
    Updates image editor to show the new channel's source image.
    """
    # Get the active channel
    channel = self.channels[self.active_index]
    
    # Get the channel's source image
    image = get_channel_source_image(channel)
    
    # Update the image editor
    update_image_editor_image(context, image)
```

### Step 4: Register Image Editor Tracking
In your window manager properties, track which image editor is active:

```python
# In window_manager properties
edit_image_editor_area_index : IntProperty(default=-1)
edit_image_editor_window_index : IntProperty(default=-1)
```

## Key Benefits

✅ **Automatic Updates**: Image editor updates without manual layer triggering  
✅ **Mode-Aware**: Different behavior for EDIT vs other modes  
✅ **Safe**: Graceful handling of missing images or invalid indices  
✅ **User-Friendly**: Seamless workflow when switching channels  

## Implementation Checklist

- [ ] Copy `update_image_editor_image()` function pattern from UCUpaint
- [ ] Copy `get_edit_image_editor_space()` helper function
- [ ] Create `update_active_channel_index()` callback
- [ ] Add `update=` parameter to active channel index property
- [ ] Add image editor tracking properties to window manager
- [ ] Test switching channels with Ctrl+Q
- [ ] Verify image editor updates without manual refresh

## Reference Files Location
- **UCUpaint BakeTarget.py**: Line 19-29 (update callback)
- **UCUpaint common.py**: Line 1160-1185 (update functions)
- **UCUpaint**: Used as reference for proper image editor handling in Blender

