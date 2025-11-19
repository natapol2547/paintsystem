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
        
        # Main toggle button with pressed state
        row.operator("paint_system.toggle_transform_gizmos", text="Transform Gizmo", icon='GIZMO', depress=gizmos_enabled)
        
        # Individual gizmo type toggles (grayed out when main toggle is off)
        row = row.row(align=True)
        row.enabled = gizmos_enabled
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


class MAT_PT_PaintSystemQuickToolsPaint(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_PaintSystemQuickToolsPaint'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Paint"
    bl_category = 'Quick Tools'
    # bl_parent_id = 'MAT_PT_PaintSystemQuickTools'
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        obj = ps_ctx.active_object
        return obj and hasattr(obj, "mode") and obj.mode == 'TEXTURE_PAINT'
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="BRUSHES_ALL")
    
    def draw(self, context):
        from bl_ui.properties_paint_common import UnifiedPaintPanel
        from ..utils.unified_brushes import get_unified_settings
        
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False
        
        ps_ctx = self.parse_context(context)
        
        # Get paint settings and brush
        settings = UnifiedPaintPanel.paint_settings(context)
        if not settings:
            return
        brush = settings.brush
        
        # Get unified settings for color
        prop_owner = get_unified_settings(context, "use_unified_color")
        if not prop_owner or not hasattr(prop_owner, 'color'):
            prop_owner = brush
        
        # Compact Color Wheel
        if prop_owner and hasattr(prop_owner, 'color'):
            # Color picker settings button (dropdown)
            row = layout.row(align=True)
            row.popover(
                panel="MAT_PT_BrushColorSettings",
                icon="SETTINGS",
                text="Color Picker Settings"
            )
            
            # Compact color picker with value slider
            row = layout.row()
            row.scale_y = 1.5
            row.template_color_picker(prop_owner, "color", value_slider=True)
            
            # Show "No Active Channel" alert between wheel and swatches
            if not brush:
                box = layout.box()
                box.alert = True
                box.label(text="No Active Channel", icon='INFO')
            
            # Color swatches row
            row = layout.row(align=True)
            row.prop(prop_owner, "color", text="")
            # Add eyedropper
            try:
                use_unified = getattr(context.tool_settings.unified_paint_settings, 'use_unified_color', False) if hasattr(context.tool_settings, 'unified_paint_settings') else False
                path = (
                    "tool_settings.unified_paint_settings.color" if use_unified else
                    "tool_settings.image_paint.brush.color"
                )
                props = row.operator("ui.eyedropper_color", text="", icon='EYEDROPPER')
                props.prop_data_path = path
            except Exception:
                pass
        
        # Blend Mode
        if brush:
            layout.label(text="Blend:")
            layout.prop(brush, "blend", text="")
        
        # Radius & Strength
        size_owner = get_unified_settings(context, "use_unified_size")
        if size_owner:
            if hasattr(size_owner, 'size'):
                layout.prop(size_owner, "size", text="Radius", slider=True)
            if hasattr(size_owner, 'strength'):
                layout.prop(size_owner, "strength", text="Strength", slider=True)
        
        # Palette (if available)
        if hasattr(settings, 'palette') and settings.palette:
            layout.separator()
            layout.template_palette(settings, "palette", color=True)
            layout.template_ID(settings, "palette", new="palette.new")
        
        # Quick Edit button
        layout.separator()
        row = layout.row()
        scale_content(context, row, 1.5, 1.5)
        row.operator("paint_system.quick_edit", text="Edit Externally", icon='IMAGE')


classes = (
    MAT_PT_PaintSystemQuickToolsDisplay,
    MAT_PT_PaintSystemQuickToolsMesh,
    MAT_PT_PaintSystemQuickToolsPaint,
)

register, unregister = register_classes_factory(classes)    