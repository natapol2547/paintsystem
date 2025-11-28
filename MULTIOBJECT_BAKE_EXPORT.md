# Multi-Object Bake and Export Implementation

## Summary
Added multi-object support to `PAINTSYSTEM_OT_BakeChannel` and `PAINTSYSTEM_OT_BakeAllChannels` operators, following the proven pattern from `PAINTSYSTEM_OT_TransferImageLayerUVDirect`.

## Changes Made

### 1. PAINTSYSTEM_OT_BakeChannel (Single Channel Baking)
**File**: `operators/bake_operators.py`

#### Class Declaration
- Now inherits from `MultiMaterialOperator, BakeOperator` (was just `BakeOperator`)
- Added `multiple_objects` BoolProperty (default=True)
- Updated description to indicate multi-object support

#### UI (draw method)
- Detects when multiple objects use the same material
- Shows "Multi-Object Baking" section with toggle
- Displays object count (e.g., "All 5 Objects" vs "Only CurrentObject")

#### Logic (execute method)
- Split into `_execute_single_object()` and `_execute_multi_object()`
- Single object: Original behavior preserved exactly
- Multi-object workflow:
  1. Get all mesh objects using the material
  2. Pre-create or get shared baked image (created once, shared across all objects)
  3. Loop through each object with temp_override
  4. Use per-object bake counter for `use_clear` logic (only clear on first object)
  5. Pack images automatically
  6. Comprehensive error handling and progress feedback
  7. Console output showing per-object progress
  8. Report results with success/error counts

### 2. PAINTSYSTEM_OT_BakeAllChannels (All Channels Baking)
**File**: `operators/bake_operators.py`

#### Class Declaration
- Now inherits from `MultiMaterialOperator, BakeOperator` (was just `BakeOperator`)
- Added `multiple_objects` BoolProperty (default=True)
- Updated description to indicate multi-object support

#### UI (draw method)
- Shows multi-object toggle when multiple objects detected
- Same UI pattern as BakeChannel

#### Logic (execute method)
- Split into `_execute_single_object()` and `_execute_multi_object()`
- Single object: Original behavior preserved exactly
- Multi-object workflow:
  1. Get all mesh objects using the material
  2. Pre-create shared baked images for ALL channels before object loop
  3. Initialize per-channel bake counters (for `use_clear` logic)
  4. Loop through each object:
     - Bake all channels for that object
     - Each channel uses its counter for proper clearing
  5. Update all channel settings after all objects complete
  6. Comprehensive error handling per object and per channel
  7. Detailed console output showing progress
  8. Report results with success/error counts

### 3. PAINTSYSTEM_OT_ExportAllImages
**No changes needed** - already works correctly with multi-object baking because:
- It exports the shared baked images from channels
- Images are pre-created and shared when using multi-object baking
- Export doesn't need to know about multiple objects

## Technical Implementation Details

### Per-Object vs Per-Channel Bake Counters
- **BakeChannel**: Uses simple `bake_count` variable (one channel, multiple objects)
- **BakeAllChannels**: Uses `channel_bake_counts` dict (multiple channels × multiple objects)
- Both ensure `use_clear=True` only for first object per layer/channel
- Prevents image clearing on subsequent objects

### Shared Image Creation
Images are created ONCE before the object loop:
```python
# Create shared image
bake_image = self.create_image(context)
bake_image.pack()  # Important: pack immediately

# Then bake each object into the same image
for obj in objects:
    channel.bake(context, mat, bake_image, uv_name, use_clear=(count == 0))
    count += 1
```

### Error Handling
- UV layer validation per object
- Try/except per object (continues on failure)
- Detailed console output for debugging
- User-friendly summary reports
- Distinguishes between partial success and total failure

### Progress Feedback
Console output shows:
```
Baking channel 'Base Color' for 3 objects...
[1/3] Baking Cube...
  ✓ Cube baked successfully
[2/3] Baking Sphere...
  ✓ Sphere baked successfully
[3/3] Baking Cylinder...
  ⚠ Skipping Cylinder: UV 'UVMap' not found
```

User sees:
- INFO: "Successfully baked channel for 2 object(s)."
- WARNING: "Baked channel for 2/3 objects. 1 failed - check console."
- ERROR: "Baking failed for all 3 objects. Check console for details."

## User Workflow

### Before (Single Object)
1. Select object with Paint System material
2. Bake Channel → bakes only that object
3. Select another object with same material
4. Bake Channel again → creates separate baked images (Material.001, Material.002, etc.)
5. Textures not shared, memory wasted

### After (Multi-Object, Default)
1. Select any object with Paint System material
2. Bake Channel → automatically detects 5 objects using material
3. Shows "All 5 Objects" toggle (enabled by default)
4. Bake → creates ONE shared baked image
5. All 5 objects baked into same image
6. Images packed automatically
7. Progress shown in console
8. Export works seamlessly with shared images

### Toggle to Single Object
- User can toggle off "All 5 Objects" → changes to "Only CurrentObject"
- Original single-object behavior preserved
- Useful for testing or debugging individual objects

## Pattern Consistency

This implementation follows the exact pattern from `PAINTSYSTEM_OT_TransferImageLayerUVDirect`:
- ✓ MultiMaterialOperator inheritance
- ✓ multiple_objects BoolProperty with auto-detection
- ✓ _get_objects_with_material() for object collection
- ✓ Pre-create shared images before object loop
- ✓ temp_override for each object
- ✓ Per-layer/channel bake counters for use_clear logic
- ✓ Comprehensive error handling
- ✓ Progress feedback and console output
- ✓ Auto-packing of images
- ✓ User-friendly summary reports

## Backwards Compatibility
- ✓ Single-object behavior preserved (toggle off or only one object)
- ✓ No breaking changes to existing functionality
- ✓ Export operator works seamlessly with new multi-object baking
- ✓ All original parameters and options retained

## Testing Checklist
- [ ] Bake single channel with multiple objects
- [ ] Bake all channels with multiple objects
- [ ] Verify images are shared (not duplicated)
- [ ] Test with objects missing UV layers
- [ ] Test toggle between multi/single object
- [ ] Test with UDIM tiles
- [ ] Export images after multi-object bake
- [ ] Verify use_clear logic (first object clears, others don't)
- [ ] Test error handling (one object fails)
- [ ] Verify progress feedback and console output
- [ ] Test with as_layer option
- [ ] Test with as_tangent_normal option (Vector channels)

## Future Enhancements
- Consider adding object selection filter in UI
- Add "Select Objects" button to show which objects will be baked
- Option to skip objects with missing UVs vs error
- Batch processing progress bar in UI (not just console)
