import bpy
from bpy.types import Panel

from .common import scale_content
from ..paintsystem.data import PSContextMixin
from bpy.utils import register_classes_factory


class MAT_PT_PaintSystemQuickToolsDisplay(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemQuickToolsDisplay'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Display"
    bl_category = 'Quick Tools'
    # bl_parent_id = 'MAT_PT_PaintSystemQuickTools'

    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="HIDE_OFF")

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.active_object
        layout = self.layout
        
        # Safety check for space
        if not context.area or not context.area.spaces:
            return
        space = context.area.spaces[0]
        if space.type != 'VIEW_3D':
            return

        box = layout.box()
        if obj and hasattr(obj, 'mode'):
            row = box.row()
            scale_content(context, row)
            # Different wireframe toggle based on mode
            if obj.mode == 'EDIT':
                # In edit mode, toggle overlay wireframe
                overlay = space.overlay
                if overlay:
                    row.prop(overlay, "show_wireframes", text="Toggle Wireframe", icon='MOD_WIREFRAME')
            else:
                # In object mode, toggle object wireframe display
                row.prop(obj, "show_wire", text="Toggle Wireframe", icon='MOD_WIREFRAME')
        
        row = box.row()
        if ps_ctx.ps_settings and not ps_ctx.ps_settings.use_compact_design:
            row.scale_y = 1
            row.scale_x = 1
        
        # Toggle gizmo button with state memory
        gizmos_enabled = (space.show_gizmo_object_translate or 
                         space.show_gizmo_object_rotate or 
                         space.show_gizmo_object_scale)
        
        # Check if in paint/sculpt mode
        in_paint_mode = obj and obj.mode in {'PAINT_TEXTURE', 'SCULPT', 'PAINT_VERTEX', 'PAINT_WEIGHT'}
        
        # In paint mode, show the stored preference state (what gizmos will be when exiting)
        # Otherwise show actual gizmo state
        if in_paint_mode:
            wm = context.window_manager
            stored_enabled = wm.get("ps_gizmo_translate", True) or wm.get("ps_gizmo_rotate", True) or wm.get("ps_gizmo_scale", False)
            display_state = stored_enabled
        else:
            display_state = gizmos_enabled
        
        row.operator("paint_system.toggle_transform_gizmos", text="Transform Gizmo", icon='GIZMO', depress=display_state)
        
        # Individual gizmo type toggles (grayed out when main toggle is off or in paint mode)
        row = row.row(align=True)
        row.enabled = gizmos_enabled and not in_paint_mode
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

    def draw_header(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.label(icon="MESH_CUBE")

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.active_object
        layout = self.layout
        
        # Safety check for space
        if not context.area or not context.area.spaces:
            return
        space = context.area.spaces[0]
        if space.type != 'VIEW_3D':
            return
        
        overlay = space.overlay
        if not overlay:
            return

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
        if obj and hasattr(obj, 'scale') and (obj.scale[0] != 1 or obj.scale[1] != 1 or obj.scale[2] != 1):
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


classes = (
    MAT_PT_PaintSystemQuickToolsDisplay,
    MAT_PT_PaintSystemQuickToolsMesh,
)

register, unregister = register_classes_factory(classes)  # type: ignore[misc]