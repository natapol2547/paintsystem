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

# from .paintsystem.data import parse_context

bl_info = {
    "name": "Paint System",
    "author": "Tawan Sunflower, @blastframe",
    "description": "",
    "blender": (4, 2, 0),
    "version": (2, 1, 4),
    "location": "View3D > Sidebar > Paint System",
    "warning": "",
    "category": "Paint",
    'support': 'COMMUNITY',
    "tracker_url": "https://github.com/natapol2547/paintsystem"
}

bl_info_copy = bl_info.copy()

print("Paint System: Registering...")

submodules = [
    "paintsystem",
    "panels",
    "operators",
    "keymaps",
]

_register, _unregister = register_submodule_factory(__name__, submodules)

def register():
    load_icons()
    _register()
    
def unregister():
    _unregister()
    unload_icons()
    print("Paint System: Unregistered", __package__)