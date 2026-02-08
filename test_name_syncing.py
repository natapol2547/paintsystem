"""Simple verification script for Paint System name syncing.

Run inside Blender:
- Open Text Editor
- Load this file
- Run Script
"""

import bpy

# Ensure addon enabled
if "paintsystem" not in bpy.context.preferences.addons:
    print("Paint System addon is not enabled.")

# Create a test material
mat = bpy.data.materials.new("Sword")
mat.use_nodes = True

# Ensure Paint System data exists
if not hasattr(mat, "ps_mat_data"):
    print("Paint System material data not initialized.")
else:
    # Trigger rename
    mat.name = "Sword"
    bpy.ops.paint_system.sync_names()

    # Verify group naming
    if mat.ps_mat_data.groups:
        print("Group name:", mat.ps_mat_data.groups[0].name)

    # Verify layer/image names
    for group in mat.ps_mat_data.groups:
        for channel in group.channels:
            for layer in channel.layers:
                if layer.type == "IMAGE" and layer.image:
                    print("Layer:", layer.name, "Image:", layer.image.name)
