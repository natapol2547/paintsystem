import bpy
from bpy.types import UIList, Menu
from bpy.utils import register_classes_factory
from bpy.types import Panel
from bpy_extras.node_utils import find_base_socket_type

from ..paintsystem.data import CHANNEL_TEMPLATE_ENUM
from .common import (
    PSContextMixin,
    get_icon_from_channel,
    check_group_multiuser,
    get_icon,
)

class MAT_MT_PaintSystemChannelsMergeAndExport(PSContextMixin, Menu):
    bl_label = "Baked and Export"
    bl_idname = "MAT_MT_PaintSystemChannelsMergeAndExport"
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        col = layout.column(align=True)
        col.label(text="Bake")
        col.operator("paint_system.bake_all_channels", text=f"Bake All Channels", icon_value=get_icon('channels'))
        col.operator("paint_system.bake_channel", text=f"Bake Active Channel ({active_channel.name})", icon_value=get_icon_from_channel(active_channel))
        # col.operator("paint_system.bake_all_channels", text="Bake all Channels")
        col.separator()
        col.label(text="Export")
        col.operator("paint_system.export_all_images", text="Export All Images", icon='EXPORT')
        if active_channel.bake_image:
            col.operator("paint_system.export_image", text=f"Export Active Channel ({active_channel.name})", icon='EXPORT').image_name = active_channel.bake_image.name
        else:
            col.operator("paint_system.export_image", text=f"Export Active Channel ({active_channel.name})", icon='EXPORT')

class PAINTSYSTEM_UL_channels(PSContextMixin, UIList):
    """UIList for displaying paint channels."""

    def draw_item(self, context, layout: bpy.types.UILayout, data, item, icon, active_data, active_propname, index):
        channel = item
        ps_ctx = self.parse_context(context)
        if channel.use_bake_image:
            row = layout.row()
            icon_row = row.row(align=True)
            icon_row.label(icon_value=get_icon_from_channel(channel))
            icon_row.prop(channel, "name", text="", emboss=False)
            
            bake_row = row.row(align=True)
            bake_row.label(text="Baked", icon="TEXTURE_DATA")
            return
        split = layout.split(factor=0.7)
        group_node = ps_ctx.active_group.get_group_node(ps_ctx.active_material.node_tree)
        icon_row = split.row(align=True)
        icon_row.prop(channel, "type", text="", icon_only=True, emboss=False)
        icon_row.prop(channel, "name", text="", emboss=False)
        if group_node and channel.name in group_node.inputs:
            socket = group_node.inputs[channel.name]
            if socket.enabled and len(socket.links) == 0:
                socket_type = find_base_socket_type(socket)
                if socket_type == "NodeSocketColor":
                    split.prop(socket, "default_value", text="", icon="COLOR")
                elif socket_type == "NodeSocketFloat":
                    split.prop(socket, "default_value", text="")

    # def filter_items(self, context, data, propname):
    #     channels = getattr(data, propname)
    #     flt_flags = [self.bitflag_filter_item] * len(channels)
    #     flt_neworder = list(range(len(channels)))
    #     return flt_flags, flt_neworder

class MAT_PT_ChannelsSelect(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_ChannelsSelect'
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_label = "Channels"
    bl_options = {"INSTANCED"}
    bl_ui_units_x = 10
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        col = layout.column(align=True)
        col.label(text="Channels")
        row = col.row()
        row.template_list(
            "PAINTSYSTEM_UL_channels", 
            "",
            ps_ctx.active_group,
            "channels", 
            ps_ctx.active_group,
            "active_index",
            rows=max(len(ps_ctx.active_group.channels), 4),
        )
        col = row.column(align=True)
        col.operator("paint_system.add_channel", icon='ADD', text="")
        col.operator("paint_system.delete_channel", icon='REMOVE', text="")
        col.operator("paint_system.move_channel_up", icon='TRIA_UP', text="")
        col.operator("paint_system.move_channel_down", icon='TRIA_DOWN', text="")

class MAT_PT_ChannelsPanel(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_ChannelsPanel'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Channels"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_PaintSystemMainPanel'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if ps_ctx.active_group and check_group_multiuser(ps_ctx.active_group.node_tree):
            return False
        return ps_ctx.ps_mat_data and ps_ctx.active_group is not None
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon_value=get_icon('channel'))
        
    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        if ps_ctx.active_channel:
            layout.popover(
                panel="MAT_PT_ChannelsSelect",
                text=ps_ctx.active_channel.name if ps_ctx.active_channel else "No Channel",
                icon_value=get_icon_from_channel(ps_ctx.active_channel)
            )

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        if ps_ctx.ps_settings.use_legacy_ui:
            layout.menu("MAT_MT_PaintSystemChannelsMergeAndExport", icon="TEXTURE_DATA", text="Bake and Export")
        row = layout.row()
        row.template_list(
            "PAINTSYSTEM_UL_channels", 
            "",
            ps_ctx.active_group,
            "channels", 
            ps_ctx.active_group,
            "active_index",
            rows=max(len(ps_ctx.active_group.channels), 4),
        )
        col = row.column(align=True)
        
        available_templates = [template for template in CHANNEL_TEMPLATE_ENUM if not any(channel.name == template[1] for channel in ps_ctx.active_group.channels)]
        if available_templates:
            col.operator("wm.call_menu", icon='ADD', text="").name = "MAT_MT_AddChannelMenu"
        else:
            col.operator("paint_system.add_channel", icon='ADD', text="").template = "CUSTOM"
        col.operator("paint_system.delete_channel", icon='REMOVE', text="")
        col.operator("paint_system.move_channel_up", icon='TRIA_UP', text="")
        col.operator("paint_system.move_channel_down", icon='TRIA_DOWN', text="")


class MAT_PT_ChannelsSettings(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_ChannelsSettings'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Channels Settings"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_ChannelsPanel'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel is not None and len(ps_ctx.active_group.channels) > 0
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if active_channel.bake_image:
            row = layout.row(align=True)
            row.prop(active_channel, "use_bake_image", text="Use Baked Image", icon="TEXTURE_DATA")
            row.operator("paint_system.delete_bake_image", text="", icon="TRASH")
        col = layout.column(align=True)
        if active_channel.use_bake_image:
            if active_channel.type == "VECTOR":
                col.prop(active_channel, "bake_vector_space", text="")
            return
        box = col.box()
        col = box.column()
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(active_channel, "type", text="Type")
        col.prop(active_channel, "color_space", text="Color Space")
        col.prop(active_channel, "use_alpha", text="Use Alpha")
        if active_channel.use_alpha:
            group_node = ps_ctx.active_group.get_group_node(ps_ctx.active_material.node_tree)
            if group_node:
                socket = group_node.inputs[f"{active_channel.name} Alpha"]
                if socket.enabled and len(socket.links) == 0:
                    col.prop(socket, "default_value", text="Alpha")
        if active_channel.type == "VECTOR":
            col.prop(active_channel, "default_value", text="Default Value")
            box = col.box()
            box.use_property_split = False
            header, panel = box.panel("vector_space_settings_panel", default_closed=True)
            header.label(text="Vector Transform")
            if panel:
                row = panel.row(align=True)
                row.prop(active_channel, "use_space_transform_input", text="Transform Input", toggle=1)
                row.prop(active_channel, "use_space_transform_output", text="Transform Output", toggle=1)
                panel.use_property_split = True
                panel.prop(active_channel, "vector_type", text="Vector Type", expand=True)
                row = panel.row(align=True)
                row.enabled = active_channel.use_space_transform_input
                row.prop(active_channel, "input_vector_space", text="Input Space")
                row = panel.row(align=True)
                row.enabled = active_channel.use_space_transform_output or active_channel.use_space_transform_input
                row.prop(active_channel, "vector_space", text="Painting Space")
                if active_channel.vector_space != "TANGENT":
                    row.prop(active_channel, "normalize_input", text="", icon="NORMALS_VERTEX_FACE")
                row = panel.row(align=True)
                row.enabled = active_channel.use_space_transform_output
                row.prop(active_channel, "output_vector_space", text="Output Space")
                if active_channel.vector_space == "TANGENT" or active_channel.output_vector_space == "TANGENT":
                    panel.prop_search(active_channel, "tangent_uv_map", ps_ctx.ps_object.data, "uv_layers", text="Tangent UV", icon='GROUP_UVS')
        if active_channel.type == "FLOAT":
            float_box = col.box()
            col = float_box.column()
            col.use_property_split = False
            col.prop(active_channel, "use_max_min")
            if active_channel.use_max_min:
                col.prop(active_channel, "factor_min")
                col.prop(active_channel, "factor_max")

class MAT_MT_AddChannelMenu(PSContextMixin, Menu):
    bl_label = "Add Channel"
    bl_idname = "MAT_MT_AddChannelMenu"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None

    def draw(self, context):
        layout = self.layout
        
        if layout.operator_context == 'EXEC_REGION_WIN':
            layout.operator_context = 'INVOKE_REGION_WIN'
        layout.operator_context = 'INVOKE_REGION_WIN'
        
        ps_ctx = self.parse_context(context)
        col = layout.column()
        col.operator("paint_system.add_channel", text="Custom Channel", icon_value=get_icon('channels')).template = "CUSTOM"
        col.separator()
        available_templates = [template for template in CHANNEL_TEMPLATE_ENUM if not any(channel.name == template[1] for channel in ps_ctx.active_group.channels)]
        if available_templates:
            col.label(text="Templates")
            for template in available_templates:
                col.operator("paint_system.add_channel", text=template[1], icon_value=template[3]).template = template[0]

classes = (
    MAT_MT_PaintSystemChannelsMergeAndExport,
    PAINTSYSTEM_UL_channels,
    MAT_PT_ChannelsSelect,
    MAT_PT_ChannelsPanel,
    MAT_PT_ChannelsSettings,
    MAT_MT_AddChannelMenu,
)

register, unregister = register_classes_factory(classes)