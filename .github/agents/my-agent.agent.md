# Paint System Copilot Instructions

## Project Overview
Paint System is a Blender 4.0+ addon for non-photorealistic rendering with node-based layer painting. It provides a comprehensive painting workflow using Blender's shader editor and node system to manage textures, adjustments, and effects across multiple layers.

## Architecture

### Core Data Model (paintsystem/data.py)
- **Layer System**: Polymorphic layer types (IMAGE, SOLID_COLOR, ADJUSTMENT, ATTRIBUTE, TEXTURE, GEOMETRY, GRADIENT, RANDOM, NODE_GROUP, FOLDER)
- **Hierarchy**: Layers → Channels → Groups → Materials, managed via `NestedListManager`
- **Blender Integration**: PropertyGroups store layer/channel/group data; Material data (ps_mat_data) extends bpy.types.Material
- **Key Classes**: GlobalLayer, MaterialData, Channel, Group, Layer - all use PropertyGroups for Blender persistence

### Context System (paintsystem/context.py)
- **PSContextMixin**: Used by operators to parse context via `PSContextMixin.parse_context(context)`
- Returns **PSContext dataclass** containing: ps_settings, ps_scene_data, active_object, ps_object, ps_mat_data, active_layer, etc.
- Always check if ps_object is valid MESH before operations

### Node Graph System (paintsystem/graph/)
- **NodeTreeBuilder**: Generates shader node graphs from layer definitions
- **Layer-Specific Graphs**: Each layer type has a builder (basic_layers.py) - e.g., `create_image_graph()`, `create_adjustment_graph()`
- **Blend Modes**: Implemented via ShaderNodeMixRGB with alpha_over for compositing
- **UDIM Support**: Handled at image loading/saving (image.py)

### Image Handling (paintsystem/image.py)
- **ImageTiles Class**: Encapsulates UDIM tile management with numpy arrays
- **Conversion**: `blender_image_to_numpy()` (RGBA→uint8), `set_image_pixels()` (numpy→Blender)
- **Persistence**: Packed images, filepath preservation, auto-save on dirty

## Key Conventions

### Operator Mixins & Composition (operators/common.py)
All operators use mixin composition for reusable functionality:

**Mixin Hierarchy:**
```
PSContextMixin (base: provides parse_context(), static method)
  ↓
PSUVOptionsMixin (provides: coord_type, uv_map_name, use_paint_system_uv properties + methods)
  ↓
PSImageCreateMixin (adds: image_name, resolution, UDIM properties + create_image(), image_create_ui())
```

**Individual Mixins:**
- **PSImageFilterMixin**: For image editing operators - provides `get_image(context)` and `invoke_get_image()` to auto-detect active image layer or baked image
- **PSContextMixin**: Base for all operators; provides `parse_context(context)` → PSContext dataclass
- **PSUVOptionsMixin**: UV/coordinate system selection with consistency checks:
  - `get_coord_type(context)`: Sync operator state from active group
  - `store_coord_type(context)`: Sync operator state to active group
  - `select_coord_type_ui(layout, context)`: Render UV/coordinate selector
- **PSImageCreateMixin** (extends PSUVOptionsMixin): Image creation dialog UI
  - `image_create_ui(layout, context, show_name=True, show_float=True)`: Reusable resolution/UDIM selector
  - `create_image(context)`: Factory method to instantiate image with properties

**Template for New Operators:**
```python
class PAINTSYSTEM_OT_MyOperator(PSContextMixin, MultiMaterialOperator):
    bl_idname = "paint_system.my_operator"
    bl_label = "My Operator"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None

    def process_material(self, context):  # Called by MultiMaterialOperator for each material
        ps_ctx = self.parse_context(context)
        # Logic here, called per-material with context override
        return {'FINISHED'}
```

### Operator Base Classes
- **MultiMaterialOperator** (operators/common.py): Handle multiple objects/materials with context override
  - Override `process_material(context)` - receives properly scoped context
  - Properties: `multiple_objects`, `multiple_materials`
  - `execute()` batches material iteration; calls `process_material()` per material with temp_override
  - `multiple_objects_ui(layout, context)`: Shows info when multiple objects selected
- **PSContextMixin**: Provides `parse_context()` static method for all operators
- **BakeOperator** (operators/bake_operators.py): Specialized bake workflow
  - Inherits from: `PSContextMixin`, `PSImageCreateMixin`, `Operator`
  - Provides: `multi_object_ui()`, `bake_image_ui()`, `advanced_bake_settings_ui()` for consistent bake dialog UX
  - Provides: `find_objects_with_materials()`, `get_enabled_materials()` for batch baking logic

### Composing Operators (Examples)
- **Image layer creation**: `PAINTSYSTEM_OT_NewImage(PSContextMixin, PSImageCreateMixin, MultiMaterialOperator)` - uses both image UI and multi-material processing
- **Image filters**: `PAINTSYSTEM_OT_InvertColors(PSImageFilterMixin, Operator)` - simple mixin for image access
- **UV-dependent layers**: `PAINTSYSTEM_OT_NewTexture(PSContextMixin, PSUVOptionsMixin, MultiMaterialOperator)` - adds UV selection dialog
- **Baking**: `PAINTSYSTEM_OT_BakeChannel(BakeOperator)` - extends specialized bake operator

### UI/Panel Pattern (panels/)
- **Panel Structure**: Extend `Panel` class, use `PSContextMixin` for context parsing
  - `draw_header()` and `draw_header_preset()` for compact controls
  - `draw()` for main content layout
- **Context Awareness**: Always parse context first: `ps_ctx = PSContextMixin.parse_context(context)`
- **Compact Design Support**: Use `scale_content(context, layout)` to respect user's compact design preference (prefs.use_compact_design)
- **Icon System**: 
  - Custom icons: `get_icon(icon_name)` (defined in custom_icons.py)
  - Channel icons: `get_icon_from_channel(channel)` returns socket-type specific icons
  - Blender defaults: `icon_parser(icon, default="NONE")` validates icon names
- **Common UI Patterns**:
  - `layout.panel(id, default_closed=True)` for collapsible sections (returns header, panel tuples)
  - `image_node_settings()` helper for image properties with UDIM/colorspace/interpolation controls
  - `draw_layer_icon()` renders layer-specific icons (IMAGE shows preview, FOLDER is expandable, SOLID_COLOR shows RGB picker)
  - `toggle_paint_mode_ui()` and `layer_settings_ui()` abstractions for common layer controls
- **UIList Implementation** (MAT_PT_UL_LayerList):
  - Inherits from UIList and PSContextMixin
  - `draw_item()` receives active_channel as data, item as layer reference
  - Access flattened layers via `active_channel.flattened_layers` and hierarchy depth via `get_item_level_from_id()`

### Module Registration (Blender 4.0+)
- Uses `register_submodule_factory(__name__, submodules)` in each `__init__.py`
- Main addon handles idempotent registration for CI/reloads
- Icon system: load_icons() / unload_icons() in main register/unregister

## Layer Type System
Each layer type maps to specific node graph builders:
- **IMAGE**: Image texture input with opacity
- **SOLID_COLOR**: RGB constant node
- **ADJUSTMENT**: Tone/saturation/hue correction node groups
- **ATTRIBUTE**: Vertex/face color extraction
- **NODE_GROUP**: Linked node groups from library (library2.blend)
- **GRADIENT**: Linear/radial gradient construction
- **GEOMETRY**: Position/normal-based procedural patterns
- **RANDOM**: Voronoi/noise-based color

## Data Persistence & Versioning (paintsystem/versioning.py)
- **Migration System**: Version-aware migration functions in handlers.py
- **frame_change_pre Handler**: Processes timeline actions (FRAME/MARKER binds) to enable/disable layers
- **load_post Handler**: Runs version migrations, validates UUIDs, updates deprecated structures
- **Layer UIDs**: Each layer has UUID for cross-session tracking

## Testing
- **run_tests.py**: Simple addon enable test (verifies registration in CI)
- Uses `bpy.ops.preferences.addon_enable()` to validate registration
- Extend with feature tests via operators in test context

## File Organization
```
paint_system/          # Main addon folder
├── paintsystem/       # Core logic (data, context, handlers, versioning)
├── operators/         # All operator implementations + base classes
├── panels/            # UI panel definitions
├── utils/             # Helper functions (version, nodes, brushes)
└── wheels/            # Bundled dependencies (Pillow for image processing)
```

## Layer Operations (operators/layers_operators.py)

### Layer Creation Pattern
All "New [Type] Layer" operators inherit from `MultiMaterialOperator`:
- Override `process_material(context)` to create the layer
- Call `ps_ctx.active_channel.create_layer(context, layer_name, layer_type, **kwargs)`
- Use `invoke()` to show dialog with `context.window_manager.invoke_props_dialog(self)`
- Each layer type has specific kwargs (e.g., IMAGE needs `image=`, NODE_GROUP needs `custom_node_tree=`)

### Common Layer Operation Patterns
- **Image Layer** (PAINTSYSTEM_OT_NewImage): Supports NEW/IMPORT/EXISTING modes; handles UV map and coordinate type selection
- **Folder Layer** (PAINTSYSTEM_OT_NewFolder): Simple hierarchical container
- **Attribute Layer** (PAINTSYSTEM_OT_NewAttribute): Binds to object attribute (vertex/face color, uv, weight)
- **Node Group Layer** (PAINTSYSTEM_OT_NewNodeGroup): Links external node trees from library2.blend with socket mapping
- **Geometry/Gradient/Texture Layers**: All use `PSUVOptionsMixin` for UV/coordinate system selection

### Layer Deletion & Management
- `PAINTSYSTEM_OT_DeleteItem`: Deletes active layer/folder/group with hierarchy handling
- Deletion cascades: folders delete children, groups unlink associated materials
- Layer operations batch inside single MaterialData transaction (no per-layer flushing)

## Baking Operations (operators/bake_operators.py)

### BakeOperator Base Class Pattern
- Inherits from `PSContextMixin`, `PSImageCreateMixin`, `Operator`
- **Key Properties**:
  - `bake_multiple_objects`: Boolean to enable multi-object baking
  - `use_gpu`: GPU acceleration toggle (default True)
  - `margin`: Bake margin (0-100 pixels) with margin_type (ADJACENT_FACES/EXTEND)
  - `as_tangent_normal`: For VECTOR channels, bake as tangent-space normals
- **Context Handling**: Uses `parse_material()` to get material-specific active channel per bake target

### Bake Workflow
1. **invoke()**: Shows dialog; updates temp_materials list for multi-object display
2. **draw()**: 
   - `multi_object_ui()`: Shows material list with enable/disable checkboxes
   - `bake_image_ui()`: Image resolution, UV map selection, float format option
   - `advanced_bake_settings_ui()`: GPU/margin/margin_type controls
3. **execute()**:
   - Iterates enabled_materials from `get_enabled_materials(context)`
   - Calls `active_channel.bake(context, mat, bake_image, uv_map_name, **options)`
   - **as_layer=True**: Creates new IMAGE layer with baked result
   - **as_layer=False**: Updates `active_channel.bake_image` property; sets `use_bake_image=True`
   - Returns cursor to normal, reports timing

### Key Baking Details
- **Vector Space Handling**: For VECTOR channels, detects tangent vs. object space via `as_tangent_normal` param
- **Colorspace Preservation**: Sets 'sRGB' for color, 'Non-Color' for data channels
- **Multi-Material Support**: `update_bake_multiple_objects()` callback filters to materials with Paint System data
- **Object Detection**: `find_objects_with_materials()` warns if other objects use baked material but aren't selected

### Bake Operators Available
- **PAINTSYSTEM_OT_BakeChannel**: Bakes single active channel to image/layer
- **PAINTSYSTEM_OT_BakeAllChannels**: Iterates all channels in active_group, bakes each
- **PAINTSYSTEM_OT_SelectAllBakedObjects**: Helper to select all objects that use any baked material

## Common Patterns

### Adding a New Layer Type
1. Add enum to LAYER_TYPE_ENUM in data.py
2. Create `create_[type]_graph(builder: NodeTreeBuilder)` in graph/basic_layers.py
3. Add to layer_factory dictionary
4. Panel rendering auto-discovers via UI loops

### Working with Materials
- Always retrieve via `ps_ctx.ps_mat_data` (automatically initialized)
- Access layer tree via `ps_mat_data.layer_tree` (nested NestedListManager)
- Use `MultiMaterialOperator` for batch material updates

### Accessing Layers
- Global layers: `bpy.context.scene.ps_scene_data.layers`
- Material-local layers: `ps_mat_data.layer_tree.flatten()` (get all layers across hierarchy)
- Traverse hierarchy: `ps_mat_data.layer_tree.get_children(layer)`

## Blender API Specifics
- **Context Override**: Use `context.temp_override()` for scoped material/object context (4.0+)
- **Icons**: Custom icons in `custom_icons.py`, register in load_icons()
- **Preferences**: Extend bpy.types.AddonPreferences via PreferencesPanel
- **Handlers**: Use @persistent decorator; for 4.0+ register updates on `depsgraph_update_post` only (no `scene_update_pre`)

## Dependencies
- **PIL/Pillow**: Image I/O and numpy conversions (bundled via wheels)
- **numpy**: Image tile processing and conversions
- **bpy**: Blender Python API (4.0+)

## Common Pitfalls
- Don't access `ps_object` without type checking (verify MESH/GREASEPENCIL before use)
- Layer operations must flush through `layer.update_node_tree()` to reflect in viewport
- UDIM images require special handling in ImageTiles; non-UDIM fallback to single tile 1001
- Multiple operations should batch inside single MaterialData transaction, not per-layer

## Branch Sync Workflow

When you update both the main `pink-system` branch and individual feature branches, follow these patterns.

Updating `pink-system`, then syncing a feature branch:

```bash
# 1. Update pink-system with your changes
git checkout pink-system
git add <modified-files>
git commit -m "Update: feature description"
git push origin pink-system

# 2. Rebase the individual feature branch to incorporate changes
git checkout feature/quick-tools  # (or whichever feature)
git rebase pink-system
git push origin feature/quick-tools --force-with-lease
```

Updating a feature branch directly, then rebasing `pink-system`:

```bash
# 1. Update the feature branch
git checkout feature/quick-tools
git add <modified-files>
git commit -m "Update: feature description"
git push origin feature/quick-tools

# 2. Rebase pink-system to include the change
git checkout pink-system
git rebase feature/quick-tools
git push origin pink-system --force-with-lease
```

Use `--force-with-lease` for safety when rewriting history, and replace `feature/quick-tools` with the actual feature branch name.
