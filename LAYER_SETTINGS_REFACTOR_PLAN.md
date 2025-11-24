# Layer Settings Panel Refactor Plan

## Current Structure

```
Paint System Panel Hierarchy (VIEW_3D)
└── MAT_PT_Layers
    └── MAT_PT_LayerSettings (Parent)
        ├── [Primary Section - Inline in draw()]
        │   ├── Warnings box
        │   ├── layer_settings_ui() - legacy/modern toggle strip
        │   │   ├── Clip toggle (is_clip)
        │   │   ├── Lock Alpha toggle (IMAGE only)
        │   │   ├── Lock Layer toggle
        │   │   ├── Blend Mode dropdown
        │   │   └── Opacity slider
        │   └── Type-specific controls (inline match statement)
        │       ├── ADJUSTMENT: template_node_inputs(adjustment_node)
        │       ├── NODE_GROUP: template_node_inputs(custom nodes)
        │       ├── ATTRIBUTE: template_node_inputs(attribute_node)
        │       ├── GRADIENT: gradient settings + empty object
        │       ├── SOLID_COLOR: color picker
        │       ├── RANDOM: seed + HSV controls
        │       ├── TEXTURE: texture type + template_node_inputs
        │       └── GEOMETRY: geometry type + optional controls
        │
        ├── MAT_PT_GreasePencilMaskSettings (Grease Pencil, DEFAULT_CLOSED)
        ├── MAT_PT_GreasePencilOnionSkinningSettings (Grease Pencil, DEFAULT_CLOSED)
        ├── MAT_PT_LayerTransformSettings (IMAGE/TEXTURE, DEFAULT_CLOSED)
        │   ├── Coordinate Type dropdown
        │   ├── UV Map selection (UV mode)
        │   ├── Empty object controls (DECAL mode)
        │   ├── Warning box (non-UV modes)
        │   └── Mapping node inputs (transform)
        │
        ├── MAT_PT_ImageLayerSettings (IMAGE only, DEFAULT_CLOSED)
        │   ├── Correct Aspect toggle
        │   ├── External edit operators
        │   ├── image_node_settings() helper
        │   │   ├── Image selector
        │   │   ├── Color space
        │   │   ├── Alpha mode
        │   │   ├── Extension mode
        │   │   └── Interpolation
        │   └── UDIM management (if is_udim)
        │
        ├── MAT_PT_UDIMTileManagement (IMAGE + is_udim, DEFAULT_CLOSED)
        │   ├── Tile summary (total/painted/dirty)
        │   ├── Tile grid visualization
        │   └── Tile action operators
        │
        └── MAT_PT_UDIMTileList (IMAGE + is_udim + tiles exist, DEFAULT_CLOSED)
            └── Detailed tile list with controls
```

## Proposed New Structure

```
Paint System Panel Hierarchy (VIEW_3D)
└── MAT_PT_Layers
    └── MAT_PT_LayerSettings (Parent - REFACTORED)
        │
        ├── [PRIMARY CONTROLS SECTION - Always Visible]
        │   │
        │   ├── Status Badge Row (new)
        │   │   ├── Layer type icon + name
        │   │   ├── UDIM badge (if is_udim)
        │   │   └── Linked badge (if is_linked)
        │   │
        │   ├── Quick Controls Strip (refactored layer_settings_ui)
        │   │   ├── Enabled toggle (eye icon)
        │   │   ├── Lock Layer toggle
        │   │   ├── Lock Alpha toggle (IMAGE only)
        │   │   ├── Blend Mode dropdown
        │   │   └── Opacity slider
        │   │
        │   └── Essential Type-Specific Controls (condensed)
        │       ├── IMAGE: Image selector + Use Bake Image toggle
        │       ├── GRADIENT: Gradient type dropdown + color ramp
        │       ├── SOLID_COLOR: Color picker
        │       ├── ADJUSTMENT: Adjustment type (read-only) + key sliders
        │       ├── TEXTURE: Texture type dropdown
        │       ├── ATTRIBUTE: Attribute name selector
        │       ├── RANDOM: Base color + variance sliders
        │       └── GEOMETRY: Geometry type dropdown
        │
        ├── [ADVANCED PANEL DISCLOSURE]
        │   └── "More Settings..." button (operator that expands advanced)
        │
        ├── MAT_PT_LayerSettingsAdvanced (NEW - DEFAULT_CLOSED)
        │   │
        │   ├── Layer Properties Subgroup
        │   │   ├── Clip to Below (is_clip)
        │   │   ├── Auto Update Node Tree toggle
        │   │   ├── UID display (read-only)
        │   │   └── Linked layer info (if linked)
        │   │
        │   ├── Type-Specific Advanced (moved from inline)
        │   │   ├── IMAGE:
        │   │   │   ├── Color space
        │   │   │   ├── Alpha mode
        │   │   │   ├── Extension mode
        │   │   │   ├── Interpolation
        │   │   │   ├── Correct aspect toggle
        │   │   │   └── External edit operators
        │   │   │
        │   │   ├── GRADIENT:
        │   │   │   ├── Empty object management
        │   │   │   ├── Map range interpolation
        │   │   │   ├── Start/End distance
        │   │   │   └── Steps (if STEPPED)
        │   │   │
        │   │   ├── ADJUSTMENT:
        │   │   │   └── Full template_node_inputs
        │   │   │
        │   │   ├── NODE_GROUP:
        │   │   │   ├── Custom node tree selector
        │   │   │   ├── Socket overrides
        │   │   │   └── Full template_node_inputs
        │   │   │
        │   │   ├── RANDOM:
        │   │   │   └── Random seed control
        │   │   │
        │   │   └── GEOMETRY:
        │   │       ├── Normalize normal toggle
        │   │       ├── Backface culling (BACKFACING type)
        │   │       └── Vector transform inputs
        │   │
        │   └── Debug/Developer Section
        │       ├── Layer version info
        │       └── Node tree name
        │
        ├── MAT_PT_LayerTransform (renamed, DEFAULT_CLOSED)
        │   ├── Coordinate Type dropdown
        │   ├── UV Map selection (UV mode)
        │   ├── Empty object controls (DECAL mode)
        │   ├── Warning box (non-UV modes)
        │   └── Mapping node inputs (transform)
        │
        ├── MAT_PT_ImageSettings (renamed from MAT_PT_ImageLayerSettings)
        │   └── [REMOVED - contents moved to Advanced or Primary]
        │
        ├── MAT_PT_UDIMTiles (renamed, condensed)
        │   ├── Quick tile summary (1 line)
        │   ├── Tile grid (if <10 tiles, else button to expand list)
        │   └── Primary actions (Bake All, Mark Dirty)
        │
        ├── MAT_PT_GreasePencilMask (unchanged)
        └── MAT_PT_GreasePencilOnionSkinning (unchanged)
```

## Key Changes Summary

### 1. Primary Controls Section (Always Visible)
**Before:**
- Warnings
- Legacy/modern toggle strip (clip, lock alpha, lock layer, blend, opacity)
- Full type-specific controls inline (all properties exposed)

**After:**
- Status badge row (type icon, UDIM badge, linked badge)
- Simplified quick controls strip (enabled eye, locks, blend, opacity)
- Minimal type-specific controls (only most-used 1-3 properties)
- "More Settings..." disclosure button

**Frequency-Based Categorization:**
- **High (Primary):** enabled, blend_mode, opacity, lock_layer, lock_alpha, image selector, gradient type, color pickers
- **Medium (Advanced):** coord_type, uv_map, color_space, interpolation, aspect correction, clip, empty objects
- **Low (Advanced):** auto_update_node_tree, socket overrides, debugging info, node tree references

### 2. New MAT_PT_LayerSettingsAdvanced Panel
- Collects all niche/specialist properties
- Grouped by: Layer Properties, Type-Specific Advanced, Debug
- Uses `bl_options = {'DEFAULT_CLOSED'}`
- Parent: `MAT_PT_LayerSettings`

### 3. Consolidated Image Settings
- Remove `MAT_PT_ImageLayerSettings` as separate panel
- Move image selector to primary section
- Move color space, alpha mode, extension to advanced
- Keep UDIM management separate but condensed

### 4. Transform Panel Refinement
- Rename to `MAT_PT_LayerTransform` for clarity
- Keep as child panel (coordinate/UV is medium-frequency)
- Maintain current structure

### 5. UDIM Panel Simplification
- Rename to `MAT_PT_UDIMTiles`
- Show inline summary if ≤10 tiles
- Use child panel (`MAT_PT_UDIMTileList`) for detailed view

## Implementation Checklist

- [ ] 1. Analyze current layer_settings_ui() in panels/common.py
  - Identify all controls and their usage frequency
  - Map to primary vs advanced categories

- [ ] 2. Create primary controls layout function
  - Status badge row (type icon, UDIM/linked badges)
  - Simplified quick controls strip
  - Minimal type-specific controls (match statement)
  - "More Settings..." button operator

- [ ] 3. Create MAT_PT_LayerSettingsAdvanced panel class
  - Set bl_parent_id = 'MAT_PT_LayerSettings'
  - Set bl_options = {'DEFAULT_CLOSED'}
  - Group sections: Layer Properties, Type-Specific, Debug

- [ ] 4. Refactor draw() in MAT_PT_LayerSettings
  - Replace current inline logic with primary controls function
  - Remove type-specific boxes (move to advanced)
  - Add disclosure button at bottom

- [ ] 5. Populate MAT_PT_LayerSettingsAdvanced.draw()
  - Move niche properties from main panel
  - Add layer properties subgroup (clip, auto_update, UID)
  - Add type-specific advanced sections
  - Add debug section (versions, node tree name)

- [ ] 6. Refactor type-specific controls
  - IMAGE: selector + bake toggle (primary), rest to advanced
  - GRADIENT: type + ramp (primary), empty/map range to advanced
  - SOLID_COLOR: color (primary only)
  - ADJUSTMENT: type + 2 key sliders (primary), full inputs to advanced
  - TEXTURE: type dropdown (primary), template_node_inputs to advanced
  - ATTRIBUTE: name selector (primary), template_node_inputs to advanced
  - RANDOM: base color + variance (primary), seed to advanced
  - GEOMETRY: type dropdown (primary), rest to advanced
  - NODE_GROUP: show type only (primary), selectors/inputs to advanced

- [ ] 7. Remove/consolidate panels
  - Remove MAT_PT_ImageLayerSettings (contents redistributed)
  - Rename MAT_PT_UDIMTileManagement → MAT_PT_UDIMTiles
  - Simplify UDIM panel (inline summary for <10 tiles)

- [ ] 8. Update classes tuple in layers_panels.py
  - Add MAT_PT_LayerSettingsAdvanced
  - Remove MAT_PT_ImageLayerSettings
  - Rename UDIM panels

- [ ] 9. Test and validate
  - Test all layer types (IMAGE, GRADIENT, ADJUSTMENT, etc.)
  - Verify controls appear in correct sections
  - Check disclosure button navigation
  - Test with legacy UI mode
  - Test with UDIM layers
  - Test with linked layers

## UI/UX Principles

1. **Progressive Disclosure:** Most users need 3-5 controls; advanced users can expand
2. **Frequency-Based Layout:** Daily controls visible, weekly controls one click away
3. **Type-Appropriate Defaults:** Each layer type shows its most-used properties
4. **Visual Hierarchy:** Status badges > Quick controls > Type-specific > Advanced button
5. **Discoverability:** "More Settings..." link ensures users know advanced options exist
6. **Consistency:** Similar to Blender's modifier panels (basic view + advanced)

## Expected Benefits

1. **Reduced Visual Clutter:** Primary panel ~40% shorter for typical use
2. **Faster Workflow:** High-frequency controls always visible, no scrolling
3. **Better Organization:** Related properties grouped logically in advanced
4. **Scalability:** Easy to add new properties without overwhelming primary UI
5. **Flexibility:** Power users can keep advanced panel open, beginners stay simple
