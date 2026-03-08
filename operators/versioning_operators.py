import bpy
from bpy.types import Operator, Object, NodeTree, Node
from bpy.utils import register_classes_factory

from ..paintsystem.version_check import get_latest_version, get_current_version, reset_version_cache
from .common import PSContextMixin

from ..paintsystem.data import (
    LegacyPaintSystemContextParser,
    LegacyPaintSystemLayer,
    LegacyLayer,
    PSLayerData,
    LAYER_TYPE_ENUM,
)
from ..paintsystem.graph.nodetree_builder import capture_node_state, apply_node_state
from ..utils.nodes import find_nodes
from bpy_extras.node_utils import connect_sockets
from ..utils.version import is_online
from ..preferences import addon_package
import addon_utils
from ..utils.logging import get_logger

logger = get_logger(__name__)

pid_mapping = {
    "name": "name",
    "enabled": "enabled",
    "image": "image",
    "clip": "is_clip",
    "lock_alpha": "lock_alpha",
    "lock_layer": "lock_layer",
    "external_image": "external_image",
    "expanded": "is_expanded",
}

type_mapping = {
    "FOLDER": "FOLDER",
    "IMAGE": "IMAGE",
    "SOLID_COLOR": "SOLID_COLOR",
    "ATTRIBUTE": "ATTRIBUTE",
    "ADJUSTMENT": "ADJUSTMENT",
    "SHADER": "SHADER",
    "NODE_GROUP": "NODE_GROUP",
    "GRADIENT": "GRADIENT",
}

def get_legacy_layer_adjustment_type(legacy_layer: LegacyPaintSystemLayer) -> str:
    adjustment_type = None
    for node in legacy_layer.node_tree.nodes:
        if node.label == "Adjustment":
            adjustment_type = node.type
            break
    return adjustment_type

def get_legacy_layer_gradient_type(legacy_layer: LegacyPaintSystemLayer) -> str:
    for node in legacy_layer.node_tree.nodes:
        if node.bl_idname == "ShaderNodeSeparateXYZ":
            return "LINEAR"
    return "RADIAL"

def get_legacy_layer_empty_object(legacy_layer: LegacyPaintSystemLayer) -> Object:
    tex_coord_node = legacy_layer.node_tree.nodes["Texture Coordinate"]
    if tex_coord_node:
        return tex_coord_node.object
    return None

def find_node_by_name(node_tree: NodeTree, name: str) -> Node:
    for node in node_tree.nodes:
        if node.name == name:
            return node
    return None

class PAINTSYSTEM_OT_UpdatePaintSystemData(PSContextMixin, Operator):
    bl_idname = "paint_system.update_paint_system_data"
    bl_description = "Update Paint System Data"
    bl_label = "Update Paint System Data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        legacy_ps_ctx = LegacyPaintSystemContextParser(context)
        legacy_groups = legacy_ps_ctx.get_material_settings().groups
        ps_ctx = self.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        warning_messages = []
        for legacy_group in legacy_groups:
            # Workaround to remap alpha socket name
            for item in legacy_group.node_tree.interface.items_tree:
                if item.item_type == 'SOCKET' and item.name == "Alpha":
                    item.name = "Color Alpha"
            legacy_group_nodes = find_nodes(ps_ctx.active_material.node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': legacy_group.node_tree})
            relink_map = {}
            for node_group in legacy_group_nodes:
                # Snapshot link endpoints so we don't hold onto link objects that Blender may free
                input_links = []
                output_links = []
                for input_socket in node_group.inputs[:]:
                    for link in input_socket.links:
                        input_links.append({
                            'from_socket': link.from_socket,
                            'dest_name': getattr(input_socket, "name", None),
                        })
                for output_socket in node_group.outputs[:]:
                    for link in output_socket.links:
                        output_links.append({
                            'to_socket': link.to_socket,
                            'src_name': getattr(link.from_socket, "name", None),
                        })
                relink_map[node_group] = {
                    'input_links': input_links,
                    'output_links': output_links,
                }
            new_group = ps_mat_data.create_new_group(context, legacy_group.name, legacy_group.node_tree)
            new_channel = new_group.create_channel(context, channel_name='Color', channel_type='COLOR', use_alpha=True)
            ps_ctx = self.parse_context(context)
            for legacy_layer in legacy_group.items:
                if legacy_layer.type not in [layer[0] for layer in LAYER_TYPE_ENUM]:
                    logger.warning(f"Skipping layer {legacy_layer.name} of type {legacy_layer.type} because it is not supported anymore")
                    warning_messages.append(f"Skipping layer {legacy_layer.name} of type {legacy_layer.type} because it is not supported anymore")
                    continue
                new_layer = new_channel.create_layer(context, legacy_layer.name, legacy_layer.type)
                
                # Apply legacy layer properties
                for prop in legacy_layer.bl_rna.properties:
                    pid = getattr(prop, 'identifier', '')
                    if not pid or getattr(prop, 'is_readonly', False):
                        continue
                    if pid in {"name", "node_tree", "type"} or pid not in pid_mapping:
                        continue
                    setattr(new_layer, pid_mapping[pid], getattr(legacy_layer, pid))
                if legacy_layer.type == "ADJUSTMENT":
                    new_layer.adjustment_type = get_legacy_layer_adjustment_type(legacy_layer)
                if legacy_layer.type == "GRADIENT":
                    new_layer.gradient_type = get_legacy_layer_gradient_type(legacy_layer)
                    new_layer.empty_object = get_legacy_layer_empty_object(legacy_layer)
                if legacy_layer.type == "IMAGE":
                    uv_map_node = legacy_ps_ctx.find_node(legacy_layer.node_tree, {'bl_idname': 'ShaderNodeUVMap'})
                    if uv_map_node:
                        uv_map_name = uv_map_node.uv_map
                        new_layer.coord_type = "UV"
                        new_layer.uv_map_name = uv_map_name
                new_layer.update_node_tree(context)
                if legacy_layer.type == "NODE_GROUP":
                    new_layer.custom_node_tree = legacy_layer.node_tree

                    def _pick_enum(items, target, fallback="_NONE_"):
                        for ident, name, *_ in items:
                            if ident == target or name == target:
                                return ident
                        return fallback if items else fallback

                    # Inputs (include _NONE_)
                    input_items = new_layer.get_inputs_enum(context)
                    if input_items:
                        new_layer.color_input_name = _pick_enum(input_items, "Color", fallback=input_items[0][0])
                        new_layer.alpha_input_name = _pick_enum(input_items, "Color Alpha", fallback=input_items[0][0])

                    # Outputs (may lack alpha; use first available if target missing)
                    try:
                        color_out_items = new_layer.get_color_enum(context)
                    except TypeError:
                        color_out_items = []
                    if color_out_items:
                        new_layer.color_output_name = _pick_enum(color_out_items, "Color", fallback=color_out_items[0][0])

                    try:
                        alpha_out_items = new_layer.get_alpha_enum(context)
                    except TypeError:
                        alpha_out_items = []
                    if alpha_out_items:
                        new_layer.alpha_output_name = _pick_enum(alpha_out_items, "Color Alpha", fallback=alpha_out_items[0][0])

                # Preserve blend mode if possible
                legacy_mix = next(
                    (n for n in legacy_layer.node_tree.nodes
                     if getattr(n, "bl_idname", "") == "ShaderNodeMix" and getattr(n, "data_type", "") == "RGBA"),
                    None,
                ) if legacy_layer.node_tree else None
                if legacy_mix and hasattr(new_layer, "blend_mode"):
                    new_layer.blend_mode = getattr(legacy_mix, "blend_type", new_layer.blend_mode)
                # Apply node values
                # Copy rgb node value
                if legacy_layer.type == "SOLID_COLOR":
                    rgb_node = find_node_by_name(legacy_layer.node_tree, 'RGB')
                    if rgb_node:
                        new_layer.source_node.outputs[0].default_value = rgb_node.outputs[0].default_value
                if legacy_layer.type == "ADJUSTMENT":
                    state = capture_node_state(legacy_ps_ctx.find_node(legacy_layer.node_tree, {'label': 'Adjustment'}))
                    apply_node_state(new_layer.source_node, state)
                if legacy_layer.type == "GRADIENT":
                    state = capture_node_state(legacy_ps_ctx.find_node(legacy_layer.node_tree, {'label': 'Gradient Color Ramp'}))
                    apply_node_state(new_layer.source_node, state)
                
                # Copy opacity node value
                opacity_node = find_node_by_name(legacy_layer.node_tree, 'Opacity')
                if opacity_node:
                    new_layer.pre_mix_node.inputs['Opacity'].default_value = opacity_node.inputs[0].default_value
                # refresh paintsystem context
            new_channel.update_node_tree(context)
            new_group.update_node_tree(context)
            
            # Remap the node tree
            # Find node group
            for node_group, links in relink_map.items():
                node_group.node_tree = new_group.node_tree
                for link in links['input_links']:
                    dest_name = link.get('dest_name')
                    from_socket = link.get('from_socket')
                    if dest_name and dest_name in node_group.inputs and from_socket:
                        connect_sockets(from_socket, node_group.inputs[dest_name])
                for link in links['output_links']:
                    src_name = link.get('src_name')
                    to_socket = link.get('to_socket')
                    if src_name and src_name in node_group.outputs and to_socket:
                        connect_sockets(node_group.outputs[src_name], to_socket)
        legacy_groups.clear()
        if warning_messages:
            self.report({'WARNING'}, "\n".join(warning_messages))
        return {'FINISHED'}


class PAINTSYSTEM_OT_CheckForUpdates(PSContextMixin, Operator):
    bl_idname = "paint_system.check_for_updates"
    bl_label = "Check for Updates"
    bl_description = "Check for Updates"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if ps_ctx.ps_settings is None:
            return False
        return is_online() and ps_ctx.ps_settings.update_state != 'LOADING'
    
    def execute(self, context):
        # Delete version cache
        reset_version_cache()
        # Check for updates
        get_latest_version()
        return {'FINISHED'}


class PAINTSYSTEM_OT_OpenExtensionPreferences(Operator):
    bl_idname = "paint_system.open_extension_preferences"
    bl_label = "Open Extension Preferences"
    bl_description = "Open Extension Preferences"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        bpy.ops.screen.userpref_show()
        bpy.context.preferences.active_section = 'EXTENSIONS'
        bpy.context.window_manager.extension_search = 'Paint System'
        modules = addon_utils.modules()
        mod = None
        for mod in modules:
            if mod.bl_info.get("name") == "Paint System":
                mod = mod
                break
        if mod is None:
            logger.error("Paint System not found")
            return {'FINISHED'}
        bl_info = addon_utils.module_bl_info(mod)
        show_expanded = bl_info["show_expanded"]
        if not show_expanded:
            bpy.ops.preferences.addon_expand(module=addon_package())
        return {'FINISHED'}


class PAINTSYSTEM_OT_DismissUpdate(PSContextMixin, Operator):
    bl_idname = "paint_system.dismiss_update"
    bl_label = "Dismiss Update"
    bl_description = "Dismiss Update"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.ps_settings.update_state = 'UNAVAILABLE'
        return {'FINISHED'}

ASSET_PROPERTIES = [
    'uid', 'layer_name', 'type', 'image', 'correct_image_aspect',
    'custom_node_tree', 'color_input_name', 'alpha_input_name',
    'color_output_name', 'alpha_output_name', 'coord_type', 'uv_map_name',
    'adjustment_type', 'gradient_type', 'texture_type', 'geometry_type',
    'normalize_normal', 'empty_object', 'projection_position',
    'projection_rotation', 'projection_fov', 'projection_space',
    'use_decal_depth_clip', 'parallax_space', 'parallax_uv_map_name',
    'edit_external_mode', 'external_image',
]


def migrate_legacy_layer_to_ps_layer_data(legacy_layer: "LegacyLayer", node_tree: "NodeTree") -> list[str]:
    """Copy asset properties from a LegacyLayer to NodeTree.ps_layer_data.
    
    Returns list of property names that failed to migrate.
    """
    ps_data: PSLayerData = node_tree.ps_layer_data
    
    failed = []
    ps_data.auto_update_node_tree = False
    for pid in ASSET_PROPERTIES:
        try:
            setattr(ps_data, pid, getattr(legacy_layer, pid))
        except Exception:
            failed.append(pid)
    
    for action in legacy_layer.actions:
        new_action = ps_data.actions.add()
        for prop in action.bl_rna.properties:
            pid = getattr(prop, 'identifier', '')
            if not pid or getattr(prop, 'is_readonly', False):
                continue
            try:
                setattr(new_action, pid, getattr(action, pid))
            except Exception:
                pass
    ps_data.active_action_index = legacy_layer.active_action_index
    
    for mask in legacy_layer.masks:
        new_mask = ps_data.masks.add()
        for prop in mask.bl_rna.properties:
            pid = getattr(prop, 'identifier', '')
            if not pid or getattr(prop, 'is_readonly', False):
                continue
            try:
                setattr(new_mask, pid, getattr(mask, pid))
            except Exception:
                pass
    ps_data.active_mask_index = legacy_layer.active_mask_index
    ps_data.auto_update_node_tree = True
    
    if failed:
        logger.warning(f"Failed to migrate properties {failed} for {legacy_layer.name}")
    return failed


class PAINTSYSTEM_OT_MigrateV2ToV3(PSContextMixin, Operator):
    bl_idname = "paint_system.migrate_v2_to_v3"
    bl_label = "Update to Version 3"
    bl_description = "Migrate Paint System data from V2 to V3 (NodeTree-based layer data)"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        for mat in bpy.data.materials:
            if hasattr(mat, 'ps_mat_data') and mat.ps_mat_data.groups:
                if mat.ps_mat_data.data_version < 3:
                    return True
        return False

    def execute(self, context):
        migrated_count = 0
        failed_materials = []
        linked_tree_map = {}

        for mat in bpy.data.materials:
            if not hasattr(mat, 'ps_mat_data') or not mat.ps_mat_data.groups:
                continue
            if mat.ps_mat_data.data_version >= 3:
                continue

            try:
                for group in mat.ps_mat_data.groups:
                    for channel in group.channels:
                        for legacy_layer in channel.layers:
                            if legacy_layer.is_linked:
                                share_key = (
                                    legacy_layer.linked_material.name if legacy_layer.linked_material else "",
                                    legacy_layer.linked_layer_uid
                                )
                            else:
                                share_key = (mat.name, legacy_layer.uid)

                            if share_key in linked_tree_map:
                                target_tree = linked_tree_map[share_key]
                            else:
                                layer_data = legacy_layer.get_layer_data()
                                if layer_data is None:
                                    logger.warning(f"Skipping layer {legacy_layer.name}: could not resolve source data")
                                    continue
                                target_tree = layer_data.node_tree
                                if not target_tree:
                                    target_tree = bpy.data.node_groups.new(
                                        name=f"PS_Layer ({layer_data.name})",
                                        type='ShaderNodeTree'
                                    )
                                migrate_legacy_layer_to_ps_layer_data(layer_data, target_tree)
                                try:
                                    target_tree.ps_layer_data.blend_mode = legacy_layer.blend_mode
                                except Exception:
                                    pass
                                linked_tree_map[share_key] = target_tree

                            new_layer = channel.v3_layers.add()
                            new_layer.id = legacy_layer.id
                            new_layer.name = legacy_layer.name
                            new_layer.parent_id = legacy_layer.parent_id
                            new_layer.order = legacy_layer.order
                            new_layer.uid = legacy_layer.uid
                            new_layer.layer_name = legacy_layer.layer_name
                            new_layer.layer_tree = target_tree
                            new_layer.auto_update_node_tree = False
                            new_layer.enabled = legacy_layer.enabled
                            new_layer.is_clip = legacy_layer.is_clip
                            new_layer.lock_layer = legacy_layer.lock_layer
                            new_layer.lock_alpha = legacy_layer.lock_alpha
                            new_layer.is_expanded = legacy_layer.is_expanded
                            new_layer.auto_update_node_tree = True
                            new_layer.update_node_tree(context)

                        max_id = max((l.id for l in channel.v3_layers), default=0)
                        channel.next_id = max(channel.next_id, max_id + 1)
                        channel.layers.clear()
                        channel.update_node_tree(context)

                    group.update_node_tree(context)

                mat.ps_mat_data.data_version = 3
                migrated_count += 1
            except Exception as e:
                logger.error(f"Failed to migrate material {mat.name}: {e}")
                failed_materials.append(mat.name)

        if failed_materials:
            self.report({'WARNING'}, f"Migration completed with errors on: {', '.join(failed_materials)}")
        else:
            self.report({'INFO'}, f"Successfully migrated {migrated_count} material(s) to V3")
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_UpdatePaintSystemData,
    PAINTSYSTEM_OT_CheckForUpdates,
    PAINTSYSTEM_OT_OpenExtensionPreferences,
    PAINTSYSTEM_OT_DismissUpdate,
    PAINTSYSTEM_OT_MigrateV2ToV3,
)

register, unregister = register_classes_factory(classes)