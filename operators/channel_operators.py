import bpy

# ---
from ..paintsystem.data import CHANNEL_TYPE_ENUM, COLOR_SPACE_ENUM
from ..utils import get_next_unique_name
from .common import MultiMaterialOperator, PSContextMixin
from .list_manager import ListManager
from .operators_utils import redraw_panel

class PAINTSYSTEM_OT_AddChannel(PSContextMixin, MultiMaterialOperator):
    """Create a new channel in the Paint System"""
    bl_idname = "paint_system.add_channel"
    bl_label = "Add Channel"
    bl_options = {'REGISTER', 'UNDO'}
    
    def get_unique_channel_name(self, context):
        """Set a unique name for the new channel."""
        ps_ctx = PSContextMixin.parse_context(context)
        active_group = ps_ctx.active_group
        return get_next_unique_name(self.channel_name, [channel.name for channel in active_group.channels])

    channel_name: bpy.props.StringProperty(
        name="Channel Name",
        description="Name of the new channel",
        default="New Channel",
    )
    # Template preset to simplify setup
    template: bpy.props.EnumProperty(
        name="Template",
        description="Preset for common channel types",
        items=[
            ('GENERIC', 'Generic', 'No preset; use manual settings'),
            ('COLOR', 'Color', 'sRGB color channel'),
            ('ROUGHNESS', 'Roughness', 'Grayscale roughness channel'),
            ('METALLIC', 'Metallic', 'Grayscale metallic channel'),
            ('NORMAL', 'Normal (Tangent)', 'Vector normal map channel'),
            ('EMISSION', 'Emission', 'sRGB emission channel'),
            ('AO', 'Ambient Occlusion', 'Grayscale AO channel'),
            ('DISPLACEMENT', 'Displacement', 'Grayscale displacement/height'),
        ],
        default='GENERIC'
    )
    create_starter_layer: bpy.props.BoolProperty(
        name="Create Starter Image Layer",
        description="Automatically add a paintable image layer",
        default=True,
        options={'SKIP_SAVE'}
    )
    channel_type: bpy.props.EnumProperty(
        name="Channel Type",
        description="Type of the new channel",
        items=CHANNEL_TYPE_ENUM,
        default='COLOR'
    )
    color_space: bpy.props.EnumProperty(
        items=COLOR_SPACE_ENUM,
        name="Color Space",
        description="Color space",
        default='COLOR'
    )
    use_alpha: bpy.props.BoolProperty(
        name="Expose Alpha Socket",
        description="Expose alpha socket in the Paint System group",
        default=False,
        options={'SKIP_SAVE'}
    )
    normalize_input: bpy.props.BoolProperty(
        name="Normalize Channel",
        description="Normalize the channel",
        default=False,
        options={'SKIP_SAVE'}
    )
    # world_to_object_normal: bpy.props.BoolProperty(
    #     name="World to Object Normal",
    #     description="World to object normal",
    #     default=False,
    #     options={'SKIP_SAVE'}
    # )
    use_max_min: bpy.props.BoolProperty(
        name="Use Max Min",
        description="Use max min for the channel",
        default=False,
        options={'SKIP_SAVE'}
    )
    factor_min: bpy.props.FloatProperty(
        name="Factor Value Min",
        description="Minimum value for the factor",
        default=0,
        options={'SKIP_SAVE'}
    )
    factor_max: bpy.props.FloatProperty(
        name="Factor Value Max",
        description="Maximum value for the factor",
        default=1,
        options={'SKIP_SAVE'}
    )
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)

        # Apply template defaults
        channel_type = self.channel_type
        color_space = self.color_space
        normalize_input = self.normalize_input
        use_alpha = self.use_alpha
        use_max_min = self.use_max_min
        factor_min = self.factor_min
        factor_max = self.factor_max

        match self.template:
            case 'COLOR':
                channel_type = 'COLOR'
                color_space = 'COLOR'
                use_alpha = True
            case 'ROUGHNESS':
                channel_type = 'FLOAT'
                color_space = 'NON_COLOR'
                use_max_min = False
            case 'METALLIC':
                channel_type = 'FLOAT'
                color_space = 'NON_COLOR'
                use_max_min = False
            case 'NORMAL':
                channel_type = 'VECTOR'
                color_space = 'NON_COLOR'
                normalize_input = True
            case 'EMISSION':
                channel_type = 'COLOR'
                color_space = 'COLOR'
                use_alpha = False
            case 'AO':
                channel_type = 'FLOAT'
                color_space = 'NON_COLOR'
            case 'DISPLACEMENT':
                channel_type = 'FLOAT'
                color_space = 'NON_COLOR'
            case _:
                pass

        new_channel = ps_ctx.active_group.create_channel(
            context,
            channel_name=self.channel_name,
            channel_type=channel_type,
            color_space=color_space,
            use_alpha=use_alpha,
            normalize_input=normalize_input,
            use_max_min=use_max_min,
            factor_min=factor_min,
            factor_max=factor_max,
            vector_space="OBJECT" if channel_type == "VECTOR" else "NONE"
        )

        # Optionally create a starter image layer
        if self.create_starter_layer and new_channel:
            # Derive UV defaults
            coord_type = 'UV'
            uv_name = ''
            obj = ps_ctx.ps_object
            if obj and getattr(obj.data, 'uv_layers', None):
                uv_layers = obj.data.uv_layers
                active_uv = next((uv for uv in uv_layers if getattr(uv, 'active', False)), None)
                uv_name = active_uv.name if active_uv else ''

            # Create an image suitable for painting
            img_name = f"{new_channel.name}"
            try:
                image = bpy.data.images.new(img_name, width=2048, height=2048, alpha=True)
                image.generated_color = (0, 0, 0, 0)
            except Exception:
                image = None

            new_channel.create_layer(
                context,
                layer_name=f"{new_channel.name} Image",
                layer_type="IMAGE",
                coord_type=coord_type,
                uv_map_name=uv_name,
                image=image,
            )

        redraw_panel(context)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        """Invoke the operator to create a new channel."""
        self.channel_name = self.get_unique_channel_name(context)
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "channel_name", text="Name")
        layout.prop(self, "template", text="Template")
        layout.prop(self, "channel_type", text="Type")
        layout.prop(self, "color_space", text="Color Space")
        layout.prop(self, "use_alpha", text="Expose Alpha Socket")
        if self.channel_type == "VECTOR":
            layout.prop(self, "normalize_input", text="Normalize")
        layout.prop(self, "create_starter_layer", text="Create Starter Image Layer")
        unique_name = self.get_unique_channel_name(context)
        if unique_name != self.channel_name:
            box = layout.box()
            box.alert = True
            box.alignment = 'CENTER'
            box.label(text=f"Name will be changed to '{unique_name}'", icon='ERROR')
        if self.channel_type == "FLOAT":
            layout.prop(self, "use_max_min", text="Use Max Min")
            if self.use_max_min:
                layout.prop(self, "factor_min", text="Factor Min")
                layout.prop(self, "factor_max", text="Factor Max")

class PAINTSYSTEM_OT_DeleteChannel(PSContextMixin, MultiMaterialOperator):
    """Delete the selected channel in the Paint System"""
    bl_idname = "paint_system.delete_channel"
    bl_label = "Delete Channel"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        return bool(ps_mat_data and ps_mat_data.active_index >= 0)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, title="Delete Channel", width=300)

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_group.delete_channel(context, ps_ctx.active_channel)
        redraw_panel(context)
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.label(text=f"Are you sure you want to delete '{ps_ctx.active_group.channels[ps_ctx.active_group.active_index].name}' Channel?")


class PAINTSYSTEM_OT_MoveChannelUp(PSContextMixin, MultiMaterialOperator):
    """Move the selected channel in the Paint System"""
    bl_idname = "paint_system.move_channel_up"
    bl_label = "Move Channel"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_group = ps_ctx.active_group
        lm = ListManager(active_group, 'channels', active_group, 'active_index')
        return bool(active_group and active_group.active_index >= 0 and "UP" in lm.possible_moves())
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        lm = ListManager(active_group, 'channels', active_group, 'active_index')
        lm.move_active_up()
        ps_ctx.active_group.update_node_tree(context)
        redraw_panel(context)
        return {'FINISHED'}

class PAINTSYSTEM_OT_MoveChannelDown(PSContextMixin, MultiMaterialOperator):
    """Move the selected channel in the Paint System"""
    bl_idname = "paint_system.move_channel_down"
    bl_label = "Move Channel"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_group = ps_ctx.active_group
        lm = ListManager(active_group, 'channels', active_group, 'active_index')
        return bool(active_group and active_group.active_index >= 0 and "DOWN" in lm.possible_moves())
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        lm = ListManager(active_group, 'channels', active_group, 'active_index')
        lm.move_active_down()
        ps_ctx.active_group.update_node_tree(context)
        redraw_panel(context)
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_AddChannel,
    PAINTSYSTEM_OT_DeleteChannel,
    PAINTSYSTEM_OT_MoveChannelUp,
    PAINTSYSTEM_OT_MoveChannelDown,
)

register, unregister = bpy.utils.register_classes_factory(classes)