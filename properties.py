import bpy
from bpy.props import (IntProperty,
                       FloatProperty,
                       BoolProperty,
                       StringProperty,
                       PointerProperty,
                       CollectionProperty,
                       EnumProperty)
from bpy.types import PropertyGroup
from bpy.utils import register_classes_factory
from .nestedListManager import BaseNestedListItem, BaseNestedListManager


def get_groups(self, context):
    mat = context.active_object.active_material
    if not mat or not hasattr(mat, "paint_system"):
        return []
    return [(str(i), group.name, f"Group {i}") for i, group in enumerate(mat.paint_system.groups)]


class PaintSystemLayer(BaseNestedListItem):
    enabled: BoolProperty(
        name="Enabled",
        description="Toggle layer visibility",
        default=True
    )
    opacity: FloatProperty(
        name="Opacity",
        description="Layer opacity",
        min=0.0,
        max=1.0,
        default=1.0
    )
    clip_below: BoolProperty(
        name="Clip Below",
        description="Clip layers below this one",
        default=False
    )
    blend_mode: EnumProperty(
        name="Blend Mode",
        items=[
            ('NORMAL', "Normal", "Normal blend mode"),
            ('MULTIPLY', "Multiply", "Multiply blend mode"),
            ('SCREEN', "Screen", "Screen blend mode"),
            ('OVERLAY', "Overlay", "Overlay blend mode"),
            ('DARKEN', "Darken", "Darken blend mode"),
            ('LIGHTEN', "Lighten", "Lighten blend mode"),
            ('COLOR_DODGE', "Color Dodge", "Color Dodge blend mode"),
            ('COLOR_BURN', "Color Burn", "Color Burn blend mode"),
            ('HARD_LIGHT', "Hard Light", "Hard Light blend mode"),
            ('SOFT_LIGHT', "Soft Light", "Soft Light blend mode"),
            ('DIFFERENCE', "Difference", "Difference blend mode"),
            ('EXCLUSION', "Exclusion", "Exclusion blend mode"),
            ('HUE', "Hue", "Hue blend mode"),
            ('SATURATION', "Saturation", "Saturation blend mode"),
            ('COLOR', "Color", "Color blend mode"),
            ('LUMINOSITY', "Luminosity", "Luminosity blend mode"),
        ],
        default='NORMAL'
    )
    image: PointerProperty(
        name="Image",
        type=bpy.types.Image
    )
    type: EnumProperty(
        items=[
            ('FOLDER', "Folder", "Folder layer"),
            ('IMAGE', "Image", "Image layer"),
        ],
        default='IMAGE'
    )


class PaintSystemLayerManager(BaseNestedListManager):
    # Define the collection property directly in the class
    items: CollectionProperty(type=PaintSystemLayer)

    @property
    def item_type(self):
        return PaintSystemLayer

    def get_movement_menu_items(self, item_id, direction):
        """
        Get menu items for movement options.
        Returns list of tuples (identifier, label, description)
        """
        options = self.get_movement_options(item_id, direction)
        menu_items = []

        # Map option identifiers to their operators
        operator_map = {
            'UP': 'paint_system.move_up',
            'DOWN': 'paint_system.move_down'
        }

        for identifier, description in options:
            menu_items.append((
                operator_map[direction],
                description,
                {'action': identifier}
            ))

        return menu_items


class PaintSystemGroups(PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Paint system name",
        default="Paint System"
    )
    groups: CollectionProperty(type=PaintSystemLayerManager)
    active_group: EnumProperty(
        name="Active Group",
        description="Select active group",
        items=get_groups
    )


classes = (
    PaintSystemLayer,
    PaintSystemLayerManager,
    PaintSystemGroups
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Material.paint_system = PointerProperty(type=PaintSystemGroups)


def unregister():
    del bpy.types.Material.paint_system
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
