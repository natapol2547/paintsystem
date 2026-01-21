import bpy
from bpy.utils import register_submodule_factory

submodules = [
    # "custom_icons",
    "preferences_panels",
    "main_panels",
    "channels_panels",
    "extras_panels",
    "layers_panels",
    "quick_tools_panels",
]

register, unregister = register_submodule_factory(__name__, submodules)