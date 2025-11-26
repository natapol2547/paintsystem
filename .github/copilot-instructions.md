# Paint System: Copilot Instructions

Concise guidance for AI agents working in this Blender (4.2+) NPR painting add-on. Focus on existing patterns; do not invent new architectures.

## Big Picture
- Material-centric system with three hierarchies:
    - UI list: `nested_list_manager.py` flattens parent-child layers for display.
    - Nodes: shader graphs in `material.node_tree` built by `graph/*.py`.
    - Data: `paintsystem/data.py` PropertyGroups for Material → Group → Channel → Layer.
- Changes to properties must rely on `update_node_tree()` callbacks; do not call compilers directly.

## Key Files
- `paintsystem/data.py`: PropertyGroups, `parse_context()`, layer enum, core callbacks.
- `paintsystem/graph/basic_layers.py`: Per-layer graph builders + `get_layer_version_for_type()`.
- `operators/common.py`: Mixins (`PSContextMixin`, `MultiMaterialOperator`, `PSUVOptionsMixin`, `PSImageCreateMixin`).
- `operators/layers_operators.py`: Creation/editing of layers; follow mixin patterns.
- `utils/nodes.py`: Node lookup helpers; use for consistent node access.

## Essential Patterns
- Update callbacks: define properties with `update=update_node_tree`; avoid manual compilation.
- Context access: in operators, call `self.parse_context(context)` (from `PSContextMixin`). Non-operators use `paintsystem.data.parse_context(context)`.
- Layer dispatch: in `Layer.update_node_tree()`, add `match self.type` cases that call `create_<type>_graph()`.
- Linked layers: use `linked_layer_uid` and `get_layer_data()` to resolve the source; do not duplicate node trees.
- Versioning: bump `get_layer_version_for_type()` when graph node counts/ids change; migration runs via `handlers.load_post`.

## Common Workflows
- Add new layer type:
    1) Extend `LAYER_TYPE_ENUM` in `data.py`.
    2) Implement `create_<type>_graph()` in `graph/basic_layers.py`.
    3) Add dispatch case in `Layer.update_node_tree()`.
    4) Define needed Layer properties with `update=...`.
    5) Update version in `get_layer_version_for_type()`.
- Bake channel: use `Channel.bake()` (Cycles). Assumes GPU-first with CPU fallback; render settings saved/restored.
- UI panels: under `panels/*.py`, get active items via `parse_context()`; draw properties that trigger updates via callbacks.

## Conventions & Gotchas
- Do not mutate Blender context directly in batch ops; use `context.temp_override()` inside `MultiMaterialOperator.process_material()`.
- Auto-UV: layers may create `DEFAULT_PS_UV_MAP_NAME` when `coord_type` requires it.
- Brush sync: `utils/unified_brushes.py` updates brush color/size/alpha based on active layer.
- Runtime API detection: prefer `getattr()` over version checks for Blender 5+/Bforartists.

## Build/Run/Test
- Syntax check quickly from repo root:
    - `python -m py_compile paintsystem/data.py`
    - `python -m py_compile paintsystem/graph/basic_layers.py`
    - `python -m py_compile operators/layers_operators.py panels/layers_panels.py`
- Wheels: Pillow is vendored in `wheels/`; NumPy used for baking math.
- Extension manifest: `blender_manifest.toml` governs registration and permissions.

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
