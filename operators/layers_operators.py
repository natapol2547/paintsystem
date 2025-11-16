import bpy
from bpy.props import (
    StringProperty, IntProperty, EnumProperty,
    BoolProperty
)
from bpy.types import Operator, Context, NodeTree
from bpy.utils import register_classes_factory

from ..paintsystem.data import (
    ACTION_BIND_ENUM,
    ACTION_TYPE_ENUM,
    ADJUSTMENT_TYPE_ENUM,
    ATTRIBUTE_TYPE_ENUM,
    TEXTURE_TYPE_ENUM,
    GRADIENT_TYPE_ENUM,
    GEOMETRY_TYPE_ENUM,
    get_layer_by_uid,
    is_layer_linked,
)
from ..utils import get_next_unique_name
from .common import (
    PSContextMixin,
    scale_content,
    get_icon,
    MultiMaterialOperator,
    PSUVOptionsMixin,
    PSImageCreateMixin
    )
from .operators_utils import redraw_panel, intern_enum_items

def get_object_uv_maps(self, context: Context):
    items = [
        (uv_map.name, uv_map.name, "") for uv_map in context.object.data.uv_layers
    ]
    return intern_enum_items(items)
    
def get_icon_from_type(type: str) -> int:
    type_to_icon = {
        'COLOR': 'color_socket',
        'VECTOR': 'vector_socket',
        'FLOAT': 'float_socket',
    }
    return get_icon(type_to_icon.get(type, 'color_socket'))

class PAINTSYSTEM_OT_NewImage(PSContextMixin, PSUVOptionsMixin, PSImageCreateMixin, MultiMaterialOperator):
    """Create a new image layer"""
    bl_idname = "paint_system.new_image_layer"
    bl_label = "New Image Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    image_name: StringProperty(
        name="Layer Name",
        description="Name of the new image layer",
        default="Image Layer"
    )
    
    image_add_type: EnumProperty(
        name="Image Add Type",
        description="How to add the image layer",
        items=[
            ('NEW', "New Image", "Create a new image layer"),
            ('IMPORT', "Import Image", "Import an image from file"),
            ('EXISTING', "Existing Image", "Use an existing image from the blend file"),
        ],
        default='NEW'
    )
    filepath: StringProperty(
        subtype='FILE_PATH',
    )
    filter_glob: StringProperty(
        default='*.jpg;*.jpeg;*.png;*.tif;*.tiff;*.bmp',
        options={'HIDDEN'}
    )
            
    def get_next_image_name(self, context):
        """Get the next image name from the active channel"""
        ps_ctx = self.parse_context(context)
        if ps_ctx.active_channel:
            return get_next_unique_name("Image Layer", [layer.name for layer in ps_ctx.active_channel.layers])

    def process_material(self, context):
        self.store_coord_type(context)
        ps_ctx = self.parse_context(context)
        if self.image_add_type == 'NEW':
            img = self.create_image()
        elif self.image_add_type == 'IMPORT':
            img = bpy.data.images.load(self.filepath, check_existing=True)
            if not img:
                self.report({'ERROR'}, "Failed to load image")
                return False
            self.image_name = img.name
        elif self.image_add_type == 'EXISTING':
            if not self.image_name:
                self.report({'ERROR'}, "No image selected")
                return False
            img = bpy.data.images.get(self.image_name)
            img.pack()
            if not img:
                self.report({'ERROR'}, "Image not found")
                return False
        img.colorspace_settings.name = 'Non-Color' if ps_ctx.active_channel.color_space == 'NONCOLOR' else 'sRGB'
        ps_ctx.active_channel.create_layer(
            context, 
            layer_name=self.image_name, 
            layer_type="IMAGE", 
            image=img,
            coord_type=self.coord_type,
            uv_map_name=self.uv_map_name
        )
        return {'FINISHED'}
    
    def invoke(self, context, event):
        self.get_coord_type(context)
        self.image_name = self.get_next_image_name(context)
        if self.image_resolution != 'CUSTOM':
            self.image_width = int(self.image_resolution)
            self.image_height = int(self.image_resolution)
        if self.image_add_type == 'IMPORT':
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        if self.image_add_type == 'EXISTING':
            self.image_name = ""
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        self.multiple_objects_ui(layout, context)
        if self.image_add_type == 'NEW':
            self.image_create_ui(layout, context)
        elif self.image_add_type == 'EXISTING':
            layout.prop_search(self, "image_name", bpy.data,
                           "images", text="Image")
            
        box = layout.box()
        self.select_coord_type_ui(box, context)


class PAINTSYSTEM_OT_NewFolder(PSContextMixin, MultiMaterialOperator):
    """Create a new folder layer"""
    bl_idname = "paint_system.new_folder_layer"
    bl_label = "New Folder"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None

    layer_name: StringProperty(
        name="Layer Name",
        description="Name of the new folder",
        default="Folder"
    )

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.create_layer(context, self.layer_name, "FOLDER")
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewSolidColor(PSContextMixin, MultiMaterialOperator):
    """Create a new solid color layer"""
    bl_idname = "paint_system.new_solid_color_layer"
    bl_label = "New Solid Color Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None

    layer_name: StringProperty(
        name="Layer Name",
        description="Name of the new solid color layer",
        default="Solid Color Layer"
    )

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.create_layer(context, self.layer_name, "SOLID_COLOR")
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewAttribute(PSContextMixin, MultiMaterialOperator):
    """Create a new attribute layer"""
    bl_idname = "paint_system.new_attribute_layer"
    bl_label = "New Attribute Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    attribute_name: StringProperty(
        name="Attribute Name",
        description="Name of the attribute to use"
    )
    attribute_type: EnumProperty(
        name="Attribute Type",
        items=ATTRIBUTE_TYPE_ENUM,
        default='GEOMETRY'
    )

    layer_name: StringProperty(
        name="Layer Name",
        description="Name of the new attribute layer",
        default="Attribute Layer"
    )

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.create_layer(context, self.layer_name, "ATTRIBUTE")
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewAdjustment(PSContextMixin, MultiMaterialOperator):
    """Create a new adjustment layer"""
    bl_idname = "paint_system.new_adjustment_layer"
    bl_label = "New Adjustment Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    adjustment_type: EnumProperty(
        name="Adjustment Type",
        items=ADJUSTMENT_TYPE_ENUM,
    )

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        layer_name = next(name for adjustment_type, name, description in ADJUSTMENT_TYPE_ENUM if adjustment_type == self.adjustment_type)
        ps_ctx.active_channel.create_layer(context, layer_name, "ADJUSTMENT", adjustment_type=self.adjustment_type)
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewShader(PSContextMixin, MultiMaterialOperator):
    """Create a new shader layer"""
    bl_idname = "paint_system.new_shader_layer"
    bl_label = "New Shader Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None

    layer_name: StringProperty(
        name="Layer Name",
        description="Name of the new shader layer",
        default="Shader Layer"
    )

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.create_layer(context, self.layer_name, "SHADER")
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewGradient(PSContextMixin, MultiMaterialOperator):
    """Create a new gradient layer"""
    bl_idname = "paint_system.new_gradient_layer"
    bl_label = "New Gradient Layer"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None

    layer_name: StringProperty(
        name="Layer Name",
        description="Name of the new gradient layer",
        default="Gradient Layer"
    )
    
    gradient_type: EnumProperty(
        name="Gradient Type",
        items=GRADIENT_TYPE_ENUM,
        default='LINEAR'
    )

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.create_layer(context, self.gradient_type.title(), "GRADIENT", gradient_type=self.gradient_type)
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewGeometry(PSContextMixin, MultiMaterialOperator):
    """Create a new geometry layer"""
    bl_idname = "paint_system.new_geometry_layer"
    bl_label = "New Geometry Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    geometry_type: EnumProperty(
        name="Geometry Type",
        items=GEOMETRY_TYPE_ENUM,
        default='WORLD_NORMAL'
    )
    normalize_normal: BoolProperty(
        name="Normalize Normal",
        description="Normalize the normal",
        default=False,
        options={'SKIP_SAVE'}
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        layer_name = next(name for geometry_type, name, description in GEOMETRY_TYPE_ENUM if geometry_type == self.geometry_type)
        ps_ctx.active_channel.create_layer(
            context,
            layer_name,
            layer_type="GEOMETRY",
            geometry_type=self.geometry_type,
            normalize_normal=self.normalize_normal
        )
        return {'FINISHED'}


class PAINTSYSTEM_OT_FixMissingGradientEmpty(PSContextMixin, Operator):
    """Fix missing gradient empty"""
    bl_idname = "paint_system.fix_missing_gradient_empty"
    bl_label = "Fix Missing Gradient Empty"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        for layer in ps_ctx.active_channel.layers:
            if layer.type == 'GRADIENT':
                layer.update_node_tree(context)
        ps_ctx.active_layer.update_node_tree(context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_SelectEmpty(PSContextMixin, Operator):
    """Select the empty"""
    bl_idname = "paint_system.select_empty"
    bl_label = "Select Empty"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        empty_object = ps_ctx.active_layer.empty_object
        if empty_object:
            bpy.ops.object.mode_set(mode='OBJECT')
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = empty_object
            empty_object.select_set(True)
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewRandomColor(PSContextMixin, MultiMaterialOperator):
    """Create a new random color layer"""
    bl_idname = "paint_system.new_random_color_layer"
    bl_label = "New Random Color Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    layer_name: StringProperty(
        name="Layer Name",
        description="Name of the new random color layer",
        default="Random Color Layer"
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.create_layer(context, self.layer_name, "RANDOM")
        return {'FINISHED'}


    
def get_inputs(node_tree: NodeTree, context: Context):
    socket_items = []
    count = 0
    for socket in node_tree.interface.items_tree:
        if socket.item_type == 'SOCKET' and socket.in_out == 'INPUT' and socket.socket_type != 'NodeSocketShader':
            socket_items.append((str(count), socket.name, "", get_icon_from_type(socket.socket_type.replace("NodeSocket", "").upper()), count))
            count += 1
    return socket_items

def get_outputs(node_tree: NodeTree, context: Context):
    socket_items = []
    count = 0
    for socket in node_tree.interface.items_tree:
        if socket.item_type == 'SOCKET' and socket.in_out == 'OUTPUT' and socket.socket_type != 'NodeSocketShader':
            socket_items.append((str(count), socket.name, "", get_icon_from_type(socket.socket_type.replace("NodeSocket", "").upper()), count))
            count += 1
    return socket_items
class PAINTSYSTEM_OT_NewCustomNodeGroup(PSContextMixin, MultiMaterialOperator):
    """Create a new custom node group layer"""
    bl_idname = "paint_system.new_custom_node_group_layer"
    bl_label = "New Custom Node Group Layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    def get_node_groups(self, context: Context):
        node_groups = []
        for node_group in bpy.data.node_groups:
            if node_group.bl_idname == 'ShaderNodeTree' and not node_group.name.startswith(".PS") and not node_group.name.startswith("Paint System") and not node_group.name.startswith("PS "):
                node_groups.append((node_group.name, node_group.name, ""))
        return node_groups
    
    def get_inputs_enum(self, context: Context):
        if not self.node_tree_name:
            return []
        custom_node_tree = bpy.data.node_groups.get(self.node_tree_name)
        inputs = get_inputs(custom_node_tree, context)
        inputs.append(('-1', 'None', '', 'BLANK1', len(inputs)))
        return inputs
    
    def get_outputs_enum_without_none(self, context: Context):
        if not self.node_tree_name:
            return []
        custom_node_tree = bpy.data.node_groups.get(self.node_tree_name)
        outputs = get_outputs(custom_node_tree, context)
        return outputs
    
    def get_outputs_enum(self, context: Context):
        if not self.node_tree_name:
            return []
        custom_node_tree = bpy.data.node_groups.get(self.node_tree_name)
        outputs = get_outputs(custom_node_tree, context)
        outputs.append(('-1', 'None', '', 'BLANK1', len(outputs)))
        return outputs
    
    def auto_select_sockets(self, context: Context):
        if not self.node_tree_name:
            return
        custom_node_tree = bpy.data.node_groups.get(self.node_tree_name)
        input_sockets = get_inputs(custom_node_tree, context)
        output_sockets = get_outputs(custom_node_tree, context)
        for input_socket in input_sockets:
            if input_socket[1] == 'Color':
                self.custom_color_input = input_socket[0]
            elif input_socket[1] == 'Alpha':
                self.custom_alpha_input = input_socket[0]
        for output_socket in output_sockets:
            if output_socket[1] == 'Color':
                self.custom_color_output = output_socket[0]
            elif output_socket[1] == 'Alpha':
                self.custom_alpha_output = output_socket[0]
                
    def has_unsupported_sockets(self, node_tree: NodeTree):
        for socket in node_tree.interface.items_tree:
            if socket.item_type == 'SOCKET' and socket.socket_type not in ['NodeSocketColor', 'NodeSocketFloat', 'NodeSocketVector']:
                return True
        return False
    
    node_tree_name: EnumProperty(
        name="Node Tree",
        description="Name of the node tree to use",
        items=get_node_groups,
        update=auto_select_sockets
    )
    
    custom_color_input: EnumProperty(
        name="Custom Color Input",
        description="Custom color input",
        items=get_inputs_enum,
    )
    custom_alpha_input: EnumProperty(
        name="Custom Alpha Input",
        description="Custom alpha input",
        items=get_inputs_enum,
        
    )
    custom_color_output: EnumProperty(
        name="Custom Color Output",
        description="Custom color output",
        items=get_outputs_enum_without_none
    )
    custom_alpha_output: EnumProperty(
        name="Custom Alpha Output",
        description="Custom alpha output",
        items=get_outputs_enum
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    def process_material(self, context):
        if not self.node_tree_name:
            return {'CANCELLED'}
        ps_ctx = self.parse_context(context)
        custom_node_tree = bpy.data.node_groups.get(self.node_tree_name)
        ps_ctx.active_channel.create_layer(
            context,
            layer_name=self.node_tree_name,
            layer_type="NODE_GROUP",
            custom_node_tree=custom_node_tree,
            custom_color_input=int(self.custom_color_input),
            custom_alpha_input=int(self.custom_alpha_input if self.custom_alpha_input != "" else "-1"),
            custom_color_output=int(self.custom_color_output),
            custom_alpha_output=int(self.custom_alpha_output if self.custom_alpha_output != "" else "-1")
        )
        return {'FINISHED'}
    
    def invoke(self, context, event):
        self.auto_select_sockets(context)
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Select node tree:", icon='NODETREE')
        available_node_trees = self.get_node_groups(context)
        if not available_node_trees:
            layout.label(text="No supported node trees found", icon='ERROR')
            return
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(self, "node_tree_name", text="")
        if self.has_unsupported_sockets(bpy.data.node_groups.get(self.node_tree_name)):
            box = layout.box()
            box.alert = True
            row = box.row()
            row.label(icon='ERROR')
            col = row.column()
            col.label(text="Node has unsupported sockets (Shader)")
        if self.node_tree_name:
            box = layout.box()
            row = box.row()
            row.alignment = 'CENTER'
            row.label(text="Socket Connection", icon='NODETREE')
            row = box.row()
            box = row.box()
            text_row = box.row()
            text_row.alignment = 'CENTER'
            text_row.label(text="Input")
            box.prop(self, "custom_color_input", text="Color")
            box.prop(self, "custom_alpha_input", text="Alpha")
            box = row.box()
            text_row = box.row()
            text_row.alignment = 'CENTER'
            text_row.label(text="Output")
            box.prop(self, "custom_color_output", text="Color")
            box.prop(self, "custom_alpha_output", text="Alpha")


class PAINTSYSTEM_OT_NewTexture(PSContextMixin, PSUVOptionsMixin, MultiMaterialOperator):
    """Create a new texture layer"""
    bl_idname = "paint_system.new_texture_layer"
    bl_label = "New Texture Layer"
    bl_options = {'REGISTER', 'UNDO'}

    texture_type: EnumProperty(
        name="Texture Type",
        description="Type of texture to create",
        items=TEXTURE_TYPE_ENUM,
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    def invoke(self, context, event):
        self.get_coord_type(context)
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        self.multiple_objects_ui(layout, context)
        box = layout.box()
        self.select_coord_type_ui(box, context, show_warning=False)
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        self.store_coord_type(context)
        layer_name = next(name for texture_type, name, description in TEXTURE_TYPE_ENUM if texture_type == self.texture_type)
        ps_ctx.active_channel.create_layer(
            context,
            layer_name=layer_name,
            layer_type="TEXTURE",
            texture_type=self.texture_type,
            coord_type=self.coord_type,
            uv_map_name=self.uv_map_name
        )
        return {'FINISHED'}

class PAINTSYSTEM_OT_DeleteItem(PSContextMixin, MultiMaterialOperator):
    """Remove the active item"""
    bl_idname = "paint_system.delete_item"
    bl_label = "Remove Item"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Remove the active item"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.unlinked_layer is not None

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        unlinked_layer = ps_ctx.unlinked_layer
        active_channel.delete_layer(context, unlinked_layer)
        
        redraw_panel(context)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        unlinked_layer = ps_ctx.unlinked_layer
        layout.label(
            text=f"Delete '{unlinked_layer.layer_name}' ?", icon='ERROR')
        layout.label(
            text="Click OK to delete, or cancel to keep the layer")


class PAINTSYSTEM_OT_MoveUp(PSContextMixin, MultiMaterialOperator):
    """Move the active item up"""
    bl_idname = "paint_system.move_up"
    bl_label = "Move Item Up"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Move the active item up"

    action: EnumProperty(
        items=[
            ('MOVE_INTO', "Move Into", "Move into folder"),
            ('MOVE_ADJACENT', "Move Adjacent", "Move as sibling"),
            ('MOVE_OUT', "Move Out", "Move out of folder"),
            ('SKIP', "Skip", "Skip over item"),
        ]
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return False
        item_id = active_channel.get_id_from_flattened_index(active_channel.active_index)
        options = active_channel.get_movement_options(item_id, 'UP')
        return bool(options)

    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}

        item_id = active_channel.get_id_from_flattened_index(
            active_channel.active_index)

        options = active_channel.get_movement_options(item_id, 'UP')
        if not options:
            return {'CANCELLED'}

        if len(options) == 1 and options[0][0] == 'SKIP':
            self.action = 'SKIP'
            return self.process_material(context)

        context.window_manager.popup_menu(
            self.draw_menu,
            title="Move Options"
        )
        return {'FINISHED'}

    def draw_menu(self, self_menu, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}
        item_id = active_channel.get_id_from_flattened_index(
            active_channel.active_index)

        for op_id, label, props in active_channel.get_movement_menu_items(item_id, 'UP'):
            op = self_menu.layout.operator(op_id, text=label)
            for key, value in props.items():
                setattr(op, key, value)

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}
        item_id = active_channel.get_id_from_flattened_index(
            active_channel.active_index)

        if active_channel.execute_movement(item_id, 'UP', self.action):
            # Update active_index to follow the moved item
            # active_group.active_index = active_group.layers.values().index(self)

            active_channel.update_node_tree(context)

            # Force the UI to update
            redraw_panel(context)

            return {'FINISHED'}

        return {'CANCELLED'}


class PAINTSYSTEM_OT_MoveDown(PSContextMixin, MultiMaterialOperator):
    """Move the active item down"""
    bl_idname = "paint_system.move_down"
    bl_label = "Move Item Down"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Move the active item down"

    action: EnumProperty(
        items=[
            ('MOVE_OUT_BOTTOM', "Move Out Bottom", "Move out of folder"),
            ('MOVE_INTO_TOP', "Move Into Top", "Move to top of folder"),
            ('MOVE_ADJACENT', "Move Adjacent", "Move as sibling"),
            ('SKIP', "Skip", "Skip over item"),
        ]
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return False
        item_id = active_channel.get_id_from_flattened_index(active_channel.active_index)
        options = active_channel.get_movement_options(item_id, 'DOWN')
        return bool(options)

    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}

        item_id = active_channel.get_id_from_flattened_index(
            active_channel.active_index)

        options = active_channel.get_movement_options(item_id, 'DOWN')
        if not options:
            return {'CANCELLED'}

        if len(options) == 1 and options[0][0] == 'SKIP':
            self.action = 'SKIP'
            return self.process_material(context)

        context.window_manager.popup_menu(
            self.draw_menu,
            title="Move Options"
        )
        return {'FINISHED'}

    def draw_menu(self, self_menu, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}

        item_id = active_channel.get_id_from_flattened_index(
            active_channel.active_index)

        for op_id, label, props in active_channel.get_movement_menu_items(item_id, 'DOWN'):
            op = self_menu.layout.operator(op_id, text=label)
            for key, value in props.items():
                setattr(op, key, value)

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}

        item_id = active_channel.get_id_from_flattened_index(
            active_channel.active_index)

        if active_channel.execute_movement(item_id, 'DOWN', self.action):
            # Update active_index to follow the moved item
            # active_group.active_index = active_group.items.values().index(self)

            active_channel.update_node_tree(context)

            # Force the UI to update
            redraw_panel(context)

            return {'FINISHED'}

        return {'CANCELLED'}


class PAINTSYSTEM_OT_CopyLayer(PSContextMixin, Operator):
    """Copy the active layer"""
    bl_idname = "paint_system.copy_layer"
    bl_label = "Copy Layer"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Copy the active layer"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        unlinked_layer = ps_ctx.unlinked_layer
        ps_scene_data = ps_ctx.ps_scene_data
        if not ps_scene_data:
            return {'CANCELLED'}
        ps_scene_data.clear_clipboard()
        ps_scene_data.add_layer_to_clipboard(unlinked_layer)
        return {'FINISHED'}


class PAINTSYSTEM_OT_CopyAllLayers(PSContextMixin, Operator):
    """Copy all layers"""
    bl_idname = "paint_system.copy_all_layers"
    bl_label = "Copy All Layers"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Copy all layers"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        ps_scene_data = ps_ctx.ps_scene_data
        if not ps_scene_data:
            return {'CANCELLED'}
        ps_scene_data.clear_clipboard()
        for layer in active_channel.flattened_unlinked_layers:
            ps_scene_data.add_layer_to_clipboard(layer)
        return {'FINISHED'}


class PAINTSYSTEM_OT_PasteLayer(PSContextMixin, Operator):
    """Paste the copied layer"""
    bl_idname = "paint_system.paste_layer"
    bl_label = "Paste Layer"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Paste the copied layer"
    
    linked: BoolProperty(
        name="Linked",
        description="Paste the copied layer as linked",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    @classmethod
    def poll(cls, context):
        return len(bpy.context.scene.ps_scene_data.clipboard_layers) > 0
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        clipboard_layers = bpy.context.scene.ps_scene_data.clipboard_layers
        new_layer_id_map = {}
        if active_layer:
            is_folder = active_layer and active_layer.type == "FOLDER"
            base_parent_id = active_layer.id if is_folder else active_layer.parent_id
        else:
            base_parent_id = -1
        for idx, clipboard_layer in enumerate(clipboard_layers):
            layer = get_layer_by_uid(clipboard_layer.material, clipboard_layer.uid)
            print(f"Layer: {layer}")
            if not layer:
                continue
            if self.linked:
                new_layer = ps_ctx.active_channel.create_layer(context, layer.layer_name, layer.type, insert_at="BEFORE" if idx == 0 else "AFTER")
            else:
                new_layer = ps_ctx.active_channel.create_layer(context, layer.layer_name, layer.type, insert_at="BEFORE" if idx == 0 else "AFTER")
            new_layer_id_map[layer.id] = new_layer
            if layer.parent_id != -1:
                new_layer.parent_id = new_layer_id_map[layer.parent_id].id
            else:
                new_layer.parent_id = base_parent_id
            if self.linked:
                print(f"Linked layer: {clipboard_layer.uid} {clipboard_layer.material}")
                new_layer.linked_layer_uid = clipboard_layer.uid
                new_layer.linked_material = clipboard_layer.material
            else:
                new_layer.copy_layer_data(layer)
            new_layer.update_node_tree(context)
        ps_ctx.active_channel.update_node_tree(context)
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_UnlinkLayer(PSContextMixin, Operator):
    """Unlink the active layer"""
    bl_idname = "paint_system.unlink_layer"
    bl_label = "Unlink Layer"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Unlink the active layer"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        unlinked_layer = ps_ctx.unlinked_layer
        unlinked_layer.unlink_layer_data()
        ps_ctx.active_channel.update_node_tree(context)
        return {'FINISHED'}

class PAINTSYSTEM_OT_AddAction(PSContextMixin, Operator):
    """Add an action to the active layer"""
    bl_idname = "paint_system.add_action"
    bl_label = "Add Action"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Add an action to the active layer"
    
    action_bind: EnumProperty(
        name="Action Type",
        description="Action type",
        items=ACTION_BIND_ENUM
    )
    action_type: EnumProperty(
        name="Action Type",
        description="Action type",
        items=ACTION_TYPE_ENUM
    )
    frame: IntProperty(
        name="Frame",
        description="Frame to enable/disable the layer",
        default=0
    )
    marker_name: StringProperty(
        name="Marker Name",
        description="Marker name",
        default=""
    )
    
    def get_next_action_name(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        return get_next_unique_name("Action", [action.name for action in active_layer.actions])
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer is not None
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.prop(self, "action_bind", text="Bind to")
        layout.prop(self, "action_type", text="Once reached")
        if self.action_bind == 'FRAME':
            layout.prop(self, "frame", text="Frame")
        elif self.action_bind == 'MARKER':
            layout.prop_search(self, "marker_name", context.scene, "timeline_markers", text="Marker", icon="MARKER_HLT")
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        action = active_layer.actions.add()
        action.name = self.name
        action.action_bind = self.action_bind
        action.action_type = self.action_type
        if self.action_bind == 'FRAME':
            action.frame = self.frame
        elif self.action_bind == 'MARKER':
            action.marker_name = self.marker_name
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Get current frame
        self.frame = bpy.context.scene.frame_current
        return context.window_manager.invoke_props_dialog(self)


class PAINTSYSTEM_OT_DeleteAction(PSContextMixin, Operator):
    """Delete the active action"""
    bl_idname = "paint_system.delete_action"
    bl_label = "Delete Action"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Delete the active action"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        active_layer.actions.remove(active_layer.active_action_index)
        active_layer.active_action_index = min(active_layer.active_action_index, len(active_layer.actions) - 1)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ShowLayerWarnings(PSContextMixin, Operator):
    """Show layer warnings"""
    bl_idname = "paint_system.show_layer_warnings"
    bl_label = "Layer Warnings"
    bl_options = {'REGISTER'}
    bl_description = "Show layer warnings"
    
    layer_id: IntProperty(
        name="Warnings",
        description="Layer ID to display warnings for",
        default=-1
    )
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=200)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        layer = active_channel.get_item_by_id(self.layer_id)
        warnings = layer.get_layer_data().get_layer_warnings(context)
        warnings_box = layout.box()
        warnings_col = warnings_box.column(align=True)
        for warning in warnings:
            # Split warning into chunks of 6 words
            words = warning.split()
            chunks = [' '.join(words[j:j+6]) for j in range(0, len(words), 6)]
            for i, chunk in enumerate(chunks):
                warnings_col.label(text=chunk, icon='ERROR' if not i else 'BLANK1')
    
    def execute(self, context):
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_NewImage,
    PAINTSYSTEM_OT_NewFolder,
    PAINTSYSTEM_OT_NewSolidColor,
    PAINTSYSTEM_OT_NewAttribute,
    PAINTSYSTEM_OT_NewAdjustment,
    PAINTSYSTEM_OT_NewShader,
    PAINTSYSTEM_OT_NewGradient,
    PAINTSYSTEM_OT_NewGeometry,
    PAINTSYSTEM_OT_FixMissingGradientEmpty,
    PAINTSYSTEM_OT_SelectEmpty,
    PAINTSYSTEM_OT_NewRandomColor,
    PAINTSYSTEM_OT_NewTexture,
    PAINTSYSTEM_OT_NewCustomNodeGroup,
    PAINTSYSTEM_OT_DeleteItem,
    PAINTSYSTEM_OT_MoveUp,
    PAINTSYSTEM_OT_MoveDown,
    PAINTSYSTEM_OT_CopyLayer,
    PAINTSYSTEM_OT_CopyAllLayers,
    PAINTSYSTEM_OT_PasteLayer,
    PAINTSYSTEM_OT_UnlinkLayer,
    PAINTSYSTEM_OT_AddAction,
    PAINTSYSTEM_OT_DeleteAction,
    PAINTSYSTEM_OT_ShowLayerWarnings,
)

register, unregister = register_classes_factory(classes)