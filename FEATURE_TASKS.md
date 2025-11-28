# Paint System - Comprehensive Feature Task List

## 🎯 Active Development: UV Edit Mode Workflow

### **AGENT 1: UV Mode State Management**
**Specialization**: Blender operators, modal operations, scene state management

#### Tasks:
1. **Create UV Edit Mode Operator** (`operators/uv_edit_operators.py`)
   - [ ] `PAINTSYSTEM_OT_EnterUVEditMode` operator
   - [ ] Store original UV map reference
   - [ ] Create/copy target UV based on mode (Auto/Existing/New)
   - [ ] Set active UV to target
   - [ ] Disable painting operations (add modal handler)
   - [ ] Store mode state in scene properties

2. **Create Apply Changes Operator** (`operators/uv_edit_operators.py`)
   - [ ] `PAINTSYSTEM_OT_ApplyUVChanges` operator
   - [ ] Validate UV maps exist
   - [ ] Trigger baking pipeline
   - [ ] Update all layers using the UV
   - [ ] Update all objects with same material
   - [ ] Optional UV cleanup
   - [ ] Exit UV edit mode

3. **Create Cancel Operator** (`operators/uv_edit_operators.py`)
   - [ ] `PAINTSYSTEM_OT_CancelUVEdit` operator
   - [ ] Restore original active UV
   - [ ] Delete temporary UV if created
   - [ ] Re-enable painting
   - [ ] Clear mode state

4. **Scene Properties** (`paintsystem/data.py`)
   - [ ] `ps_uv_edit_mode_active: BoolProperty`
   - [ ] `ps_uv_original_map: StringProperty`
   - [ ] `ps_uv_target_map: StringProperty`
   - [ ] `ps_uv_keep_old: BoolProperty`
   - [ ] `ps_uv_cleanup_others: BoolProperty`
   - [ ] `ps_uv_replace_image: BoolProperty`

---

### **AGENT 2: Baking Pipeline Integration**
**Specialization**: Cycles baking, image operations, multi-object processing

#### Tasks:
1. **Multi-Layer Baking** (`operators/bake_operators.py`)
   - [ ] Extend `Channel.bake()` to accept source/target UV parameters
   - [ ] Add `bake_all_layers_with_uv()` function
   - [ ] Iterate through all layers in channel
   - [ ] Bake each layer from source UV to target UV
   - [ ] Handle alpha channels properly
   - [ ] Update layer UV references after bake

2. **Multi-Object Baking** (`operators/bake_operators.py`)
   - [ ] Add `bake_all_material_users()` function
   - [ ] Find all objects using the material
   - [ ] Sync UV names across all objects first
   - [ ] Loop through objects with `use_clear=False` for accumulation
   - [ ] Handle different mesh topologies
   - [ ] Report progress and errors per object

3. **Image Management** (`operators/bake_operators.py`)
   - [ ] Handle "Replace Image" mode
   - [ ] Handle "Create New Image" mode
   - [ ] Copy image settings (resolution, format, color space)
   - [ ] Update image references in all layers
   - [ ] Pack images if requested
   - [ ] Handle UDIM tiles properly

4. **UV Map Management** (`operators/uv_edit_operators.py`)
   - [ ] Implement UV cleanup function
   - [ ] Keep original UV + target UV only
   - [ ] Remove all other UV maps
   - [ ] Update active render UV
   - [ ] Validate UV references in all layers

---

### **AGENT 3: UI/UX Implementation**
**Specialization**: Blender UI panels, conditional layouts, user feedback

#### Tasks:
1. **UV Edit Mode Panel States** (`panels/uv_editor_panels.py`)
   - [ ] Detect if in UV edit mode (`ps_uv_edit_mode_active`)
   - [ ] **Normal State UI**: Current setup + "Enter UV Edit" button
   - [ ] **UV Edit State UI**: Baking settings + Apply/Cancel buttons
   - [ ] Add visual indicator (alert bar) when in edit mode
   - [ ] Disable painting-related UI when in edit mode

2. **Information Display** (`panels/uv_editor_panels.py`)
   - [ ] Show current UV map with icon
   - [ ] List objects using this material (collapsible)
   - [ ] Display UDIM status prominently
   - [ ] Show original → target UV mapping
   - [ ] Layer count affected display

3. **Baking Settings Panel** (`panels/uv_editor_panels.py`)
   - [ ] Image output section (size, format, resolution)
   - [ ] Replace vs New Image toggle
   - [ ] Keep Old UV toggle
   - [ ] Cleanup Other UVs toggle
   - [ ] Preview affected layers list
   - [ ] Apply button (large, prominent)
   - [ ] Cancel button (secondary styling)

4. **User Feedback** (`panels/uv_editor_panels.py`)
   - [ ] Progress indication during baking
   - [ ] Success/error messages via reports
   - [ ] Confirmation dialogs for destructive actions
   - [ ] Tooltips explaining each option

---

### **AGENT 4: Performance & Optimization**
**Specialization**: Caching, threading, progress tracking

#### Tasks:
1. **Material User Detection Cache** (`panels/common.py`)
   - [x] ~~Already implemented: `check_group_multiuser` cache~~
   - [ ] Add `get_material_users()` cached function
   - [ ] Cache object list per material
   - [ ] Invalidate cache on scene changes
   - [ ] Add to `clear_panel_caches()`

2. **Progress Tracking** (`operators/uv_edit_operators.py`)
   - [ ] Add WindowManager progress indicator
   - [ ] Update during multi-object baking
   - [ ] Show current layer being baked
   - [ ] Allow cancellation mid-process
   - [ ] Cleanup on cancel

3. **Background Operations** (Future)
   - [ ] Research Blender background baking
   - [ ] Implement non-blocking bake if possible
   - [ ] Queue system for multiple operations
   - [ ] Progress notifications

4. **Cache Management** (`panels/uv_editor_panels.py`)
   - [x] ~~Already implemented: UDIM cache~~
   - [ ] Add UV map list cache per object
   - [ ] Cache layer UV dependencies
   - [ ] Clear caches on UV operations

---

## 🚀 Additional Paint System Features

### **AGENT 5: Layer Management Enhancements**
**Specialization**: Layer hierarchy, blend modes, masking

#### Tasks:
1. **Layer Groups**
   - [ ] Nested folder organization
   - [ ] Group blend modes
   - [ ] Group opacity controls
   - [ ] Expand/collapse states

2. **Advanced Masking**
   - [ ] Vector masks
   - [ ] Gradient masks
   - [ ] Procedural masks
   - [ ] Mask operations (add/subtract/intersect)

3. **Smart Objects**
   - [ ] Non-destructive layer transforms
   - [ ] Edit in place
   - [ ] Linked instances

---

### **AGENT 6: Brush & Painting Tools**
**Specialization**: Texture painting, brush dynamics, tool presets

#### Tasks:
1. **Brush Presets**
   - [ ] Preset library system
   - [ ] Import/export brush packs
   - [ ] Thumbnail generation
   - [ ] Categorization/tagging

2. **Advanced Brush Dynamics**
   - [ ] Pressure curves
   - [ ] Tilt support
   - [ ] Rotation jitter
   - [ ] Custom falloff curves

3. **Painting Tools**
   - [ ] Clone stamp tool
   - [ ] Healing brush
   - [ ] Smudge tool enhancements
   - [ ] Pattern stamp

---

### **AGENT 7: Channel & Material System**
**Specialization**: PBR workflows, material templates, channel management

#### Tasks:
1. **Material Templates**
   - [ ] Template presets (PBR, NPR, Stylized)
   - [ ] Auto-setup channel structure
   - [ ] Smart defaults for channels
   - [ ] Template sharing/import

2. **Channel Enhancements**
   - [ ] Channel linking/unlinking
   - [ ] Channel presets
   - [ ] Channel operations (copy/merge)
   - [ ] Normal map baking improvements

3. **PBR Workflow**
   - [ ] Metallic/Roughness workflow
   - [ ] Specular/Glossiness workflow
   - [ ] Channel conversion tools
   - [ ] Material validator

---

### **AGENT 8: Baking & Export**
**Specialization**: Texture baking, export formats, LOD generation

#### Tasks:
1. **Advanced Baking**
   - [ ] Ambient occlusion baking
   - [ ] Curvature map generation
   - [ ] Multi-resolution baking
   - [ ] Bake queue system

2. **Export Pipeline**
   - [ ] Batch export presets
   - [ ] Multiple format support
   - [ ] Automatic compression
   - [ ] Texture atlas generation

3. **LOD Support**
   - [ ] Generate LOD textures
   - [ ] Resolution stepping
   - [ ] Detail preservation algorithms
   - [ ] LOD preview

---

### **AGENT 9: UV Tools Extended**
**Specialization**: UV operations, unwrapping, packing

#### Tasks:
1. **UV Unwrapping**
   - [ ] Custom unwrap presets
   - [ ] Smart UV with settings
   - [ ] Angle-based unwrap
   - [ ] Cylinder/sphere projections

2. **UV Packing**
   - [ ] Advanced packing algorithm
   - [ ] Island rotation options
   - [ ] Margin settings
   - [ ] Pack multiple objects

3. **UV Editing**
   - [ ] Straighten UVs
   - [ ] Align/distribute
   - [ ] Scale/rotate islands
   - [ ] UV checker pattern

---

### **AGENT 10: Performance & Stability**
**Specialization**: Memory management, error handling, crash prevention

#### Tasks:
1. **Memory Optimization**
   - [ ] Image cache management
   - [ ] Lazy loading for large textures
   - [ ] Memory usage monitoring
   - [ ] Cleanup unused data

2. **Error Handling**
   - [ ] Comprehensive try/except blocks
   - [ ] Graceful degradation
   - [ ] User-friendly error messages
   - [ ] Error recovery mechanisms

3. **Stability**
   - [ ] Undo/redo system validation
   - [ ] Prevent circular dependencies
   - [ ] Handle missing data gracefully
   - [ ] Scene corruption recovery

---

## 📋 Implementation Priority

### **Phase 1: UV Edit Mode (Current)**
- AGENT 1, 2, 3, 4 working together
- Target: Complete UV workflow feature

### **Phase 2: Core Improvements**
- AGENT 5: Layer system enhancements
- AGENT 6: Brush tools expansion
- AGENT 10: Stability improvements

### **Phase 3: Advanced Features**
- AGENT 7: Material system expansion
- AGENT 8: Baking pipeline
- AGENT 9: UV tools suite

### **Phase 4: Polish & Optimization**
- All agents: Bug fixes, performance, UX refinement

---

## 🔧 Development Guidelines

### Code Structure
- Follow existing patterns in `operators/`, `panels/`, `paintsystem/`
- Use `PSContextMixin` for context parsing
- Inherit from `MultiMaterialOperator` for batch ops
- Add update callbacks to properties

### Testing Checklist
- [ ] Test with single object
- [ ] Test with multiple objects
- [ ] Test with linked materials
- [ ] Test with UDIM textures
- [ ] Test undo/redo
- [ ] Test with different Blender versions

### Documentation
- Docstrings for all functions/classes
- Update `copilot-instructions.md` for new patterns
- Add tooltips to UI elements
- Update README with new features

---

## 🤝 Agent Coordination

### Communication Points
- **Agent 1 → Agent 2**: UV map names, mode state, trigger baking
- **Agent 2 → Agent 3**: Baking progress, completion status, errors
- **Agent 3 → Agent 1**: User actions, mode transitions
- **Agent 4 → All**: Cache invalidation, performance metrics

### Shared Resources
- `paintsystem/data.py`: Scene properties (coordinate changes)
- `operators/common.py`: Mixins and utilities
- `panels/common.py`: UI utilities and caches

### Integration Testing
- Test complete UV Edit workflow end-to-end
- Verify state transitions
- Check multi-object scenarios
- Validate error recovery

---

*Generated: November 27, 2025*
*Branch: Help-tawan-pls-27/11*
