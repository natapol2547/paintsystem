import bpy
from bpy.types import Panel
from bpy.utils import register_classes_factory

from .common import PSContextMixin, scale_content


class IMAGE_PT_PaintSystemUVEdit(PSContextMixin, Panel):
    bl_idname = "IMAGE_PT_PaintSystemUVEdit"
    bl_space_type = "IMAGE_EDITOR"
    bl_region_type = "UI"
    bl_label = "Paint System"
    bl_category = "Paint System"
    bl_options = {"DEFAULT_CLOSED"}

    @classmethod
    def poll(cls, context):
        return context.space_data and context.space_data.ui_mode == 'UV'

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
            alert_box = layout.box()
            alert_box.alert = True
            alert_box.label(text="UV Edit Mode Active", icon='ERROR')
            alert_row = alert_box.row(align=True)
            alert_row.operator("paint_system.exit_uv_edit", text="Exit UV Edit", icon='CANCEL')
            alert_box.alert = False

        step1 = layout.box()
        step1.label(text="Step 1: Setup", icon='SETTINGS')
        active_box = step1.box()
        active_box.label(text="Active UV", icon='GROUP_UVS')
        active_box.prop_search(ps_scene_data, "uv_edit_source_uv", ps_ctx.ps_object.data, "uv_layers", text="")
        row = active_box.row(align=True)
        row.operator("paint_system.grab_active_layer_uv", text="Grab Current Layer UV", icon='EYEDROPPER')
        row.operator("paint_system.sync_uv_names", text="Sync UV Names", icon='FILE_REFRESH')

        target_box = step1.box()
        target_box.label(text="Target UV", icon='UV')
        target_box.prop(ps_scene_data, "uv_edit_target_mode", text="")
        if ps_scene_data.uv_edit_target_mode == 'EXISTING':
            target_box.prop_search(ps_scene_data, "uv_edit_target_uv", ps_ctx.ps_object.data, "uv_layers", text="Target UV")
        else:
            target_box.prop(ps_scene_data, "uv_edit_target_uv", text="Target UV")
            target_box.prop(ps_scene_data, "uv_edit_new_uv_method", text="")
            if ps_scene_data.uv_edit_new_uv_method in {'UNWRAP_ANGLE', 'UNWRAP_CONFORMAL'}:
                unwrap_box = target_box.box()
                unwrap_box.label(text="Unwrap Settings", icon='UV')
                unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_fill_holes")
                unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_correct_aspect")
                unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_use_subsurf")
                unwrap_box.prop(ps_scene_data, "uv_edit_unwrap_margin")
            elif ps_scene_data.uv_edit_new_uv_method == 'MIN_STRETCH':
                stretch_box = target_box.box()
                stretch_box.label(text="Minimum Stretch", icon='UV')
                stretch_box.prop(ps_scene_data, "uv_edit_min_stretch_blend")
                stretch_box.prop(ps_scene_data, "uv_edit_min_stretch_iterations")
            elif ps_scene_data.uv_edit_new_uv_method == 'LIGHTMAP':
                lightmap_box = target_box.box()
                lightmap_box.label(text="Lightmap Pack", icon='UV')
                lightmap_box.prop(ps_scene_data, "uv_edit_lightmap_quality")
                lightmap_box.prop(ps_scene_data, "uv_edit_lightmap_margin")
                lightmap_box.prop(ps_scene_data, "uv_edit_lightmap_pack_in_one")
            elif ps_scene_data.uv_edit_new_uv_method == 'SMART':
                smart_box = target_box.box()
                smart_box.label(text="Smart UV Project", icon='UV')
                smart_box.prop(ps_scene_data, "uv_edit_smart_angle_limit")
                smart_box.prop(ps_scene_data, "uv_edit_smart_island_margin")
                smart_box.prop(ps_scene_data, "uv_edit_smart_area_weight")
                smart_box.prop(ps_scene_data, "uv_edit_smart_correct_aspect")
                smart_box.prop(ps_scene_data, "uv_edit_smart_scale_to_bounds")

        row = step1.row(align=True)
        scale_content(context, row, 1.1, 1.1)
        row.operator("paint_system.start_uv_edit", text="Edit UVs", icon='EDITMODE_HLT')
        row.operator("paint_system.clear_unused_uvs", text="", icon='TRASH')

        if ps_scene_data.uv_edit_enabled:
            step2 = layout.box()
            step2.alert = True
            step2.label(text="UV Edit Mode Active", icon='INFO')
            step2.alert = False

            checker_box = step2.box()
            checker_box.label(text="UV Checker", icon='GRID')
            checker_box.prop(ps_scene_data, "uv_edit_checker_type", text="Type")
            checker_box.prop(ps_scene_data, "uv_edit_checker_resolution", text="Size")
            checker_box.operator("paint_system.update_uv_checker", text="Apply Checker", icon='CHECKMARK')

            apply_row = step2.row(align=True)
            scale_content(context, apply_row, 1.1, 1.1)
            apply_row.operator("paint_system.apply_uv_edit", text="Apply UV Edit", icon='FILE_TICK')


classes = (
    IMAGE_PT_PaintSystemUVEdit,
)

register, unregister = register_classes_factory(classes)
