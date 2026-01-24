import bpy
from datetime import datetime
from bpy.utils import register_classes_factory
from bpy.types import Panel, Menu, UIList

from ..paintsystem.version_check import get_latest_version

from ..utils.version import is_newer_than, is_online

from ..paintsystem.donations import get_donation_info
from .common import (
    PSContextMixin,
    get_icon,
    line_separator,
    scale_content,
    check_group_multiuser,
    toggle_paint_mode_ui
)

from ..paintsystem.data import LegacyPaintSystemContextParser

creators = [
    ("Tawan Sunflower", "https://x.com/himawari_hito"),
    ("@blastframe", "https://github.com/blastframe"),
    ("Pink.Ninjaa", "https://pinkninjaa.net/"),
    ("Zoomy Toons", "https://www.youtube.com/channel/UCNCKsXWIBFoWH6cMzeHmkhA")
]

def align_center(layout):
    row = layout.row(align=True)
    row.alignment = 'CENTER'
    return row

class MAT_PT_Support(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_Support'
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_label = "Support"
    bl_options = {"INSTANCED"}
    bl_ui_units_x = 10
    

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        row = layout.row(align=True)
        row.scale_x = 1.5
        row.scale_y = 1.5
        row.operator('wm.url_open', text="Support us!",
                        icon='FUND', depress=True).url = "https://tawansunflower.gumroad.com/l/paint_system"
        if is_online():
            donations_box = layout.box()
            donation_info = get_donation_info()
            col = donations_box.column(align=True)
            row = align_center(col)
            row.template_icon(get_icon("star"))
            row.label(text=f"Recent Donations:")
            row.template_icon(get_icon("star"))
            
            if ps_ctx.ps_settings is None or ps_ctx.ps_settings.loading_donations:
                align_center(col).label(text="Loading...", icon="INFO")
            if donation_info:
                if donation_info['recentDonations'] and len(donation_info['recentDonations']) > 0:
                    line_separator(col)
                    date_format = '%d-%m-%y %H:%M'
                    # year is current year
                    current_year = datetime.now().year
                    for idx, donation in enumerate(donation_info['recentDonations'][:3]):
                        donation_year = datetime.fromisoformat(donation['timestamp']).year
                        if donation_year != current_year:
                            date_format = '%d %b %y %H:%M'
                        else:
                            date_format = '%d %b %H:%M'
                        row = align_center(col)
                        row.enabled = idx == 0
                        row.label(text=f"${donation['price']} donated on {datetime.fromisoformat(donation['timestamp']).strftime(date_format)}")
        align_center(layout).label(text="But more importantly,")
        row = layout.row(align=True)
        row.scale_x = 1.5
        row.scale_y = 1.5
        row.operator('wm.url_open', text="Donate to Blender Foundation!!!",
                        icon='BLENDER').url = "https://fund.blender.org/"
        header, content = layout.panel("paintsystem_credits", default_closed=True)
        header.label(text="Credits:")
        if content:
            for idx, creator in enumerate(creators):
                column = content.column(align=True)
                column.operator('wm.url_open', text=creator[0],
                                icon='URL').url = creator[1]

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
            if mat and hasattr(mat, "paint_system") and mat.paint_system.groups:
                op = layout.operator("paint_system.select_material_index", text=material_slot.material.name if mat else "Empty Material", icon="MATERIAL" if mat else "MESH_CIRCLE", depress=is_selected)
            else:
                op = layout.operator("paint_system.select_material_index", text=material_slot.material.name if mat else "Empty Material", icon="MATERIAL" if mat else "MESH_CIRCLE", depress=is_selected)
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
        groups = ps_ctx.ps_mat_data.groups
        if ps_ctx.ps_mat_data and groups:
            if len(groups) > 1:
                row.popover("MAT_PT_PaintSystemGroups", text="", icon="NODETREE")
            row.operator("paint_system.new_group", icon='ADD', text="")
            row.operator("wm.call_menu", text="", icon="REMOVE").name = "MAT_MT_DeleteGroupMenu"
        else:
            row.popover("MAT_PT_Support", icon="FUND", text="Wah!")
    
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
        if is_online() and ps_ctx.ps_settings:
            # Trigger version check (non-blocking)
            get_latest_version()
            
            # Check update state
            update_state = ps_ctx.ps_settings.update_state
            if update_state == 'AVAILABLE':
                box = layout.box()
                box.alert = True
                row = box.row()
                row.label(text="Update Available", icon="INFO")
                row.operator("paint_system.dismiss_update", text="", icon="X")
                row = box.row()
                scale_content(context, row)
                row.operator("paint_system.open_extension_preferences", text="Update Paint System", icon="FILE_REFRESH")
            # elif update_state == 'LOADING':
            #     box = layout.box()
            #     box.label(text="Checking for updates...", icon="INFO")
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
            # Show a warning
            box = layout.box()
            box.alert = True
            box.label(text="Duplicated Paint System Data", icon="ERROR")
            row = box.row(align=True)
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

class MAT_MT_DeleteGroupMenu(PSContextMixin, Menu):
    bl_label = "Delete Group"
    bl_idname = "MAT_MT_DeleteGroupMenu"
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        
        if layout.operator_context == 'EXEC_REGION_WIN':
            layout.operator_context = 'INVOKE_REGION_WIN'
        layout.operator_context = 'INVOKE_REGION_WIN'
        
        layout.alert = True
        layout.operator("paint_system.delete_group", text="Remove Paint System", icon="TRASH")


classes = (
    MAT_PT_Support,
    MAT_PT_PaintSystemMaterialSettings,
    MATERIAL_UL_PaintSystemGroups,
    MAT_MT_PaintSystemMaterialSelectMenu,
    MAT_PT_PaintSystemMainPanel,
    MAT_PT_PaintSystemGroups,
    MAT_MT_DeleteGroupMenu,
)

register, unregister = register_classes_factory(classes)