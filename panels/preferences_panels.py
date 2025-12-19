import bpy
from bpy.types import AddonPreferences
from bpy.props import BoolProperty, FloatProperty, IntProperty, EnumProperty
from bpy.utils import register_classes_factory

from ..paintsystem.version_check import get_latest_version
from .common import find_keymap
from ..preferences import addon_package

class PaintSystemPreferences(AddonPreferences):
    """Demo bare-bones preferences"""
    bl_idname = addon_package()

    show_tooltips: BoolProperty(
        name="Show Tooltips",
        description="Show tooltips in the UI",
        default=True
    )
    show_hex_color: BoolProperty(
        name="Show Hex Color",
        description="Show hex color in the color picker settings",
        default=False
    )
    show_more_color_picker_settings: BoolProperty(
        name="Show More Color Picker Settings",
        description="Show more color picker settings",
        default=False
    )

    use_compact_design: BoolProperty(
        name="Use Compact Design",
        description="Use a more compact design for the UI",
        default=False
    )
    
    color_picker_scale: FloatProperty(
        name="Color Picker Scale",
        description="Scale the color picker",
        default=1.0,
        min=0.5,
        max=3.0
    )

    color_picker_scale_rmb: FloatProperty(
        name="RMB Color Wheel Scale",
        description="Scale the color wheel in the Texture Paint right-click popover",
        default=1.2,
        min=0.5,
        max=3.0
    )
    
    # Tips
    hide_norm_paint_tips: BoolProperty(
        name="Hide Normal Painting Tips",
        description="Hide the normal painting tips",
        default=False
    )
    hide_color_attr_tips: BoolProperty(
        name="Hide Color Attribute Tips",
        description="Hide the color attribute tips",
        default=False
    )

    use_legacy_ui: BoolProperty(
        name="Use Legacy UI",
        description="Use the legacy UI",
        default=False
    )

    # RMB popover options
    show_hsv_sliders_rmb: BoolProperty(
        name="Show Hue/Saturation/Value sliders (RMB)",
        description="Show HSV sliders under the color wheel in the Texture Paint right-click popover",
        default=True
    )
    show_active_palette_rmb: BoolProperty(
        name="Show Active Palette (RMB)",
        description="Show the active palette swatches in the Texture Paint right-click popover",
        default=True
    )
    show_brush_settings_rmb: BoolProperty(
        name="Show Brush Controls (RMB)",
        description="Show brush radius/strength controls in the Texture Paint right-click popover",
        default=True
    )
    
    loading_donations: BoolProperty(
        name="Loading Donations",
        description="Loading donations",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    # Version check settings
    version_check_interval_days: IntProperty(
        name="Version Check Interval (Days)",
        description="Days between version checks",
        default=1,
        min=0,
        soft_max=30
    )
    
    version_check_interval_hours: IntProperty(
        name="Version Check Interval (Hours)",
        description="Hours between version checks",
        default=0,
        min=0,
        soft_max=23
    )
    
    version_check_interval_minutes: IntProperty(
        name="Version Check Interval (Minutes)",
        description="Minutes between version checks",
        default=0,
        min=0,
        soft_max=59
    )
    
    update_state: EnumProperty(
        name='Update State',
        description='Extension update state',
        items=(
            ('UNAVAILABLE', 'Unavailable', ''),
            ('AVAILABLE', 'Available', ''),
            ('LOADING', 'Loading', ''),
            ("ERROR", 'Error', '')
        ),
        default='UNAVAILABLE',
        options={'SKIP_SAVE'}
    )

    def draw_shortcut(self, layout, kmi, text):
        row = layout.row(align=True)
        row.prop(kmi, "active", text="", emboss=False)
        row.label(text=text)
        row.prop(kmi, "map_type", text="")
        map_type = kmi.map_type
        if map_type == 'KEYBOARD':
            row.prop(kmi, "type", text="", full_event=True)
        elif map_type == 'MOUSE':
            row.prop(kmi, "type", text="", full_event=True)
        elif map_type == 'NDOF':
            row.prop(kmi, "type", text="", full_event=True)
        elif map_type == 'TWEAK':
            subrow = row.row()
            subrow.prop(kmi, "type", text="")
            subrow.prop(kmi, "value", text="")
        elif map_type == 'TIMER':
            row.prop(kmi, "type", text="")
        else:
            row.label()

        if (not kmi.is_user_defined) and kmi.is_user_modified:
            row.operator("preferences.keyitem_restore", text="", icon='BACK').item_id = kmi.id

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "show_tooltips", text="Show Tooltips")
        layout.prop(self, "use_compact_design", text="Use Compact Design")
        layout.prop(self, "use_legacy_ui", text="Use Legacy UI")
        # layout.prop(self, "name_layers_group",
        #             text="Name Layers According to Group Name")

        # --- Texture Paint Right Click Menu ---
        rmb_box = layout.box()
        rmb_box.label(text="Texture Paint Right Click Menu", icon='MOUSE_RMB')
        rmb_box.prop(self, "color_picker_scale_rmb", text="Color Wheel Scale")
        rmb_box.prop(self, "show_hsv_sliders_rmb", text="Show HSV sliders in RMB popover")
        # rmb_box.prop(self, "show_active_palette_rmb", text="Show Active Palette in RMB popover")
        rmb_box.prop(self, "show_brush_settings_rmb", text="Show Brush Controls in RMB popover")
        
        # Version check settings
        from ..utils.version import is_online
        if is_online():
            box = layout.box()
            row = box.row()
            row.operator("paint_system.check_for_updates", text="", icon='FILE_REFRESH')
            latest_version = get_latest_version()
            if latest_version:
                row.label(text=f"Latest Version: {latest_version}")
            else:
                row.label(text="Failed to check latest version")
            box.label(text="Version Check Interval:")
            row = box.row()
            row.prop(self, "version_check_interval_days", text="Days")
            row.prop(self, "version_check_interval_hours", text="Hours")
            row.prop(self, "version_check_interval_minutes", text="Minutes")

        box = layout.box()
        box.label(text="Paint System Shortcuts:")
        kmi = find_keymap('paint_system.color_sampler')
        if kmi:
            self.draw_shortcut(box, kmi, "Color Sampler Shortcut")
        kmi = find_keymap('paint_system.toggle_brush_erase_alpha')
        if kmi:
            self.draw_shortcut(box, kmi, "Toggle Eraser")

classes = (
    PaintSystemPreferences,
)

register, unregister = register_classes_factory(classes)