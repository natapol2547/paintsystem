# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

addon_keymaps = []
disabled_builtin_kmis = []  # Track disabled built-in keymap items so we can restore them

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


def _disable_builtin_texture_paint_rmb_menus() -> None:
    """Disable built-in RMB context menu keymaps in texture paint modes to prevent conflicts."""
    try:
        wm = bpy.context.window_manager
        if not wm:
            return
        
        print("Paint System: Disabling built-in RMB menus...")
        
        # Check all keyconfig sources (user, addon, default)
        for kc_name in ('default', 'addon', 'user'):
            kc = getattr(wm.keyconfigs, kc_name, None)
            if not kc:
                continue
            
            # Look for texture paint related keymaps
            for km_name in (
                '3D View Tool: Paint Draw',
                'Image Paint',
                'Paint',
                '3D View',
            ):
                km = kc.keymaps.get(km_name)
                if not km:
                    continue
                
                # Find and disable ANY RMB menu/panel triggers
                for kmi in km.keymap_items:
                    if (kmi.type == 'RIGHTMOUSE' and kmi.active):
                        if kmi.idname in ('wm.call_menu', 'wm.call_panel', 'wm.call_menu_pie'):
                            menu_name = getattr(kmi.properties, 'name', '')
                            print(f"  Disabling RMB {kmi.idname}: '{menu_name}' in '{km_name}' ({kc_name})")
                            kmi.active = False
                            disabled_builtin_kmis.append((km, kmi))
                        
        print(f"Paint System: Disabled {len(disabled_builtin_kmis)} built-in RMB menu items")
    except Exception as e:
        print(f"Paint System: Error disabling built-in menus: {e}")
        import traceback
        traceback.print_exc()


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
            # First, disable any built-in RMB context menu keymaps in texture paint modes
            # to prevent them from appearing alongside our popover
            _disable_builtin_texture_paint_rmb_menus()
            
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
    # Restore any disabled built-in keymap items
    for km, kmi in disabled_builtin_kmis:
        try:
            kmi.active = True
        except Exception:
            pass
    disabled_builtin_kmis.clear()
    
    # Remove our addon keymaps
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass

    addon_keymaps.clear()
