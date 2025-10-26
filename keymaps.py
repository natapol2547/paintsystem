# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

addon_keymaps = []


def register() -> None:
    assert bpy.context
    if kc := bpy.context.window_manager.keyconfigs.addon:
        # Node Editor mappings
        km = kc.keymaps.new(name='Node Editor', space_type="NODE_EDITOR")
        kmi = km.keymap_items.new("node.na_recenter_selected", type='G', value='PRESS', alt=True)
        addon_keymaps.append((km, kmi))
        # Ctrl+Q: Next Painting Target
        kmi = km.keymap_items.new("paint_system.next_active_channel", type='Q', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        # Ctrl+Shift+Q: Previous Painting Target
        kmi = km.keymap_items.new("paint_system.prev_active_channel", type='Q', value='PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))

        # Image Editor mappings
        km = kc.keymaps.new(name='Image', space_type='IMAGE_EDITOR')
        kmi = km.keymap_items.new("paint_system.next_active_channel", type='Q', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new("paint_system.prev_active_channel", type='Q', value='PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))

        # 3D View (Texture Paint) mappings
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("paint_system.next_active_channel", type='Q', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new("paint_system.prev_active_channel", type='Q', value='PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))


def unregister() -> None:
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)

    addon_keymaps.clear()
