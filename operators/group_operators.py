import bpy
from bpy.props import BoolProperty, EnumProperty, IntProperty
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
    bl_label = "New Paint System"
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
        name="Setup Name",
        description="Name of the new setup",
        default="",
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
        return ps_ctx.ps_object is not None and context.mode == 'OBJECT'

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        # See if there is any material slot on the active object
        if not ps_ctx.active_material:
            # Use the chosen group name (defaults to object name) for the material
            mat = bpy.data.materials.new(name=self.group_name)
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
                # Check if principled_node is not connected to anything
                if len(principled_node.outputs[0].links) == 0:
                    connect_sockets(principled_node.outputs[0], material_output.inputs[0])
                if self.pbr_add_color:
                    new_group.create_channel_template(context, "COLOR", add_layers=self.add_layers)
                if self.pbr_add_metallic:
                    new_group.create_channel_template(context, "METALLIC", add_layers=self.add_layers)
                if self.pbr_add_roughness:
                    new_group.create_channel_template(context, "ROUGHNESS", add_layers=self.add_layers)
                if self.pbr_add_normal:
                    new_group.create_channel_template(context, "NORMAL", add_layers=self.add_layers)
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
                right_most_node = get_right_most_node(mat_node_tree)
                node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
                node_group.node_tree = node_tree
                node_group.location = right_most_node.location + Vector((200, 0))
                diffuse_node = mat_node_tree.nodes.new(type='ShaderNodeBsdfDiffuse')
                diffuse_node.location = node_group.location + Vector((200, 0))
                mat_output = mat_node_tree.nodes.new(type='ShaderNodeOutputMaterial')
                mat_output.location = diffuse_node.location + Vector((200, 0))
                mat_output.is_active_output = True
                connect_sockets(diffuse_node.outputs[0], mat_output.inputs[0])
                new_group.create_channel_template(context, "NORMAL", add_layers=self.add_layers)
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
        # Default name: use existing material name if available, otherwise use object name
        if ps_ctx.active_material:
            base_name = ps_ctx.active_material.name
        elif ps_ctx.ps_object:
            base_name = ps_ctx.ps_object.name
        else:
            base_name = "New Paint System"
        
        if ps_ctx.ps_mat_data and ps_ctx.ps_mat_data.groups:
            self.group_name = get_next_unique_name(base_name, [group.name for group in ps_ctx.ps_mat_data.groups])
        else:
            self.group_name = base_name
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
        
        # Setup name above the "Add Template Layers" toggle
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(self, "group_name", text="Setup Name", icon='NODETREE')
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(self, "add_layers", text="Add Template Layers", icon_value=get_icon('layer_add'))
        if self.add_layers:
            box = layout.box()
            self.select_coord_type_ui(box, context) 
        box = layout.box()
        header, panel = box.panel("advanced_settings_panel", default_closed=True)
        header.label(text="Advanced Settings:", icon="TOOL_SETTINGS")
        if panel:
            # Group name moved above; keep advanced options here
            if self.template in ['BASIC']:
                panel.prop(self, "use_alpha_blend", text="Use Smooth Alpha")
                if self.use_alpha_blend:
                    warning_box = panel.box()
                    warning_box.alert = True
                    row = warning_box.row()
                    row.label(icon='ERROR')
                    col = row.column(align=True)
                    col.label(text="Warning: Smooth Alpha (Alpha Blend)")
                    col.label(text="may cause transparency artifacts.")
                panel.prop(self, "disable_show_backface",
                        text="Use Backface Culling")
            if self.template == 'BASIC' and context.scene.view_settings.view_transform != 'Standard':
                panel.prop(self, "set_view_transform",
                        text="Use Standard View Transform")

def find_basic_setup_nodes(group_node: Node) -> list[Node]:
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
    return nodes


class PAINTSYSTEM_OT_DeleteGroup(PSContextMixin, Operator):
    """Delete the selected group in the Paint System"""
    bl_idname = "paint_system.delete_group"
    bl_label = "Delete Paint System"
    bl_options = {'REGISTER', 'UNDO'}
    
    bake_channels: BoolProperty(
        name="Bake Channels",
        description="Bake the channels",
        default=False,
        options={'SKIP_SAVE'}
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        active_group = ps_ctx.active_group
        node_tree = ps_ctx.active_material.node_tree
        if self.bake_channels:
            pass
        for group_node in find_nodes(node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree}):
            match active_group.template:
                case 'BASIC':
                    nodes = find_basic_setup_nodes(group_node)
                    dissolve_nodes(node_tree, nodes)
                case 'PBR':
                    nodes = [group_node]
                    dissolve_nodes(node_tree, nodes)
                case 'PAINT_OVER':
                    nodes = find_basic_setup_nodes(group_node)
                    dissolve_nodes(node_tree, nodes)
                case 'NORMAL':
                    nodes = [group_node]
                    dissolve_nodes(node_tree, nodes)
        lm = ListManager(ps_mat_data, 'groups', ps_mat_data, 'active_index')
        lm.remove_active_item()
        redraw_panel(context)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Delete Group", width=300)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        box = layout.box()
        col = box.column(align=True)
        col.alert = True
        col.label(text="Danger Zone!", icon="ERROR")
        col.label(text=f"Are you sure you want to delete Paint System?", icon="BLANK1")


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


class PAINTSYSTEM_OT_ConvertMaterialToPS(PSContextMixin, PSUVOptionsMixin, MultiMaterialOperator):
    """Convert an existing material to Paint System by replacing Principled BSDF with paint system groups"""
    bl_idname = "paint_system.convert_material_to_ps"
    bl_label = "Convert Material to Paint System"
    bl_options = {'REGISTER', 'UNDO'}
    
    group_name: bpy.props.StringProperty(
        name="Setup Name",
        description="Name of the new paint system setup",
        default="Paint System",
    )
    
    setup_color: BoolProperty(
        name="Setup Color Channel",
        description="Set up Color channel from Base Color input",
        default=True
    )
    
    setup_metallic: BoolProperty(
        name="Setup Metallic Channel",
        description="Set up Metallic channel",
        default=True
    )
    
    setup_roughness: BoolProperty(
        name="Setup Roughness Channel",
        description="Set up Roughness channel",
        default=True
    )
    
    setup_normal: BoolProperty(
        name="Setup Normal Channel",
        description="Set up Normal channel",
        default=True
    )
    
    setup_emission: BoolProperty(
        name="Setup Emission Channel",
        description="Set up Emission channel",
        default=False
    )
    
    add_layers: BoolProperty(
        name="Add Layers From Inputs",
        description="Create layers from existing input connections",
        default=True
    )
    
    image_mode: EnumProperty(
        name="Image Mode",
        description="How to handle images when creating layers",
        items=[
            ('CONVERT', "Convert to Layers", "Use existing images directly in layers"),
            ('DUPLICATE', "Duplicate to Layer", "Create copies of images to preserve originals"),
        ],
        default='CONVERT'
    )
    
    apply_to_all_objects: BoolProperty(
        name="Apply to All Objects",
        description="Apply to all objects using the same material",
        default=True
    )
    
    detected_objects_count: IntProperty(
        name="Detected Objects Count",
        description="Number of objects detected with the same material",
        default=0,
        options={'SKIP_SAVE'}
    )
    
    def execute(self, context):
        # Override parent execute to control multiple_objects based on apply_to_all_objects
        self.multiple_objects = self.apply_to_all_objects
        return super().execute(context)
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if context.mode != 'OBJECT':
            return False
        if ps_ctx.ps_object is None or ps_ctx.active_material is None:
            return False
        # Check if material has a Principled BSDF
        mat = ps_ctx.active_material
        if not mat.use_nodes:
            return False
        principled = find_node(mat.node_tree, {'bl_idname': 'ShaderNodeBsdfPrincipled'})
        return principled is not None
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        mat_node_tree = mat.node_tree
        
        # Find the Principled BSDF node
        principled_node = find_node(mat_node_tree, {'bl_idname': 'ShaderNodeBsdfPrincipled'})
        if principled_node is None:
            self.report({'ERROR'}, "No Principled BSDF found in material")
            return {'CANCELLED'}
        
        # Create a new paint system group
        node_tree = bpy.data.node_groups.new(name=f"Temp Group Name", type='ShaderNodeTree')
        new_group = ps_ctx.ps_mat_data.create_new_group(context, self.group_name, node_tree)
        new_group.template = 'PBR'
        
        # Store coordinate type
        self.store_coord_type(context)
        
        # Get material output for positioning
        material_output = get_material_output(mat_node_tree)
        
        # Store the principled node location for positioning the paint system group
        ps_group_location = principled_node.location + Vector((-300, 0))
        
        # Create paint system group node
        node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
        node_group.node_tree = node_tree
        node_group.location = ps_group_location
        node_group.name = "Paint System Group"
        
        # Process each channel
        channel_setups = []
        
        # Color Channel
        if self.setup_color and 'Base Color' in principled_node.inputs:
            channel = new_group.create_channel(
                context, 
                channel_name='Color', 
                channel_type='COLOR', 
                use_alpha=True
            )
            channel_setups.append({
                'channel': channel,
                'bsdf_input': 'Base Color',
                'bsdf_alpha_input': 'Alpha',
                'group_output': 'Color',
                'group_alpha_output': 'Color Alpha',
                'needs_layers': True,
                'layer_type': 'IMAGE'
            })
        
        # Metallic Channel
        if self.setup_metallic and 'Metallic' in principled_node.inputs:
            channel = new_group.create_channel(
                context,
                channel_name='Metallic',
                channel_type='FLOAT',
                use_alpha=False,
                use_max_min=True,
                color_space='NONCOLOR'
            )
            channel_setups.append({
                'channel': channel,
                'bsdf_input': 'Metallic',
                'group_output': 'Metallic',
                'needs_layers': True,
                'layer_type': 'IMAGE'
            })
        
        # Roughness Channel
        if self.setup_roughness and 'Roughness' in principled_node.inputs:
            channel = new_group.create_channel(
                context,
                channel_name='Roughness',
                channel_type='FLOAT',
                use_alpha=False,
                use_max_min=True,
                color_space='NONCOLOR'
            )
            channel_setups.append({
                'channel': channel,
                'bsdf_input': 'Roughness',
                'group_output': 'Roughness',
                'needs_layers': True,
                'layer_type': 'IMAGE'
            })
        
        # Normal Channel
        if self.setup_normal and 'Normal' in principled_node.inputs:
            channel = new_group.create_channel(
                context,
                channel_name='Normal',
                channel_type='VECTOR',
                use_alpha=False,
                normalize_input=True,
                color_space='NONCOLOR'
            )
            channel_setups.append({
                'channel': channel,
                'bsdf_input': 'Normal',
                'group_output': 'Normal',
                'needs_layers': True,
                'layer_type': 'IMAGE',
                'needs_normal_map': True
            })
        
        # Emission Channel
        if self.setup_emission and 'Emission Color' in principled_node.inputs:
            channel = new_group.create_channel(
                context,
                channel_name='Emission',
                channel_type='COLOR',
                use_alpha=False,
                color_space='COLOR'
            )
            channel_setups.append({
                'channel': channel,
                'bsdf_input': 'Emission Color',
                'group_output': 'Emission',
                'needs_layers': True,
                'layer_type': 'IMAGE'
            })
        
        # Transfer connections and create layers
        for setup in channel_setups:
            channel = setup['channel']
            bsdf_input = setup['bsdf_input']
            group_output = setup['group_output']
            
            # Transfer the connection from BSDF input to paint system group input
            if bsdf_input in principled_node.inputs:
                input_socket = principled_node.inputs[bsdf_input]
                group_input_name = group_output  # The group input has the same name as output
                
                if group_input_name in node_group.inputs:
                    has_connection = transfer_connection(
                        mat_node_tree, 
                        input_socket, 
                        node_group.inputs[group_input_name]
                    )
                    
                    # Create layers if add_layers is enabled
                    if self.add_layers and setup.get('needs_layers', False):
                        # If there was a connection, try to create a layer from it
                        if has_connection:
                            # Check if the connected node is an image texture
                            if input_socket.is_linked:
                                from_node = input_socket.links[0].from_node
                                if from_node.bl_idname == 'ShaderNodeTexImage' and from_node.image:
                                    original_image = from_node.image
                                    
                                    # In DUPLICATE mode: original stays as input, duplicate becomes layer
                                    # In CONVERT mode: use original as layer (becomes editable)
                                    if self.image_mode == 'DUPLICATE':
                                        # Create a duplicate for the layer
                                        duplicate_image = original_image.copy()
                                        duplicate_image.name = f"{original_image.name}.001"
                                        image_to_use = duplicate_image
                                        layer_name = duplicate_image.name
                                    else:
                                        # Convert mode: use original directly
                                        image_to_use = original_image
                                        layer_name = original_image.name
                                    
                                    # Create an image layer with the image
                                    layer = channel.create_layer(
                                        context,
                                        layer_name=layer_name,
                                        layer_type='IMAGE',
                                        coord_type=self.coord_type,
                                        uv_map_name=self.uv_map_name
                                    )
                                    # Set the layer's image
                                    layer.image = image_to_use
                                    
                                    # If extension is CLIP, disable correct_image_aspect
                                    if hasattr(from_node, 'extension') and from_node.extension == 'CLIP':
                                        layer.correct_image_aspect = False
                                else:
                                    # For other node types, just add a placeholder layer
                                    channel.create_layer(
                                        context,
                                        layer_name='Layer',
                                        layer_type=setup.get('layer_type', 'IMAGE'),
                                        coord_type=self.coord_type,
                                        uv_map_name=self.uv_map_name
                                    )
                        else:
                            # No connection, create a default layer
                            if bsdf_input == 'Normal':
                                # For normal, add a geometry layer first
                                channel.create_layer(
                                    context,
                                    layer_name='Object Normal',
                                    layer_type='GEOMETRY',
                                    geometry_type='OBJECT_NORMAL',
                                    normalize_normal=True
                                )
                            channel.create_layer(
                                context,
                                layer_name='Layer',
                                layer_type=setup.get('layer_type', 'IMAGE'),
                                coord_type=self.coord_type,
                                uv_map_name=self.uv_map_name
                            )
                
                # Handle alpha for color channel
                if 'bsdf_alpha_input' in setup and setup['bsdf_alpha_input'] in principled_node.inputs:
                    alpha_input = principled_node.inputs[setup['bsdf_alpha_input']]
                    if 'group_alpha_output' in setup and setup['group_alpha_output'] in node_group.inputs:
                        transfer_connection(
                            mat_node_tree,
                            alpha_input,
                            node_group.inputs[setup['group_alpha_output']]
                        )
                
                # Connect paint system group output to BSDF input
                if group_output in node_group.outputs:
                    # Handle normal channel specially - needs a normal map node
                    if setup.get('needs_normal_map', False):
                        # Check if there's already a normal map node connected
                        existing_normal_map = None
                        if input_socket.is_linked:
                            from_node = input_socket.links[0].from_node
                            if from_node.bl_idname == 'ShaderNodeNormalMap':
                                existing_normal_map = from_node
                        
                        if existing_normal_map:
                            # Use the existing normal map node
                            connect_sockets(node_group.outputs[group_output], existing_normal_map.inputs[1])
                        else:
                            # Create a new normal map node
                            norm_map_node = mat_node_tree.nodes.new(type='ShaderNodeNormalMap')
                            norm_map_node.location = node_group.location + Vector((300, -300))
                            norm_map_node.space = 'OBJECT'
                            connect_sockets(node_group.outputs[group_output], norm_map_node.inputs[1])
                            connect_sockets(norm_map_node.outputs[0], principled_node.inputs[bsdf_input])
                    else:
                        connect_sockets(node_group.outputs[group_output], principled_node.inputs[bsdf_input])
                    
                    # Connect alpha for color channel
                    if 'group_alpha_output' in setup and setup['group_alpha_output'] in node_group.outputs:
                        alpha_output_name = setup['group_alpha_output']
                        if 'bsdf_alpha_input' in setup and setup['bsdf_alpha_input'] in principled_node.inputs:
                            connect_sockets(
                                node_group.outputs[alpha_output_name],
                                principled_node.inputs[setup['bsdf_alpha_input']]
                            )
        
        # Keep the principled BSDF and its output connection intact
        # The paint system group is now providing inputs to it
        
        # Set active channel to the first one
        ps_ctx = self.parse_context(context)
        if ps_ctx.active_group:
            ps_ctx.active_group.active_index = 0
        
        redraw_panel(context)
        self.report({'INFO'}, f"Converted material '{mat.name}' to Paint System")
        return {'FINISHED'}
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        
        # Detect all objects that share the same material
        if mat:
            objects_with_material = []
            for obj in context.scene.objects:
                if obj.type == 'MESH' and obj.data.materials:
                    if mat in obj.data.materials[:]:
                        objects_with_material.append(obj)
            
            self.detected_objects_count = len(objects_with_material)
            
            # If user wants to apply to all objects, select them
            if self.apply_to_all_objects and objects_with_material:
                for obj in context.selected_objects:
                    obj.select_set(False)
                for obj in objects_with_material:
                    obj.select_set(True)
                if objects_with_material and context.view_layer.objects.active not in objects_with_material:
                    context.view_layer.objects.active = objects_with_material[0]
        
        # Set group name to material name
        if mat:
            base_name = mat.name
            if ps_ctx.ps_mat_data and ps_ctx.ps_mat_data.groups:
                self.group_name = get_next_unique_name(base_name, [group.name for group in ps_ctx.ps_mat_data.groups])
            else:
                self.group_name = base_name
        
        # Auto-detect which channels have connections or non-default values
        mat_node_tree = mat.node_tree
        principled_node = find_node(mat_node_tree, {'bl_idname': 'ShaderNodeBsdfPrincipled'})
        
        if principled_node:
            # Check Base Color - enable if linked or non-white
            if 'Base Color' in principled_node.inputs:
                input_socket = principled_node.inputs['Base Color']
                is_linked = input_socket.is_linked
                is_non_default = False
                if hasattr(input_socket, 'default_value'):
                    # Check if color is not white (default is usually (0.8, 0.8, 0.8, 1.0))
                    default_val = input_socket.default_value
                    is_non_default = not (abs(default_val[0] - 0.8) < 0.01 and 
                                         abs(default_val[1] - 0.8) < 0.01 and 
                                         abs(default_val[2] - 0.8) < 0.01)
                self.setup_color = is_linked or is_non_default
            
            # Check Metallic - enable if linked or > 0
            if 'Metallic' in principled_node.inputs:
                input_socket = principled_node.inputs['Metallic']
                is_linked = input_socket.is_linked
                is_non_default = False
                if hasattr(input_socket, 'default_value'):
                    is_non_default = input_socket.default_value > 0.01
                self.setup_metallic = is_linked or is_non_default
            
            # Check Roughness - enable if linked or not 0.5
            if 'Roughness' in principled_node.inputs:
                input_socket = principled_node.inputs['Roughness']
                is_linked = input_socket.is_linked
                is_non_default = False
                if hasattr(input_socket, 'default_value'):
                    # Default roughness is usually 0.5
                    is_non_default = abs(input_socket.default_value - 0.5) > 0.01
                self.setup_roughness = is_linked or is_non_default
            
            # Check Normal - enable if linked
            if 'Normal' in principled_node.inputs:
                self.setup_normal = principled_node.inputs['Normal'].is_linked
            
            # Check Emission - enable if linked or emission strength > 0
            if 'Emission Color' in principled_node.inputs:
                input_socket = principled_node.inputs['Emission Color']
                is_linked = input_socket.is_linked
                has_emission_strength = False
                if 'Emission Strength' in principled_node.inputs:
                    strength_socket = principled_node.inputs['Emission Strength']
                    if hasattr(strength_socket, 'default_value'):
                        has_emission_strength = strength_socket.default_value > 0.01
                self.setup_emission = is_linked or has_emission_strength
            
            # If nothing is detected, default to standard PBR channels
            if not any([self.setup_color, self.setup_metallic, self.setup_roughness, self.setup_normal, self.setup_emission]):
                self.setup_color = True
                self.setup_roughness = True
                self.setup_normal = True
        
        # Ensure Auto UV is off by default for conversion
        self.use_paint_system_uv = False
        self.get_coord_type(context)
        
        if ps_ctx.ps_object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
        
        return context.window_manager.invoke_props_dialog(self, width=300)
    
    def draw(self, context):
        layout = self.layout
        self.multiple_objects_ui(layout, context)
        
        # Show option to apply to all objects with the material
        if self.detected_objects_count > 1:
            box = layout.box()
            box.alert = not self.apply_to_all_objects
            row = box.row()
            row.prop(self, "apply_to_all_objects", text=f"Apply to All {self.detected_objects_count} Objects", icon='OBJECT_DATA')
            if not self.apply_to_all_objects:
                info_row = box.row()
                info_row.label(text="Will only affect current object", icon='INFO')
        
        box = layout.box()
        row = box.row()
        row.alignment = "CENTER"
        row.label(text="Channels to Setup:", icon="MATERIAL")
        col = box.column(align=True)
        col.prop(self, "setup_color", text="Color", icon_value=get_icon('color_socket'))
        col.prop(self, "setup_metallic", text="Metallic", icon_value=get_icon('float_socket'))
        col.prop(self, "setup_roughness", text="Roughness", icon_value=get_icon('float_socket'))
        col.prop(self, "setup_normal", text="Normal", icon_value=get_icon('vector_socket'))
        col.prop(self, "setup_emission", text="Emission", icon_value=get_icon('color_socket'))
        
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(self, "add_layers", text="Create Layers From Inputs", icon_value=get_icon('layer_add'))
        
        if self.add_layers:
            box = layout.box()
            row = box.row()
            row.label(text="Image Handling:", icon='IMAGE_DATA')
            col = box.column(align=True)
            col.prop(self, "image_mode", expand=True)
            self.select_coord_type_ui(box, context)
        
        box = layout.box()
        row = box.row()
        row.alignment = "CENTER"
        row.label(text="Setup Settings:", icon="NODETREE")
        box.prop(self, "group_name", text="Setup Name", icon='NODETREE')


classes = (
    PAINTSYSTEM_OT_NewGroup,
    PAINTSYSTEM_OT_DeleteGroup,
    PAINTSYSTEM_OT_MoveGroup,
    PAINTSYSTEM_OT_ConvertMaterialToPS,
)

register, unregister = register_classes_factory(classes)    