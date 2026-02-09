import bpy
import os
import pathlib

ICON_FOLDER = 'icons'

custom_icons = None

def load_icons():
    import bpy.utils.previews
    # Custom Icon
    if not hasattr(bpy.utils, 'previews'):
        return
    global custom_icons
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
        bpy.utils.previews.remove(custom_icons)
        custom_icons = None


def get_icon(custom_icon_name):
    def resolve_icon_id():
        if custom_icons is None:
            return 0
        if custom_icon_name not in custom_icons:
            return 0
        icon_id = custom_icons[custom_icon_name].icon_id
        return icon_id or 0

    icon_id = resolve_icon_id()
    if icon_id:
        return icon_id
    load_icons()
    return resolve_icon_id()

    
def get_icon_from_socket_type(socket_type: str) -> int:
    type_to_icon = {
        'COLOR': 'color_socket',
        'VECTOR': 'vector_socket',
        'FLOAT': 'float_socket',
    }
    return get_icon(type_to_icon.get(socket_type, 'color_socket'))

def get_image_editor_icon(current_image_editor: str) -> int:
        if not current_image_editor:
            return None
        editor_path = pathlib.Path(current_image_editor)
        app_name = editor_path.name.lower()
        if "clipstudiopaint" in app_name:
            return get_icon("clip_studio_paint")
        elif "photoshop" in app_name:
            return get_icon("photoshop")
        elif "gimp" in app_name:
            return get_icon("gimp")
        elif "krita" in app_name:
            return get_icon("krita")
        elif "affinity" in app_name:
            return get_icon("affinity")
        return get_icon("image")