import bpy
from bpy.utils import register_submodule_factory

submodules = [
    # "graph",
    "layers_operators",
    "channel_operators",
    "group_operators",
    "utils_operators",
    "image_operators",
    "quick_edit",
    "versioning_operators",
    "bake_operators",
    "shader_editor",
]

register, unregister = register_submodule_factory(__name__, submodules)