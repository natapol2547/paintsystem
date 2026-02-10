# Naming Sync (PR #103)

## Feature Notes
- Files: paintsystem/data.py, paintsystem/handlers.py, operators/utils_operators.py
- Manual changes applied:
   - Group name base uses `<material>` (no PS_ prefix) and ensures unique names.
   - Layer/image rename updates are robust and use group index.
   - Msgbus and handlers restore last material name safely.
   - New Paint System setup dialog uses a simple "Setup Name" field; it drives material > group > image naming.
   - Naming UX vs node flexibility:
     - Keep the user-facing name simple (material name) while allowing node group renames in the Shader Editor.
     - Use a stable internal ID (e.g., custom property/UUID) for lookups so manual node renames do not break links.
- Validation:
   - Renaming material updates group/layer/image names and bake images.

## Detailed Change Map (Level 4)
- paintsystem/data.py
   - Group name base now follows `<material>` (no PS_ prefix) and stays unique.
- paintsystem/handlers.py
   - Msgbus rename handling restores last material name safely.
- operators/utils_operators.py
   - Layer/image rename updates use group index for stability.
