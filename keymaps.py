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


def _override_rmb_in_keymap(kc, keymap_name, idname, space_type='VIEW_3D'):
    """Find existing keymap and override its RMB binding, or create new one."""
    try:
        km = kc.keymaps.get(keymap_name)
        if km is None:
            km = kc.keymaps.new(name=keymap_name, space_type=space_type)
        
        # Look for existing RMB PRESS binding and replace it
        for kmi in km.keymap_items:
            if kmi.type == 'RIGHTMOUSE' and kmi.value == 'PRESS' and not kmi.shift and not kmi.ctrl and not kmi.alt:
                # Replace existing RMB binding
                kmi.idname = idname
                addon_keymaps.append((km, kmi))
                return True
        
        # No existing RMB binding found, create new one
        kmi = km.keymap_items.new(idname, type='RIGHTMOUSE', value='PRESS')
        addon_keymaps.append((km, kmi))
        return True
    except Exception as e:
        print(f"Error overriding RMB in {keymap_name}: {e}")
        return False


def register() -> None:
    try:
        wm = bpy.context.window_manager
        if not wm:
            return
        
        kc = wm.keyconfigs.addon
        if not kc:
            return

        # Override RMB in Texture Paint - IMAGE EDITOR is the main space for texture paint
        if ENABLE_RMB_OVERRIDE_IN_TEXPAINT:
            # IMAGE EDITOR keymaps (primary texture paint location in both Blender and Bforartists)
            image_keymaps = [
                'Image Paint',
                'Image Editor',
                'Paint Mode',
            ]
            
            for km_name in image_keymaps:
                _override_rmb_in_keymap(kc, km_name, 'paint_system.open_texpaint_menu', space_type='IMAGE_EDITOR')
            
            # 3D View keymaps (fallback for paint modes and generic 3D operations)
            view3d_keymaps = [
                '3D View Tool: Paint Draw',
                'Texture Paint',
                '3D View Generic',
                '3D View',
                'Paint Mode',
            ]
            
            for km_name in view3d_keymaps:
                _override_rmb_in_keymap(kc, km_name, 'paint_system.open_texpaint_menu', space_type='VIEW_3D')

        # Optional Shift+RMB fallback
        if ENABLE_SHIFT_RMB_FALLBACK:
            try:
                km = kc.keymaps.get('3D View')
                if km is None:
                    km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
                kmi = km.keymap_items.new('paint_system.open_texpaint_menu', type='RIGHTMOUSE', value='PRESS', shift=True)
                addon_keymaps.append((km, kmi))
            except Exception:
                pass
    except Exception as e:
        # Keymap setup is best-effort; failures shouldn't block add-on load
        print(f"Keymap registration error: {e}")
        pass


def unregister() -> None:
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass

    addon_keymaps.clear()
