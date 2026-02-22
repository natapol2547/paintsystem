import bpy
from importlib import import_module
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

for submodule in submodules:
    globals()[submodule] = import_module(f".{submodule}", __name__)

register, unregister = register_submodule_factory(__name__, submodules)