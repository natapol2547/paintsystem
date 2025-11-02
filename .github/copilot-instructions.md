# Paint System - Blender Add-on Copilot Instructions

## Project Overview
Paint System is a Blender 4.2+ add-on for non-photorealistic rendering (NPR) painting workflows. It provides a layer-based painting system similar to traditional 2D painting software, built on top of Blender's shader node system.

## Architecture

### Core Data Model (paintsystem/data.py)
- **Hierarchical Structure**: Material → Groups → Channels → Layers
  - `MaterialData`: Root container attached to each Blender material
  - `Group`: Organizes channels (e.g., "Basic", "PBR")
  - `Channel`: Represents shader output types (COLOR, VECTOR, FLOAT)
  - `Layer`: Individual paint layers with node trees (IMAGE, FOLDER, SOLID_COLOR, ADJUSTMENT, etc.)
- **Context Pattern**: Use `parse_context(context)` (or `PSContextMixin.parse_context()`) to safely access Paint System data. Returns `PSContext` dataclass with all relevant objects.
- **Node Trees**: Each layer/channel/group has a `node_tree` property - a Blender ShaderNodeTree that's dynamically rebuilt on property changes
- **Layer Linking**: Layers can reference layers from other materials via `linked_layer_uid` and `linked_material` properties. Use `layer.get_layer_data()` to resolve to actual data.

### Node Tree Builder (paintsystem/graph/nodetree_builder.py)
- **Declarative Graph Construction**: `NodeTreeBuilder` class creates shader node graphs programmatically
- **Frame-Based Organization**: Each builder operates within a `NodeFrame` for visual grouping
- **Compilation Pattern**:
  ```python
  builder = NodeTreeBuilder(node_tree, frame_name="My Graph")
  builder.add_node("tex_coord", "ShaderNodeTexCoord")
  builder.add_node("noise", "ShaderNodeTexNoise")
  builder.link("tex_coord", "noise", "Generated", "Vector")
  builder.compile()  # Creates actual nodes and links
  ```
- **State Preservation**: On recompilation, captures and restores node properties/defaults unless `force_properties=True`
- **Nested Graphs**: Support subgraphs - pass `NodeTreeBuilder` instances to `link()`
- **START/END Keywords**: Use `START` and `END` as special node identifiers for graph entry/exit points (creates reroute nodes)

### Library System (paintsystem/graph/common.py)
- **Shared Node Groups**: Common node groups stored in `library2.blend`
- **Auto-Append**: `get_library_nodetree(name)` automatically appends from library if not present
- **Mixing Graphs**: `create_mixing_graph()` provides standard pre/post mix logic for layers
- **UV Coordinates**: `DEFAULT_PS_UV_MAP_NAME = "PS_UVMap"` - automatically created UV map for procedural painting

### Operator Patterns (operators/common.py)
- **PSContextMixin**: Inherit to access `self.parse_context(context)` method
- **MultiMaterialOperator**: Base class for operators that work across multiple objects/materials
  - Override `process_material(context)` method
  - Handles context temp_override automatically
- **PSUVOptionsMixin**: Standard UV coordinate selection UI (AUTO/UV/OBJECT/etc.)
- **PSImageCreateMixin**: Standard image creation dialog with resolution options

### Blender Integration
- **Registration**: Uses `register_submodule_factory()` for hierarchical module registration
- **Properties**: Custom properties registered via Blender's PropertyGroup system
- **Handlers**: Frame change handlers in `paintsystem/handlers.py` enable timeline-based layer animations
- **Manifest**: `blender_manifest.toml` defines extension metadata (Blender 4.2+ format)

## Key Workflows

### Adding a New Layer Type
1. Add enum to `LAYER_TYPE_ENUM` in `paintsystem/data.py`
2. Create `create_<type>_graph()` function in `paintsystem/graph/basic_layers.py`
3. Add case to `Layer.update_node_tree()` match statement
4. Add properties to `Layer` class if needed
5. Create UI in `panels/layers_panels.py` for layer-specific settings

### Creating Operators
```python
class PAINTSYSTEM_OT_MyOperator(PSContextMixin, Operator):
    bl_idname = "paint_system.my_operator"
    bl_label = "My Operator"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        # Access: ps_ctx.active_layer, ps_ctx.active_channel, etc.
        return {'FINISHED'}
```

### Updating Node Trees
- **Never modify nodes directly** - use `update_node_tree()` methods
- **Trigger updates** via property `update=update_node_tree` callbacks
- **Layer changes**: Call `layer.update_node_tree(context)` to rebuild layer's node graph
- **Channel changes**: Rebuilds entire layer stack with alpha blending
- **Group changes**: Ensures proper socket interfaces match channels

### Baking Workflow
- Use `Channel.bake()` to render channel output to an image
- Switches to Cycles, renders with emission, captures RGB+Alpha separately
- Stored as `channel.bake_image` with `use_bake_image` toggle

## Development Practices

### Import Patterns
- **Relative imports** within package: `from ..paintsystem.data import parse_context`
- **Blender modules** at top: `import bpy` then specific types: `from bpy.types import Operator`
- **Avoid circular imports**: Use type hints with string literals if needed

### Error Handling
- **Context validation**: Always use `parse_context()` - returns None for missing data
- **Node tree checks**: Verify `node_tree` exists before operations
- **Material checks**: Check `hasattr(mat, 'ps_mat_data')` before accessing Paint System data

### Performance Considerations
- **Layer UID cache**: `_get_material_layer_uid_map()` caches UID→Layer lookups (O(1) instead of nested loops)
- **Invalidate cache**: Call `_invalidate_material_layer_cache(material)` after structural changes
- **Node tree versioning**: Check `get_nodetree_version()` for migration needs

### UI Conventions
- **scale_content()**: Use for consistent panel scaling based on preferences
- **Icons**: Load from `custom_icons.py` via `get_icon(name)` for custom icons
- **Tooltips**: Respect `ps_settings.show_tooltips` preference

## External Dependencies
- **Pillow**: Bundled in `wheels/` for image processing (filters in `operators/image_filters/`)
- **Platform-specific**: Separate wheels for Windows (win_amd64) and macOS (macosx_arm64)

## Testing & Debugging
- **Manual testing**: Install from zip in Blender 4.2+ (Edit → Preferences → Add-ons → Install from Disk)
- **Console output**: Use `print()` statements - visible in Blender's system console (Window → Toggle System Console on Windows)
- **Property inspection**: Use `dir(obj)` and `obj.bl_rna.properties` to explore Blender objects
- **Temp override**: Use `context.temp_override()` to safely modify context in operators

## File Organization
- `paintsystem/`: Core data model and logic
- `operators/`: Blender operators (user actions)
- `panels/`: UI panels and menus
- `utils/`: Helper utilities (nodes, brushes, versioning)
- `operators/image_filters/`: Image processing with Pillow
- `references/`: Documentation and examples

## Common Gotchas
- **Layer data resolution**: Always call `layer.get_layer_data()` before accessing properties (handles linked layers)
- **Material slots**: Object can have multiple materials - use `ps_ctx.active_material` not `obj.data.materials[0]`
- **Paint mode switching**: `update_active_image()` sets `image_paint.canvas` based on active layer
- **Node tree names**: Prefix with "." to hide from UI (e.g., ".PS_Layer (Layer Name)")
- **Property updates**: Callbacks receive `self` and `context` - use property `update=func`

## Documentation Links
- User Docs: https://prairie-yarrow-e25.notion.site/PAINT-SYSTEM-DOCUMENTATION-1910a7029e86803f9ac3e0c79c67bd8c
- Blender 4.2 API: https://docs.blender.org/api/4.2/
- Extension Format: https://docs.blender.org/manual/en/dev/advanced/extensions/
