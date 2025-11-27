# Paint System: Copilot Instructions

Guidance for AI agents working in this Blender (4.2+) NPR painting add-on. Focus on existing patterns; do not invent new architectures.

## Big Picture
- Material-centric system with three synchronized hierarchies:
  - UI list: `paintsystem/nested_list_manager.py` flattens parent-child layers for UI. Base classes provide hierarchical operations.
  - Nodes: shader graphs in `paintsystem/graph/*`. NodeTreeBuilder creates versioned graphs with named nodes and stable identifiers.
  - Data: `paintsystem/data.py` defines PropertyGroups (Group, Channel, Layer) with update callbacks (`update_node_tree`) and baking helpers.
- Panels/Operators orchestrate editing and baking; handlers manage runtime migration and UI sync.

## Key Files
- `__init__.py`, `paintsystem/__init__.py`: Registration order. Data must register first (PropertyGroups), then operators/panels.
- `paintsystem/data.py`: Core data model, enums, PSContext parsing, bake entry points.
- `paintsystem/graph/basic_layers.py`: Per-layer graph builders; bump version constant when node IDs or structure change.
- `operators/common.py`: Mixins (`PSContextMixin`, `MultiMaterialOperator`, `PSUVOptionsMixin`, `PSImageCreateMixin`).
- `operators/bake_operators.py`: Channel baking, export, transfer UV, merge up/down.
- `panels/*`: UI panels for layers, brush, extras, quick tools.
- `utils/nodes.py`: Node traversal and material output helpers.

## Essential Patterns

### Context & Data Access
- Operators inherit `PSContextMixin`; call `self.parse_context(context)` for a `PSContext` with `ps_object`, `active_material`, `active_group`, `active_channel`, `active_layer`.
- For batch operations, inherit `MultiMaterialOperator` and implement `process_material(self, context)`; it handles `context.temp_override` safely.

### Update Callbacks
- Properties often call `update_node_tree` to rebuild node graphs. Keep updates cheap and idempotent.
- When toggling clip/opacity/blend mode, call layer’s `update_node_tree` instead of rebuilding entire material.

### Baking
- Use `Channel.bake(context, mat, image, uv_name, ...)` as the single entry point.
- Preserve render settings; return to OBJECT mode after bake.
- When creating images, prefer `PSImageCreateMixin.create_image(context)` so resolution and naming are consistent.

### Linked Layers
- Linked layers refer to a source layer’s node tree; do not duplicate graphs.
- Use `layer.get_layer_data()` to resolve to the source if linked; otherwise returns self.

### Versioning & Migration
- Bump `get_layer_version_for_type()` in `graph/basic_layers.py` when changing node structure.
- Migration runs from `paintsystem/handlers.py` via `@persistent` handlers; compare stored version to current and rebuild if mismatched.

## Common Workflows

### Add New Layer Type
1) Extend enum in `paintsystem/data.py` (LAYER_TYPE_ENUM).
2) Implement `create_<type>_graph()` in `graph/basic_layers.py` and wire into the builder.
3) Add UI in `panels/layers_panels.py` draw switch.
4) Add operators if needed.

### Bake Workflow
- Baking to existing baked image: ensure `channel.use_bake_image=True` and `channel.bake_image` is set.
- Baking as new layer: create image, bake with `force_alpha=True` if supported, then `channel.create_layer(..., image=img)`.

### Batch Operations
- Set `multiple_objects` / `multiple_materials` flags; `MultiMaterialOperator` will iterate with safe overrides.
- Do not mutate Blender context globally; always operate inside `context.temp_override(...)`.

## Conventions & Gotchas
- Prefer runtime API detection (`getattr`, `hasattr`) over hard version checks.
- Don’t change operator idnames or panel ids unless absolutely necessary; Blender keymaps and saved layouts depend on them.
- Keep UI code resilient: guard against missing `ps_object`, `active_layer`, or absent properties.

## PR Tips
- Small, surgical changes. Avoid broad refactors.
- Update docstrings and panel tooltips where behavior changes.
- Add notes in this file when you introduce a new operator/panel pattern.
