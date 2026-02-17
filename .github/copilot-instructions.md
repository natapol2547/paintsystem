# Paint System Copilot Instructions

Use the attached Paint System instruction set as the project source of truth.

## Primary API Reference (required)
- Blender Python API index: https://docs.blender.org/api/current/index.html
- Prefer current Blender API patterns and symbols from the latest docs.
- If older examples conflict with current docs, follow current docs and keep compatibility only when needed.

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

### UI/Panel Pattern (panels/)
- **Panel Structure**: Extend `Panel` class, use `PSContextMixin` for context parsing
- **Context Awareness**: Always parse context first: `ps_ctx = PSContextMixin.parse_context(context)`
- **Compact Design Support**: Use `scale_content(context, layout)` to respect user's compact design preference (prefs.use_compact_design)
- **Icon System**:
  - Custom icons: `get_icon(icon_name)` (defined in custom_icons.py)
  - Channel icons: `get_icon_from_channel(channel)` returns socket-type specific icons
  - Blender defaults: `icon_parser(icon, default="NONE")` validates icon names

## Data Persistence & Versioning (paintsystem/versioning.py)
- **Migration System**: Version-aware migration functions in handlers.py
- **frame_change_pre Handler**: Processes timeline actions (FRAME/MARKER binds) to enable/disable layers
- **load_post Handler**: Runs version migrations, validates UUIDs, updates deprecated structures
- **Layer UIDs**: Each layer has UUID for cross-session tracking

## Testing
- **run_tests.py**: Simple addon enable test (verifies registration in CI)
- Uses `bpy.ops.preferences.addon_enable()` to validate registration
- Extend with feature tests via operators in test context

## Blender API Specifics
- **Context Override**: Use `context.temp_override()` for scoped material/object context (4.0+)
- **Handlers**: Use @persistent decorator; for 4.0+ register updates on `depsgraph_update_post` only (no `scene_update_pre`)
- Always verify API calls/operators against the current Blender API docs above.

## Common Pitfalls
- Don't access `ps_object` without type checking (verify MESH/GREASEPENCIL before use)
- Layer operations must flush through `layer.update_node_tree()` to reflect in viewport
- UDIM images require special handling in ImageTiles; non-UDIM fallback to single tile 1001
- Multiple operations should batch inside single MaterialData transaction, not per-layer
