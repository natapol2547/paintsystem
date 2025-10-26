# Implementation Checklist

## Pre-Implementation Review

- [ ] Read `QUICK_INTEGRATION.md` for overview
- [ ] Read `UCUPAINT_REFERENCE_COMPARISON.md` to understand the pattern
- [ ] Backup your current `paintsystem/data.py` file
- [ ] Close Blender or prepare to reload addon

## Implementation Steps

### Step 1: Copy the Module
- [ ] Locate `operators/image_editor_sync.py` in your Paint System addon
- [ ] Verify it exists and has ~230 lines of code
- [ ] Verify it contains these functions:
  - [ ] `get_edit_image_editor_space()`
  - [ ] `get_first_unpinned_image_editor_space()`
  - [ ] `update_image_editor_image()`
  - [ ] `get_channel_source_image()`
  - [ ] `update_active_channel_on_switch()`

### Step 2: Modify `paintsystem/data.py`

#### Add Import (around line 20-40)
- [ ] Add this line with other imports:
  ```python
  from ..operators.image_editor_sync import update_active_channel_on_switch
  ```

#### Modify `update_channel()` Function (around line 1303)
- [ ] Find the `update_channel()` function in the Channel class
- [ ] Add this line at the END of the function:
  ```python
  update_active_channel_on_switch(self, context)
  ```
- [ ] Verify the modified function looks like:
  ```python
  def update_channel(self, context):
      ps_ctx = parse_context(context)
      ps_mat_data = ps_ctx.ps_mat_data
      if ps_mat_data.preview_channel:
          bpy.ops.paint_system.isolate_active_channel('EXEC_DEFAULT')
          bpy.ops.paint_system.isolate_active_channel('EXEC_DEFAULT')
      if ps_ctx.active_channel.use_bake_image:
          bpy.ops.object.mode_set(mode="OBJECT")
      update_active_image(self, context)
      
      # NEW LINE ADDED:
      update_active_channel_on_switch(self, context)
  ```

### Step 3: Verify No Syntax Errors
- [ ] Check that indentation matches existing code
- [ ] Verify no typos in import or function call
- [ ] Check that files were saved

## Testing

### Basic Setup
- [ ] Restart Blender or reload addon (Ctrl+Shift+R or toggle off/on)
- [ ] Check console for import errors
- [ ] No errors should appear when addon loads

### Create Test Material
- [ ] Create a new material with Paint System
- [ ] Use one of the templates (e.g., "PBR")
- [ ] Verify material has multiple channels created
- [ ] Open an Image Editor window in your layout

### Test Channel Switching
- [ ] Click on the first channel in the channels list
- [ ] Verify Image Editor shows that channel's image
- [ ] Click on the second channel
- [ ] Verify Image Editor updates to show new channel's image
- [ ] Repeat for all channels
- [ ] Try rapidly switching channels
- [ ] All should update smoothly without manual refresh

### Mode-Specific Testing

#### EDIT Mode (Texture Paint)
- [ ] Select object with Paint System material
- [ ] Enter EDIT mode (Tab or mode dropdown)
- [ ] Switch channels with UI
- [ ] Verify Image Editor updates
- [ ] Pin the Image Editor manually
- [ ] Switch channels again
- [ ] Should still update correctly

#### Object Mode
- [ ] Exit EDIT mode
- [ ] Switch channels with UI
- [ ] Verify Image Editor updates
- [ ] Try with pinned/unpinned Image Editor

### Edge Cases
- [ ] Create material with single channel
- [ ] Switch to and from that channel
- [ ] Should not error
- [ ] Create channel with no image
- [ ] Switch to it
- [ ] Image Editor should clear (show nothing)
- [ ] Switch away
- [ ] Image Editor should show previous image

## Verification Checklist

### Code-Level
- [ ] Import statement added correctly
- [ ] Function call added in right location
- [ ] Indentation matches file style
- [ ] No typos in function names
- [ ] Function is called from `update_channel()`

### Functional
- [ ] Image Editor updates when switching channels via UI
- [ ] No console errors appear
- [ ] Works in both EDIT and Object modes
- [ ] Works with channels that have/don't have images
- [ ] Works with single and multiple channels
- [ ] No performance issues (lag/freeze)

### No Regression
- [ ] Existing channel switching still works
- [ ] Layer isolation still works (if previously working)
- [ ] Bake image functionality still works
- [ ] Other addon features unchanged

## Troubleshooting During Testing

### Image Editor Doesn't Update
1. [ ] Verify Image Editor window exists in your layout
2. [ ] Check console for errors with pattern: "Error updating channel on switch:"
3. [ ] Try switching to EDIT mode first
4. [ ] Verify channel actually has a source image
5. [ ] Check that you added the import correctly
6. [ ] Check that you called the function from `update_channel()`

### Import Error
1. [ ] Verify `operators/image_editor_sync.py` exists
2. [ ] Check that relative import path is correct
3. [ ] Verify no circular imports
4. [ ] Reload addon (toggle off/on)

### No Error But Nothing Happens
1. [ ] Verify `update_channel()` is being called (add print statement)
2. [ ] Verify Image Editor spaces exist in context
3. [ ] Try with a fresh Blender window
4. [ ] Check Blender version (should be 4.2+)

### Crashes/Freezes
1. [ ] Look for infinite loops or recursion in console
2. [ ] Check for circular callback triggers
3. [ ] Verify no blocking Blender API calls
4. [ ] Reduce number of channels to test

## Rollback Steps (If Issues)

If something goes wrong:
1. [ ] Close Blender without saving
2. [ ] Revert `paintsystem/data.py` to backup
3. [ ] Delete `operators/image_editor_sync.py`
4. [ ] Reopen Blender and verify addon works

## Success Criteria ✅

Implementation is successful when:
- ✅ Addon loads without errors
- ✅ Image Editor updates when switching channels
- ✅ No console errors appear
- ✅ Works in both EDIT and Object modes
- ✅ Existing functionality still works
- ✅ No performance degradation

## Final Sign-Off

- [ ] All tests passed
- [ ] No console errors
- [ ] Implementation complete and working
- [ ] Ready for production use
- [ ] Document this checklist was completed (date: ______)

---

**Date Implemented**: _____________  
**Implemented By**: _____________  
**Tested By**: _____________  
**Status**: [ ] In Progress [ ] Complete [ ] Issues Found

**Notes/Issues Found**:
_________________________________________________________________
_________________________________________________________________
_________________________________________________________________

