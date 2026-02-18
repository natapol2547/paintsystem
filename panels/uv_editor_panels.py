import bpy
from bpy.types import Panel
from bpy.utils import register_classes_factory

from .common import PSContextMixin, draw_uv_edit_alert, draw_uv_edit_checker, scale_content


class IMAGE_PT_PaintSystemUVEdit(PSContextMixin, Panel):
    bl_idname = "IMAGE_PT_PaintSystemUVEdit"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_label = "Paint System"
    bl_category = "Paint System"
    bl_options = set()

    @classmethod
    def poll(cls, context):
        if not context.space_data or context.space_data.type != 'IMAGE_EDITOR':
            return False
        ui_mode = getattr(context.space_data, "ui_mode", None)
        if ui_mode is None:
            return True
        return ui_mode in {'UV', 'UV_EDIT'}

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        ps_scene_data = context.scene.ps_scene_data

        layout.use_property_split = True
        layout.use_property_decorate = False

        if not ps_ctx.ps_object:
            layout.label(text="No active Paint System object.", icon='ERROR')
            return

        if ps_scene_data.uv_edit_enabled:
            draw_uv_edit_alert(layout, context)
            options_box = layout.box()
            options_box.use_property_split = False
            options_box.use_property_decorate = False
            options_box.label(text="UV Options", icon='PREFERENCES')
            uv_editor = getattr(context.space_data, "uv_editor", None)
            space = context.space_data

            def toggle_if(col, obj, prop_name, text, icon):
                if obj and hasattr(obj, prop_name):
                    col.prop(obj, prop_name, text=text, toggle=True, icon=icon)
                    return True
                return False

            options_col = options_box.column(align=True)
            options_col.scale_y = 1.3
            options_col.scale_x = 1.3

            if not toggle_if(options_col, uv_editor, "use_image_bounds", "Constrain to Image Bounds", "IMAGE"):
                toggle_if(options_col, uv_editor, "use_image_clip", "Constrain to Image Bounds", "IMAGE")
            toggle_if(options_col, uv_editor, "use_live_unwrap", "Live Unwrap", "MOD_UVPROJECT")
            toggle_if(options_col, uv_editor, "use_custom_region", "UV Custom Region", "UV")
            if not toggle_if(options_col, uv_editor, "use_realtime_update", "Update Automatically", "TIME"):
                toggle_if(options_col, space, "use_realtime_update", "Update Automatically", "TIME")
            toggle_if(options_col, uv_editor, "lock_bounds", "Lock Bounds", "LOCKED")

            options_box.label(text="Snap to Pixel Options", icon='SNAP_ON')
            snap_row = options_box.row(align=True)
            snap_row.scale_y = 1.2
            snap_row.scale_x = 1.2
            toggle_if(snap_row, uv_editor, "use_snap_to_pixels", "Snap to Pixels", "SNAP_ON")
            if uv_editor and hasattr(uv_editor, "pixel_snap_mode"):
                snap_row.prop(uv_editor, "pixel_snap_mode", text="")
            if uv_editor and hasattr(uv_editor, "pixel_round_mode"):
                snap_row.prop(uv_editor, "pixel_round_mode", text="")
        else:
            fix_box = layout.box()
            fix_box.label(text="Fix UVs", icon='UV')
            fix_box.use_property_split = False
            fix_box.use_property_decorate = False

            active_row = fix_box.row(align=True)
            active_row.prop_search(ps_scene_data, "uv_edit_source_uv", ps_ctx.ps_object.data, "uv_layers", text="Active UV", icon='GROUP_UVS')
            action_col = fix_box.column(align=True)
            action_col.operator("paint_system.grab_active_layer_uv", text="Grab Current Layer UV", icon='EYEDROPPER')
            action_col.operator("paint_system.sync_uv_names", text="Sync UV Names", icon='FILE_REFRESH')
            action_col.operator("paint_system.clear_unused_uvs", text="Clear Unused UVs", icon='TRASH')
            action_col.prop(ps_scene_data, "uv_edit_keep_ps_prefix_uvs", text="Keep PS_ UVs")

            target_box = fix_box.box()
            target_box.use_property_split = False
            target_box.use_property_decorate = False
            target_box.label(text="Bake to Target", icon='UV_DATA')
            uv_layers = ps_ctx.ps_object.data.uv_layers if ps_ctx.ps_object else None
            existing_uv_count = len(uv_layers) if uv_layers else 0

            target_box.prop(ps_scene_data, "uv_edit_target_mode", text="")
            if ps_scene_data.uv_edit_target_mode == 'EXISTING':
                if existing_uv_count <= 1:
                    warn_box = target_box.box()
                    warn_box.alert = True
                    warn_box.label(text="No alternative UV maps found", icon='ERROR')
                target_row = target_box.row(align=True)
                target_row.prop_search(ps_scene_data, "uv_edit_target_uv", ps_ctx.ps_object.data, "uv_layers", text="", icon='GROUP_UVS')
            else:
                target_row = target_box.row(align=True)
                target_row.prop(ps_scene_data, "uv_edit_target_uv", text="UV Name", icon='GROUP_UVS')
                target_box.prop(ps_scene_data, "uv_edit_new_uv_method", text="")
                if ps_scene_data.uv_edit_new_uv_method in {'UNWRAP_ANGLE', 'UNWRAP_CONFORMAL'}:
                    unwrap_box = target_box.box()
                    unwrap_box.label(text="Unwrap", icon='UV')
                    unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_fill_holes")
                    unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_correct_aspect")
                    unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_use_subsurf")
                    unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_margin")
                elif ps_scene_data.uv_edit_new_uv_method == 'MIN_STRETCH':
                    stretch_box = target_box.box()
                    stretch_box.label(text="Minimize Stretch", icon='UV')
                    stretch_box.prop(ps_scene_data, "uv_edit_unwrap_fill_holes")
                    stretch_box.prop(ps_scene_data, "uv_edit_min_stretch_blend")
                    stretch_box.prop(ps_scene_data, "uv_edit_min_stretch_iterations")
                elif ps_scene_data.uv_edit_new_uv_method == 'LIGHTMAP':
                    lightmap_box = target_box.box()
                    lightmap_box.label(text="Lightmap Pack", icon='UV')
                    lightmap_box.prop(ps_scene_data, "uv_edit_lightmap_pack_in_one")
                    lightmap_box.prop(ps_scene_data, "uv_edit_lightmap_margin")
                    lightmap_box.prop(ps_scene_data, "uv_edit_lightmap_quality")
                elif ps_scene_data.uv_edit_new_uv_method == 'SMART':
                    smart_box = target_box.box()
                    smart_box.label(text="Smart UV Project", icon='UV')
                    smart_box.prop(ps_scene_data, "uv_edit_smart_angle_limit")
                    smart_box.prop(ps_scene_data, "uv_edit_smart_island_margin")
                    smart_box.prop(ps_scene_data, "uv_edit_smart_margin_method")
                    smart_box.prop(ps_scene_data, "uv_edit_smart_rotate_method")
                    smart_box.prop(ps_scene_data, "uv_edit_smart_area_weight")
                    smart_box.prop(ps_scene_data, "uv_edit_smart_correct_aspect")
                    smart_box.prop(ps_scene_data, "uv_edit_smart_scale_to_bounds")

            row = fix_box.row(align=True)
            scale_content(context, row, 1.1, 1.1)
            can_start = True
            if ps_scene_data.uv_edit_target_mode == 'EXISTING':
                can_start = bool(ps_scene_data.uv_edit_target_uv)
            else:
                can_start = bool(ps_scene_data.uv_edit_target_uv)
            row.enabled = can_start
            row.operator("paint_system.start_uv_edit", text="Edit UVs", icon='EDITMODE_HLT')

        if ps_scene_data.uv_edit_enabled:
            step2 = layout.box()
            draw_uv_edit_checker(step2, context, show_apply=True)


classes = (
    IMAGE_PT_PaintSystemUVEdit,
)

register, unregister = register_classes_factory(classes)
