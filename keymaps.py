# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

addon_keymaps = []

# Toggleable shortcuts
# 1) Optional Shift+RMB fallback (off by default to avoid duplicates)
ENABLE_SHIFT_RMB_FALLBACK = False
# 2) Plain RMB override (enabled by default for Bforartists compatibility)
#    Bforartists 4.4.3 doesn't have a default Texture Paint RMB menu,
#    so we NEED to override RMB to provide menu access
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = True


def _add_call_menu(kc, name: str, space_type: str, menu_idname: str, key: str, value: str = 'PRESS', shift=False, ctrl=False, alt=False):
    km = kc.keymaps.new(name=name, space_type=space_type)
    kmi = km.keymap_items.new('wm.call_menu', type=key, value=value, shift=shift, ctrl=ctrl, alt=alt)
    kmi.properties.name = menu_idname
    addon_keymaps.append((km, kmi))


def _add_call_operator(kc, name: str, space_type: str, operator_idname: str, key: str, value: str = 'PRESS', shift=False, ctrl=False, alt=False):
    km = kc.keymaps.new(name=name, space_type=space_type)
    kmi = km.keymap_items.new(operator_idname, type=key, value=value, shift=shift, ctrl=ctrl, alt=alt)
    addon_keymaps.append((km, kmi))


def _has_builtin_texpaint_rmb() -> bool:
    # Blender main branch exposes a dedicated Texture Paint RMB menu
    for name in (
        'VIEW3D_MT_paint_texture_context_menu',
        'VIEW3D_MT_paint_texture',
    ):
        if hasattr(bpy.types, name):
            return True
    return False


def register() -> None:
    try:
        kc = getattr(getattr(bpy.context, 'window_manager', None), 'keyconfigs', None)
        kc = getattr(kc, 'addon', None)
        if not kc:
            return

        # Decide whether to override RMB or rely on native RMB menu
        do_override = ENABLE_RMB_OVERRIDE_IN_TEXPAINT or not _has_builtin_texpaint_rmb()

        # Plain RMB override in Texture Paint tool context (preferred on Bforartists)
        if do_override:
            # Tool-specific keymap names vary slightly across versions; add to a couple of common ones
            for km_name, space in (
                ('3D View Tool: Paint Draw', 'VIEW_3D'),
                ('Image Paint', 'EMPTY'),
            ):
                _add_call_operator(
                    kc,
                    name=km_name,
                    space_type=space,
                    operator_idname='paint_system.open_texpaint_menu',
                    key='RIGHTMOUSE',
                    value='PRESS',
                )

        # Optional Shift+RMB fallback
        if ENABLE_SHIFT_RMB_FALLBACK:
            _add_call_menu(
                kc,
                name='3D View',
                space_type='VIEW_3D',
                menu_idname='VIEW3D_MT_paintsystem_texture_paint_context',
                key='RIGHTMOUSE',
                value='PRESS',
                shift=True,
            )
    except Exception:
        # Keymap setup is best-effort; failures shouldn't block add-on load
        pass


def unregister() -> None:
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass

    addon_keymaps.clear()
