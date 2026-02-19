"""Assertion-based name-sync verification for Paint System.

Run inside Blender Text Editor.
"""

import bpy

from paintsystem.paintsystem.context import parse_context
from paintsystem.paintsystem.data import create_ps_image, sync_names, update_material_name
from paintsystem.preferences import get_preferences


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def _first_layer_data(channel):
    for layer in channel.layers:
        layer_data = layer.get_layer_data() if hasattr(layer, "get_layer_data") else layer
        if layer_data:
            return layer_data
    return None


def main():
    assert_true("paintsystem" in bpy.context.preferences.addons, "Paint System addon is not enabled")

    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.mesh.primitive_cube_add()
    obj = bpy.context.active_object
    assert_true(obj is not None and obj.type == 'MESH', "Failed to create test object")

    mat = bpy.data.materials.new("Sword")
    mat.use_nodes = True
    obj.data.materials.append(mat)
    obj.active_material = mat

    result = bpy.ops.paint_system.new_group(
        'EXEC_DEFAULT',
        template='BASIC',
        group_name='Sword',
        add_layers=False,
    )
    assert_true('FINISHED' in result, f"new_group failed: {result}")

    result = bpy.ops.paint_system.add_channel(
        'EXEC_DEFAULT',
        template='CUSTOM',
        channel_name='Color',
        channel_type='COLOR',
        color_space='COLOR',
        use_alpha=True,
    )
    assert_true('FINISHED' in result, f"add_channel failed: {result}")

    ps_ctx = parse_context(bpy.context)
    assert_true(ps_ctx.active_channel is not None, "Active channel is missing")
    prefs = get_preferences(bpy.context)
    prefs.automatic_name_syncing = True

    test_image = create_ps_image("Imported_Source", width=1024, height=1024)
    new_layer = ps_ctx.active_channel.create_layer(
        bpy.context,
        layer_name="Image",
        layer_type="IMAGE",
        image=test_image,
        coord_type='UV',
        uv_map_name=ps_ctx.ps_object.data.uv_layers.active.name if ps_ctx.ps_object and ps_ctx.ps_object.data.uv_layers.active else "",
    )
    assert_true(new_layer is not None, "Image layer creation failed")
    assert_true(new_layer.name == "Sword_Image", f"Create-time layer naming mismatch: {new_layer.name}")
    assert_true(new_layer.image and new_layer.image.name == "Sword_Image", "Create-time image naming mismatch")

    prefs.automatic_name_syncing = False
    manual_image = create_ps_image("Manual_Source", width=512, height=512)
    manual_layer = ps_ctx.active_channel.create_layer(
        bpy.context,
        layer_name="Manual_Layer",
        layer_type="IMAGE",
        image=manual_image,
        coord_type='UV',
        uv_map_name=ps_ctx.ps_object.data.uv_layers.active.name if ps_ctx.ps_object and ps_ctx.ps_object.data.uv_layers.active else "",
    )
    assert_true(manual_layer is not None, "Manual layer creation failed")
    assert_true(manual_layer.name == "Manual_Layer", "Layer was unexpectedly renamed while auto-sync disabled")
    assert_true(manual_layer.image and manual_layer.image.name == "Manual_Source", "Image was unexpectedly renamed while auto-sync disabled")

    image_layer = new_layer.get_layer_data() if hasattr(new_layer, "get_layer_data") else new_layer
    assert_true(image_layer is not None and image_layer.type == 'IMAGE', "Image layer missing after setup")

    prefs.automatic_name_syncing = True
    mat.ps_mat_data.last_material_name = "Sword"
    mat.name = "Blade"
    update_material_name(mat, bpy.context)

    assert_true(mat.ps_mat_data.groups[0].name == "Blade", "Group name did not follow material rename")
    assert_true(image_layer.name.startswith("Blade"), "Layer name did not follow material rename")
    assert_true(image_layer.image and image_layer.image.name == image_layer.name, "Image name did not follow layer name")

    prev_group_name = mat.ps_mat_data.groups[0].name
    prev_layer_name = image_layer.name
    prefs.automatic_name_syncing = False
    mat.name = "Dagger"
    update_material_name(mat, bpy.context)

    assert_true(mat.ps_mat_data.groups[0].name == prev_group_name, "Group name changed while auto-sync was disabled")
    assert_true(image_layer.name == prev_layer_name, "Layer name changed while auto-sync was disabled")

    image_layer.name = "Custom_Manual"
    assert_true(image_layer.image and image_layer.image.name == "Custom_Manual", "Layer rename did not propagate to image while auto-sync disabled")

    sync_names(bpy.context, material=mat, force=True)
    assert_true(mat.ps_mat_data.groups[0].name == "Dagger", "Manual sync did not update group name")
    assert_true(image_layer.name.startswith("Dagger"), "Manual sync did not update layer name")
    assert_true(image_layer.image and image_layer.image.name == image_layer.name, "Manual sync did not update image name")

    print("Name syncing checks passed.")


if __name__ == "__main__":
    main()
