import bpy
from bpy.utils import register_submodule_factory
from .context import PSContextMixin

submodules = [
    "switch_panel",
    "data",
    "handlers",
    # "graph",
    # "nested_list_manager",
    # "move",
]

register, unregister = register_submodule_factory(__name__, submodules)