# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

# Toggleable shortcuts
# 1) Optional Shift+RMB fallback (off by default to avoid duplicates)
ENABLE_SHIFT_RMB_FALLBACK = False
# 2) Plain RMB override in Texture Paint (off by default; some forks lack RMB menu)
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = False

addon_keymaps = []


def register() -> None:
    assert bpy.context
    if kc := bpy.context.window_manager.keyconfigs.addon:
        km = kc.keymaps.new(name='Node Editor', space_type="NODE_EDITOR")
        kmi = km.keymap_items.new("node.na_recenter_selected", type='G', value='PRESS', alt=True)
        addon_keymaps.append((km, kmi))

        # Optional: Texture Paint RMB override (context menu/popup)
        try:
            if ENABLE_RMB_OVERRIDE_IN_TEXPAINT:
                km_tp = kc.keymaps.new(name='Image Paint', space_type='EMPTY')
                # As a conservative default, open Blender's built-in context menu
                kmi_tp = km_tp.keymap_items.new("wm.call_menu", type='RIGHTMOUSE', value='PRESS')
                kmi_tp.properties.name = "VIEW3D_MT_paint_texture_context_menu"
                addon_keymaps.append((km_tp, kmi_tp))
            if ENABLE_SHIFT_RMB_FALLBACK:
                km_tp2 = kc.keymaps.new(name='Image Paint', space_type='EMPTY')
                kmi_tp2 = km_tp2.keymap_items.new("wm.call_menu", type='RIGHTMOUSE', value='PRESS', shift=True)
                kmi_tp2.properties.name = "VIEW3D_MT_paint_texture_context_menu"
                addon_keymaps.append((km_tp2, kmi_tp2))
        except Exception:
            # Fail gracefully if keymap isn't available in the environment
            pass


def unregister() -> None:
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            # Keymap item may already be removed or keymap missing
            pass

    addon_keymaps.clear()
