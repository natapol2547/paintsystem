import bpy
from bpy.utils import register_classes_factory
from bpy.types import Panel, Menu, UIList
from bl_ui.properties_paint_common import (
    UnifiedPaintPanel
)

from .channels_panels import draw_channels_settings_panel, poll_channels_panel, draw_channels_panel
from .extras_panels import poll_brush_color_settings, draw_brush_color_settings, poll_brush_settings, draw_brush_settings

from ..utils.version import is_newer_than

from .common import (
    PSContextMixin,
    draw_indent,
    get_icon,
    get_icon_from_channel,
    line_separator,
    scale_content,
    check_group_multiuser,
    toggle_paint_mode_ui,
    ensure_invoke_context,
    draw_warning_box,
)

from ..paintsystem.data import LegacyPaintSystemContextParser

class MAT_MT_PaintSystemMaterialSelectMenu(PSContextMixin, Menu):
    bl_label = "Material Select Menu"
    bl_idname = "MAT_MT_PaintSystemMaterialSelectMenu"

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        ob = ps_ctx.ps_object
        for idx, material_slot in enumerate(ob.material_slots):
            is_selected = ob.active_material_index == idx
            mat = material_slot.material is not None
            op = layout.operator(
                "paint_system.select_material_index",
                text=material_slot.material.name if mat else "Empty Material",
                icon="MATERIAL" if mat else "MESH_CIRCLE",
                depress=is_selected,
            )
            op.index = idx


# class MAT_MT_PaintsystemTemplateSelectMenu(PSContextMixin, Menu):
#     bl_label = "Template Select Menu"
#     bl_idname = "MAT_MT_PaintsystemTemplateSelectMenu"
    
#     def draw(self, context):
#         layout = self.layout
#         ps_ctx = self.parse_context(context)
#         for template in TEMPLATE_ENUM:
#             op = layout.operator("paint_system.new_group", text=template[0], icon=template[3])
#             op.template = template[0]

class MATERIAL_UL_PaintSystemGroups(PSContextMixin, UIList):
    bl_idname = "MATERIAL_UL_PaintSystemGroups"
    bl_label = "Paint System Groups"
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        layout.prop(item, "name", text="", emboss=False)


class MAT_PT_PaintSystemGroups(PSContextMixin, Panel):
    bl_idname = "MAT_PT_PaintSystemGroups"
    bl_label = "Groups"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"INSTANCED"}
    bl_ui_units_x = 12

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        layout.label(text="Groups")
        scale_content(context, layout)
        layout.template_list("MATERIAL_UL_PaintSystemGroups", "", ps_ctx.ps_mat_data, "groups", ps_ctx.ps_mat_data, "active_index")


class MAT_PT_PaintSystemMaterialSettings(PSContextMixin, Panel):
    bl_idname = "MAT_PT_PaintSystemMaterialSettings"
    bl_label = "Material Settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_options = {"INSTANCED"}
    bl_ui_units_x = 12
    
    def draw(self, context):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        ob = ps_ctx.ps_object
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        if not ps_ctx.ps_settings.use_legacy_ui:
            row = layout.row(align=True)
            scale_content(context, row, 1.5, 1.2)
            row.menu("MAT_MT_PaintSystemMaterialSelectMenu", text="" if ob.active_material else "Empty Material", icon="MATERIAL" if ob.active_material else "MESH_CIRCLE")
            if mat:
                row.prop(mat, "name", text="")
        layout.prop(mat, "surface_render_method", text="Render Method")
        layout.prop(mat, "use_backface_culling", text="Backface Culling")
        if ps_ctx.ps_mat_data and ps_ctx.ps_mat_data.groups:
            box = layout.box()
            box.label(text=f"Paint System Node Groups:", icon_value=get_icon("sunflower"))
            row = box.row(align=True)
            scale_content(context, row, 1.3, 1.2)
            row.popover("MAT_PT_PaintSystemGroups", text="", icon="NODETREE")
            row.prop(ps_ctx.active_group, "name", text="")
            row.operator("paint_system.new_group", icon='ADD', text="")
            row.operator("wm.call_menu", text="", icon="REMOVE").name = "MAT_MT_DeleteGroupMenu"

class MAT_PT_PaintSystemMainPanel(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemMainPanel'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Paint System"
    bl_category = 'Paint System'
    
    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        row = layout.row(align=True)
        if ps_ctx.ps_mat_data is None:
            return
        groups = ps_ctx.ps_mat_data.groups
        if ps_ctx.ps_mat_data and groups:
            if len(groups) > 1:
                row.popover("MAT_PT_PaintSystemGroups", text="", icon="NODETREE")
            row.operator("paint_system.new_group", icon='ADD', text="")
            row.operator("wm.call_menu", text="", icon="REMOVE").name = "MAT_MT_DeleteGroupMenu"
        else:
            row.operator("paint_system.new_group", icon='ADD', text="")
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon_value=get_icon("sunflower"))

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        legacy_ps_ctx = LegacyPaintSystemContextParser(context)
        legacy_material_settings = legacy_ps_ctx.get_material_settings()
        if legacy_material_settings and legacy_material_settings.groups:
            box = layout.box()
            col = box.column()
            warning_box = col.box()
            col = warning_box.column()
            col.alert = True
            col.label(text="Legacy Paint System Detected", icon="ERROR")
            col.label(text="Please save as before updating")
            row = warning_box.row()
            scale_content(context, row)
            row.operator("wm.save_as_mainfile", text="Save As")
            row = warning_box.row()
            row.alert = True
            scale_content(context, row)
            row.operator("paint_system.update_paint_system_data", text="Update Paint System Data", icon="FILE_REFRESH")
            
            return
        ps_ctx = self.parse_context(context)
        if ps_ctx.ps_settings and not ps_ctx.ps_settings.use_legacy_ui and ps_ctx.active_channel:
            toggle_paint_mode_ui(layout, context)
        ob = ps_ctx.ps_object
        if ob.type != 'MESH':
            return
        
        if ps_ctx.ps_settings.use_legacy_ui:
            mat = ps_ctx.active_material
            if any([ob.material_slots[i].material for i in range(len(ob.material_slots))]):
                col = layout.column(align=True)
                row = col.row(align=True)
                scale_content(context, row, 1.5, 1.2)
                row.menu("MAT_MT_PaintSystemMaterialSelectMenu", text="" if ob.active_material else "Empty Material", icon="MATERIAL" if ob.active_material else "MESH_CIRCLE")
                if mat:
                    row.prop(mat, "name", text="")
                
                # row.operator("object.material_slot_add", icon='ADD', text="")
                if mat:
                    row.popover("MAT_PT_PaintSystemMaterialSettings", text="", icon="PREFERENCES")
        

        if ps_ctx.active_group and check_group_multiuser(ps_ctx.active_group.node_tree):
            warning_col = draw_warning_box(layout, [
                ("Duplicated Paint System Data", 'ERROR'),
            ])
            row = warning_col.row(align=True)
            scale_content(context, row, 1.5, 1.5)
            row.operator("paint_system.duplicate_paint_system_data", text="Fix Data Duplication")
            return

        if not ps_ctx.active_group:
            row = layout.row()
            row.scale_x = 2
            row.scale_y = 2
            row.operator("paint_system.new_group", text="Add Paint System", icon="ADD")
            return
        # layout.label(text="Welcome to the Paint System!")
        # layout.operator("paint_system.new_image_layer", text="Create New Image Layer")
        
        if poll_channels_panel(context):
            header, panel = layout.panel("MAT_PT_ChannelsPanel", default_closed=True)
            header.label(text="Channels", icon_value=get_icon('channel'))
            if panel:
                draw_channels_panel(panel, context)
            else:
                row = header.row(align=True)
                row.scale_x = 1.1
                row.alignment = 'RIGHT'
                row.popover(
                    panel="MAT_PT_ChannelsSelect",
                    text=ps_ctx.active_channel.name if ps_ctx.active_channel else "No Channel",
                    icon_value=get_icon_from_channel(ps_ctx.active_channel)
                )
        if poll_brush_settings(context):
            header, panel = layout.panel("MAT_PT_Brush", default_closed=True)
            header.label(text="Brush", icon_value=get_icon('brush'))
            if ps_ctx.ps_settings.show_tooltips:
                header.popover(
                    panel="MAT_PT_BrushTooltips",
                    text='',
                    icon='INFO_LARGE' if is_newer_than(4,3) else 'INFO'
                )
            if panel:
                draw_brush_settings(panel, context)
        if poll_brush_color_settings(context):
            header, panel = layout.panel("MAT_PT_BrushColor", default_closed=True)
            header.label(text="Color", icon_value=get_icon('color'))
            if panel:
                row = header.row(align=True)
                row.scale_x = 1.1
                row.alignment = 'RIGHT'
                row.popover(
                    panel="MAT_PT_BrushColorSettings",
                    text="Settings",
                    icon="SETTINGS"
                )
                draw_brush_color_settings(panel, context)
            else:
                settings = UnifiedPaintPanel.paint_settings(context)
                brush = settings.brush
                row = header.row(align=True)
                row.alignment = 'RIGHT'
                if ps_ctx.ps_object.type == 'MESH':
                    split = row.split(factor=0.5, align=True)
                    split.scale_x = 1
                    split.alignment = 'RIGHT'
                    UnifiedPaintPanel.prop_unified_color(split, context, brush, "color", text="")
                    UnifiedPaintPanel.prop_unified_color(split, context, brush, "secondary_color", text="")
                    row.operator('paint.brush_colors_flip', icon='FILE_REFRESH', text="")
                elif ps_ctx.ps_object.type == 'GREASEPENCIL':
                    row.prop(brush, "color", text="")

class MAT_MT_DeleteGroupMenu(PSContextMixin, Menu):
    bl_label = "Delete Group"
    bl_idname = "MAT_MT_DeleteGroupMenu"
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        ensure_invoke_context(layout)
        
        layout.alert = True
        layout.operator("paint_system.delete_group", text="Remove Paint System", icon="TRASH")


classes = (
    MAT_PT_PaintSystemMaterialSettings,
    MATERIAL_UL_PaintSystemGroups,
    MAT_MT_PaintSystemMaterialSelectMenu,
    MAT_PT_PaintSystemMainPanel,
    MAT_PT_PaintSystemGroups,
    MAT_MT_DeleteGroupMenu,
)

register, unregister = register_classes_factory(classes)