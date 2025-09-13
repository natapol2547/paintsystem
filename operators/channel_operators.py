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
        name="Use Alpha",
        description="Use alpha for the new channel",
        default=True
    )
    use_normalize: bpy.props.BoolProperty(
        name="Normalize Channel",
        description="Normalize the channel",
        default=False
    )
    use_max_min: bpy.props.BoolProperty(
        name="Use Max Min",
        description="Use max min for the channel",
        default=False
    )
    factor_min: bpy.props.FloatProperty(
        name="Factor Value Min",
        description="Minimum value for the factor",
        default=0
    )
    factor_max: bpy.props.FloatProperty(
        name="Factor Value Max",
        description="Maximum value for the factor",
        default=1
    )
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        channels = ps_ctx.active_group.channels
        node_tree = bpy.data.node_groups.new(name=f"PS_Channel ({self.channel_name})", type='ShaderNodeTree')
        new_channel = channels.add()
        ps_ctx.active_group.active_index = len(channels) - 1
        unique_name = self.get_unique_channel_name(context)
        new_channel.name = unique_name
        new_channel.type = self.channel_type
        new_channel.use_alpha = self.use_alpha
        new_channel.use_normalize = self.use_normalize
        new_channel.color_space = self.color_space
        new_channel.use_max_min = self.use_max_min
        if self.channel_type == "FLOAT" and new_channel.use_max_min:
            new_channel.factor_min = self.factor_min
            new_channel.factor_max = self.factor_max
        new_channel.node_tree = node_tree
        new_channel.update_node_tree(context)
        ps_ctx.active_group.update_node_tree(context)
        redraw_panel(context)
        return {'FINISHED'}
    
    def invoke(self, context, event):
        """Invoke the operator to create a new channel."""
        self.channel_name = self.get_unique_channel_name(context)
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "channel_name", text="Name")
        layout.prop(self, "channel_type", text="Type")
        layout.prop(self, "color_space", text="Color Space")
        layout.prop(self, "use_alpha", text="Use Alpha")
        if self.channel_type == "VECTOR":
            layout.prop(self, "use_normalize", text="Normalize")
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

    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        active_index = ps_ctx.active_group.active_index
        if active_index < 0 or active_index >= len(ps_ctx.active_group.channels):
            self.report({'ERROR'}, "No valid channel selected")
            return {'CANCELLED'}
        
        ps_ctx.active_group.channels.remove(active_index)
        ps_ctx.active_group.active_index = max(0, active_index - 1)
        ps_ctx.active_group.update_node_tree(context)
        redraw_panel(context)
        return {'FINISHED'}


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