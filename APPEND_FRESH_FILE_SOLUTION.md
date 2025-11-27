# Appending Paint System Setups to Fresh Files

## Problem
When appending materials/groups to a fresh file, references (node trees, images, objects) may be missing and light linking can be lost.

## Recommendations
1. Validate material has Paint System data (`mat.ps_mat_data`).
2. Verify node trees exist; rebuild layer graphs if missing.
3. Detect if material output already has a surface connected; insert PS group non-destructively.
4. Ensure minimal object/UV setup for painting (valid mesh, material slot, UV map).

## Validation Operator (Concept)
- Scan material’s groups/channels/layers.
- If a referenced node tree is missing, rebuild via the layer graph builder.
- If images are missing, recreate placeholders.

## Notes
- Prefer preserving existing material structure (mix in Paint System) rather than replacing outputs.
- Use `parse_context(context)` and operate inside `context.temp_override(...)`.
