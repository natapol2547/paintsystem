import bpy
from bpy.types import AddonPreferences, Panel
from bpy.props import BoolProperty, FloatProperty
from bpy.utils import register_classes_factory
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

    # Deprecated toggle retained for compatibility with stored preferences (not exposed in UI)
    use_legacy_ui: BoolProperty(
        name="Use Legacy UI",
        description="Deprecated legacy UI toggle",
        default=False,
        options={'HIDDEN'}
    )
    
    # RMB Context Menu Options
    show_hsv_sliders_rmb: BoolProperty(
        name="Show HSV Sliders in RMB Menu",
        description="Show Hue, Saturation, Value sliders in the RMB quick paint menu",
        default=True
    )
    show_active_palette_rmb: BoolProperty(
        name="Show Palette in RMB Menu",
        description="Show active palette in the RMB quick paint menu",
        default=True
    )
    show_rmb_layers_panel: BoolProperty(
        name="Show Layers Option in RMB Menu",
        description="Show 'Paint System Layers' option in the RMB context menu",
        default=True
    )
    rmb_color_wheel_scale: FloatProperty(
        name="Color Wheel Scale",
        description="Scale of the color wheel in RMB menu",
        default=1.2,
        min=0.5,
        max=2.5,
        step=0.1
    )

    loading_donations: BoolProperty(
        name="Loading Donations",
        description="Loading donations",
        default=False,
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
        # layout.prop(self, "name_layers_group",
        #             text="Name Layers According to Group Name")

        box = layout.box()
        box.label(text="Paint System Shortcuts:")
        kmi = find_keymap('paint_system.color_sampler')
        if kmi:
            self.draw_shortcut(box, kmi, "Color Sampler Shortcut")
        kmi = find_keymap('paint_system.toggle_brush_erase_alpha')
        if kmi:
            self.draw_shortcut(box, kmi, "Toggle Eraser")
        
        # RMB Context Menu preferences
        box = layout.box()
        col = box.column()
        col.label(text="RMB Context Menu:", icon='BRUSHES_ALL')
        col.prop(self, "show_rmb_layers_panel", text="Show Layers Option")
        col.prop(self, "show_active_palette_rmb", text="Show Color History")
        col.prop(self, "show_hsv_sliders_rmb", text="Show HSV Sliders")
        col.separator()
        col.prop(self, "rmb_color_wheel_scale", text="Color Wheel Scale", slider=True)


class PREFERENCES_PT_PaintSystemRMBMenu(Panel):
    """RMB Context Menu Preferences"""
    bl_label = "RMB Context Menu"
    bl_idname = "PREFERENCES_PT_PaintSystemRMBMenu"
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'WINDOW'
    bl_context = "addons"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.preferences.addons.get(addon_package()) is not None

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons.get(addon_package())
        if not prefs:
            return
        prefs = prefs.preferences

        layout.use_property_split = True
        layout.use_property_decorate = False

        col = layout.column()
        col.label(text="Right-Click Menu Options:", icon='BRUSHES_ALL')
        col.prop(prefs, "show_rmb_layers_panel", text="Show Layers Option")
        col.prop(prefs, "show_active_palette_rmb", text="Show Color History")
        col.prop(prefs, "show_hsv_sliders_rmb", text="Show HSV Sliders")
        col.separator()
        col.prop(prefs, "rmb_color_wheel_scale", text="Color Wheel Scale", slider=True)

classes = (
    PaintSystemPreferences,
    PREFERENCES_PT_PaintSystemRMBMenu,
)

register, unregister = register_classes_factory(classes)