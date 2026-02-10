# Implementation Guide - Main Branch

This guide documents how to integrate each feature without conflicts, and what was changed beyond the original branches.

## Scope
- Merge selected PRs and UV Edit workflow.
- Capture manual edits applied after cherry-picking.
- Provide a repeatable implementation path.

## Merge Order (Least Destructive)
1. PR #86: Quick tools
2. PR #92: Color picker
3. PR #103: Naming
4. PR #106: Removed AutoUV coord type
5. PR #105: Convert to PS
6. UV Edit workflow (UV-EditWorkflow branch)

## Baseline Workflow
1. Update local `main`
    - `git checkout main`
    - `git pull`
2. Cherry-pick PRs in order
    - `git fetch origin pull/86/head:pr-86`
    - `git cherry-pick main..pr-86`
    - `git fetch origin pull/92/head:pr-92`
    - `git cherry-pick main..pr-92`
    - `git fetch origin pull/103/head:pr-103`
    - `git cherry-pick main..pr-103`
    - `git fetch origin pull/106/head:pr-106`
    - `git cherry-pick main..pr-106`
3. Resolve conflicts, then continue
    - `git status`
    - Fix conflicts, `git add <files>`
    - `git cherry-pick --continue`

## Feature Notes

### Quick Tools (PR #86)
- Files: panels/quick_tools_panels.py
- Manual changes applied:
   - Move Quick Tools to its own sidebar tab: `bl_category = "Quick Tools"`.
- Validation:
   - Quick Tools appears in its own tab; paint panel still works in Texture Paint.

### Color Picker (PR #92)
- Files: panels/extras_panels.py, preferences.py
- Manual changes: none.
- Validation:
   - Color picker and palette UI render without errors.

### Naming Sync (PR #103)
- Files: paintsystem/data.py, paintsystem/handlers.py, operators/utils_operators.py
- Manual changes applied:
   - Group name prefix uses `PS_<material>` and ensures unique names.
   - Layer/image rename updates are robust and use group index.
   - Msgbus and handlers restore last material name safely.
- Validation:
   - Renaming material updates group/layer/image names and bake images.

### Removed AutoUV (PR #106)
- Files: operators/common.py, related UI usage
- Manual changes: none beyond conflict resolution.
- Validation:
   - UV coord selection works; AutoUV removed where expected.

### Convert to PS (PR #105)
- Files: panels/extras_panels.py, operators/utils_operators.py
- Manual changes:
   - Conflict resolved to keep Convert to PS and Sync Names in the panel.
- Validation:
   - Convert button appears on materials with Principled BSDF.

### UV Edit Workflow (UV-EditWorkflow)
Core files:
- operators/uv_edit_operators.py
- panels/uv_editor_panels.py
- panels/common.py
- paintsystem/data.py
- paintsystem/handlers.py

Behavior implemented:
- UV Editor panel appears in UV mode even on Bforartists variants.
- Start UV Edit switches to Edit mode; target UV is active/render.
- Checker shows on objects and in UV editor; restores on Exit/Apply.
- Apply UV Edit uses original material for baking (checker is ignored).
- Keep Old UV keeps original map but sets layers to target UV.
- Override Existing Images optionally bakes into existing images.
- Channel Scope controls which channels are processed.
- UDIM detection auto-switches to Auto UDIM and shows notice.

Manual changes beyond original branch:
- Checker uses a temporary material override on affected objects.
- Apply UV Edit temporarily restores original materials for baking, then restores.
- UVs and render-active UV are kept in sync; checker UV is temporary.
- Added Advanced options: alpha mode, bake margin/margin type, UDIM policy, override mode.
- Image Resolution exposed outside Advanced; new image settings moved into Advanced.
- Quick tools moved into its own category.
 - UI: Add Paint System and Convert to PS only show in Object mode.
 - UI: Add Paint System is hidden while UV Edit mode is active.
 - UI: Brush Shortcuts popover moved into the Brush panel header; Settings header removed.
 - Updates: version check runs on addon enable, and console log is silenced.

Layer Settings UI changes:
- panels/layers_panels.py
   - Image/Transform panel headers and body layout are split between open/closed states.

Conflict-sensitive areas:
- panels/common.py: add UV edit alert/guard without breaking existing UI.
- paintsystem/data.py: add UV edit properties and keep existing handlers stable.
- paintsystem/handlers.py: add UV edit mode guard; avoid conflicts with msgbus setup.
- operators/__init__.py and panels/__init__.py: ensure new modules are registered.

#### Detailed Change Map (Level 4)
This section lists the concrete API surface, per-file changes, and key behaviors.

Quick Tools (PR #86)
- panels/quick_tools_panels.py
   - Set `bl_category = "Quick Tools"` to move the panel to its own tab.

Color Picker (PR #92)
- panels/extras_panels.py
- preferences.py
   - No manual edits beyond conflict resolution.

Naming Sync (PR #103)
- paintsystem/data.py
   - Group name prefix now follows `PS_<material>` and stays unique.
- paintsystem/handlers.py
   - Msgbus rename handling restores last material name safely.
- operators/utils_operators.py
   - Layer/image rename updates use group index for stability.

Removed AutoUV (PR #106)
- operators/common.py
   - AutoUV coord type removed from UI/options.

Convert to PS (PR #105)
- panels/extras_panels.py
   - Convert to PS and Sync Names retained in the same panel.
- operators/utils_operators.py
   - Convert operator remains accessible for Principled BSDF materials.

UV Edit Workflow (UV-EditWorkflow)
- operators/uv_edit_operators.py
   - UV editor integration helpers: `_get_uv_editor_spaces`, `_set_uv_editor_image`, `_store_uv_editor_image`, `_restore_uv_editor_image`.
   - Checker assets: `_get_checker_image`, `_get_checker_material`, `_update_checker_preview`.
   - UV creation and unwrap routing: `_create_new_uv_map`, `_run_uv_ops` with Lightmap Pack property guard.
   - UV state tracking: `_store_previous_uvs`, `_restore_previous_uvs`, `_track_created_uv`, `_remove_created_uvs`.
   - Checker material overrides: `_apply_checker_materials`, `_restore_checker_materials`, `_restore_checker_materials_temp`.
   - Bake path: `_bake_layer_to_uv` handles override images, alpha policy, margin, and channel layer toggles.
   - Operators:
      - `paint_system.grab_active_layer_uv` (PAINTSYSTEM_OT_GrabActiveLayerUV)
      - `paint_system.sync_uv_names` (PAINTSYSTEM_OT_SyncUVNames)
      - `paint_system.clear_unused_uvs` (PAINTSYSTEM_OT_ClearUnusedUVs)
      - `paint_system.update_uv_checker` (PAINTSYSTEM_OT_UpdateUVChecker)
      - `paint_system.start_uv_edit` (PAINTSYSTEM_OT_StartUVEdit)
      - `paint_system.apply_uv_edit` (PAINTSYSTEM_OT_ApplyUVEdit)
      - `paint_system.exit_uv_edit` (PAINTSYSTEM_OT_ExitUVEdit)
- panels/uv_editor_panels.py
   - New UV Editor side panel `IMAGE_PT_PaintSystemUVEdit` (IMAGE_EDITOR, UV/UV_EDIT modes).
   - Step 1: Fix UVs (grab/sync/clear) and target UV selection or creation.
   - Step 2: UV edit options when enabled (checker + apply).
- panels/common.py
   - New UI helpers: `is_uv_edit_active`, `draw_uv_edit_alert`, `draw_uv_edit_checker`.
- panels/main_panels.py
   - Adds `draw_uv_edit_alert` banner to the main paint panel.
- paintsystem/data.py
   - New property groups: `UVEditMaterialOverride` and UV edit state on `PaintSystemGlobalData`.
   - UV edit state: mode, target, unwrap settings, bake options, checker settings, and temporary override storage.
- paintsystem/handlers.py
   - `uv_edit_mode_guard` msgbus hook forces exit from Texture Paint while UV Edit is active.
   - Update check runs on addon enable instead of on every load.
- paintsystem/version_check.py
   - Update check log line removed.
- panels/__init__.py and operators/__init__.py
   - Register `uv_editor_panels` and `uv_edit_operators` modules.
Additional UI and mode gating
- panels/main_panels.py
   - Add Paint System and Convert to PS only appear in Object mode.
   - Add Paint System is hidden during UV Edit mode.
- panels/extras_panels.py
   - Brush Shortcuts popover moved to the Brush panel header.
   - Settings header removed from the Brush panel.
- operators/group_operators.py
   - `paint_system.new_group` and `paint_system.convert_material_to_ps` require Object mode.

Layer Settings UI changes
- panels/layers_panels.py
   - Image/Transform panel headers and body layout are split between open/closed states.

#### UV Edit Operators: Behavior Notes
- Start UV Edit
   - Ensures target UV exists or is created based on method.
   - Switches to Edit mode when possible.
   - Enables checker preview and updates active image.
- Apply UV Edit
   - Temporarily restores original materials for baking if checker overrides are active.
   - Supports channel scopes (All, Active, Exclude) with comma-separated excludes.
   - Respects UDIM policy and image resolution settings.
   - Optionally removes source UV if Keep Old UV is disabled.
- Exit UV Edit
   - Restores UV editor image, UV states, and checker materials.
   - Removes UVs created during UV Edit when exiting without apply.

#### UV Edit Properties (PaintSystemGlobalData)
- Mode/Target: `uv_edit_enabled`, `uv_edit_source_uv`, `uv_edit_target_uv`, `uv_edit_target_mode`.
- Unwrap settings: `uv_edit_new_uv_method`, `uv_edit_unwrap_fill_holes`, `uv_edit_unwrap_correct_aspect`, `uv_edit_unwrap_use_subsurf`, `uv_edit_unwrap_margin`.
- Smart UV: `uv_edit_smart_angle_limit`, `uv_edit_smart_island_margin`, `uv_edit_smart_area_weight`, `uv_edit_smart_correct_aspect`, `uv_edit_smart_scale_to_bounds`, `uv_edit_smart_margin_method`, `uv_edit_smart_rotate_method`.
- Min Stretch: `uv_edit_min_stretch_blend`, `uv_edit_min_stretch_iterations`.
- Lightmap: `uv_edit_lightmap_quality`, `uv_edit_lightmap_margin`, `uv_edit_lightmap_pack_in_one`.
- Baking: `uv_edit_keep_old_uv`, `uv_edit_override_existing_images`, `uv_edit_image_resolution`, `uv_edit_image_width`, `uv_edit_image_height`, `uv_edit_use_float`, `uv_edit_udim_policy`, `uv_edit_alpha_mode`, `uv_edit_bake_margin`, `uv_edit_bake_margin_type`.
- Channel scope: `uv_edit_channel_scope`, `uv_edit_exclude_channels`.
- Checker: `uv_edit_checker_enabled`, `uv_edit_checker_type`, `uv_edit_checker_resolution`, `uv_edit_previous_image`.
- UV bookkeeping: `uv_edit_created_uvs`, `uv_edit_previous_uvs`, `uv_edit_keep_ps_prefix_uvs`.
- Material override tracking: `uv_edit_material_overrides`, `uv_edit_apply_in_progress`, `uv_edit_source_material_name`.

### UV Edit Validation Checklist
- Image Editor panel appears in UV mode.
- Start UV Edit switches to Edit mode and activates target UV.
- Checker appears on objects and in UV editor; unpins on exit.
- Apply UV Edit bakes with original material even when checker is on.
- Keep Old UV keeps source UV present but does not keep it active.
- Override Existing Images bakes into existing images when enabled.

## Post-Merge Checks
- Enable addon in Blender (register/unregister works).
- Rename a material and confirm group/layer/image/bake image names update.
- Run `run_tests.py` if available.

## Known Implementation Notes
- Name sync is controlled by preferences: `automatic_name_syncing`.
- Material rename sync uses handlers and msgbus.
- Blender extensions reload may fail if PIL binaries are locked on Windows.

## Change Log
- 2026-02-10: Added UV Edit workflow details and manual change list.
