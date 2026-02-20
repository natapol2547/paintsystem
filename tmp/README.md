# Clean Branch Patches

These patch files contain the changes for the `convert-to-ps-clean` and `remove-auto-uv-clean` branches.

## How to apply

### convert-to-ps-clean

```bash
git checkout main
git checkout -b convert-to-ps-clean
git apply tmp/convert-to-ps-clean.patch
git push origin convert-to-ps-clean
```

### remove-auto-uv-clean

```bash
git checkout main  
git checkout -b remove-auto-uv-clean
git apply tmp/remove-auto-uv-clean.patch
git push origin remove-auto-uv-clean
```

## Branch contents

### naming-clean (already pushed as `copilot/add-naming-feature`)
- Adds `find_material_for_layer`, `ensure_layer_name_prefix`, `update_material_name`, `sync_names` to `paintsystem/data.py`
- Adds `material_name_update_handler`, `material_name_msgbus_callback` to `paintsystem/handlers.py`
- Adds `PAINTSYSTEM_OT_SyncNames` to `operators/utils_operators.py`
- Adds `automatic_name_syncing` preference to `preferences.py` and `panels/preferences_panels.py`
- Adds `IMPLEMENTATION_SUMMARY.md` and `NAME_SYNCING_GUIDE.md`

### convert-to-ps-clean
- Adds `PAINTSYSTEM_OT_ConvertMaterialToPS` operator to `operators/group_operators.py`
- Adds Convert Material UI in `panels/extras_panels.py` and `panels/main_panels.py`

### remove-auto-uv-clean
- Improves icon loading in `custom_icons.py`
- Updates Auto UV button label in `operators/common.py`
- Consolidates AUTO coord type with UV type in `panels/layers_panels.py`
