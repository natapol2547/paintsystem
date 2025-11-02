# Paint System Add-on: Copilot Instructions

## Overview
Paint System is a Blender add-on (4.2+) providing a **non-photorealistic rendering (NPR) painting system**. It uses Blender's node-based architecture to compose complex painting workflows into a hierarchical layer structure similar to traditional paint software.

## Architecture

### Core Data Model (Hierarchical Composition)
```
Material (Paint System enabled)
├── Group (composites channels into material outputs)
│   ├── Channel (COLOR, VECTOR, or FLOAT types)
│   │   └── Layer (hierarchical tree of layer types)
│   │       ├── IMAGE (texture-based)
│   │       ├── FOLDER (groups layers with blending)
│   │       ├── SOLID_COLOR, GRADIENT, TEXTURE
│   │       ├── ADJUSTMENT (brightness, curves, hue-sat)
│   │       ├── ATTRIBUTE (vertex/object attributes)
│   │       ├── GEOMETRY (normals, positions)
│   │       └── NODE_GROUP (custom shader nodes)
│   └── Layer can link to another material's layer
└── UI represents this as flat list via nested_list_manager
```

**Key File**: `paintsystem/data.py` (2200+ lines) - Contains all PropertyGroup definitions and context parsing.

### Data Flow
1. **Paint Context Parsing** (`parse_context()` in `data.py`): Extracts active object, material, group, channel, layer from Blender context
2. **Node Tree Compilation**: Each layer/channel updates its node tree via `update_node_tree()` callbacks triggered by property changes
3. **Graph Building**: `NodeTreeBuilder` constructs shader node networks from layer definitions
4. **Baking**: Cycles render engine used to bake layer compositions into textures

### Three Parallel Hierarchies
- **UI Layer Hierarchy**: `BaseNestedListManager` flattens for display (parent-child relationships in UI)
- **Node Composition**: Actual shader nodes in `.node_tree` (composed via socket linking)
- **Global/Linked Layers**: Old system (deprecated) for layer reuse across materials - use `linked_layer_uid` property instead

## Critical Patterns

### 1. Update Callbacks Pattern
All property changes trigger `update_node_tree()` callbacks. **Never manually trigger node compilation** — let callbacks handle it:
```python
# ✓ Correct: Property with callback
layer_name: StringProperty(update=update_node_tree)

# ✗ Wrong: Manual call
layer.layer_name = "New"
layer.update_node_tree(context)  # Don't do this
```

### 2. Context Access (PSContext Dataclass)
Always use `parse_context()` to extract hierarchy, not raw material inspection:
```python
from paintsystem.data import parse_context
ps_ctx = parse_context(context)
# Access: ps_ctx.ps_object, ps_ctx.active_material, ps_ctx.active_layer, etc.
```

### 3. Layer Type Dispatch Pattern
Each layer type has dedicated graph builder (`create_image_graph()`, `create_adjustment_graph()`, etc.). When adding new layer types:
```python
match self.type:
    case "IMAGE":
        layer_graph = create_image_graph(self)
    case "NEW_TYPE":
        layer_graph = create_new_type_graph(self)  # Add here
```

### 4. Node Tree Versioning
Layers track node tree structure versions. After code changes affecting node counts/names:
- Update `get_layer_version_for_type()` in `graph/basic_layers.py`
- `load_post` handler auto-upgrades old files
- UUIDs track layer identity across saves

### 5. Linked Layers Pattern
Layer linking enables single layer definition reused across materials:
```python
linked_layer_uid: StringProperty()  # References source layer's uid
linked_material: PointerProperty(type=Material)  # Source material

# get_layer_data() returns actual layer; linked layers proxy to it
actual_layer = layer.get_layer_data()
```

## File Organization

| Path | Purpose |
|------|---------|
| `paintsystem/data.py` | PropertyGroups, Layer/Channel/Group types, `parse_context()` |
| `paintsystem/graph/` | Node tree builders (one per layer type) |
| `paintsystem/handlers.py` | Frame handlers for layer actions, post-load versioning |
| `operators/` | UI commands (layer ops, bake, channel isolation) |
| `panels/` | UI panels using Blender's panel layout system |
| `utils/` | Helper: nodes.py (node lookup), unified_brushes.py (brush settings) |
| `operators/operators_utils/` | Timing decorator, internal enums |

## Common Workflows

### Adding a New Layer Type
1. Add enum to `LAYER_TYPE_ENUM` in `data.py`
2. Create `create_<type>_graph()` in `graph/basic_layers.py` returning `NodeTreeBuilder`
3. Add case in `Layer.update_node_tree()` match statement
4. Define properties (e.g., `adjustment_type`, `gradient_type`) on Layer class

### Baking Workflow
1. `Channel.bake()` method composes layer tree into single texture
2. Uses Cycles to render shader output to image
3. Splits alpha into separate bake pass (combined afterward)
4. Saves render settings/restores (GPU/CPU fallback)

### Brush Integration
- **Unified settings**: `utils/unified_brushes.py` accesses brush color/size
- **Canvas auto-switch**: `update_active_image()` sets `image_paint.canvas` when layer selected
- **Alpha lock**: `lock_alpha` property updates brush `use_alpha` (via `update_brush_settings()`)

## Performance Considerations
- **Caching**: Material layer UID lookup cached in `_material_uid_cache` — invalidate when adding/deleting layers
- **Node deduplication**: Linked layers share node trees (don't recreate)
- **Texture vs shader**: Heavy adjustments (curves) best applied as adjustment layers, not real-time filters
- **GPU baking**: Attempts GPU first, falls back to CPU if unavailable

## Blender-Specific Details
- **Render Engine**: Add-on uses Cycles (toggles automatically during bake)
- **Node Types**: Primarily `ShaderNodeGroup`, `ShaderNodeMix`, `ShaderNodeTexImage`
- **UV Requirements**: Auto-creates `DEFAULT_PS_UV_MAP_NAME` UV map if missing
- **Camera Plane**: Special object for texture painting reference (parent: mesh, child: empty)
- **Permissions** (manifest): File I/O (images), clipboard (colors)

## Testing & Debugging
- **Enable printing**: Layer/channel/group names help trace node tree construction
- **Inspector**: Check `node_tree.nodes` to verify expected nodes post-update
- **Context validation**: Always check `ps_ctx` results before accessing (nulls possible)
- **Versioning**: `load_post` handler logs migrations; check console on file load

## Dependencies
- **Pillow**: Bundled (wheels/) for cross-platform image handling
- **NumPy**: Used for efficient pixel array manipulation in baking
- **Blender 4.2+**: Required for extension manifest system, node interface API

## Known Limitations
- Global layers system (deprecated) still present for legacy file support — use material-local groups instead
- Adjustment layers muted during playback (performance); unmute per-frame if needed
- Linked layers share all properties with source — changes cascade
