import bpy
from bpy.utils import register_classes_factory
from bpy.types import Panel, Menu, UIList
from .common import (
    PSContextMixin,
    get_icon,
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

class MAT_PT_Support(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_Support'
    bl_space_type = "VIEW_3D"
    bl_region_type = "WINDOW"
    bl_label = "Support"
    bl_options = {"INSTANCED"}
    bl_ui_units_x = 10
    

    def draw(self, context):
        layout = self.layout
        layout.label(text="Addon created by:")
        for creator in creators:
            layout.operator('wm.url_open', text=creator[0],
                            icon='URL').url = creator[1]
        layout.separator()
        layout.operator('wm.url_open', text="Support us!",
                        icon='FUND', depress=True).url = "https://tawansunflower.gumroad.com/l/paint_system"

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
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        layout.prop(mat, "surface_render_method", text="Render Method")
        layout.prop(mat, "use_backface_culling", text="Backface Culling")
        if ps_ctx.ps_mat_data and ps_ctx.ps_mat_data.groups:
            box = layout.box()
            box.label(text=f"Paint System Groups:", icon_value=get_icon("sunflower"))
            row = box.row(align=True)
            scale_content(context, row, 1.2, 1.2)
            row.popover("MAT_PT_PaintSystemGroups", text=ps_ctx.active_group.name, icon="NODETREE")
            row.operator("paint_system.new_group", icon='ADD', text="")
            row.operator("paint_system.delete_group", icon='REMOVE', text="")

class MAT_PT_PaintSystemMainPanel(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemMainPanel'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Paint System"
    bl_category = 'Paint System'
    
    def draw_header_preset(self, context):
        layout = self.layout
        layout.popover("MAT_PT_Support", icon="FUND", text="Wah!")
    
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
        if not ps_ctx.ps_settings.use_legacy_ui and ps_ctx.active_channel:
            toggle_paint_mode_ui(layout, context)
            # Expose Use Baked Image only in the main panel when a baked image exists
            if ps_ctx.ps_object.type == 'MESH' and ps_ctx.active_channel.bake_image:
                row = layout.row(align=True)
                row.prop(ps_ctx.active_channel, "use_bake_image", text="Use Baked Image", icon="TEXTURE_DATA")
        ob = ps_ctx.ps_object
        if ob.type != 'MESH':
            return
        
        if ps_ctx.ps_settings.use_legacy_ui:
            mat = ps_ctx.active_material
            groups = ps_ctx.ps_mat_data.groups if mat else []
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


classes = (
    MAT_PT_Support,
    MAT_PT_PaintSystemMaterialSettings,
    MATERIAL_UL_PaintSystemGroups,
    MAT_MT_PaintSystemMaterialSelectMenu,
    MAT_PT_PaintSystemMainPanel,
    MAT_PT_PaintSystemGroups,
)

register, unregister = register_classes_factory(classes)