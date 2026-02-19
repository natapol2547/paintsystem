import sys
import traceback
import bpy


RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append((name, True, "ok"))
    except Exception as exc:
        RESULTS.append((name, False, f"{type(exc).__name__}: {exc}"))


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def main():
    sys.path.insert(0, r"c:\Users\pinkn\Documents\PinkSystem1")
    import paintsystem as addon
    from paintsystem.paintsystem.context import parse_context
    from paintsystem.paintsystem.data import create_ps_image

    check("register", addon.register)

    state = {
        "obj1": None,
        "obj2": None,
        "mat": None,
        "target_uv": "UV_New_Smoke",
    }

    def _setup_scene_shared_material():
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)

        bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))
        obj1 = bpy.context.active_object
        bpy.ops.mesh.primitive_cube_add(location=(2, 0, 0))
        obj2 = bpy.context.active_object

        assert_true(obj1 and obj1.type == 'MESH', "first mesh not created")
        assert_true(obj2 and obj2.type == 'MESH', "second mesh not created")

        mat = bpy.data.materials.new("SmokeBakeUVMat")
        obj1.data.materials.append(mat)
        obj2.data.materials.append(mat)

        if not obj1.data.uv_layers.active:
            obj1.data.uv_layers.new(name="UVMap")
        if not obj2.data.uv_layers.active:
            obj2.data.uv_layers.new(name="UVMap")

        bpy.context.view_layer.objects.active = obj1
        obj1.select_set(True)
        obj2.select_set(True)
        obj1.active_material = mat

        state["obj1"] = obj1
        state["obj2"] = obj2
        state["mat"] = mat

    check("setup_scene_shared_material", _setup_scene_shared_material)

    def _setup_paint_system_data():
        result = bpy.ops.paint_system.new_group(
            'EXEC_DEFAULT',
            template='BASIC',
            group_name='SmokeGroup',
            add_layers=False,
        )
        assert_true('FINISHED' in result, f"new_group failed: {result}")

        result = bpy.ops.paint_system.add_channel(
            'EXEC_DEFAULT',
            template='CUSTOM',
            channel_name='SmokeColor',
            channel_type='COLOR',
            color_space='COLOR',
            use_alpha=True,
        )
        assert_true('FINISHED' in result, f"add_channel failed: {result}")

        ps_ctx = parse_context(bpy.context)
        assert_true(ps_ctx.active_channel is not None, "active channel missing")

        image = create_ps_image("SmokeSourceNonSquare", width=1536, height=768)
        layer = ps_ctx.active_channel.create_layer(
            bpy.context,
            layer_name="SmokeSourceLayer",
            layer_type="IMAGE",
            image=image,
            coord_type='UV',
            uv_map_name='UVMap',
        )
        assert_true(layer is not None and layer.type == 'IMAGE', "image layer creation failed")

        scene_data = bpy.context.scene.ps_scene_data
        scene_data.temp_materials.clear()
        temp_mat = scene_data.temp_materials.add()
        temp_mat.material = state["mat"]
        temp_mat.enabled = True

    check("setup_paint_system_data", _setup_paint_system_data)

    def _bake_channel_auto_size():
        result = bpy.ops.paint_system.bake_channel(
            'EXEC_DEFAULT',
            image_resolution='2048',
            uv_map_name='UVMap',
            use_gpu=False,
            as_layer=False,
        )
        assert_true('FINISHED' in result, f"bake_channel failed: {result}")

        ps_ctx = parse_context(bpy.context)
        baked = ps_ctx.active_channel.bake_image
        assert_true(baked is not None, "bake image missing")
        assert_true(tuple(baked.size) == (1536, 768), f"expected (1536, 768), got {tuple(baked.size)}")

    check("bake_channel_auto_size", _bake_channel_auto_size)

    def _transfer_uv_shared_objects():
        result = bpy.ops.paint_system.transfer_image_layer_uv(
            'EXEC_DEFAULT',
            uv_map_name=state["target_uv"],
            use_gpu=False,
        )
        assert_true('FINISHED' in result, f"transfer_image_layer_uv failed: {result}")

        for obj in (state["obj1"], state["obj2"]):
            uv_layer = obj.data.uv_layers.get(state["target_uv"])
            assert_true(uv_layer is not None, f"{obj.name} missing target UV")
            assert_true(uv_layer.active_render, f"{obj.name} target UV not active render")

    check("transfer_uv_shared_objects", _transfer_uv_shared_objects)

    def _uv_edit_shared_workflow_sync():
        scene_data = bpy.context.scene.ps_scene_data
        scene_data.uv_edit_target_mode = 'EXISTING'
        scene_data.uv_edit_source_uv = 'UVMap'
        scene_data.uv_edit_target_uv = state["target_uv"]

        result = bpy.ops.paint_system.start_uv_edit('EXEC_DEFAULT')
        assert_true('FINISHED' in result, f"start_uv_edit failed: {result}")

        for obj in (state["obj1"], state["obj2"]):
            uv_layer = obj.data.uv_layers.get(state["target_uv"])
            assert_true(uv_layer is not None, f"{obj.name} missing uv during edit")
            assert_true(uv_layer.active_render, f"{obj.name} uv not render-active during edit")

        result = bpy.ops.paint_system.exit_uv_edit('EXEC_DEFAULT')
        assert_true('FINISHED' in result, f"exit_uv_edit failed: {result}")

    check("uv_edit_shared_workflow_sync", _uv_edit_shared_workflow_sync)

    check("unregister", addon.unregister)

    failed = [row for row in RESULTS if not row[1]]
    print("\n=== Paint System Bake/UV Feature Smoke Test ===")
    for name, ok, msg in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {msg}")

    if failed:
        print(f"\nFAILED: {len(failed)} checks")
        sys.exit(1)

    print("\nALL CHECKS PASSED")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        sys.exit(1)
