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


def _add_keymap_entry(
    kc,
    name: str,
    space_type: str,
    idname: str,
    key: str,
    value: str = 'PRESS',
    shift: bool = False,
    ctrl: bool = False,
    alt: bool = False,
    properties: dict | None = None,
):
    km = kc.keymaps.new(name=name, space_type=space_type)
    kmi = km.keymap_items.new(idname, type=key, value=value, shift=shift, ctrl=ctrl, alt=alt)
    if properties:
        for prop, prop_value in properties.items():
            try:
                setattr(kmi.properties, prop, prop_value)
            except Exception:
                pass
    addon_keymaps.append((km, kmi))


def register() -> None:
    try:
        kc = getattr(getattr(bpy.context, 'window_manager', None), 'keyconfigs', None)
        kc = getattr(kc, 'addon', None)
        if not kc:
            return

        # Plain RMB override in Texture Paint tool context (preferred)
        if ENABLE_RMB_OVERRIDE_IN_TEXPAINT:
            # Tool-specific keymap names vary slightly across versions; add to a couple of common ones
            for km_name, space in (
                ('3D View Tool: Paint Draw', 'VIEW_3D'),
                ('Image Paint', 'EMPTY'),
            ):
                _add_keymap_entry(
                    kc,
                    name=km_name,
                    space_type=space,
                    idname='paint_system.open_texpaint_menu',
                    key='RIGHTMOUSE',
                    value='PRESS',
                )

        # Optional Shift+RMB fallback
        if ENABLE_SHIFT_RMB_FALLBACK:
            _add_keymap_entry(
                kc,
                name='3D View',
                space_type='VIEW_3D',
                idname='paint_system.open_texpaint_menu',
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
