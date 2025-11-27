# Paint System: Copilot Instructions

Guidance for AI agents working in this Blender (4.2+) NPR painting add-on. Focus on existing patterns; do not invent new architectures.

## Big Picture
- **Material-centric system** with three synchronized hierarchies:
    - **UI list**: `nested_list_manager.py` flattens parent-child layers for UI display. Generic base classes (`BaseNestedListManager`, `BaseNestedListItem`) provide hierarchical list operations.
    - **Nodes**: shader graphs in `material.node_tree` built by `graph/*.py`. NodeTreeBuilder creates versioned graphs with named nodes.
    - **Data**: `paintsystem/data.py` PropertyGroups for PaintSystemGlobalData → MaterialData → Group → Channel → Layer (4-level hierarchy).
- **Update flow**: Property changes trigger `update_node_tree()` callbacks which rebuild shader nodes. Never call graph builders directly from UI/operators.
- **Registration order matters**: `paintsystem` module (contains PropertyGroups) must register first, then operators/panels that reference them.

## Key Files & Modules
- `paintsystem/data.py` (3466 lines): Core PropertyGroups, `parse_context()`, `LAYER_TYPE_ENUM`, all update callbacks, linked layer system.
- `paintsystem/graph/basic_layers.py`: Per-layer graph builders (`create_<type>_graph`) + `get_layer_version_for_type()` for migration.
- `paintsystem/graph/nodetree_builder.py`: `NodeTreeBuilder` class - creates/updates shader node graphs with versioning.
- `paintsystem/nested_list_manager.py`: Base classes for hierarchical UI lists (folder/item structure).
- `paintsystem/handlers.py`: Load-time migration via `@persistent` handlers, layer versioning, frame-based layer actions.
- `operators/common.py`: Essential mixins - `PSContextMixin` (context parsing), `MultiMaterialOperator` (batch ops), `PSUVOptionsMixin`, `PSImageCreateMixin`.
- `operators/layers_operators.py`: All layer CRUD operations; demonstrates proper mixin usage.
- `utils/nodes.py`: Node tree traversal (`traverse_connected_nodes`), lookups (`find_node`, `get_material_output`).
- `utils/udim.py`: UDIM detection/creation utilities using NumPy for UV analysis.

## Essential Patterns

### Context & Data Access
- **Context parsing**: Operators inherit `PSContextMixin` and call `self.parse_context(context)` → returns `PSContext` dataclass with `ps_object`, `active_material`, `active_group`, `active_channel`, `active_layer`.
- Non-operators use `from paintsystem.data import parse_context; ps_ctx = parse_context(context)`.
- **Safe parsing**: `PSContextMixin.safe_parse_context(context)` returns None instead of raising on missing data.

### Property Updates & Node Graphs
- **Update callbacks**: Define properties with `update=update_node_tree` (module-level dispatcher). The PropertyGroup's `update_node_tree()` method rebuilds nodes.
- **Never call graph builders directly** from UI/operators; change properties and let callbacks handle compilation.
- **Layer dispatch**: In `Layer.update_node_tree()`, use `match self.type:` cases calling `create_<type>_graph(self)` from `graph/basic_layers.py`.
- **NodeTreeBuilder pattern**: Builders use named nodes (e.g., "image", "rgb", "mixing") for consistent lookups. Links reference node names, not objects.

### Linked Layers
- Layers share node trees via `linked_layer_uid` + `linked_material` (stores source material).
- Use `layer.get_layer_data()` to resolve source layer; returns self if unlinked, source if linked.
- **Do not duplicate node trees** for linked layers; reference the original material's layer.

### Versioning & Migration
- Bump `get_layer_version_for_type()` in `graph/basic_layers.py` when node count/IDs change.
- Migration runs in `handlers.py` via `@persistent` `load_post` handler - compares stored version to current, rebuilds if mismatch.
- Store version in node tree via `NodeTreeBuilder(node_tree, "Layer", version=N)`.

## Common Workflows

### Add New Layer Type
1. **Extend enum**: Add item to `LAYER_TYPE_ENUM` in `paintsystem/data.py` (around line 119).
2. **Graph builder**: Implement `create_<type>_graph(layer)` in `paintsystem/graph/basic_layers.py`:
   ```python
   def create_mytype_graph(layer: "Layer"):
       node_tree = layer.node_tree
       blend_mode = get_layer_blend_type(layer)
       builder = NodeTreeBuilder(node_tree, "Layer", version=MYTYPE_LAYER_VERSION)
       # Add nodes, create mixing graph, link sockets
       return builder
   ```
3. **Dispatch case**: In `Layer.update_node_tree()` (in `data.py`), add `case "MYTYPE": create_mytype_graph(self)`.
4. **Properties**: Add layer-specific props to `Layer` class with `update=update_node_tree` or `update=update_uv_map_name_and_sync` (for UV-dependent types).
5. **Version constant**: Define `MYTYPE_LAYER_VERSION = 1` at top of `basic_layers.py` and add case to `get_layer_version_for_type()`.
6. **Operator** (optional): Create `PAINTSYSTEM_OT_New<Type>` inheriting `PSContextMixin, MultiMaterialOperator` in `operators/layers_operators.py`.

### Bake Workflow
- **Channel baking**: `Channel.bake(context, image, uv_map_name, multi_object=False)` uses Cycles with GPU/CPU fallback.
- Render settings automatically saved/restored via context manager pattern.
- Pass `context` to `PSImageCreateMixin.create_image(context)` to enable UDIM detection.
- UDIM baking: System detects multi-tile UVs, prompts user, creates tiled images with all required tiles.

### Batch Operations
- **MultiMaterialOperator pattern**: Override `process_material(context)` method.
- Use `context.temp_override()` inside `process_material` - never mutate context directly in loops.
- Set `multiple_objects=True` / `multiple_materials=True` in operator properties for scope.
- Example: `PAINTSYSTEM_OT_NewImage` processes each selected object's materials in isolation.

### UI Panels
- Inherit from `panels.common` base classes; call `parse_context(context)` in `draw()`.
- Properties draw automatically triggers update callbacks.
- Use `scale_content(context, layout)` for consistent spacing (respects compact mode preference).

## Conventions & Gotchas
- Do not mutate Blender context directly in batch ops; use `context.temp_override()` inside `MultiMaterialOperator.process_material()`.
- Auto-UV: layers may create `DEFAULT_PS_UV_MAP_NAME` when `coord_type` requires it.
- Brush sync: `utils/unified_brushes.py` updates brush color/size/alpha based on active layer.
- Runtime API detection: prefer `getattr()` over version checks for Blender 5+/Bforartists.

## Build/Run/Test

### Development Commands (PowerShell)
```powershell
# Quick syntax check from repo root
python -m py_compile paintsystem/data.py
python -m py_compile paintsystem/graph/basic_layers.py
python -m py_compile operators/layers_operators.py; python -m py_compile panels/layers_panels.py

# Test all modules in parallel (chain with semicolons in PowerShell)
python -m py_compile __init__.py; python -m py_compile paintsystem/__init__.py; python -m py_compile operators/__init__.py; python -m py_compile panels/__init__.py
```

### Testing in Blender
- `run_tests.py`: Loads addon `paint_system` in Blender and verifies registration succeeds.
- Run via: `blender --background --python run_tests.py`
- Addon ID: `paint_system` (defined in `blender_manifest.toml`).

### Dependencies & Packaging
- **Pillow** (12.0.0): Vendored wheels for all platforms in `wheels/` (used for image filters).
- **NumPy**: Required for UDIM UV analysis (`utils/udim.py`) and baking math - use array operations, not loops.
- **Extension manifest**: `blender_manifest.toml` v2.1.1 - defines permissions (files, network), supported platforms, and metadata.
- No max Blender version - forward compatible via runtime API detection (`getattr`/`hasattr`).

### Registration Architecture
```
__init__.py register()
 ├─ load_icons()                    # Early load for EnumProperty icons
 ├─ paintsystem.register()          # Data PropertyGroups FIRST
 │   ├─ data.register()             # PaintSystemGlobalData, MaterialData, etc.
 │   └─ handlers.register()         # @persistent load_post for migration
 └─ register_submodule_factory()    # panels, operators, keymaps
```
**Order matters**: PropertyGroups must exist before operators reference them via PointerProperty/CollectionProperty.

## Examples
- Operator pattern:
    ```python
    from operators.common import PSContextMixin, MultiMaterialOperator
    class MyOp(PSContextMixin, MultiMaterialOperator):
            def process_material(self, context):
                    ps = self.parse_context(context)
                    # mutate ps.active_layer properties; callbacks rebuild nodes
    ```
- Layer graph addition:
    ```python
    # in graph/basic_layers.py
    def create_mytype_graph(layer):
            builder = NodeTreeBuilder(layer)
            # build nodes + links; return builder
            return builder
    ```

Questions or unclear areas? Point to file paths and I’ll refine this guide.
