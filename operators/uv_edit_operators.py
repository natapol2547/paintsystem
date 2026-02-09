import bpy
import json
from bpy.types import Context, Operator
from bpy.props import BoolProperty
from bpy.utils import register_classes_factory

from .common import PSContextMixin, MultiMaterialOperator, DEFAULT_PS_UV_MAP_NAME
from ..paintsystem.data import create_ps_image, get_udim_tiles, set_layer_blend_type, get_layer_blend_type
from ..paintsystem.data import update_active_image
from ..utils import get_next_unique_name
from ..utils.nodes import get_material_output

CHECKER_IMAGE_NAME = "PS_UV_Checker"
DEFAULT_UV_EDIT_NAME = "PS_UV_Edit"
CHECKER_TEX_NODE_NAME = "PS_UV_Checker_Tex"
CHECKER_UV_NODE_NAME = "PS_UV_Checker_UV"


def _ensure_uv_map(obj: bpy.types.Object, uv_name: str) -> bpy.types.MeshUVLoopLayer | None:
    if not obj or obj.type != 'MESH' or not uv_name:
        return None
    uv_layers = obj.data.uv_layers
    if not uv_layers.get(uv_name):
        uv_layers.new(name=uv_name)
    uv_layers.active = uv_layers[uv_name]
    return uv_layers[uv_name]


def _get_target_uv_name(ps_scene_data, obj: bpy.types.Object) -> str:
    target_name = (ps_scene_data.uv_edit_target_uv or "").strip()
    if ps_scene_data.uv_edit_target_mode == 'EXISTING':
        if not target_name and obj and obj.data.uv_layers.active:
            target_name = obj.data.uv_layers.active.name
    else:
        if not target_name:
            target_name = DEFAULT_UV_EDIT_NAME
        if obj and obj.type == 'MESH':
            target_name = get_next_unique_name(target_name, [uv.name for uv in obj.data.uv_layers])
    ps_scene_data.uv_edit_target_uv = target_name
    return target_name


def _get_source_uv_name(ps_scene_data, obj: bpy.types.Object) -> str:
    source_name = (ps_scene_data.uv_edit_source_uv or "").strip()
    if not source_name and obj and obj.data.uv_layers.active:
        source_name = obj.data.uv_layers.active.name
    return source_name


def _copy_uv_data(source_uv, target_uv):
    if not source_uv or not target_uv:
        return
    if len(source_uv.data) != len(target_uv.data):
        return
    for idx, loop in enumerate(source_uv.data):
        target_uv.data[idx].uv = loop.uv


def _apply_uv_unwrap(context: Context, obj: bpy.types.Object, uv_name: str, ps_scene_data):
    if not obj or obj.type != 'MESH':
        return
    selection = list(context.selected_objects)
    active = context.view_layer.objects.active
    for sel in selection:
        if sel != obj:
            sel.select_set(False)
    obj.select_set(True)
    context.view_layer.objects.active = obj
    original_mode = str(obj.mode)
    bpy.ops.object.mode_set(mode='EDIT')
    obj.update_from_editmode()
    bpy.ops.mesh.select_all(action='SELECT')
    obj.data.uv_layers.active = obj.data.uv_layers[uv_name]
    match ps_scene_data.uv_edit_new_uv_method:
        case 'UNWRAP_ANGLE':
            bpy.ops.uv.unwrap(
                method='ANGLE_BASED',
                fill_holes=ps_scene_data.uv_edit_unwrap_fill_holes,
                correct_aspect=ps_scene_data.uv_edit_unwrap_correct_aspect,
                use_subsurf_data=ps_scene_data.uv_edit_unwrap_use_subsurf,
                margin=ps_scene_data.uv_edit_unwrap_margin
            )
        case 'UNWRAP_CONFORMAL':
            bpy.ops.uv.unwrap(
                method='CONFORMAL',
                fill_holes=ps_scene_data.uv_edit_unwrap_fill_holes,
                correct_aspect=ps_scene_data.uv_edit_unwrap_correct_aspect,
                use_subsurf_data=ps_scene_data.uv_edit_unwrap_use_subsurf,
                margin=ps_scene_data.uv_edit_unwrap_margin
            )
        case 'MIN_STRETCH':
            bpy.ops.uv.minimize_stretch(
                fill_holes=ps_scene_data.uv_edit_unwrap_fill_holes,
                blend=ps_scene_data.uv_edit_min_stretch_blend,
                iterations=ps_scene_data.uv_edit_min_stretch_iterations
            )
        case 'LIGHTMAP':
            bpy.ops.uv.lightmap_pack(
                PREF_CONTEXT='ALL_FACES',
                PREF_PACK_IN_ONE=ps_scene_data.uv_edit_lightmap_pack_in_one,
                PREF_NEW_UVLAYER=False,
                PREF_APPLY_IMAGE=False,
                PREF_MARGIN_DIV=ps_scene_data.uv_edit_lightmap_margin,
                PREF_BOX_DIV=ps_scene_data.uv_edit_lightmap_quality
            )
        case _:
            bpy.ops.uv.smart_project(
                angle_limit=ps_scene_data.uv_edit_smart_angle_limit,
                island_margin=ps_scene_data.uv_edit_smart_island_margin,
                area_weight=ps_scene_data.uv_edit_smart_area_weight,
                correct_aspect=ps_scene_data.uv_edit_smart_correct_aspect,
                scale_to_bounds=ps_scene_data.uv_edit_smart_scale_to_bounds
            )
    bpy.ops.object.mode_set(mode=original_mode)
    for sel in selection:
        sel.select_set(True)
    context.view_layer.objects.active = active


def _get_checker_image(ps_scene_data) -> bpy.types.Image:
    size = int(ps_scene_data.uv_edit_checker_resolution)
    image = bpy.data.images.get(CHECKER_IMAGE_NAME)
    if not image:
        image = bpy.data.images.new(CHECKER_IMAGE_NAME, width=size, height=size, alpha=False)
    if image.size[0] != size or image.size[1] != size:
        image.scale(size, size)
    image.generated_type = ps_scene_data.uv_edit_checker_type
    return image


def _apply_checker_to_uv_editors(context: Context, image: bpy.types.Image):
    pass


def _set_uv_checker_on_material(mat: bpy.types.Material, image: bpy.types.Image, target_uv: str):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return
    output = get_material_output(mat.node_tree)
    if not output:
        return
    surface_input = output.inputs.get("Surface")
    if not surface_input:
        return

    prev_link = None
    if surface_input.is_linked:
        link = surface_input.links[0]
        prev_link = {
            "node": link.from_node.name,
            "socket": link.from_socket.name
        }
        mat.node_tree.links.remove(link)
    mat["ps_uv_edit_prev_link"] = json.dumps(prev_link) if prev_link else ""

    tex_node = mat.node_tree.nodes.get(CHECKER_TEX_NODE_NAME)
    if not tex_node:
        tex_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex_node.name = CHECKER_TEX_NODE_NAME
        tex_node.label = "UV Checker"
    uv_node = mat.node_tree.nodes.get(CHECKER_UV_NODE_NAME)
    if not uv_node:
        uv_node = mat.node_tree.nodes.new("ShaderNodeUVMap")
        uv_node.name = CHECKER_UV_NODE_NAME
        uv_node.label = "UV Checker UV"

    uv_node.uv_map = target_uv
    tex_node.image = image
    tex_node.interpolation = "Closest"

    for link in list(mat.node_tree.links):
        if link.to_node == tex_node and link.to_socket == tex_node.inputs.get("Vector"):
            mat.node_tree.links.remove(link)
    if uv_node.outputs.get("UV") and tex_node.inputs.get("Vector"):
        mat.node_tree.links.new(uv_node.outputs["UV"], tex_node.inputs["Vector"])

    for link in list(surface_input.links):
        mat.node_tree.links.remove(link)
    if tex_node.outputs.get("Color"):
        mat.node_tree.links.new(tex_node.outputs["Color"], surface_input)


def _restore_uv_checker_on_material(mat: bpy.types.Material):
    if not mat or not mat.use_nodes or not mat.node_tree:
        return
    output = get_material_output(mat.node_tree)
    if not output:
        return
    surface_input = output.inputs.get("Surface")
    if not surface_input:
        return

    for link in list(surface_input.links):
        mat.node_tree.links.remove(link)

    tex_node = mat.node_tree.nodes.get(CHECKER_TEX_NODE_NAME)
    uv_node = mat.node_tree.nodes.get(CHECKER_UV_NODE_NAME)
    if tex_node:
        mat.node_tree.nodes.remove(tex_node)
    if uv_node:
        mat.node_tree.nodes.remove(uv_node)

    prev_data = mat.get("ps_uv_edit_prev_link", "")
    if prev_data:
        try:
            link_data = json.loads(prev_data)
        except Exception:
            link_data = None
        if link_data and link_data.get("node") and link_data.get("socket"):
            from_node = mat.node_tree.nodes.get(link_data["node"])
            if from_node and from_node.outputs.get(link_data["socket"]):
                mat.node_tree.links.new(from_node.outputs[link_data["socket"]], surface_input)
    if "ps_uv_edit_prev_link" in mat:
        del mat["ps_uv_edit_prev_link"]


def _get_objects_with_material(context: Context, material: bpy.types.Material) -> list[bpy.types.Object]:
    objects = []
    if not context.scene or not material:
        return objects
    for obj in context.scene.objects:
        if obj.type == 'MESH' and material.name in obj.data.materials:
            objects.append(obj)
    return objects


def _collect_used_uvs_from_material(mat: bpy.types.Material) -> set[str]:
    used_uvs = set()
    if not mat or not hasattr(mat, "ps_mat_data") or not mat.ps_mat_data:
        return used_uvs
    for group in mat.ps_mat_data.groups:
        for channel in group.channels:
            if channel.tangent_uv_map:
                used_uvs.add(channel.tangent_uv_map)
            if channel.bake_uv_map:
                used_uvs.add(channel.bake_uv_map)
            for layer in channel.flattened_layers:
                if not layer or layer.type == 'FOLDER':
                    continue
                if getattr(layer, 'coord_type', None) == 'UV' and layer.uv_map_name:
                    used_uvs.add(layer.uv_map_name)
                elif getattr(layer, 'coord_type', None) == 'AUTO':
                    used_uvs.add(DEFAULT_PS_UV_MAP_NAME)
                if getattr(layer, 'parallax_space', None) == 'UV' and layer.parallax_uv_map_name:
                    used_uvs.add(layer.parallax_uv_map_name)
    return used_uvs


def _get_image_size(ps_scene_data) -> tuple[int, int]:
    if ps_scene_data.uv_edit_image_resolution != 'CUSTOM':
        size = int(ps_scene_data.uv_edit_image_resolution)
        return size, size
    return int(ps_scene_data.uv_edit_image_width), int(ps_scene_data.uv_edit_image_height)


def _bake_layer_to_uv(context: Context, channel, layer, target_uv: str, ps_scene_data, obj: bpy.types.Object, active_material: bpy.types.Material):
    if not layer or layer.type == 'FOLDER':
        return
    if not active_material:
        return

    to_be_enabled_layers = []
    for other in channel.layers:
        if other.enabled and other != layer and other.type != 'FOLDER':
            to_be_enabled_layers.append(other)
            other.enabled = False

    original_blend_mode = get_layer_blend_type(layer)
    set_layer_blend_type(layer, 'MIX')
    orig_is_clip = bool(layer.is_clip)
    if layer.is_clip:
        layer.is_clip = False

    if layer.type == 'IMAGE' and layer.image:
        new_image = layer.image.copy()
        new_name = get_next_unique_name(f"{layer.image.name}_UVEdit", [img.name for img in bpy.data.images])
        new_image.name = new_name
    else:
        width, height = _get_image_size(ps_scene_data)
        use_udim_tiles = False
        if ps_scene_data.uv_edit_use_udim_tiles and obj:
            use_udim_tiles = get_udim_tiles(obj, target_uv) != {1001}
        image_name = get_next_unique_name(f"{layer.name}_UVEdit", [img.name for img in bpy.data.images])
        if use_udim_tiles and obj:
            new_image = create_ps_image(
                name=image_name,
                width=width,
                height=height,
                use_udim_tiles=True,
                objects=[obj],
                uv_layer_name=target_uv,
                use_float=ps_scene_data.uv_edit_use_float
            )
        else:
            new_image = create_ps_image(
                name=image_name,
                width=width,
                height=height,
                use_udim_tiles=False,
                use_float=ps_scene_data.uv_edit_use_float
            )

    channel.bake(context, active_material, new_image, target_uv, use_group_tree=False, force_alpha=True)

    if layer.is_clip != orig_is_clip:
        layer.is_clip = orig_is_clip
    set_layer_blend_type(layer, original_blend_mode)
    layer.coord_type = 'UV'
    layer.uv_map_name = target_uv
    layer.image = new_image
    layer.type = 'IMAGE'

    for other in to_be_enabled_layers:
        other.enabled = True


class PAINTSYSTEM_OT_GrabActiveLayerUV(PSContextMixin, Operator):
    bl_idname = "paint_system.grab_active_layer_uv"
    bl_label = "Grab Current Layer UV"
    bl_description = "Grab the active layer UV and store it for the UV edit workflow"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        active_layer = ps_ctx.active_layer
        if not active_layer:
            self.report({'ERROR'}, "No active layer found.")
            return {'CANCELLED'}
        if active_layer.coord_type == 'AUTO':
            ps_scene_data.uv_edit_source_uv = DEFAULT_PS_UV_MAP_NAME
        elif active_layer.coord_type == 'UV':
            ps_scene_data.uv_edit_source_uv = active_layer.uv_map_name
        else:
            self.report({'WARNING'}, "Active layer is not using UV coordinates.")
            return {'CANCELLED'}
        return {'FINISHED'}


class PAINTSYSTEM_OT_SyncUVNames(PSContextMixin, Operator):
    bl_idname = "paint_system.sync_uv_names"
    bl_label = "Sync UV Names"
    bl_description = "Sync all selected objects to use the same active UV name"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        target_name = (ps_scene_data.uv_edit_source_uv or "").strip()
        if not target_name:
            active_uv = ps_ctx.ps_object.data.uv_layers.active if ps_ctx.ps_object else None
            if not active_uv:
                self.report({'ERROR'}, "No active UV map found.")
                return {'CANCELLED'}
            target_name = active_uv.name
        for obj in ps_ctx.ps_objects or []:
            if obj.type != 'MESH' or not obj.data.uv_layers:
                continue
            uv_layers = obj.data.uv_layers
            if uv_layers.get(target_name):
                uv_layers.active = uv_layers[target_name]
            else:
                uv_layers.active.name = target_name
                uv_layers.active = uv_layers[target_name]
        ps_scene_data.uv_edit_source_uv = target_name
        return {'FINISHED'}


class PAINTSYSTEM_OT_UpdateUVChecker(PSContextMixin, Operator):
    bl_idname = "paint_system.update_uv_checker"
    bl_label = "Update UV Checker"
    bl_description = "Update the UV checker preview in UV Editor"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        image = _get_checker_image(ps_scene_data)
        target_uv = _get_target_uv_name(ps_scene_data, ps_ctx.ps_object)
        if ps_ctx.active_material:
            ps_scene_data.uv_edit_checker_material = ps_ctx.active_material.name
            _set_uv_checker_on_material(ps_ctx.active_material, image, target_uv)
        return {'FINISHED'}


class PAINTSYSTEM_OT_StartUVEdit(PSContextMixin, Operator):
    bl_idname = "paint_system.start_uv_edit"
    bl_label = "Start UV Edit"
    bl_description = "Enable UV edit mode and set the target UV"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        if not ps_ctx.ps_object:
            self.report({'ERROR'}, "No active paint system object found.")
            return {'CANCELLED'}
        ps_scene_data = context.scene.ps_scene_data
        target_uv = _get_target_uv_name(ps_scene_data, ps_ctx.ps_object)
        source_uv = _get_source_uv_name(ps_scene_data, ps_ctx.ps_object)
        for obj in ps_ctx.ps_objects or []:
            if ps_scene_data.uv_edit_target_mode == 'EXISTING':
                _ensure_uv_map(obj, target_uv)
            else:
                _ensure_uv_map(obj, target_uv)
                if ps_scene_data.uv_edit_new_uv_method == 'COPY':
                    src_uv = obj.data.uv_layers.get(source_uv) if source_uv else None
                    dst_uv = obj.data.uv_layers.get(target_uv)
                    _copy_uv_data(src_uv, dst_uv)
                else:
                    _apply_uv_unwrap(context, obj, target_uv, ps_scene_data)
        ps_scene_data.uv_edit_enabled = True
        update_active_image(context=context)
        image = _get_checker_image(ps_scene_data)
        target_uv = _get_target_uv_name(ps_scene_data, ps_ctx.ps_object)
        if ps_ctx.active_material:
            ps_scene_data.uv_edit_checker_material = ps_ctx.active_material.name
            _set_uv_checker_on_material(ps_ctx.active_material, image, target_uv)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ClearUnusedUVs(PSContextMixin, Operator):
    bl_idname = "paint_system.clear_unused_uvs"
    bl_label = "Clear Unused UVs"
    bl_description = "Remove UV maps not used by Paint System layers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context: Context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data
        for obj in ps_ctx.ps_objects or []:
            if obj.type != 'MESH' or not obj.data.uv_layers:
                continue
            used_uvs = set()
            for mat in obj.data.materials:
                used_uvs.update(_collect_used_uvs_from_material(mat))
            if ps_scene_data.uv_edit_source_uv:
                used_uvs.add(ps_scene_data.uv_edit_source_uv)
            if ps_scene_data.uv_edit_target_uv:
                used_uvs.add(ps_scene_data.uv_edit_target_uv)
            if obj.data.uv_layers.active:
                used_uvs.add(obj.data.uv_layers.active.name)
            if not used_uvs:
                continue
            for uv_layer in list(obj.data.uv_layers):
                if uv_layer.name not in used_uvs:
                    obj.data.uv_layers.remove(uv_layer)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ApplyUVEdit(PSContextMixin, MultiMaterialOperator, Operator):
    bl_idname = "paint_system.apply_uv_edit"
    bl_label = "Apply UV Edit"
    bl_description = "Bake textures to the target UV and update all layers"
    bl_options = {'REGISTER', 'UNDO'}

    multiple_materials: BoolProperty(
        name="Multiple Materials",
        description="Run the operator on multiple materials",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return context.scene and context.scene.ps_scene_data and context.scene.ps_scene_data.uv_edit_enabled

    def invoke(self, context: Context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context: Context):
        ps_scene_data = context.scene.ps_scene_data
        layout = self.layout
        layout.label(text="Image Output", icon='IMAGE_DATA')
        row = layout.row(align=True)
        row.prop(ps_scene_data, "uv_edit_image_resolution", expand=True)
        if ps_scene_data.uv_edit_image_resolution == 'CUSTOM':
            col = layout.column(align=True)
            col.prop(ps_scene_data, "uv_edit_image_width")
            col.prop(ps_scene_data, "uv_edit_image_height")
        layout.prop(ps_scene_data, "uv_edit_use_udim_tiles")
        layout.prop(ps_scene_data, "uv_edit_use_float")
        layout.prop(ps_scene_data, "uv_edit_keep_old_uv")

    def execute(self, context: Context):
        context.window.cursor_set('WAIT')
        result = super().execute(context)
        context.window.cursor_set('DEFAULT')
        ps_scene_data = context.scene.ps_scene_data
        ps_scene_data.uv_edit_enabled = False
        update_active_image(context=context)
        ps_ctx = self.parse_context(context)
        material_name = ps_scene_data.uv_edit_checker_material
        if material_name:
            mat = bpy.data.materials.get(material_name)
            if mat:
                _restore_uv_checker_on_material(mat)
        ps_scene_data.uv_edit_checker_material = ""
        return result

    def process_material(self, context: Context):
        ps_ctx = self.parse_context(context)
        if not ps_ctx.active_group:
            return True
        ps_scene_data = context.scene.ps_scene_data
        target_uv = _get_target_uv_name(ps_scene_data, ps_ctx.ps_object)
        _ensure_uv_map(ps_ctx.ps_object, target_uv)

        objects_with_mat = _get_objects_with_material(context, ps_ctx.active_material)
        if ps_ctx.ps_object and ps_ctx.ps_object not in objects_with_mat:
            objects_with_mat.append(ps_ctx.ps_object)

        if objects_with_mat:
            with context.temp_override(selected_objects=objects_with_mat, active_object=ps_ctx.ps_object, object=ps_ctx.ps_object):
                for channel in ps_ctx.active_group.channels:
                    for layer in channel.flattened_layers:
                        _bake_layer_to_uv(bpy.context, channel, layer, target_uv, ps_scene_data, ps_ctx.ps_object, ps_ctx.active_material)
        else:
            for channel in ps_ctx.active_group.channels:
                for layer in channel.flattened_layers:
                    _bake_layer_to_uv(context, channel, layer, target_uv, ps_scene_data, ps_ctx.ps_object, ps_ctx.active_material)

        if not ps_scene_data.uv_edit_keep_old_uv:
            source_uv = (ps_scene_data.uv_edit_source_uv or "").strip()
            if ps_ctx.ps_object and source_uv and source_uv != target_uv and ps_ctx.ps_object.data.uv_layers.get(source_uv):
                ps_ctx.ps_object.data.uv_layers.remove(ps_ctx.ps_object.data.uv_layers[source_uv])

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
        ps_scene_data = context.scene.ps_scene_data
        ps_scene_data.uv_edit_enabled = False
        material_name = ps_scene_data.uv_edit_checker_material
        if material_name:
            mat = bpy.data.materials.get(material_name)
            if mat:
                _restore_uv_checker_on_material(mat)
        ps_scene_data.uv_edit_checker_material = ""
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

register, unregister = register_classes_factory(classes)
