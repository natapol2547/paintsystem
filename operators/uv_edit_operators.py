import math
import bpy
from bpy.props import BoolProperty
from bpy.types import Context, Operator
from bpy.utils import register_classes_factory

from .common import MultiMaterialOperator, PSContextMixin
from ..panels.common import scale_content
from ..paintsystem.data import create_ps_image, get_layer_blend_type, set_layer_blend_type, update_active_image, get_udim_tiles
from ..paintsystem.context import parse_material
from ..paintsystem.image import blender_image_to_numpy, set_image_pixels
from ..paintsystem.graph.common import DEFAULT_PS_UV_MAP_NAME
from ..utils import get_next_unique_name


def _get_uv_editor_spaces(context: Context):
    if not context or not context.screen:
        return []
    spaces = []
    for area in context.screen.areas:
        if area.type != 'IMAGE_EDITOR':
            continue
        for space in area.spaces:
            if space.type == 'IMAGE_EDITOR':
                spaces.append(space)
                break
    return spaces


def _set_space_uv_mode(space) -> None:
    mode_set = False

    if hasattr(space, "mode"):
        try:
            mode_prop = space.bl_rna.properties.get("mode")
            mode_items = {item.identifier for item in mode_prop.enum_items} if mode_prop else set()
            if "UV" in mode_items:
                space.mode = 'UV'
                mode_set = True
        except Exception:
            pass

    if hasattr(space, "ui_mode"):
        try:
            ui_mode_prop = space.bl_rna.properties.get("ui_mode")
            ui_mode_items = {item.identifier for item in ui_mode_prop.enum_items} if ui_mode_prop else set()
            if "UV" in ui_mode_items:
                space.ui_mode = 'UV'
                mode_set = True
            elif not mode_set and "VIEW" in ui_mode_items:
                space.ui_mode = 'VIEW'
        except Exception:
            pass


def _set_uv_editor_image(context: Context, image: bpy.types.Image | None) -> None:
    for space in _get_uv_editor_spaces(context):
        space.image = image
        _set_space_uv_mode(space)


def _clear_uv_editor_image(context: Context) -> None:
    for space in _get_uv_editor_spaces(context):
        space.image = None
        _set_space_uv_mode(space)
        if hasattr(space, "use_image_pin"):
            space.use_image_pin = False


def _store_uv_editor_image(ps_scene_data, context: Context) -> None:
    if ps_scene_data.uv_edit_previous_image:
        return
    for space in _get_uv_editor_spaces(context):
        if space.image:
            ps_scene_data.uv_edit_previous_image = space.image.name
            return


def _restore_uv_editor_image(ps_scene_data, context: Context) -> None:
    if not ps_scene_data.uv_edit_previous_image:
        return
    image = bpy.data.images.get(ps_scene_data.uv_edit_previous_image)
    _set_uv_editor_image(context, image)
    for space in _get_uv_editor_spaces(context):
        if hasattr(space, "use_image_pin"):
            space.use_image_pin = False
    ps_scene_data.uv_edit_previous_image = ""


def _get_checker_image(ps_scene_data) -> bpy.types.Image:
    checker_type = ps_scene_data.uv_edit_checker_type
    res = int(ps_scene_data.uv_edit_checker_resolution)
    name = f"PS_UVChecker_{checker_type}_{res}"
    image = bpy.data.images.get(name)
    if image and image.size[0] == res and image.size[1] == res:
        return image
    image = bpy.data.images.new(name=name, width=res, height=res, alpha=True)
    image.generated_type = 'UV_GRID' if checker_type == 'UV' else 'COLOR_GRID'
    image.colorspace_settings.name = 'sRGB'
    return image


def _get_checker_material(ps_scene_data) -> bpy.types.Material:
    image = _get_checker_image(ps_scene_data)
    material_name = f"PS_UVChecker_Mat_{image.name}"
    material = bpy.data.materials.get(material_name)
    if material:
        return material
    material = bpy.data.materials.new(material_name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    for node in list(nodes):
        nodes.remove(node)
    output_node = nodes.new(type="ShaderNodeOutputMaterial")
    texture_node = nodes.new(type="ShaderNodeTexImage")
    texture_node.image = image
    output_node.location = (300, 0)
    texture_node.location = (0, 0)
    links = material.node_tree.links
    links.new(texture_node.outputs[0], output_node.inputs[0])
    return material


def _update_checker_preview(context: Context) -> None:
    if not context or not context.scene or not context.scene.ps_scene_data:
        return
    ps_scene_data = context.scene.ps_scene_data
    if not ps_scene_data.uv_edit_enabled:
        return
    ps_ctx = PSContextMixin.parse_context(context)
    objects = ps_ctx.ps_objects or ([ps_ctx.ps_object] if ps_ctx.ps_object else [])
    _store_previous_uvs(ps_scene_data, objects)
    if ps_scene_data.uv_edit_checker_viewport_enabled:
        _apply_checker_uv(ps_scene_data, objects, ps_scene_data.uv_edit_target_uv)
        _apply_checker_materials(ps_scene_data, objects, ps_ctx.active_material)
    else:
        _restore_checker_materials(ps_scene_data)
    _store_uv_editor_image(ps_scene_data, context)
    if ps_scene_data.uv_edit_checker_enabled:
        checker_image = _get_checker_image(ps_scene_data)
        _set_uv_editor_image(context, checker_image)
    else:
        _clear_uv_editor_image(context)


def _ensure_uv_map(obj: bpy.types.Object, uv_name: str) -> bpy.types.MeshUVLoopLayer:
    uv_layers = obj.data.uv_layers
    if uv_layers.get(uv_name):
        return uv_layers.get(uv_name)
    return uv_layers.new(name=uv_name)


def _copy_uv_map(source, target) -> None:
    for idx, uv in enumerate(source.data):
        target.data[idx].uv = uv.uv


def _run_uv_ops(context: Context, obj: bpy.types.Object, ops_callback) -> None:
    prev_mode = obj.mode
    prev_active = context.view_layer.objects.active
    prev_selected = [o for o in context.selected_objects]
    try:
        context.view_layer.objects.active = obj
        obj.select_set(True)
        if obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.select_all(action='SELECT')
        ops_callback()
    finally:
        if obj.mode != prev_mode:
            bpy.ops.object.mode_set(mode=prev_mode)
        for o in prev_selected:
            o.select_set(True)
        if prev_active:
            context.view_layer.objects.active = prev_active


def _create_new_uv_map(context: Context, obj: bpy.types.Object, ps_scene_data) -> str:
    uv_layers = obj.data.uv_layers
    source_uv = ps_scene_data.uv_edit_source_uv
    if not source_uv and uv_layers.active:
        source_uv = uv_layers.active.name
    if not source_uv:
        source_uv = DEFAULT_PS_UV_MAP_NAME
    if not ps_scene_data.uv_edit_target_uv:
        ps_scene_data.uv_edit_target_uv = get_next_unique_name(
            f"{source_uv}_UV",
            [uv.name for uv in uv_layers]
        )
    target_uv = ps_scene_data.uv_edit_target_uv
    if uv_layers.get(target_uv):
        target_uv = get_next_unique_name(
            target_uv,
            [uv.name for uv in uv_layers]
        )
        ps_scene_data.uv_edit_target_uv = target_uv
    target_layer = _ensure_uv_map(obj, target_uv)
    uv_layers.active = target_layer

    def unwrap_ops():
        method = ps_scene_data.uv_edit_new_uv_method
        if method == 'COPY':
            if uv_layers.get(source_uv):
                _copy_uv_map(uv_layers.get(source_uv), target_layer)
            return
        if method in {'UNWRAP_ANGLE', 'UNWRAP_CONFORMAL'}:
            bpy.ops.uv.unwrap(
                method='ANGLE_BASED' if method == 'UNWRAP_ANGLE' else 'CONFORMAL',
                fill_holes=ps_scene_data.uv_edit_unwrap_fill_holes,
                correct_aspect=ps_scene_data.uv_edit_unwrap_correct_aspect,
                use_subsurf_data=ps_scene_data.uv_edit_unwrap_use_subsurf,
                margin=ps_scene_data.uv_edit_unwrap_margin,
            )
            return
        if method == 'MIN_STRETCH':
            bpy.ops.uv.minimize_stretch(
                fill_holes=ps_scene_data.uv_edit_unwrap_fill_holes,
                blend=ps_scene_data.uv_edit_min_stretch_blend,
                iterations=ps_scene_data.uv_edit_min_stretch_iterations,
            )
            return
        if method == 'LIGHTMAP':
            op_props = bpy.ops.uv.lightmap_pack.get_rna_type().properties
            kwargs = {}
            if "PREF_CONTEXT" in op_props:
                kwargs["PREF_CONTEXT"] = 'ALL_FACES'
            if "PREF_PACK_IN_ONE" in op_props:
                kwargs["PREF_PACK_IN_ONE"] = ps_scene_data.uv_edit_lightmap_pack_in_one
            if "PREF_MARGIN" in op_props:
                kwargs["PREF_MARGIN"] = ps_scene_data.uv_edit_lightmap_margin
            if "PREF_MARGIN_DIV" in op_props:
                kwargs["PREF_MARGIN_DIV"] = ps_scene_data.uv_edit_lightmap_margin
            if "PREF_PACK_QUALITY" in op_props:
                kwargs["PREF_PACK_QUALITY"] = ps_scene_data.uv_edit_lightmap_quality
            if "margin" in op_props:
                kwargs["margin"] = ps_scene_data.uv_edit_lightmap_margin
            if "pack_quality" in op_props:
                kwargs["pack_quality"] = ps_scene_data.uv_edit_lightmap_quality
            if "pack_in_one" in op_props:
                kwargs["pack_in_one"] = ps_scene_data.uv_edit_lightmap_pack_in_one
            if "context" in op_props:
                kwargs["context"] = 'ALL_FACES'
            bpy.ops.uv.lightmap_pack(**kwargs)
            return
        if method == 'SMART':
            bpy.ops.uv.smart_project(
                angle_limit=ps_scene_data.uv_edit_smart_angle_limit,
                island_margin=ps_scene_data.uv_edit_smart_island_margin,
                area_weight=ps_scene_data.uv_edit_smart_area_weight,
                correct_aspect=ps_scene_data.uv_edit_smart_correct_aspect,
                scale_to_bounds=ps_scene_data.uv_edit_smart_scale_to_bounds,
                margin_method=ps_scene_data.uv_edit_smart_margin_method,
                rotate_method=ps_scene_data.uv_edit_smart_rotate_method,
            )
            return

    _run_uv_ops(context, obj, unwrap_ops)
    return target_uv


def _get_objects_with_material(context: Context, material: bpy.types.Material) -> list[bpy.types.Object]:
    objects = []
    if not material:
        return objects
    for obj in context.scene.objects:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            if slot.material == material:
                objects.append(obj)
                break
    return objects


def _track_created_uv(ps_scene_data, obj: bpy.types.Object, uv_name: str) -> None:
    if not uv_name:
        return
    entry = ps_scene_data.uv_edit_created_uvs.add()
    entry.object_name = obj.name
    entry.uv_name = uv_name


def _remove_created_uvs(ps_scene_data) -> None:
    for entry in ps_scene_data.uv_edit_created_uvs:
        obj = bpy.data.objects.get(entry.object_name)
        if obj and obj.type == 'MESH' and obj.data.uv_layers.get(entry.uv_name):
            obj.data.uv_layers.remove(obj.data.uv_layers.get(entry.uv_name))
    ps_scene_data.uv_edit_created_uvs.clear()


def _store_previous_uvs(ps_scene_data, objects: list[bpy.types.Object]) -> None:
    if ps_scene_data.uv_edit_previous_uvs:
        return
    for obj in objects:
        if not obj or obj.type != 'MESH':
            continue
        uv_layers = obj.data.uv_layers
        entry = ps_scene_data.uv_edit_previous_uvs.add()
        entry.object_name = obj.name
        entry.active_uv = uv_layers.active.name if uv_layers.active else ""
        entry.render_uv = ""
        entry.clone_uv = ""
        for uv_layer in uv_layers:
            if uv_layer.active_render:
                entry.render_uv = uv_layer.name
            if uv_layer.active_clone:
                entry.clone_uv = uv_layer.name


def _restore_previous_uvs(ps_scene_data, restore_render: bool = True) -> None:
    for entry in ps_scene_data.uv_edit_previous_uvs:
        obj = bpy.data.objects.get(entry.object_name)
        if not obj or obj.type != 'MESH':
            continue
        uv_layers = obj.data.uv_layers
        if entry.active_uv and uv_layers.get(entry.active_uv):
            uv_layers.active = uv_layers.get(entry.active_uv)
        if restore_render and entry.render_uv and uv_layers.get(entry.render_uv):
            uv_layers.get(entry.render_uv).active_render = True
        if entry.clone_uv and uv_layers.get(entry.clone_uv):
            uv_layers.get(entry.clone_uv).active_clone = True
    ps_scene_data.uv_edit_previous_uvs.clear()


def _apply_checker_uv(ps_scene_data, objects: list[bpy.types.Object], target_uv: str) -> None:
    if not target_uv:
        return
    for obj in objects:
        if not obj or obj.type != 'MESH':
            continue
        uv_layer = obj.data.uv_layers.get(target_uv)
        if not uv_layer:
            continue
        uv_layer.active = True
        uv_layer.active_render = True
        uv_layer.active_clone = True


def _set_active_uv(objects: list[bpy.types.Object], target_uv: str) -> None:
    if not target_uv:
        return
    for obj in objects:
        if not obj or obj.type != 'MESH':
            continue
        uv_layer = obj.data.uv_layers.get(target_uv)
        if not uv_layer:
            continue
        uv_layer.active = True
        uv_layer.active_render = True


def _apply_checker_materials(ps_scene_data, objects: list[bpy.types.Object], target_material: bpy.types.Material | None) -> None:
    checker_material = _get_checker_material(ps_scene_data)
    if ps_scene_data.uv_edit_material_overrides:
        for entry in ps_scene_data.uv_edit_material_overrides:
            obj = bpy.data.objects.get(entry.object_name)
            if not obj or obj.type != 'MESH':
                continue
            if entry.slot_index >= len(obj.material_slots):
                continue
            obj.material_slots[entry.slot_index].material = checker_material
        return
    if not target_material:
        return
    ps_scene_data.uv_edit_source_material_name = target_material.name
    for obj in objects:
        if not obj or obj.type != 'MESH':
            continue
        for slot_index, slot in enumerate(obj.material_slots):
            if slot.material != target_material:
                continue
            entry = ps_scene_data.uv_edit_material_overrides.add()
            entry.object_name = obj.name
            entry.slot_index = slot_index
            entry.material_name = slot.material.name if slot.material else ""
            obj.material_slots[slot_index].material = checker_material


def _restore_checker_materials(ps_scene_data) -> None:
    for entry in ps_scene_data.uv_edit_material_overrides:
        obj = bpy.data.objects.get(entry.object_name)
        if not obj or obj.type != 'MESH':
            continue
        if entry.slot_index >= len(obj.material_slots):
            continue
        material = bpy.data.materials.get(entry.material_name) if entry.material_name else None
        obj.material_slots[entry.slot_index].material = material
    ps_scene_data.uv_edit_material_overrides.clear()
    ps_scene_data.uv_edit_source_material_name = ""


def _restore_checker_materials_temp(ps_scene_data) -> None:
    for entry in ps_scene_data.uv_edit_material_overrides:
        obj = bpy.data.objects.get(entry.object_name)
        if not obj or obj.type != 'MESH':
            continue
        if entry.slot_index >= len(obj.material_slots):
            continue
        material = bpy.data.materials.get(entry.material_name) if entry.material_name else None
        obj.material_slots[entry.slot_index].material = material


def _bake_layer_to_uv(context: Context, channel, layer, target_uv: str, ps_scene_data, obj, mat, objects_for_uv=None) -> None:
    if layer.type != 'IMAGE' or not layer.image:
        return
    if layer.coord_type not in {'UV', 'AUTO'}:
        return

    if ps_scene_data.uv_edit_override_existing_images:
        new_image = layer.image
        layer.coord_type = 'UV'
        layer.uv_map_name = target_uv
        layer.update_node_tree(context)
    else:
        if ps_scene_data.uv_edit_inherit_image_sizes:
            image_width = max(1, int(layer.image.size[0]))
            image_height = max(1, int(layer.image.size[1]))
        elif ps_scene_data.uv_edit_image_resolution != 'CUSTOM':
            image_width = int(ps_scene_data.uv_edit_image_resolution)
            image_height = int(ps_scene_data.uv_edit_image_resolution)
        else:
            image_width = ps_scene_data.uv_edit_image_width
            image_height = ps_scene_data.uv_edit_image_height

        image_name = get_next_unique_name(
            f"{layer.image.name}_{target_uv}",
            [image.name for image in bpy.data.images]
        )
        use_udim_tiles = ps_scene_data.uv_edit_udim_policy == 'AUTO'
        new_image = create_ps_image(
            name=image_name,
            width=image_width,
            height=image_height,
            use_udim_tiles=use_udim_tiles,
            objects=objects_for_uv or ([obj] if obj else None),
            uv_layer_name=target_uv,
            use_float=ps_scene_data.uv_edit_use_float,
        )
        new_image.colorspace_settings.name = layer.image.colorspace_settings.name

    to_restore = []
    for check_layer in channel.layers:
        if check_layer.enabled and check_layer != layer:
            to_restore.append(check_layer)
            check_layer.enabled = False

    original_blend_mode = get_layer_blend_type(layer)
    set_layer_blend_type(layer, 'MIX')
    original_is_clip = bool(layer.is_clip)
    if layer.is_clip:
        layer.is_clip = False

    force_alpha = ps_scene_data.uv_edit_alpha_mode in {'PRESERVE', 'PREMULTIPLY'}
    channel.bake(
        context,
        mat,
        new_image,
        target_uv,
        use_group_tree=False,
        force_alpha=force_alpha,
        margin=ps_scene_data.uv_edit_bake_margin,
        margin_type=ps_scene_data.uv_edit_bake_margin_type,
    )

    if layer.is_clip != original_is_clip:
        layer.is_clip = original_is_clip
    set_layer_blend_type(layer, original_blend_mode)
    layer.coord_type = 'UV'
    layer.uv_map_name = target_uv
    if not ps_scene_data.uv_edit_override_existing_images:
        layer.image = new_image
    layer.update_node_tree(context)

    if ps_scene_data.uv_edit_alpha_mode in {'OPAQUE', 'PREMULTIPLY'}:
        pixels = blender_image_to_numpy(new_image)
        if pixels:
            for tile_num, tile in pixels.tiles.items():
                if ps_scene_data.uv_edit_alpha_mode == 'OPAQUE':
                    tile[:, :, 3] = 1.0
                else:
                    tile[:, :, 0:3] *= tile[:, :, 3:4]
            set_image_pixels(new_image, pixels)

    for restore_layer in to_restore:
        restore_layer.enabled = True


class PAINTSYSTEM_OT_GrabActiveLayerUV(PSContextMixin, Operator):
    bl_idname = "paint_system.grab_active_layer_uv"
    bl_label = "Grab Active Layer UV"
    bl_description = "Set the UV edit source to the active layer UV"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        uv_name = ""
        if ps_ctx.active_layer and ps_ctx.active_layer.coord_type == 'UV':
            uv_name = ps_ctx.active_layer.uv_map_name
        if not uv_name and ps_ctx.ps_object and ps_ctx.ps_object.data.uv_layers.active:
            uv_name = ps_ctx.ps_object.data.uv_layers.active.name
        ps_scene_data.uv_edit_source_uv = uv_name
        if not ps_scene_data.uv_edit_target_uv:
            ps_scene_data.uv_edit_target_uv = uv_name
        return {'FINISHED'}


class PAINTSYSTEM_OT_SyncUVNames(PSContextMixin, Operator):
    bl_idname = "paint_system.sync_uv_names"
    bl_label = "Sync UV Names"
    bl_description = "Sync UV map names across image layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_mat_data is not None

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        uv_name = ps_scene_data.uv_edit_source_uv
        if not uv_name and ps_ctx.active_layer and ps_ctx.active_layer.coord_type == 'UV':
            uv_name = ps_ctx.active_layer.uv_map_name
        if not uv_name and ps_ctx.ps_object and ps_ctx.ps_object.data.uv_layers.active:
            uv_name = ps_ctx.ps_object.data.uv_layers.active.name
        if not uv_name:
            self.report({'WARNING'}, "No UV map to sync")
            return {'CANCELLED'}

        objects = ps_ctx.ps_objects or ([ps_ctx.ps_object] if ps_ctx.ps_object else [])
        for obj in objects:
            if not obj or obj.type != 'MESH' or not obj.data.uv_layers:
                continue
            if obj.data.uv_layers.get(uv_name):
                obj.data.uv_layers.active = obj.data.uv_layers.get(uv_name)
            else:
                if obj.data.uv_layers.active:
                    obj.data.uv_layers.active.name = uv_name
                    obj.data.uv_layers.active = obj.data.uv_layers.get(uv_name)
            if obj.data.uv_layers.active:
                obj.data.uv_layers.active.active_render = True

        for group in ps_ctx.ps_mat_data.groups:
            if group.coord_type == 'UV':
                group.uv_map_name = uv_name
            for channel in group.channels:
                for layer in channel.flattened_layers:
                    if layer.coord_type == 'UV':
                        layer.uv_map_name = uv_name
        ps_scene_data.uv_edit_source_uv = uv_name
        return {'FINISHED'}


class PAINTSYSTEM_OT_ClearUnusedUVs(PSContextMixin, Operator):
    bl_idname = "paint_system.clear_unused_uvs"
    bl_label = "Clear Unused UVs"
    bl_description = "Remove UV maps not used by Paint System layers"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.ps_object.type == 'MESH'

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.ps_object
        ps_scene_data = context.scene.ps_scene_data
        used_uvs = set()
        if ps_scene_data.uv_edit_source_uv:
            used_uvs.add(ps_scene_data.uv_edit_source_uv)
        if ps_scene_data.uv_edit_target_uv:
            used_uvs.add(ps_scene_data.uv_edit_target_uv)
        for group in ps_ctx.ps_mat_data.groups:
            if group.coord_type in {'UV', 'AUTO'}:
                if group.coord_type == 'AUTO':
                    used_uvs.add(DEFAULT_PS_UV_MAP_NAME)
                elif group.uv_map_name:
                    used_uvs.add(group.uv_map_name)
            for channel in group.channels:
                for layer in channel.flattened_layers:
                    if layer.coord_type == 'AUTO':
                        used_uvs.add(DEFAULT_PS_UV_MAP_NAME)
                    elif layer.coord_type == 'UV' and layer.uv_map_name:
                        used_uvs.add(layer.uv_map_name)
        if ps_scene_data.uv_edit_keep_ps_prefix_uvs:
            for uv_layer in obj.data.uv_layers:
                if uv_layer.name.startswith("PS_"):
                    used_uvs.add(uv_layer.name)
        uv_layers = obj.data.uv_layers
        if len(uv_layers) <= 1:
            return {'FINISHED'}
        remove_names = [uv.name for uv in uv_layers if uv.name not in used_uvs]
        for name in remove_names:
            layer = uv_layers.get(name)
            if layer and len(uv_layers) > 1:
                uv_layers.remove(layer)
        return {'FINISHED'}


class PAINTSYSTEM_OT_UpdateUVChecker(PSContextMixin, Operator):
    bl_idname = "paint_system.update_uv_checker"
    bl_label = "Update UV Checker"
    bl_description = "Update UV checker preview"

    def execute(self, context: Context):
        _update_checker_preview(context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_StartUVEdit(PSContextMixin, Operator):
    bl_idname = "paint_system.start_uv_edit"
    bl_label = "Start UV Edit"
    bl_description = "Start UV edit mode"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.ps_object.type == 'MESH'

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        obj = ps_ctx.ps_object
        if not obj or not obj.data.uv_layers:
            self.report({'ERROR'}, "Object has no UV maps")
            return {'CANCELLED'}

        objects_with_mat = _get_objects_with_material(context, ps_ctx.active_material)
        if obj and obj not in objects_with_mat:
            objects_with_mat.append(obj)
        objects_with_mat = [o for o in objects_with_mat if o and o.type == 'MESH']

        if not ps_scene_data.uv_edit_source_uv:
            if obj.data.uv_layers.active:
                ps_scene_data.uv_edit_source_uv = obj.data.uv_layers.active.name

        if ps_scene_data.uv_edit_target_mode == 'EXISTING':
            if not ps_scene_data.uv_edit_target_uv:
                self.report({'ERROR'}, "Select a target UV map")
                return {'CANCELLED'}
            if not obj.data.uv_layers.get(ps_scene_data.uv_edit_target_uv):
                self.report({'ERROR'}, "Target UV map not found")
                return {'CANCELLED'}
        else:
            target_uv = _create_new_uv_map(context, obj, ps_scene_data)
            ps_scene_data.uv_edit_target_uv = target_uv
            _track_created_uv(ps_scene_data, obj, target_uv)

        for sync_obj in objects_with_mat:
            uv_layer = sync_obj.data.uv_layers.get(ps_scene_data.uv_edit_target_uv)
            if not uv_layer:
                uv_layer = sync_obj.data.uv_layers.new(name=ps_scene_data.uv_edit_target_uv)
                _track_created_uv(ps_scene_data, sync_obj, uv_layer.name)
            sync_obj.data.uv_layers.active = uv_layer
            uv_layer.active_render = True
            uv_layer.active_clone = True

        obj.data.uv_layers.active = obj.data.uv_layers.get(ps_scene_data.uv_edit_target_uv)
        if obj.data.uv_layers.active:
            obj.data.uv_layers.active.active_render = True
        try:
            bpy.ops.object.mode_set(mode='EDIT')
        except Exception:
            pass
        _set_uv_editor_image(context, _get_checker_image(ps_scene_data))
        ps_scene_data.uv_edit_enabled = True
        ps_scene_data.uv_edit_checker_enabled = True
        ps_scene_data.uv_edit_checker_viewport_enabled = True
        update_active_image(context=context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ApplyUVEdit(PSContextMixin, MultiMaterialOperator, Operator):
    bl_idname = "paint_system.apply_uv_edit"
    bl_label = "Apply UV Edit"
    bl_description = "Bake Paint System layers to the target UV"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        layout.use_property_split = False
        layout.use_property_decorate = False
        material_name = ps_ctx.active_material.name if ps_ctx.active_material else "(none)"
        source_name = ps_scene_data.uv_edit_source_material_name
        if source_name:
            material_name = source_name
        layout.label(text=f"Baking material: {material_name}", icon='MATERIAL')
        list_material = bpy.data.materials.get(source_name) if source_name else ps_ctx.active_material
        objects_with_mat = _get_objects_with_material(context, list_material)
        if ps_ctx.ps_object and ps_ctx.ps_object not in objects_with_mat:
            objects_with_mat.append(ps_ctx.ps_object)
        if len(objects_with_mat) > 1:
            box = layout.box()
            box.label(text=f"Scope: {len(objects_with_mat)} Objects", icon='INFO')
            grid = box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
            for obj in objects_with_mat:
                grid.label(text=obj.name, icon='OBJECT_DATA')

        udim_detected = False
        if ps_ctx.ps_object and ps_scene_data.uv_edit_target_uv:
            tiles = get_udim_tiles(ps_ctx.ps_object, ps_scene_data.uv_edit_target_uv)
            udim_detected = len(tiles) > 1
        if udim_detected and ps_scene_data.uv_edit_udim_policy != 'AUTO':
            ps_scene_data.uv_edit_udim_policy = 'AUTO'
        if udim_detected:
            layout.label(text="UDIMs detected in target UV", icon='INFO')
        box = layout.box()
        box.label(text="Image Resolution", icon='IMAGE_DATA')
        row = box.row(align=True)
        row.prop(ps_scene_data, "uv_edit_inherit_image_sizes", text="Inherit Sizes")
        if ps_scene_data.uv_edit_inherit_image_sizes:
            row.label(text="Uses each image's original size")
        row = box.row(align=True)
        row.enabled = not ps_scene_data.uv_edit_inherit_image_sizes
        row.prop(ps_scene_data, "uv_edit_image_resolution", expand=True)
        if ps_scene_data.uv_edit_image_resolution == 'CUSTOM':
            col = box.column(align=True)
            col.enabled = not ps_scene_data.uv_edit_inherit_image_sizes
            col.prop(ps_scene_data, "uv_edit_image_width")
            col.prop(ps_scene_data, "uv_edit_image_height")
        scope_box = box.box()
        scope_box.label(text="Scope", icon='GROUP')
        row = scope_box.row(align=True)
        row.prop(ps_scene_data, "uv_edit_channel_scope", expand=True)
        if ps_scene_data.uv_edit_channel_scope == 'EXCLUDE':
            scope_box.prop(ps_scene_data, "uv_edit_exclude_channels")
        header, panel = box.panel("uv_edit_advanced", default_closed=True)
        header.label(text="Advanced", icon='PREFERENCES')
        if panel:
            panel.label(text="New Image Settings", icon='IMAGE_DATA')
            row = panel.row(align=True)
            scale_content(context, row, 1.1, 1.1)
            row.prop(ps_scene_data, "uv_edit_override_existing_images", text="Override Existing Images", toggle=True)
            image_box = panel.box()
            image_box.enabled = not ps_scene_data.uv_edit_override_existing_images
            row = image_box.row(align=True)
            row.prop(ps_scene_data, "uv_edit_use_float", text="Use Float")
            panel.prop(ps_scene_data, "uv_edit_udim_policy", text="UDIM Policy")
            panel.prop(ps_scene_data, "uv_edit_alpha_mode", text="Alpha")
            row = panel.row(align=True)
            row.prop(ps_scene_data, "uv_edit_bake_margin")
            row.prop(ps_scene_data, "uv_edit_bake_margin_type", text="")
            row = panel.row(align=True)
            row.prop(ps_scene_data, "uv_edit_keep_old_uv", text="Keep Old UV")

    def execute(self, context: Context):
        context.window.cursor_set('WAIT')
        context.scene.ps_scene_data.uv_edit_apply_in_progress = True
        result = super().execute(context)
        context.scene.ps_scene_data.uv_edit_apply_in_progress = False
        context.window.cursor_set('DEFAULT')
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        ps_scene_data.uv_edit_enabled = False
        ps_scene_data.uv_edit_checker_enabled = False
        ps_scene_data.uv_edit_checker_viewport_enabled = False
        update_active_image(context=context)
        _restore_uv_editor_image(ps_scene_data, context)
        _restore_previous_uvs(ps_scene_data, restore_render=False)
        _restore_checker_materials(ps_scene_data)
        list_material = bpy.data.materials.get(ps_scene_data.uv_edit_source_material_name) if ps_scene_data.uv_edit_source_material_name else ps_ctx.active_material
        objects_with_mat = _get_objects_with_material(context, list_material)
        if ps_ctx.ps_object and ps_ctx.ps_object not in objects_with_mat:
            objects_with_mat.append(ps_ctx.ps_object)
        objects_with_mat = [obj for obj in objects_with_mat if obj and obj.type == 'MESH']
        if not ps_scene_data.uv_edit_keep_old_uv:
            source_uv = (ps_scene_data.uv_edit_source_uv or "").strip()
            target_uv = (ps_scene_data.uv_edit_target_uv or "").strip()
            if source_uv and source_uv != target_uv:
                for obj in objects_with_mat:
                    if obj.data.uv_layers.get(source_uv) and len(obj.data.uv_layers) > 1:
                        obj.data.uv_layers.remove(obj.data.uv_layers.get(source_uv))
        _set_active_uv(objects_with_mat, ps_scene_data.uv_edit_target_uv)
        ps_scene_data.uv_edit_created_uvs.clear()
        return result

    def process_material(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        bake_material = ps_ctx.active_material
        ps_mat_data = ps_ctx.ps_mat_data
        active_channel = ps_ctx.active_channel
        source_name = ps_scene_data.uv_edit_source_material_name
        if source_name:
            source_material = bpy.data.materials.get(source_name)
            if source_material:
                bake_material = source_material
                ps_mat_data, _, active_channel, _ = parse_material(source_material)
        if not ps_mat_data or not ps_mat_data.groups:
            return True
        ps_scene_data = context.scene.ps_scene_data
        base_obj = ps_ctx.ps_object
        target_uv = ps_scene_data.uv_edit_target_uv
        if not target_uv:
            return True

        objects_with_mat = []
        if ps_scene_data.uv_edit_material_overrides:
            seen = set()
            for entry in ps_scene_data.uv_edit_material_overrides:
                override_obj = bpy.data.objects.get(entry.object_name)
                if override_obj and override_obj.name not in seen:
                    objects_with_mat.append(override_obj)
                    seen.add(override_obj.name)
        if not objects_with_mat:
            objects_with_mat = _get_objects_with_material(context, bake_material)
        if base_obj and base_obj not in objects_with_mat:
            objects_with_mat.append(base_obj)

        for sync_obj in objects_with_mat:
            uv_layer = _ensure_uv_map(sync_obj, target_uv)
            sync_obj.data.uv_layers.active = uv_layer
            uv_layer.active_render = True
            uv_layer.active_clone = True

        excluded = {
            name.strip()
            for name in ps_scene_data.uv_edit_exclude_channels.split(',')
            if name.strip()
        }

        def should_bake_channel(channel):
            if ps_scene_data.uv_edit_channel_scope == 'ACTIVE':
                return active_channel and channel == active_channel
            if ps_scene_data.uv_edit_channel_scope == 'EXCLUDE':
                return channel.name not in excluded
            return True

        def bake_all_layers(bake_context: Context):
            for group in ps_mat_data.groups:
                for channel in group.channels:
                    if not should_bake_channel(channel):
                        continue
                    for layer in channel.flattened_layers:
                        _bake_layer_to_uv(bake_context, channel, layer, target_uv, ps_scene_data, base_obj, bake_material, objects_for_uv=objects_with_mat)

        if ps_scene_data.uv_edit_material_overrides:
            _restore_checker_materials_temp(ps_scene_data)

        active_obj = base_obj if base_obj in objects_with_mat else (objects_with_mat[0] if objects_with_mat else None)
        if objects_with_mat:
            with context.temp_override(selected_objects=objects_with_mat, active_object=active_obj, object=active_obj):
                bake_all_layers(bpy.context)
        else:
            bake_all_layers(context)

        return True


class PAINTSYSTEM_OT_ExitUVEdit(PSContextMixin, Operator):
    bl_idname = "paint_system.exit_uv_edit"
    bl_label = "Exit UV Edit"
    bl_description = "Exit UV edit mode"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return context.scene and context.scene.ps_scene_data and context.scene.ps_scene_data.uv_edit_enabled

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        ps_scene_data.uv_edit_enabled = False
        ps_scene_data.uv_edit_checker_enabled = False
        ps_scene_data.uv_edit_checker_viewport_enabled = False
        _restore_uv_editor_image(ps_scene_data, context)
        _restore_previous_uvs(ps_scene_data, restore_render=True)
        _restore_checker_materials(ps_scene_data)
        _remove_created_uvs(ps_scene_data)
        update_active_image(context=context)
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_GrabActiveLayerUV,
    PAINTSYSTEM_OT_SyncUVNames,
    PAINTSYSTEM_OT_UpdateUVChecker,
    PAINTSYSTEM_OT_StartUVEdit,
    PAINTSYSTEM_OT_ClearUnusedUVs,
    PAINTSYSTEM_OT_ApplyUVEdit,
    PAINTSYSTEM_OT_ExitUVEdit,
)

def _get_registered_class(cls):
    class_name = getattr(cls, "__name__", None)
    if class_name:
        registered = getattr(bpy.types, class_name, None)
        if registered is not None:
            return registered
    bl_idname = getattr(cls, "bl_idname", None)
    if bl_idname:
        parts = bl_idname.split(".", 1)
        if len(parts) == 2:
            rna_name = f"{parts[0].upper()}_OT_{parts[1]}"
            return getattr(bpy.types, rna_name, None)
    return None


def _safe_unregister_class(cls):
    if cls is None:
        return
    try:
        bpy.utils.unregister_class(cls)
    except Exception:
        pass


def register():
    for cls in classes:
        _safe_unregister_class(_get_registered_class(cls))
        _safe_unregister_class(cls)
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError as e:
            if "already registered" not in str(e):
                raise

def unregister():
    for cls in reversed(classes):
        _safe_unregister_class(_get_registered_class(cls))
        _safe_unregister_class(cls)
