# UV Transfer Multi-Object/UDIM Implementation Tasks

## Overview
The UV Transfer feature needs to handle multiple objects sharing the same material, with proper UDIM support and per-object image creation to prevent texture breakage.

---

## Agent 1: Multi-Object Transfer Architecture

**Responsibility:** Extend transfer UV operator to handle multiple objects with material sharing detection

### Tasks:
- [ ] **1.1: Inherit from MultiMaterialOperator**
  - [ ] Change `PAINTSYSTEM_OT_TransferImageLayerUVDirect` to inherit from `MultiMaterialOperator`
  - [ ] Add `multiple_objects` and `multiple_materials` BoolProperty flags
  - [ ] Update poll() method to detect multiple objects with shared material

- [ ] **1.2: Implement process_material() method**
  - [ ] Extract current execute() logic into process_material()
  - [ ] Ensure context.temp_override is used correctly per object
  - [ ] Handle per-object active layer assignment
  - [ ] Create unique transferred images per object (append object name to image)

- [ ] **1.3: Object detection and validation**
  - [ ] Detect all objects in scene using the active material
  - [ ] Filter objects by type (MESH only)
  - [ ] Validate each object has compatible UV layers
  - [ ] Warn user about objects that will be skipped

- [ ] **1.4: Update dialog UI**
  - [ ] Add checkbox to enable/disable multi-object processing
  - [ ] Show object count in dialog (e.g., "Will process 5 objects")
  - [ ] Add object list preview (optional expandable section)
  - [ ] Show warnings for incompatible objects

### Validation:
- Transfer single object: Works as before
- Transfer with 3 objects sharing material: Creates 3 separate transferred images
- One object selected, multiple objects exist: Option to process all or just selected
- Mixed object types: Only meshes processed, others skipped with warning

---

## Agent 2: Per-Object Image Management

**Responsibility:** Handle creation and management of unique images per object during transfer

### Tasks:
- [ ] **2.1: Image naming strategy**
  - [ ] Create naming function: `{layer_name}_Transferred_{object_name}`
  - [ ] Handle name conflicts (append .001, .002, etc.)
  - [ ] Preserve UDIM tile naming convention for multi-tile images
  - [ ] Ensure image names are valid (sanitize special characters)

- [ ] **2.2: UDIM detection per object**
  - [ ] Check target UV map on each object individually
  - [ ] Detect UDIM tiles per object (may differ between objects)
  - [ ] Store UDIM info per object during processing
  - [ ] Handle objects with different UDIM layouts

- [ ] **2.3: Image creation with proper settings**
  - [ ] Apply scene settings (resolution, alpha, float, color space) to each image
  - [ ] Create UDIM images when tiles detected on object
  - [ ] Handle non-UDIM fallback for objects without tiles
  - [ ] Pack images individually if pack option enabled

- [ ] **2.4: Image cleanup on failure**
  - [ ] Track created images during batch processing
  - [ ] Implement rollback mechanism if any object fails
  - [ ] Option to keep partial results or clean up all
  - [ ] Proper error reporting per object

### Validation:
- 3 objects, all UDIM: 3 UDIM images created
- 3 objects, 2 UDIM + 1 regular: 2 UDIM + 1 regular image created
- Object name with special chars: Sanitized in image name
- One object fails bake: Other images preserved, error reported

---

## Agent 3: Layer Assignment & Material Synchronization

**Responsibility:** Assign transferred images back to layers and sync across all objects

### Tasks:
- [ ] **3.1: Layer image assignment strategy**
  - [ ] Determine if layer should be shared (same image) or per-object (different images)
  - [ ] For shared material: Consider creating separate layers per object
  - [ ] For linked data: Handle object-level overrides
  - [ ] Update active_layer.image to transferred image per object context

- [ ] **3.2: Material node tree updates**
  - [ ] Update image texture nodes for each object's context
  - [ ] Ensure node tree changes don't affect other objects prematurely
  - [ ] Handle group nodes and channel outputs correctly
  - [ ] Update UV map assignments in nodes

- [ ] **3.3: Channel data synchronization**
  - [ ] Update channel.layers collection appropriately
  - [ ] Handle layer enabled/disabled states consistently
  - [ ] Preserve layer hierarchy and parent relationships
  - [ ] Sync blend modes and opacity across objects

- [ ] **3.4: Post-transfer validation**
  - [ ] Verify each object has correct transferred image assigned
  - [ ] Check UV map assignments are correct per object
  - [ ] Validate material output shows expected result
  - [ ] Report any discrepancies to user

### Validation:
- 3 objects transfer: Each has its own image in layer
- Shared material: All objects render correctly with their images
- One object's transfer modified: Doesn't affect others
- Layer properties preserved: Blend mode, opacity, clip state maintained

---

## Agent 4: Progress Tracking & User Feedback

**Responsibility:** Provide clear feedback during multi-object processing

### Tasks:
- [ ] **4.1: Progress indicators**
  - [ ] Add progress bar for multi-object operations (bpy.context.window_manager.progress_begin/update/end)
  - [ ] Show current object being processed
  - [ ] Display estimated time remaining
  - [ ] Update progress during baking operations

- [ ] **4.2: Real-time status updates**
  - [ ] Update status bar with current operation
  - [ ] Show object count: "Processing object 2/5..."
  - [ ] Display current phase: "Baking...", "Creating image...", "Updating layers..."
  - [ ] Handle cancellation gracefully (ESC key)

- [ ] **4.3: Completion reporting**
  - [ ] Show summary dialog after completion
  - [ ] List successfully processed objects
  - [ ] Report any errors or warnings per object
  - [ ] Display total time taken
  - [ ] Show created image names and sizes

- [ ] **4.4: Error handling and recovery**
  - [ ] Catch exceptions per object without stopping batch
  - [ ] Log detailed error info to console
  - [ ] Offer "Continue" or "Stop on error" option
  - [ ] Save error log to file if requested

### Validation:
- 10 objects transfer: Progress bar updates smoothly
- Cancel mid-transfer: Partial results kept, clean exit
- One object errors: Error reported, others continue
- Completion: Summary shows 9 success, 1 failed with reason

---

## Agent 5: UDIM Handling & Validation

**Responsibility:** Ensure robust UDIM tile detection and image creation

### Tasks:
- [ ] **5.1: Enhanced UDIM detection**
  - [ ] Improve `get_udim_tiles()` function reliability
  - [ ] Cache UDIM detection per UV map per object
  - [ ] Detect UDIM tiles outside 1001 (1002-1100 range)
  - [ ] Handle edge cases (empty UVs, overlapping tiles)

- [ ] **5.2: UDIM image creation**
  - [ ] Use `create_ps_image()` with proper UDIM tile list
  - [ ] Verify all tiles are created in image
  - [ ] Set correct tile labels and properties
  - [ ] Handle UDIM tile fill colors

- [ ] **5.3: UDIM baking process**
  - [ ] Ensure bake covers all UDIM tiles
  - [ ] Verify Blender's bake system handles UDIMs correctly
  - [ ] Check for incomplete tile baking
  - [ ] Validate tile data after bake

- [ ] **5.4: UDIM validation and warnings**
  - [ ] Warn if target UV has UDIMs but source doesn't
  - [ ] Alert if UDIM tiles exceed reasonable count (>20)
  - [ ] Detect mismatched UDIM layouts between objects
  - [ ] Suggest fixes for UDIM issues

### Validation:
- Object with 4 UDIM tiles: Image created with all 4 tiles
- Mixed UDIM objects: Each gets correct tile count
- Source no UDIM, target has UDIM: Proper warning shown
- UDIM bake: All tiles contain correct texture data

---

## Agent 6: Performance Optimization

**Responsibility:** Optimize multi-object transfer for speed and memory efficiency

### Tasks:
- [ ] **6.1: Batch baking optimization**
  - [ ] Investigate baking multiple objects in single pass
  - [ ] Reuse temporary images where possible
  - [ ] Minimize node tree rebuilds
  - [ ] Cache shader compilation

- [ ] **6.2: Memory management**
  - [ ] Monitor memory usage during large batches
  - [ ] Implement streaming for very large object counts
  - [ ] Clear temporary data aggressively
  - [ ] Warn user if memory may be insufficient

- [ ] **6.3: Parallel processing research**
  - [ ] Investigate if objects can be processed in parallel
  - [ ] Check Blender API limitations for threading
  - [ ] Implement safe parallel baking if possible
  - [ ] Fall back to sequential if threading unsafe

- [ ] **6.4: UI responsiveness**
  - [ ] Ensure UI doesn't freeze during long operations
  - [ ] Update progress every N milliseconds, not per object
  - [ ] Use timer callbacks for background processing
  - [ ] Test with 100+ object scenes

### Validation:
- 50 objects: Completes in reasonable time (<5 min)
- Large UDIM images: Memory usage stays under 8GB
- During transfer: UI remains responsive, cancellation works
- Memory cleanup: All temp images freed after transfer

---

## Agent 7: Testing & Quality Assurance

**Responsibility:** Comprehensive testing of all scenarios

### Tasks:
- [ ] **7.1: Unit test creation**
  - [ ] Test single object transfer (baseline)
  - [ ] Test 2-5 object multi-transfer
  - [ ] Test large batch (50+ objects)
  - [ ] Test UDIM vs non-UDIM combinations

- [ ] **7.2: Edge case testing**
  - [ ] No UV layers on object
  - [ ] Invalid UV data (corrupted mesh)
  - [ ] Object with no material slots
  - [ ] Linked library objects
  - [ ] Instanced collections

- [ ] **7.3: Integration testing**
  - [ ] Test with different layer types (image, solid, gradient)
  - [ ] Test with adjustment layers enabled
  - [ ] Test with folder hierarchy
  - [ ] Test with linked layers

- [ ] **7.4: Regression testing**
  - [ ] Ensure single-object workflow still works
  - [ ] Verify existing test scenes don't break
  - [ ] Check backward compatibility with old .blend files
  - [ ] Test on different Blender versions (4.2, 5.0, 5.1)

### Validation:
- All unit tests pass
- Edge cases handled gracefully
- No regressions in existing features
- Works on Blender 4.2+

---

## Agent 8: Documentation & User Guide

**Responsibility:** Create clear documentation for users and developers

### Tasks:
- [ ] **8.1: User documentation**
  - [ ] Write multi-object transfer workflow guide
  - [ ] Create UDIM transfer tutorial
  - [ ] Document all dialog options and settings
  - [ ] Add troubleshooting section

- [ ] **8.2: Developer documentation**
  - [ ] Document `MultiMaterialOperator` pattern usage
  - [ ] Explain per-object image naming strategy
  - [ ] Document UDIM detection caching system
  - [ ] Add code comments for complex logic

- [ ] **8.3: Video tutorials (optional)**
  - [ ] Record basic multi-object transfer demo
  - [ ] Show UDIM workflow example
  - [ ] Demonstrate error recovery
  - [ ] Explain when to use different modes

- [ ] **8.4: In-addon help**
  - [ ] Add tooltips to all new UI elements
  - [ ] Create help popover with examples
  - [ ] Link to online documentation
  - [ ] Show quick tips in status bar

### Validation:
- User can follow docs to complete multi-object transfer
- Developer can understand code architecture from docs
- All UI elements have helpful tooltips
- Documentation matches actual behavior

---

## Implementation Phases

### **Phase 1: Foundation (Agents 1-2)** - Week 1
- Multi-object architecture
- Per-object image management
- Basic functionality working

### **Phase 2: Integration (Agents 3-4)** - Week 2
- Layer assignment and sync
- Progress tracking and feedback
- User-facing features polished

### **Phase 3: Robustness (Agents 5-6)** - Week 3
- UDIM handling improvements
- Performance optimization
- Edge case handling

### **Phase 4: Quality (Agents 7-8)** - Week 4
- Comprehensive testing
- Documentation
- Bug fixes and polish

---

## Critical Integration Points

### Between Agent 1 & 2:
- Agent 1 calls Agent 2's image creation functions per object
- Share object validation logic

### Between Agent 2 & 3:
- Agent 2 creates images, Agent 3 assigns them to layers
- Coordinate on naming and storage

### Between Agent 3 & 5:
- Agent 5 detects UDIMs, Agent 3 uses info for node updates
- Share UDIM cache

### Between Agent 1 & 4:
- Agent 1 triggers progress updates from Agent 4
- Share error handling

---

## Testing Checklist

### Basic Functionality:
- [ ] Single object transfer (no regression)
- [ ] 2 objects, same material, regular UVs
- [ ] 2 objects, same material, UDIM UVs
- [ ] 5 objects, mix of UDIM and regular
- [ ] 10+ objects batch transfer

### Error Scenarios:
- [ ] One object fails baking
- [ ] User cancels mid-transfer
- [ ] Out of memory during large batch
- [ ] Invalid UV data on one object
- [ ] Material missing on one object

### UDIM Scenarios:
- [ ] Source regular → Target UDIM
- [ ] Source UDIM → Target regular
- [ ] Source UDIM (4 tiles) → Target UDIM (4 tiles)
- [ ] Mixed: Some objects UDIM, some regular
- [ ] Very large UDIM (20+ tiles)

### UI/UX:
- [ ] Progress bar updates smoothly
- [ ] Cancel button works at any time
- [ ] Completion summary accurate
- [ ] Error messages clear and helpful
- [ ] Undo works correctly

---

## Known Issues to Address

1. **Original Problem:** Multiple objects share one transferred image, causing texture breakage
   - **Solution:** Create separate image per object with unique names

2. **UDIM Detection Lag:** Checking UDIMs on dialog open can lag
   - **Solution:** Use cached UDIM info, only detect when target UV changes

3. **Baking Message Spam:** "Baking map saved..." appears multiple times
   - **Solution:** Suppress or consolidate progress messages

4. **Layer Image Assignment:** Current layer image assignment may not handle multiple objects
   - **Solution:** Need per-object layer override or separate layer instances

5. **Material Sync Issues:** Changes to one object's material affect all objects
   - **Solution:** Use temp_override carefully, update only within object context

---

## Agent Coordination Rules

1. **Agent 1** is the coordinator - calls other agents in sequence
2. **Agent 2** provides services to Agent 1 & 3 (image creation)
3. **Agent 3** consumes Agent 2's output (assigns images)
4. **Agent 4** runs parallel to Agents 1-3 (progress tracking)
5. **Agent 5** provides validation to Agent 2 (UDIM detection)
6. **Agent 6** optimizes work of Agents 1-3
7. **Agent 7** validates work of all agents
8. **Agent 8** documents work of all agents

---

## Success Criteria

✅ **Core Functionality:**
- Multi-object transfer creates unique images per object
- UDIM images created correctly when tiles detected
- All objects render with correct textures after transfer
- No texture breakage or shared image conflicts

✅ **User Experience:**
- Clear progress indication during transfer
- Intuitive dialog with all needed options
- Helpful error messages and recovery
- Fast enough for practical use (50 objects < 5 min)

✅ **Code Quality:**
- Follows existing Paint System patterns
- Well-documented and maintainable
- Comprehensive test coverage
- No regressions in existing features

✅ **Robustness:**
- Handles edge cases gracefully
- Memory efficient for large batches
- Cancellation works cleanly
- Error recovery without data loss
