import bpy
from bpy.utils import register_submodule_factory

submodules = [
    # "graph",
    "layers_operators",
    "layer_mask_operators",
    "channel_operators",
    "group_operators",
    "utils_operators",
    "image_operators",
    "quick_edit",
    "versioning_operators",
    "bake_operators",
    "shader_editor",
    "uv_edit_operators",
]

register, unregister = register_submodule_factory(__name__, submodules)