import bpy
from bpy.types import Material

from .graph.common import LIBRARY_NODE_TREE_VERSIONS, get_library_nodetree
from .graph.basic_layers import get_layer_version_for_type
from .graph.nodetree_builder import get_nodetree_version
from .data import get_legacy_global_layer, Layer, Group, Channel
from typing import TypedDict
from .data import get_legacy_global_layer

class LayerParent(TypedDict):
    mat: Material
    group: Group
    channel: Channel

def get_layer_parent_map() -> dict[Layer, LayerParent]:
    layer_parent_map = {}
    for mat in bpy.data.materials:
        if hasattr(mat, 'ps_mat_data'):
            for group in mat.ps_mat_data.groups:
                for channel in group.channels:
                    for layer in channel.layers:
                        layer_parent_map[layer] = LayerParent(mat=mat, group=group, channel=channel)
    return layer_parent_map

def migrate_global_layer_data(layer_parent_map: dict[Layer, LayerParent]):
    seen_global_layers_map = {}
    for layer, layer_parent in layer_parent_map.items():
        has_migrated_global_layer = False
        if layer.name and not layer.layer_name: # data from global layer is not copied to layer
            global_layer = get_legacy_global_layer(layer)
            if global_layer:
                layer.auto_update_node_tree = False
                print(f"Migrating global layer data ({global_layer.name}) to layer data ({layer.name}) ({layer.layer_name})")
                has_migrated_global_layer = True
                layer.layer_name = layer.name
                layer.uid = global_layer.name
                if global_layer.name not in seen_global_layers_map:
                    seen_global_layers_map[global_layer.name] = [mat, global_layer]
                    for prop in global_layer.bl_rna.properties:
                        pid = getattr(prop, 'identifier', '')
                        if not pid or getattr(prop, 'is_readonly', False):
                            continue
                        if pid in {"layer_name"}:
                            continue
                        if pid in {"name", "uid"}:
                            continue
                        setattr(layer, pid, getattr(global_layer, pid))
                else:
                    # as linked layer, properties will not be copied
                    print(f"Layer {layer.name} is linked to {global_layer.name}")
                    mat, global_layer = seen_global_layers_map[global_layer.name]
                    layer.linked_layer_uid = global_layer.name
                    layer.linked_material = mat
                layer.auto_update_node_tree = True
                layer.update_node_tree(bpy.context)
        if has_migrated_global_layer:
            layer_parent.channel.update_node_tree(bpy.context)

def migrate_blend_mode(layer_parent_map: dict[Layer, LayerParent]):
    for layer, layer_parent in layer_parent_map.items():
        layer = layer.get_layer_data()
        mix_node = layer.mix_node
        blend_mode = "MIX"
        if mix_node:
            blend_mode = str(mix_node.blend_type)
        if blend_mode != layer.blend_mode and layer.blend_mode != "PASSTHROUGH":
            print(f"Layer {layer.name} has blend mode {blend_mode} but {layer.blend_mode} is set")
            layer.blend_mode = blend_mode

def migrate_source_node(layer_parent_map: dict[Layer, LayerParent]):
    for layer, layer_parent in layer_parent_map.items():
        # Update every source node to have label 'source'
        source_node = layer.source_node
        if source_node and source_node.name != "source":
            source_node.name = "source"
            source_node.label = "source"

def migrate_socket_names(layer_parent_map: dict[Layer, LayerParent]):
    for layer, layer_parent in layer_parent_map.items():
        # If type == NODE_GROUP, update the color and alpha input and output sockets
        if layer.type == "NODE_GROUP" and layer.custom_node_tree:
            # Get the color and alpha input and output sockets names from the custom node tree
            custom_node_tree: bpy.types.NodeTree = layer.custom_node_tree
            items = custom_node_tree.interface.items_tree
            inputs = [item for item in items if item.item_type == 'SOCKET' and item.in_out == 'INPUT']
            outputs = [item for item in items if item.item_type == 'SOCKET' and item.in_out == 'OUTPUT']
            layer.auto_update_node_tree = False
            if layer.custom_color_input != -1:
                layer.color_input_name = inputs[layer.custom_color_input].name
                layer.custom_color_input = -1
            if layer.custom_alpha_input != -1:
                layer.alpha_input_name = inputs[layer.custom_alpha_input].name
                layer.custom_alpha_input = -1
            if layer.custom_color_output != -1:
                layer.color_output_name = outputs[layer.custom_color_output].name
                layer.custom_color_output = -1
            if layer.custom_alpha_output != -1:
                layer.alpha_output_name = outputs[layer.custom_alpha_output].name
                layer.custom_alpha_output = -1
            layer.auto_update_node_tree = True
            layer.update_node_tree(bpy.context)

def update_layer_version(layer_parent_map: dict[Layer, LayerParent]):
    for layer, layer_parent in layer_parent_map.items():
        # Updating layer to the target version
        target_version = get_layer_version_for_type(layer.type)
        if get_nodetree_version(layer.node_tree) != target_version:
            print(f"Updating layer {layer.name} to version {target_version}")
            try:
                layer.update_node_tree(bpy.context)
            except Exception as e:
                print(f"Error updating layer {layer.name}: {e}")

def update_layer_name(layer_parent_map: dict[Layer, LayerParent]):
    for layer, layer_parent in layer_parent_map.items():
        if layer.layer_name != layer.name:
            layer.name = layer.layer_name

def update_library_nodetree_version():
    ps_nodetrees = []
    for node_tree in bpy.data.node_groups:
        if node_tree.name.startswith(".PS"):
            ps_nodetrees.append(node_tree)
    for node_tree in ps_nodetrees:
        print(f"Checking library nodetree {node_tree.name}")
        target_version = LIBRARY_NODE_TREE_VERSIONS.get(node_tree.name, 0)
        if get_nodetree_version(node_tree) != target_version:
            print(f"Updating library nodetree {node_tree.name} to version {target_version}")
            get_library_nodetree(node_tree.name, force_append=True)