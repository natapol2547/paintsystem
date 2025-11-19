# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTIBILITY or FITNESS FOR A PARTICULAR PURPOSE. See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import bpy
from bpy.utils import register_submodule_factory
from .custom_icons import load_icons, unload_icons
import importlib



# from .paintsystem.data import parse_context

bl_info = {
    "name": "Paint System",
    "author": "Tawan Sunflower, @blastframe",
    "description": "",
    "blender": (4, 2, 0),
    "version": (2, 1, 1),
    "location": "View3D > Sidebar > Paint System",
    "warning": "",
    "category": "Paint",
    'support': 'COMMUNITY',
    "tracker_url": "https://github.com/natapol2547/paintsystem"
}

bl_info_copy = bl_info.copy()

# Load icons early so EnumProperty item icons in submodules can resolve during import
load_icons()

# Import all modules explicitly to ensure they're available as attributes
# This is required for bl_ext wrapper compatibility
from . import paintsystem, panels, operators, keymaps

# Use register_submodule_factory only for modules without custom registration
_submodules_auto = [
    "panels",
    "operators",
    "keymaps",
]

_register_auto, _unregister_auto = register_submodule_factory(__name__, _submodules_auto)

def register():
    load_icons()
    # Register paintsystem first (contains PropertyGroups needed by other modules)
    paintsystem.register()
    # Then register remaining modules
    _register_auto()
    
def unregister():
    # Unregister in reverse order
    _unregister_auto()
    paintsystem.unregister()
    unload_icons()