import bpy
import os

ICON_FOLDER = 'icons'

custom_icons = None

def load_icons():
    import bpy.utils.previews
    # Custom Icon
    if not hasattr(bpy.utils, 'previews'):
        return
    # Idempotent: avoid creating multiple preview collections
    global custom_icons
    if custom_icons is not None:
        return
    custom_icons = bpy.utils.previews.new()

    folder = os.path.dirname(bpy.path.abspath(
        __file__)) + os.sep + ICON_FOLDER + os.sep

    for f in os.listdir(folder):
        # Remove file extension
        icon_name = os.path.splitext(f)[0]
        custom_icons.load(icon_name, folder + f, 'IMAGE')


def unload_icons():
    global custom_icons
    if hasattr(bpy.utils, 'previews'):
        if custom_icons is not None:
            bpy.utils.previews.remove(custom_icons)
            custom_icons = None


def get_icon(custom_icon_name):
    if custom_icons is None:
        return None
    if custom_icon_name not in custom_icons:
        return None
    return custom_icons[custom_icon_name].icon_id
