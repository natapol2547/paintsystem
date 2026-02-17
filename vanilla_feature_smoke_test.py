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

    def _check_registered_surface():
        ops = [name for name in dir(bpy.ops.paint_system) if not name.startswith("_")]
        assert_true("new_group" in ops, "new_group operator missing")
        assert_true("add_channel" in ops, "add_channel operator missing")
        assert_true("new_image_layer" in ops, "new_image_layer operator missing")
        assert_true("start_uv_edit" in ops, "start_uv_edit operator missing")

    check("operators_registered", _check_registered_surface)

    def _check_properties():
        assert_true(hasattr(bpy.types.Scene, "ps_scene_data"), "Scene.ps_scene_data missing")
        assert_true(hasattr(bpy.types.Material, "ps_mat_data"), "Material.ps_mat_data missing")

    check("properties_registered", _check_properties)

    def _setup_scene_and_material():
        bpy.ops.object.select_all(action='SELECT')
        bpy.ops.object.delete(use_global=False)
        bpy.ops.mesh.primitive_cube_add()
        obj = bpy.context.active_object
        assert_true(obj is not None and obj.type == 'MESH', "failed to create mesh object")
        mat = bpy.data.materials.new("SmokeMat")
        obj.data.materials.append(mat)
        obj.active_material = mat
        bpy.ops.object.mode_set(mode='OBJECT')

    check("scene_setup", _setup_scene_and_material)

    def _new_group():
        result = bpy.ops.paint_system.new_group(
            'EXEC_DEFAULT',
            template='BASIC',
            group_name='SmokeGroup',
            add_layers=False,
        )
        assert_true('FINISHED' in result, f"new_group did not finish: {result}")

    check("new_group", _new_group)

    def _add_channel():
        result = bpy.ops.paint_system.add_channel(
            'EXEC_DEFAULT',
            template='CUSTOM',
            channel_name='SmokeColor',
            channel_type='COLOR',
            color_space='COLOR',
            use_alpha=True,
        )
        assert_true('FINISHED' in result, f"add_channel did not finish: {result}")

    check("add_channel", _add_channel)

    def _new_image_layer():
        try:
            result = bpy.ops.paint_system.new_image_layer(
                'EXEC_DEFAULT',
                image_add_type='NEW',
                image_name='SmokeImage',
            )
            assert_true('FINISHED' in result, f"new_image_layer did not finish: {result}")
            return
        except RuntimeError as exc:
            if "poll() failed, context is incorrect" not in str(exc):
                raise

        ps_ctx = parse_context(bpy.context)
        assert_true(ps_ctx.active_channel is not None, "active channel missing for fallback image layer create")
        image = create_ps_image("SmokeImage", width=1024, height=1024)
        layer = ps_ctx.active_channel.create_layer(
            bpy.context,
            layer_name="SmokeImage",
            layer_type="IMAGE",
            image=image,
            coord_type='UV',
            uv_map_name=ps_ctx.ps_object.data.uv_layers.active.name if ps_ctx.ps_object and ps_ctx.ps_object.data.uv_layers.active else "",
        )
        assert_true(layer is not None and layer.type == "IMAGE", "fallback image layer creation failed")

    check("new_image_layer", _new_image_layer)

    def _sync_names():
        result = bpy.ops.paint_system.sync_names('EXEC_DEFAULT')
        assert_true('FINISHED' in result, f"sync_names did not finish: {result}")

    check("sync_names", _sync_names)

    def _uv_edit_start_update_exit():
        obj = bpy.context.active_object
        scene_data = bpy.context.scene.ps_scene_data
        assert_true(obj is not None and obj.type == 'MESH', "no active mesh for UV edit")
        assert_true(obj.data.uv_layers.active is not None, "object has no active UV")

        uv_name = obj.data.uv_layers.active.name
        scene_data.uv_edit_target_mode = 'EXISTING'
        scene_data.uv_edit_source_uv = uv_name
        scene_data.uv_edit_target_uv = uv_name

        result = bpy.ops.paint_system.start_uv_edit('EXEC_DEFAULT')
        assert_true('FINISHED' in result, f"start_uv_edit did not finish: {result}")
        assert_true(scene_data.uv_edit_enabled, "uv_edit_enabled not set after start")

        result = bpy.ops.paint_system.update_uv_checker('EXEC_DEFAULT')
        assert_true('FINISHED' in result, f"update_uv_checker did not finish: {result}")

        result = bpy.ops.paint_system.exit_uv_edit('EXEC_DEFAULT')
        assert_true('FINISHED' in result, f"exit_uv_edit did not finish: {result}")

    check("uv_edit_start_update_exit", _uv_edit_start_update_exit)

    check("unregister", addon.unregister)

    failed = [row for row in RESULTS if not row[1]]
    print("\n=== Paint System Vanilla Feature Smoke Test ===")
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
