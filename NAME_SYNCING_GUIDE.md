# Paint System Name Syncing Guide

## Overview
Paint System can synchronize naming between Materials, Groups, Layers, and Images.
When enabled, renaming a material updates its group and image layer names automatically.

## Preference Toggle
Location: Preferences → Add-ons → Paint System → Automatic Name Syncing
- Default: Enabled
- When disabled: automatic name synchronization is skipped

## Naming Hierarchy
Material: `Sword`
Group: `PS_Sword`
Layer: `Sword_Base`
Image: `Sword_Base`

## Automatic Syncing (Enabled)
- Material rename → group name updated with `PS_` prefix
- Material rename → image layer names updated with new material prefix
- Image datablocks are updated to match layer names
- Layer rename → associated image name updated

## Manual Sync Operator
If automatic syncing is disabled, run:

```
bpy.ops.paint_system.sync_names()
```

This synchronizes the active material, its groups, image layers, and images.

## Notes
- Only image layers are renamed when a material changes
- Linked layers from other materials are not modified
