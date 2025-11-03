import bpy
from bpy.types import AddonPreferences
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

    use_legacy_ui: BoolProperty(
        name="Use Legacy UI",
        description="Use the legacy UI",
        default=False
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