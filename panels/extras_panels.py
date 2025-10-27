import bpy
from bpy.types import Panel, Menu
from bpy.utils import register_classes_factory

from .common import PSContextMixin, get_event_icons, find_keymap, find_keymap_by_name, scale_content, get_icon
from ..utils.version import is_newer_than
from ..utils.unified_brushes import get_unified_settings

from bl_ui.properties_paint_common import (
    UnifiedPaintPanel,
    brush_settings,
    draw_color_settings,
)

class MAT_PT_BrushTooltips(Panel):
    bl_label = "Brush Tooltips"
    bl_description = "Brush Tooltips"
    bl_idname = "MAT_PT_BrushTooltips"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_ui_units_x = 8

    def draw_shortcut(self, layout, kmi, text):
        row = layout.row(align=True)
        icons = get_event_icons(kmi)
        for idx, icon in enumerate(icons):
            row.label(icon=icon, text=text if idx == len(icons)-1 else "")

    def draw(self, context):
        layout = self.layout
        # split = layout.split(factor=0.1)
        col = layout.column()
        kmi = find_keymap("paint_system.toggle_brush_erase_alpha")
        self.draw_shortcut(col, kmi, "Toggle Erase Alpha")
        kmi = find_keymap("paint_system.color_sampler")
        self.draw_shortcut(col, kmi, "Eyedropper")
        # kmi = find_keymap("object.transfer_mode")
        # self.draw_shortcut(col, kmi, "Switch Object")
        kmi = find_keymap_by_name("Radial Control")
        if kmi:
            self.draw_shortcut(col, kmi, "Scale Brush Size")
        # col.label(text="Scale Brush Size", icon='EVENT_F')
        layout.separator()
        layout.operator('paint_system.open_paint_system_preferences', text="Preferences", icon='PREFERENCES')
        layout.operator('wm.url_open', text="Suggest more!",
                        icon='URL').url = "https://github.com/natapol2547/paintsystem/issues"
        # layout.operator("paint_system.disable_tool_tips",
        #                 text="Disable Tooltips", icon='CANCEL')

class MAT_PT_BrushColorSettings(PSContextMixin, Panel):
    bl_idname = "MAT_PT_BrushColorSettings"
    bl_label = "Color Picker Settings"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_ui_units_x = 10
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.prop(context.preferences.view, "color_picker_type", text="")
        layout.prop(ps_ctx.ps_settings, "color_picker_scale", text="Color Picker Scale", slider=True)
        layout.prop(ps_ctx.ps_settings, "show_hex_color", text="Show Hex Color")

class MAT_PT_BrushColor(PSContextMixin, Panel, UnifiedPaintPanel):
    bl_idname = 'MAT_PT_BrushColor'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Color"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_PaintSystemMainPanel'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        # Hidden - color picker moved to Paint System Tools panel
        return False

    def draw(self, context):
        pass

classes = (
    MAT_PT_BrushTooltips,
    MAT_PT_BrushColorSettings,
    MAT_PT_BrushColor,
)

register, unregister = register_classes_factory(classes)