# Implementation Summary: Name Syncing

## Files Updated
- paintsystem/data.py
- paintsystem/handlers.py
- operators/utils_operators.py
- panels/preferences_panels.py
- preferences.py

## Core Changes
### Name Sync Helpers (paintsystem/data.py)
- Added helper utilities for resolving material/layer prefixes and suffixes
- Added `find_material_for_layer()` to resolve owning material
- Added `_set_layer_name()` to update layer names safely
- Added `update_material_name()` to cascade material rename updates
- Added `sync_names()` entry point for manual sync

### Layer Name Updates
- `Layer.update_name()` now:
  - Keeps `layer_name` in sync
  - Applies material prefix when auto syncing is enabled
  - Updates image datablock names for image layers
  - Uses `updating_name_flag` to avoid recursion

### Group Updates
- Added `Group.update_group_name()` callback

### Material Rename Handling
- Resolved handler merge conflict in `material_name_update_handler`
- Added `MaterialData.last_material_name` tracking

### Preferences
- Added `automatic_name_syncing` preference (default enabled)

### Manual Sync Operator
- Added `PAINTSYSTEM_OT_SyncNames` to trigger sync on demand

## Behavior Summary
- Material rename cascades to group + image layers (when auto syncing enabled)
- Layer rename updates image names and preserves material prefix
- Manual operator works even when auto sync is disabled
