import bpy
from bpy.props import BoolProperty, EnumProperty
from bpy.types import Node, NodeTree, Operator
from bpy.utils import register_classes_factory
from bpy_extras.node_utils import connect_sockets, find_base_socket_type
from mathutils import Vector

from ..utils.version import is_newer_than

from ..paintsystem.graph.common import get_library_nodetree

from ..paintsystem.data import TEMPLATE_ENUM
from ..utils.nodes import (
    dissolve_nodes,
    find_connected_node,
    find_node,
    find_node_on_socket,
    find_nodes,
    get_material_output,
    transfer_connection,
    traverse_connected_nodes,
)
from ..utils import get_next_unique_name
from .common import (
    MultiMaterialOperator,
    PSContextMixin,
    PSUVOptionsMixin,
    get_icon,
    scale_content,
)
from ..paintsystem.list_manager import ListManager
from .operators_utils import redraw_panel


def create_basic_setup(mat_node_tree: NodeTree, group_node_tree: NodeTree, offset: Vector):
        node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
        node_group.node_tree = group_node_tree
        node_group.location = offset
        mix_shader = mat_node_tree.nodes.new(type='ShaderNodeMixShader')
        mix_shader.location = node_group.location + Vector((200, 0))
        transparent_node = mat_node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
        transparent_node.location = node_group.location + Vector((0, 100))
        connect_sockets(node_group.outputs[0], mix_shader.inputs[2])
        connect_sockets(node_group.outputs[1], mix_shader.inputs[0])
        connect_sockets(transparent_node.outputs[0], mix_shader.inputs[1])
        return node_group, mix_shader


def get_right_most_node(mat_node_tree: NodeTree) -> Node:
    right_most_node = None
    for node in mat_node_tree.nodes:
        if right_most_node is None:
            right_most_node = node
        elif node.location.x > right_most_node.location.x:
            right_most_node = node
    return right_most_node


def node_tree_has_complex_setup(node_tree: NodeTree) -> bool:
    material_output = get_material_output(node_tree)
    nodes = traverse_connected_nodes(material_output)
    if not nodes:
        return False
    if len(nodes) > 1:
        return True
    node = nodes.pop()
    if node.bl_idname == 'ShaderNodeBsdfPrincipled':
        return False
    return True


class PAINTSYSTEM_OT_NewGroup(PSContextMixin, PSUVOptionsMixin, MultiMaterialOperator):
    """Create a new group in the Paint System"""
    bl_idname = "paint_system.new_group"
    bl_label = "New Group"
    bl_options = {'REGISTER', 'UNDO'}
    
    def get_templates(self, context):
        # If cycles remove the PAINT_OVER template
        if "EEVEE" not in bpy.context.scene.render.engine:
            return [template for template in TEMPLATE_ENUM if template[0] != 'PAINT_OVER']
        return TEMPLATE_ENUM
    
    template: EnumProperty(
        name="Template",
        items=get_templates,
    )
    
    group_name: bpy.props.StringProperty(
        name="Group Name",
        description="Name of the new group",
        default="New Group",
    )

    use_alpha_blend: BoolProperty(
        name="Use Alpha Blend",
        description="Use alpha blend instead of alpha clip",
        default=False
    )

    disable_show_backface: BoolProperty(
        name="Disable Show Backface",
        description="Disable Show Backface",
        default=True
    )
    
    set_view_transform: BoolProperty(
        name="Use Standard View Transform",
        description="Use the standard view transform",
        default=True
    )
    
    pbr_add_color: BoolProperty(
        name="Add Color",
        description="Add a color to the PBR setup",
        default=True
    )
    
    pbr_add_roughness: BoolProperty(
        name="Add Roughness",
        description="Add a roughness to the PBR setup",
        default=False
    )
    
    pbr_add_metallic: BoolProperty(
        name="Add Metallic",
        description="Add a metallic to the PBR setup",
        default=False
    )
    
    pbr_add_normal: BoolProperty(
        name="Add Normal",
        description="Add a normal to the PBR setup",
        default=True
    )
    
    add_layers: BoolProperty(
        name="Add Layers",
        description="Add layers to the group",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        # See if there is any material slot on the active object
        if not ps_ctx.active_material:
            mat = bpy.data.materials.new(name=f"{self.group_name} Material")
            ps_ctx.ps_object.active_material = mat
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        mat.use_nodes = True
        
        # For version not higher than 4.2, use the old blend method
        if not is_newer_than(4, 2):
            mat.blend_method = 'HASHED'
        
        if self.use_alpha_blend:
            mat.blend_method = 'BLEND'
        if self.disable_show_backface:
            mat.show_transparent_back = False
            mat.use_backface_culling = True
        if self.template == 'BASIC' and self.set_view_transform:
            context.scene.view_settings.view_transform = 'Standard'
        
        node_tree = bpy.data.node_groups.new(name=f"Temp Group Name", type='ShaderNodeTree')
        new_group = ps_ctx.ps_mat_data.create_new_group(context, self.group_name, node_tree)
        new_group.template = self.template
        mat_node_tree = mat.node_tree
        
        ps_ctx = self.parse_context(context)
        if not self.add_layers:
            self.coord_type = "UV"
        self.store_coord_type(context)
        
        # Create Channels and layers and setup the group
        match self.template:
            case 'BASIC':
                channel = new_group.create_channel(context, channel_name='Color', channel_type='COLOR', use_alpha=True)
                if self.add_layers:
                    channel.create_layer(context, layer_name='Solid Color', layer_type='SOLID_COLOR')
                    channel.create_layer(context, layer_name='Image', layer_type='IMAGE', coord_type=self.coord_type, uv_map_name=self.uv_map_name)
                
                right_most_node = get_right_most_node(mat_node_tree)
                node_group, mix_shader = create_basic_setup(mat_node_tree, node_tree, right_most_node.location + Vector((right_most_node.width + 50, 0)) if right_most_node else Vector((0, 0)))
                mat_output = mat_node_tree.nodes.new(type='ShaderNodeOutputMaterial')
                mat_output.location = mix_shader.location + Vector((200, 0))
                mat_output.is_active_output = True
                connect_sockets(mix_shader.outputs[0], mat_output.inputs[0])
            case 'PBR':
                material_output = get_material_output(mat_node_tree)
                principled_node = find_node(mat_node_tree, {'bl_idname': 'ShaderNodeBsdfPrincipled'})
                if principled_node is None:
                    principled_node = mat_node_tree.nodes.new(type='ShaderNodeBsdfPrincipled')
                    principled_node.location = material_output.location + Vector((-200, 0))
                nodes = traverse_connected_nodes(principled_node)
                for node in nodes:
                    node.location = node.location + Vector((-200, 0))
                node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
                node_group.node_tree = node_tree
                node_group.location = principled_node.location + Vector((-200, 0))
                connect_sockets(principled_node.outputs[0], material_output.inputs[0])

                if self.pbr_add_color:
                    channel = new_group.create_channel(context, channel_name='Color', channel_type='COLOR', use_alpha=True)
                    color_connected = transfer_connection(mat_node_tree, principled_node.inputs['Base Color'], node_group.inputs['Color'])
                    transfer_connection(mat_node_tree, principled_node.inputs['Alpha'], node_group.inputs['Color Alpha'])
                    if self.add_layers:
                        if not color_connected:
                            channel.create_layer(context, layer_name='Solid Color', layer_type='SOLID_COLOR')
                        channel.create_layer(context, layer_name='Image', layer_type='IMAGE', coord_type=self.coord_type, uv_map_name=self.uv_map_name)
                    connect_sockets(node_group.outputs['Color'], principled_node.inputs['Base Color'])
                    connect_sockets(node_group.outputs['Color Alpha'], principled_node.inputs['Alpha'])

                if self.pbr_add_metallic:
                    channel = new_group.create_channel(context, channel_name='Metallic', channel_type='FLOAT', use_alpha=False, use_max_min=True, color_space='NONCOLOR')
                    transfer_connection(mat_node_tree, principled_node.inputs['Metallic'], node_group.inputs['Metallic'])
                    connect_sockets(node_group.outputs['Metallic'], principled_node.inputs['Metallic'])
                if self.pbr_add_roughness:
                    channel = new_group.create_channel(context, channel_name='Roughness', channel_type='FLOAT', use_alpha=False, use_max_min=True, color_space='NONCOLOR')
                    transfer_connection(mat_node_tree, principled_node.inputs['Roughness'], node_group.inputs['Roughness'])
                    connect_sockets(node_group.outputs['Roughness'], principled_node.inputs['Roughness'])
                if self.pbr_add_normal:
                    channel = new_group.create_channel(context, channel_name='Normal', channel_type='VECTOR', use_alpha=False, normalize_input=True, color_space='NONCOLOR')
                    normal_connected =transfer_connection(mat_node_tree, principled_node.inputs['Normal'], node_group.inputs['Normal'])
                    connect_sockets(node_group.outputs['Normal'], principled_node.inputs['Normal'])
                    if self.add_layers:
                        if not normal_connected:
                            channel.create_layer(context, layer_name='Object Normal', layer_type='GEOMETRY', geometry_type='OBJECT_NORMAL', normalize_normal=True)
                        channel.create_layer(context, layer_name='Image', layer_type='IMAGE', coord_type=self.coord_type, uv_map_name=self.uv_map_name)
                    norm_map_node = mat_node_tree.nodes.new(type='ShaderNodeNormalMap')
                    norm_map_node.location = node_group.location + Vector((0, -300))
                    norm_map_node.space = 'OBJECT'
                    connect_sockets(node_group.outputs['Normal'], norm_map_node.inputs[1])
                    connect_sockets(norm_map_node.outputs[0], principled_node.inputs['Normal'])
                ps_ctx = self.parse_context(context)
                ps_ctx.active_group.active_index = 0

            case 'PAINT_OVER':
                # Check if Engine is EEVEE
                if 'EEVEE' not in bpy.context.scene.render.engine:
                    self.report({'ERROR'}, "Paint Over is only supported in EEVEE")
                    return {'CANCELLED'}
                
                channel = new_group.create_channel(context, channel_name='Color', channel_type='COLOR', use_alpha=True)
                if self.add_layers:
                    channel.create_layer(context, layer_name='Image', layer_type='IMAGE', coord_type=self.coord_type, uv_map_name=self.uv_map_name)
                
                mat_output = get_material_output(mat_node_tree)
                
                node_links = mat_output.inputs[0].links
                if len(node_links) > 0:
                    link = node_links[0]
                    from_node = link.from_node
                    socket_type = find_base_socket_type(link.from_socket)
                    if socket_type == 'NodeSocketShader':
                        node_group, mix_shader = create_basic_setup(mat_node_tree, node_tree, from_node.location + Vector((from_node.width + 250, 0)))
                        shader_to_rgb = mat_node_tree.nodes.new(type='ShaderNodeShaderToRGB')
                        shader_to_rgb.location = from_node.location + Vector((from_node.width + 50, 0))
                        connect_sockets(shader_to_rgb.inputs[0], link.from_socket)
                        connect_sockets(node_group.inputs['Color'], shader_to_rgb.outputs[0])
                        # connect_sockets(node_group.inputs['Color Alpha'], shader_to_rgb.outputs[1])
                    else:
                        node_group, mix_shader = create_basic_setup(mat_node_tree, node_tree, from_node.location + Vector((from_node.width + 50, 0)))
                        connect_sockets(node_group.inputs['Color'], link.from_socket)
                    node_group.inputs['Color Alpha'].default_value = 1.0
                    mat_output.location = mix_shader.location + Vector((200, 0))
                    mat_output.is_active_output = True
                    connect_sockets(mix_shader.outputs[0], mat_output.inputs[0])
                        
            case 'NORMAL':
                channel = new_group.create_channel(context, channel_name='Normal', channel_type='VECTOR', use_alpha=False, normalize_input=True, color_space='NONCOLOR')
                if self.add_layers:
                    channel.create_layer(context, layer_name='Object Normal', layer_type='GEOMETRY', geometry_type='OBJECT_NORMAL', normalize_normal=True)
                    channel.create_layer(context, layer_name='Image', layer_type='IMAGE', coord_type=self.coord_type, uv_map_name=self.uv_map_name)
                right_most_node = get_right_most_node(mat_node_tree)
                node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
                node_group.node_tree = node_tree
                node_group.location = right_most_node.location + Vector((200, 0))
                norm_map_node = mat_node_tree.nodes.new(type='ShaderNodeNormalMap')
                norm_map_node.location = node_group.location + Vector((200, 0))
                norm_map_node.space = 'OBJECT'
                diffuse_node = mat_node_tree.nodes.new(type='ShaderNodeBsdfDiffuse')
                diffuse_node.location = norm_map_node.location + Vector((200, 0))
                mat_output = mat_node_tree.nodes.new(type='ShaderNodeOutputMaterial')
                mat_output.location = diffuse_node.location + Vector((200, 0))
                mat_output.is_active_output = True
                connect_sockets(node_group.outputs['Normal'], norm_map_node.inputs[1])
                connect_sockets(norm_map_node.outputs[0], diffuse_node.inputs['Normal'])
                connect_sockets(diffuse_node.outputs[0], mat_output.inputs[0])
            case _:
                channel = new_group.create_channel(context, channel_name='Color', channel_type='COLOR', use_alpha=True)
                if self.add_layers:
                    channel.create_layer(context, layer_name='Image', layer_type='IMAGE', coord_type=self.coord_type, uv_map_name=self.uv_map_name)
                right_most_node = get_right_most_node(mat_node_tree)
                node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
                node_group.node_tree = node_tree
                node_group.location = right_most_node.location + Vector((200, 0))
        redraw_panel(context)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        if ps_ctx.ps_mat_data and ps_ctx.ps_mat_data.groups:
            self.group_name = get_next_unique_name(self.group_name, [group.name for group in ps_ctx.ps_mat_data.groups])
        else:
            self.group_name = "New Group"
        self.get_coord_type(context)
        if ps_ctx.active_material and node_tree_has_complex_setup(ps_ctx.active_material.node_tree) and "EEVEE" in bpy.context.scene.render.engine:
            self.template = 'PAINT_OVER'
        if ps_ctx.ps_object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context):
        layout = self.layout
        self.multiple_objects_ui(layout, context)
        
        if "EEVEE" not in bpy.context.scene.render.engine:
            layout.label(text="Paint Over is not supported in this render engine", icon='ERROR')
        
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(self, "template", text="Template")
        
        if self.template in ['PBR']:
            box = layout.box()
            row = box.row()
            row.alignment = "CENTER"
            row.label(text="PBR Channels:", icon="MATERIAL")
            col = box.column(align=True)
            col.prop(self, "pbr_add_color", text="Color", icon_value=get_icon('color_socket'))
            col.prop(self, "pbr_add_metallic", text="Metallic", icon_value=get_icon('float_socket'))
            col.prop(self, "pbr_add_roughness", text="Roughness", icon_value=get_icon('float_socket'))
            col.prop(self, "pbr_add_normal", text="Normal", icon_value=get_icon('vector_socket'))
        
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(self, "add_layers", text="Add Template Layers", icon_value=get_icon('layer_add'))
        if self.add_layers:
            box = layout.box()
            self.select_coord_type_ui(box, context) 
        box = layout.box()
        row = box.row()
        row.alignment = "CENTER"
        row.label(text="Advanced Settings:", icon="TOOL_SETTINGS")
        split = box.split(factor=0.4)
        split.label(text="Group Name:")
        split.prop(self, "group_name", text="", icon='NODETREE')
        if self.template in ['BASIC']:
            box.prop(self, "use_alpha_blend", text="Use Smooth Alpha")
            if self.use_alpha_blend:
                warning_box = box.box()
                warning_box.alert = True
                row = warning_box.row()
                row.label(icon='ERROR')
                col = row.column(align=True)
                col.label(text="Warning: Smooth Alpha (Alpha Blend)")
                col.label(text="may cause sorting artifacts.")
            box.prop(self, "disable_show_backface",
                     text="Use Backface Culling")
        if self.template == 'BASIC' and context.scene.view_settings.view_transform != 'Standard':
            box.prop(self, "set_view_transform",
                     text="Use Standard View Transform")


class PAINTSYSTEM_OT_DeleteGroup(PSContextMixin, Operator):
    """Delete the selected group in the Paint System"""
    bl_idname = "paint_system.delete_group"
    bl_label = "Delete Paint System"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        active_group = ps_ctx.active_group
        node_tree = ps_ctx.active_material.node_tree
        match active_group.template:
            case 'BASIC':
                for group_node in find_nodes(node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree}):
                    nodes = [group_node]
                    shader_to_rgb = find_connected_node(group_node, {'bl_idname': 'ShaderNodeShaderToRGB'})
                    if shader_to_rgb:
                        nodes.append(shader_to_rgb)
                    mix_shader = find_connected_node(group_node, {'bl_idname': 'ShaderNodeMixShader'})
                    if mix_shader:
                        nodes.append(mix_shader)
                        transparent_node = find_connected_node(mix_shader, {'bl_idname': 'ShaderNodeBsdfTransparent'})
                        if transparent_node:
                            nodes.append(transparent_node)
                        mat_output = find_connected_node(mix_shader, {'bl_idname': 'ShaderNodeOutputMaterial'})
                        if mat_output:
                            nodes.append(mat_output)
                    dissolve_nodes(node_tree, nodes)
            case 'PBR':
                for group_node in find_nodes(node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree}):
                    nodes = [group_node]
                dissolve_nodes(active_group.node_tree, active_group.node_tree.nodes)
            case 'PAINT_OVER':
                dissolve_nodes(active_group.node_tree, active_group.node_tree.nodes)
            case 'NORMAL':
                dissolve_nodes(active_group.node_tree, active_group.node_tree.nodes)
        lm = ListManager(ps_mat_data, 'groups', ps_mat_data, 'active_index')
        lm.remove_active_item()
        redraw_panel(context)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # return context.window_manager.invoke_confirm(self, event, title="Delete Group", icon='ERROR', message="Are you sure you want to delete Paint System?")
        return context.window_manager.invoke_props_dialog(self, title="Delete Group", width=300)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.label(text=f"Are you sure you want to delete '{ps_ctx.active_group.name}' Group?")


class PAINTSYSTEM_OT_MoveGroup(PSContextMixin, MultiMaterialOperator):
    """Move the selected group in the Paint System"""
    bl_idname = "paint_system.move_group"
    bl_label = "Move Group"
    bl_options = {'REGISTER', 'UNDO'}

    direction: bpy.props.EnumProperty(
        name="Direction",
        items=[
            ('UP', "Up", "Move group up"),
            ('DOWN', "Down", "Move group down")
        ],
        default='UP'
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return bool(ps_ctx.ps_mat_data and ps_ctx.ps_mat_data.active_index >= 0)

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        lm = ListManager(ps_mat_data, 'groups', ps_mat_data, 'active_index')
        lm.move_active_down() if self.direction == 'DOWN' else lm.move_active_up()
        redraw_panel(context)
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_NewGroup,
    PAINTSYSTEM_OT_DeleteGroup,
    PAINTSYSTEM_OT_MoveGroup,
)

register, unregister = register_classes_factory(classes)    