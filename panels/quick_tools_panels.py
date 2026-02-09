import bpy
from bpy.types import Panel

from .common import scale_content, PSContextMixin, is_uv_edit_active
from bpy.utils import register_classes_factory


class MAT_PT_PaintSystemQuickToolsDisplay(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemQuickToolsDisplay'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Display"
    bl_category = 'Quick Tools'
    # bl_parent_id = 'MAT_PT_PaintSystemQuickTools'

    @classmethod
    def poll(cls, context):
        return not is_uv_edit_active(context)

    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="HIDE_OFF")

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.active_object
        layout = self.layout
        space = context.area.spaces[0]

        box = layout.box()
        if obj:
            row = box.row()
            scale_content(context, row)
            row.prop(obj,
                 "show_wire", text="Toggle Wireframe", icon='MOD_WIREFRAME')
        row = box.row()
        if not ps_ctx.ps_settings.use_compact_design:
            row.scale_y = 1
            row.scale_x = 1
        row.prop(space, "show_gizmo", text="Toggle Gizmo", icon='GIZMO')
        row = row.row(align=True)
        row.prop(space, "show_gizmo_object_translate",
                 text="", icon='EMPTY_ARROWS')
        row.prop(space, "show_gizmo_object_rotate",
                 text="", icon='FILE_REFRESH')
        row.prop(space, "show_gizmo_object_scale",
                 text="", icon='MOD_MESHDEFORM')


class MAT_PT_PaintSystemQuickToolsMesh(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemQuickToolsMesh'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Mesh"
    bl_category = 'Quick Tools'
    # bl_parent_id = 'MAT_PT_PaintSystemQuickTools'

    @classmethod
    def poll(cls, context):
        return not is_uv_edit_active(context)

    def draw_header(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.label(icon="MESH_CUBE")

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.active_object
        layout = self.layout
        space = context.area.spaces[0]
        overlay = space.overlay
        mode_string = context.mode

        box = layout.box()
        row = box.row()
        row.alignment = "CENTER"
        row.label(text="Add Mesh:", icon="PLUS")
        row = box.row()
        scale_content(context, row, 1.5, 1.5)
        row.alignment = 'CENTER'
        row.operator("paint_system.add_camera_plane",
                     text="", icon='IMAGE_PLANE')
        row.operator("mesh.primitive_plane_add",
                     text="", icon='MESH_PLANE')
        row.operator("mesh.primitive_cube_add",
                     text="", icon='MESH_CUBE')
        row.operator("mesh.primitive_circle_add",
                     text="", icon='MESH_CIRCLE')
        row.operator("mesh.primitive_uv_sphere_add",
                     text="", icon='MESH_UVSPHERE')

        box = layout.box()
        row = box.row()
        row.alignment = "CENTER"
        row.label(text="Normals:", icon="NORMALS_FACE")
        row = box.row()
        scale_content(context, row, 1.5, 1.5)
        row.prop(overlay,
                 "show_face_orientation", text="Toggle Check Normals", icon='HIDE_OFF' if overlay.show_face_orientation else 'HIDE_ON')
        row = box.row()
        row.operator('paint_system.recalculate_normals',
                     text="Recalculate", icon='FILE_REFRESH')
        row.operator('paint_system.flip_normals',
                     text="Flip", icon='DECORATE_OVERRIDE')

        box = layout.box()
        row = box.row()
        row.alignment = "CENTER"
        row.label(text="Transforms:", icon="EMPTY_ARROWS")
        if obj and (obj.scale[0] != 1 or obj.scale[1] != 1 or obj.scale[0] != 1):
            box1 = box.box()
            box1.alert = True
            col = box1.column(align=True)
            col.label(text="Object is not uniform!", icon="ERROR")
            col.label(text="Apply Transform -> Scale", icon="BLANK1")
        row = box.row()
        scale_content(context, row, 1.5, 1.5)
        row.menu("VIEW3D_MT_object_apply",
                 text="Apply Transform", icon="LOOP_BACK")
        row = box.row()
        scale_content(context, row, 1.5, 1.5)
        row.operator_menu_enum(
            "object.origin_set", text="Set Origin", property="type", icon="EMPTY_AXIS")


class MAT_PT_PaintSystemQuickToolsPaint(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemQuickToolsPaint'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Paint"
    bl_category = 'Quick Tools'
    # bl_parent_id = 'MAT_PT_PaintSystemQuickTools'
    
    @classmethod
    def poll(cls, context):
        if is_uv_edit_active(context):
            return False
        ps_ctx = cls.parse_context(context)
        obj = ps_ctx.active_object
        return hasattr(obj, "mode") and obj.mode == 'TEXTURE_PAINT'
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="BRUSHES_ALL")
    
    def draw(self, context):
        layout = self.layout
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.operator("paint_system.quick_edit", text="Edit Externally", icon='IMAGE')


classes = (
    MAT_PT_PaintSystemQuickToolsDisplay,
    MAT_PT_PaintSystemQuickToolsMesh,
    MAT_PT_PaintSystemQuickToolsPaint,
)

register, unregister = register_classes_factory(classes)    