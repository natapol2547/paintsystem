import bpy
from bpy.utils import register_submodule_factory
from .data import PaintSystemGlobalData, MaterialData, get_global_layer
from . import data

submodules = [
    "handlers",
    # "graph",
    # "nested_list_manager",
    # "move",
]

_register, _unregister = register_submodule_factory(__name__, submodules)

def register():
    """Register paintsystem submodules."""
    data.register()  # Register data module first (has PropertyGroups)
    _register()      # Register remaining submodules
    
def unregister():
    """Unregister paintsystem submodules."""
    _unregister()    # Unregister submodules first
    data.unregister()  # Unregister data module last