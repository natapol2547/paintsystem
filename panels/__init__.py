import bpy
from importlib import import_module
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

for submodule in submodules:
    globals()[submodule] = import_module(f".{submodule}", __name__)

register, unregister = register_submodule_factory(__name__, submodules)