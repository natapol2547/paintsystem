import bpy
from bpy.types import Panel, Operator
from bpy.utils import register_classes_factory

from .common import PSContextMixin, get_icon
from ..utils.nodes import find_node


class NODE_PT_PaintSystemGroup(PSContextMixin, Panel):
    """Paint System panel in Shader Editor for renaming groups and viewing layers"""
    bl_label = "Paint System"
    bl_idname = "NODE_PT_paint_system_group"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Paint System"
    
    @classmethod
    def poll(cls, context):
        """Show panel only when object has Paint System data"""
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None and context.space_data.tree_type == 'ShaderNodeTree'
    
    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        
        if not ps_ctx.active_group:
            return
            
        # Group name section
        box = layout.box()
        col = box.column(align=True)
        row = col.row(align=True)
        row.label(text="Group Name:", icon='OUTLINER_OB_GROUP_INSTANCE')
        row.operator("paint_system.exit_all_node_groups", text="", icon='SCREEN_BACK')
        col.prop(ps_ctx.active_group, "name", text="")
        
        # Channels and Layers section
        if ps_ctx.active_group.channels:
            layout.separator()
            
            for channel in ps_ctx.active_group.channels:
                # Channel header
                box = layout.box()
                row = box.row(align=True)
                row.label(text=channel.name, icon='NODE_TEXTURE')
                
                # Show layers for this channel in the same order as the N panel
                flattened = channel.flattened_layers
                if flattened:
                    col = box.column(align=True)
                    for layer in flattened:
                        level = channel.get_item_level_from_id(layer.id)
                        self.draw_layer_row(col, layer, channel, ps_ctx, context, level=level)
    
    def draw_layer_row(self, layout, layer, channel, ps_ctx, context, level=0):
        """Draw a single layer row with indentation for hierarchy"""
        linked_layer = layer.get_layer_data()
        if not linked_layer:
            return
        
        row = layout.row(align=True)
        
        # Indentation for hierarchy
        for i in range(level):
            if i == level - 1:
                row.label(icon_value=get_icon('folder_indent'))
            else:
                row.label(icon='BLANK1')
        
        # Layer icon and name
        if linked_layer.type == 'FOLDER':
            icon = 'FILE_FOLDER'
        elif linked_layer.type == 'IMAGE':
            icon = 'IMAGE_DATA'
        elif linked_layer.type == 'SOLID_COLOR':
            icon = 'COLOR'
        else:
            icon = 'NODE'
        
        row.label(text=linked_layer.name, icon=icon)
        
        # Select node button - only for non-folder layers with node trees
        if linked_layer.type != 'FOLDER' and linked_layer.node_tree and ps_ctx.active_material:
            op = row.operator("paint_system.select_layer_node_in_shader", text="", icon='RESTRICT_SELECT_OFF')
            op.layer_id = layer.id
            op.channel_name = channel.name


class PAINTSYSTEM_OT_SelectLayerNodeInShader(PSContextMixin, Operator):
    """Select and focus the layer's node in the Shader Editor"""
    bl_idname = "paint_system.select_layer_node_in_shader"
    bl_label = "Select Layer Node"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Select and focus this layer's node in the Shader Editor"
    
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
        
        # Select all nodes to show the full layer graph
        for node in linked_layer.node_tree.nodes:
            node.select = True
        
        # Frame the view to show all nodes
        bpy.ops.node.view_all()
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_ExitAllNodeGroups(Operator):
    """Exit all node groups and return to material node tree"""
    bl_idname = "paint_system.exit_all_node_groups"
    bl_label = "Exit All Groups"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Exit all node groups and return to the material's main node tree"
    
    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'NODE_EDITOR' and len(context.space_data.path) > 1
    
    def execute(self, context):
        # Clear the path to return to the root node tree
        context.space_data.path.clear()
        
        # Frame all nodes
        bpy.ops.node.view_all()
        
        return {'FINISHED'}


classes = [
    NODE_PT_PaintSystemGroup,
    PAINTSYSTEM_OT_SelectLayerNodeInShader,
    PAINTSYSTEM_OT_ExitAllNodeGroups,
]

register, unregister = register_classes_factory(classes)
