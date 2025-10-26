# Quick Integration - Exact Code to Add

## Step 1: Update `paintsystem/data.py`

### Add import at top of file (around line 20-40):
```python
from ..operators.image_editor_sync import update_active_channel_on_switch
```

### Modify `update_channel` function (around line 1303):

**BEFORE:**
```python
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
```

**AFTER:**
```python
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
        
        # NEW: Update image editor when channel is switched (Reference: UCUpaint)
        update_active_channel_on_switch(self, context)
```

That's it! The `active_index` property definition stays unchanged:
```python
    active_index: IntProperty(name="Active Channel Index", update=update_channel)
```

## Step 2: Verify Integration

### In Blender:
1. Open Blender console (Window → Toggle System Console)
2. Load your Paint System addon
3. Create a Paint System material
4. Add multiple channels
5. Switch between channels
6. Check console for any errors from `image_editor_sync.py`

### Expected Behavior:
- Image editor should show different images as you switch channels
- No console errors should appear
- The functionality should be silent and automatic

## Reference Info

**UCUpaint Reference:**
- Bake Target callback: `BakeTarget.py` line 19
- Image editor update: `common.py` line 1160

**Paint System Files Modified:**
- ✅ `operators/image_editor_sync.py` (NEW - Created)
- ✅ `paintsystem/data.py` (MODIFY - Add import + 2 lines to update_channel)

## Testing Commands

In Blender Python Console:
```python
# Test that the function is available
from paint_system.operators.image_editor_sync import update_active_channel_on_switch
print("Successfully imported update_active_channel_on_switch")

# Check active channel
mat = bpy.context.object.active_material
if hasattr(mat, 'ps_mat_data'):
    group = mat.ps_mat_data.active_group
    print(f"Active channel: {group.channels[group.active_index].name}")
```

## Troubleshooting

**Import Error?**
- Make sure `image_editor_sync.py` is in the `operators/` folder
- Verify the relative import path is correct

**Function not being called?**
- Check that `update_channel` function is actually being called (add a print statement)
- Verify Blender reloaded the addon (toggle it off/on)

**Image editor not updating?**
- Ensure you have an Image Editor in your layout
- Try switching to EDIT mode (texture paint)
- Check the console for any exceptions

