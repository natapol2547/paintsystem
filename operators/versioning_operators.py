import bpy
from bpy.types import Operator, Object, NodeTree, Node
from bpy.utils import register_classes_factory

from ..paintsystem.data import (
    LegacyPaintSystemContextParser,
    PSContextMixin,
    LegacyPaintSystemLayer,
    LAYER_TYPE_ENUM,
)
from ..paintsystem.graph.nodetree_builder import capture_node_state, apply_node_state
from ..utils.nodes import find_nodes
from bpy_extras.node_utils import connect_sockets

pid_mapping = {
    "name": "name",
    "enabled": "enabled",
    "image": "image",
    "clip": "is_clip",
    "lock_alpha": "lock_alpha",
    "lock_layer": "lock_layer",
    "node_tree": "node_tree",
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

def get_layer_adjustment_type(legacy_layer: LegacyPaintSystemLayer) -> str:
    adjustment_type = None
    for node in legacy_layer.node_tree.nodes:
        if node.label == "Adjustment":
            adjustment_type = node.type
            break
    return adjustment_type

def get_layer_gradient_type(legacy_layer: LegacyPaintSystemLayer) -> str:
    for node in legacy_layer.node_tree.nodes:
        if node.bl_idname == "ShaderNodeSeparateXYZ":
            return "LINEAR"
    return "RADIAL"

def get_layer_empty_object(legacy_layer: LegacyPaintSystemLayer) -> Object:
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
    bl_label = "Update Paint System Data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        legacy_ps_ctx = LegacyPaintSystemContextParser(context)
        legacy_groups = legacy_ps_ctx.get_material_settings().groups
        ps_ctx = self.parse_context(context)
        warning_messages = []
        for legacy_group in legacy_groups:
            bpy.ops.paint_system.new_group('EXEC_DEFAULT', group_name=legacy_group.name, add_layers=False, template='NONE')
            ps_ctx = self.parse_context(context)
            for legacy_layer in legacy_group.items:
                if legacy_layer.type not in [layer[0] for layer in LAYER_TYPE_ENUM]:
                    print(f"Skipping layer {legacy_layer.name} of type {legacy_layer.type} because it is not supported anymore")
                    warning_messages.append(f"Skipping layer {legacy_layer.name} of type {legacy_layer.type} because it is not supported anymore")
                    continue
                new_layer = ps_ctx.active_channel.create_layer(context, legacy_layer.name, legacy_layer.type)
                
                # Apply legacy layer properties
                for prop in legacy_layer.bl_rna.properties:
                    pid = getattr(prop, 'identifier', '')
                    if not pid or getattr(prop, 'is_readonly', False):
                        continue
                    if pid in {"name", "node_tree", "type"} or pid not in pid_mapping:
                        continue
                    setattr(new_layer, pid_mapping[pid], getattr(legacy_layer, pid))
                if legacy_layer.type == "ADJUSTMENT":
                    new_layer.adjustment_type = get_layer_adjustment_type(legacy_layer)
                if legacy_layer.type == "GRADIENT":
                    new_layer.gradient_type = get_layer_gradient_type(legacy_layer)
                    new_layer.empty_object = get_layer_empty_object(legacy_layer)
                if legacy_layer.type == "IMAGE":
                    uv_map_node = legacy_ps_ctx.find_node(legacy_layer.node_tree, {'bl_idname': 'ShaderNodeUVMap'})
                    if uv_map_node:
                        uv_map_name = uv_map_node.uv_map
                        new_layer.coord_type = "UV"
                        new_layer.uv_map_name = uv_map_name
                if legacy_layer.type == "NODE_GROUP":
                    new_layer.custom_color_input = 0
                    new_layer.custom_alpha_input = 1
                    new_layer.custom_color_output = 0
                    new_layer.custom_alpha_output = 1
                new_layer.update_node_tree(context)
                # Apply node values
                # Copy rgb node value
                if legacy_layer.type == "SOLID_COLOR":
                    rgb_node = find_node_by_name(legacy_layer.node_tree, 'RGB')
                    if rgb_node:
                        new_layer.find_node('rgb').outputs[0].default_value = rgb_node.outputs[0].default_value
                if legacy_layer.type == "ADJUSTMENT":
                    state = capture_node_state(legacy_ps_ctx.find_node(legacy_layer.node_tree, {'label': 'Adjustment'}))
                    apply_node_state(new_layer.find_node('adjustment'), state)
                if legacy_layer.type == "GRADIENT":
                    state = capture_node_state(legacy_ps_ctx.find_node(legacy_layer.node_tree, {'label': 'Gradient Color Ramp'}))
                    apply_node_state(new_layer.find_node('gradient'), state)
                
                # Copy opacity node value
                opacity_node = find_node_by_name(legacy_layer.node_tree, 'Opacity')
                if opacity_node:
                    new_layer.pre_mix_node.inputs['Opacity'].default_value = opacity_node.inputs[0].default_value
                # refresh paintsystem context
            ps_ctx.active_channel.update_node_tree(context)
            ps_ctx.active_group.update_node_tree(context)
            
            # Remap the node tree
            # Workaround to remap alpha socket name
            for item in legacy_group.node_tree.interface.items_tree:
                if item.item_type == 'SOCKET' and item.name == "Alpha":
                    item.name = "Color Alpha"
            # Find node group
            legacy_group_nodes = find_nodes(ps_ctx.active_material.node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': legacy_group.node_tree})
            for node_group in legacy_group_nodes:
                # Get links
                input_links = []
                output_links = []
                for input_socket in node_group.inputs[:]:
                    for link in input_socket.links:
                        input_links.append(link)
                for output_socket in node_group.outputs[:]:
                    for link in output_socket.links:
                        output_links.append(link)
                node_group.node_tree = ps_ctx.active_group.node_tree
                for link in input_links:
                    connect_sockets(node_group.inputs[link.to_socket.name], link.from_socket)
                for link in output_links:
                    connect_sockets(link.to_socket, node_group.outputs[link.from_socket.name])
        legacy_groups.clear()
        if warning_messages:
            self.report({'WARNING'}, "\n".join(warning_messages))
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_UpdatePaintSystemData,
)

register, unregister = register_classes_factory(classes)