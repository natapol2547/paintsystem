import bpy
from bpy.types import Panel, Operator
from bpy.utils import register_classes_factory

from .common import PSContextMixin, execute_operator_in_area, wait_for_redraw
from ..utils.nodes import find_node, is_in_nodetree


class PAINTSYSTEM_OT_InspectLayerNodeTree(PSContextMixin, Operator):
    """Inspect the layer's node tree"""
    bl_idname = "paint_system.inspect_layer_node_tree"
    bl_label = "Inspect Layer Node Tree"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Inspect the layer's node tree"
    
    layer_id: bpy.props.IntProperty()
    channel_name: bpy.props.StringProperty()
    
    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'NODE_EDITOR'
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        
        if not ps_ctx.active_material or not ps_ctx.active_group:
            return {'CANCELLED'}
        
        # Find the channel
        channel = None
        for ch in ps_ctx.active_group.channels:
            if ch.name == self.channel_name:
                channel = ch
                break
        
        if not channel or not channel.node_tree:
            return {'CANCELLED'}
        
        # Find the layer
        layer = channel.get_item_by_id(self.layer_id)
        if not layer:
            return {'CANCELLED'}
        
        linked_layer = layer.get_layer_data()
        if not linked_layer or not linked_layer.node_tree:
            return {'CANCELLED'}
        
        # First, navigate to the material's main node tree
        context.space_data.path.start(ps_ctx.active_material.node_tree)
        
        # Find the group node for the PS group in the material
        group_node = find_node(ps_ctx.active_material.node_tree, {
            'bl_idname': 'ShaderNodeGroup',
            'node_tree': ps_ctx.active_group.node_tree
        }, connected_to_output=False)
        
        if group_node:
            # Enter the group to view its contents
            context.space_data.path.append(group_node.node_tree, node=group_node)
        
        # Now find the channel node within the group
        channel_node = find_node(ps_ctx.active_group.node_tree, {
            'bl_idname': 'ShaderNodeGroup',
            'node_tree': channel.node_tree
        }, connected_to_output=False)
        
        if channel_node:
            # Enter the channel to view its contents
            context.space_data.path.append(channel_node.node_tree, node=channel_node)
        
        # Find the layer's node group in the channel's node tree
        node_to_select = find_node(channel.node_tree, {
            'bl_idname': 'ShaderNodeGroup',
            'node_tree': linked_layer.node_tree
        }, connected_to_output=False)
        
        if not node_to_select:
            self.report({'WARNING'}, f"Could not find node for layer '{linked_layer.name}'")
            return {'CANCELLED'}
        
        # Enter the layer's node group to view its contents
        context.space_data.path.append(node_to_select.node_tree, node=node_to_select)
        
        # Frame the view to show all nodes
        execute_operator_in_area(context.area, 'node.view_all')
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_ExitAllNodeGroups(Operator):
    """Exit all node groups and return to material node tree"""
    bl_idname = "paint_system.exit_all_node_groups"
    bl_label = "Exit All Groups"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Exit all node groups and return to the material's main node tree"
    
    @classmethod
    def poll(cls, context):
        return is_in_nodetree(context)
    
    def execute(self, context):
        # Clear the path to return to the root node tree
        context.space_data.path.clear()
        
        return {'FINISHED'}


classes = [
    PAINTSYSTEM_OT_InspectLayerNodeTree,
    PAINTSYSTEM_OT_ExitAllNodeGroups,
]

register, unregister = register_classes_factory(classes)
