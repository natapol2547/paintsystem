# ##### BEGIN GPL LICENSE BLOCK #####
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
# ##### END GPL LICENSE BLOCK #####

# --- ### Header
bl_info = {"name": "BL UI Widgets",
           "description": "UI Widgets to draw in the 3D view",
           "author": "Marcelo M. Marques (fork of Jayanam's original project)",
           "version": (1, 0, 7),
           "blender": (3, 0, 0),
           "location": "View3D > side panel ([N]), [BL_UI_Widget] tab",
           "support": "COMMUNITY",
           "category": "3D View",
           "warning": "Version numbering diverges from Jayanam's original project",
           "doc_url": "https://github.com/mmmrqs/bl_ui_widgets",
           "tracker_url": "https://github.com/mmmrqs/bl_ui_widgets/issues"
           }

# --- ### Change log

# Note: Because the way Blender's Preferences window displays the Addon version number,
# I am forced to keep this file in sync with the greatest version number of all modules.

# v1.0.6 (07.29.2024) - by Marcelo M. Marques
# Chang: updated version to keep this file in sync with greatest module version

# v1.0.6 (05.27.2023) - by Marcelo M. Marques
# Chang: updated version to keep this file in sync with greatest module version

# v1.0.5 (03.06.2023) - by Marcelo M. Marques
# Chang: updated version to keep this file in sync with greatest module version

# v1.0.4 (09.28.2022) - by Marcelo M. Marques
# Chang: updated version to keep this file in sync with greatest module version

# v1.0.3 (09.25.2021) - by Marcelo M. Marques
# Chang: updated version to keep this file in sync with greatest module version

# v1.0.2 (10.31.2021) - by Marcelo M. Marques
# Chang: updated version with improvements and some clean up

# v1.0.1 (09.20.2021) - by Marcelo M. Marques
# Chang: just some pep8 code formatting

# v1.0.0 (09.01.2021) - by Marcelo M. Marques
# Added: initial creation

# --- ### Imports
import sys
import importlib

modulesFullNames = {}

modulesNames = ['prefs',
                'bl_ui_draw_op',
                'bl_ui_widget',
                'bl_ui_label',
                'bl_ui_patch',
                'bl_ui_button',
                'bl_ui_checkbox',
                'bl_ui_textbox',
                'bl_ui_slider',
                'bl_ui_tooltip',
                'bl_ui_drag_panel',
                'demo_panel_op',
                'bl_ui_widget_demo',
                ]

for currentModuleName in modulesNames:
    if 'DEBUG_MODE' in sys.argv:
        modulesFullNames[currentModuleName] = ('{}'.format(currentModuleName))
    else:
        modulesFullNames[currentModuleName] = ('{}.{}'.format(__name__, currentModuleName))

if 'DEBUG_MODE' in sys.argv:
    import os
    import time
    os.system("cls")
    timestr = time.strftime("%Y-%m-%d %H:%M:%S")
    print('---------------------------------------')
    print('-------------- RESTART ----------------')
    print('---------------------------------------')
    print(timestr, __name__ + ": registered")
    print()
    sys.argv.remove('DEBUG_MODE')

for currentModuleFullName in modulesFullNames.values():
    if currentModuleFullName in sys.modules:
        importlib.reload(sys.modules[currentModuleFullName])
    else:
        globals()[currentModuleFullName] = importlib.import_module(currentModuleFullName)
        setattr(globals()[currentModuleFullName], 'modulesNames', modulesFullNames)


def register():
    for currentModuleName in modulesFullNames.values():
        if currentModuleName in sys.modules:
            if hasattr(sys.modules[currentModuleName], 'register'):
                sys.modules[currentModuleName].register()


def unregister():
    for currentModuleName in modulesFullNames.values():
        if currentModuleName in sys.modules:
            if hasattr(sys.modules[currentModuleName], 'unregister'):
                sys.modules[currentModuleName].unregister()


if __name__ == "__main__":
    register()
