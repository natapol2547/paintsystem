import bpy
from importlib import import_module
from bpy.utils import register_submodule_factory
from .context import PSContextMixin

submodules = [
    "data",
    "handlers",
    # "graph",
    # "nested_list_manager",
    # "move",
]

for submodule in submodules:
    globals()[submodule] = import_module(f".{submodule}", __name__)

register, unregister = register_submodule_factory(__name__, submodules)