# SPDX-License-Identifier: GPL-2.0-or-later

import bpy

addon_keymaps = []

# Toggleable shortcuts
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = True


def register() -> None:
    try:
        wm = bpy.context.window_manager
        if not wm:
            return
        
        kc = wm.keyconfigs.addon
        if not kc:
            return

        if ENABLE_RMB_OVERRIDE_IN_TEXPAINT:
            # Try to override existing RMB binding in Image Paint keymap
            km = kc.keymaps.get('Image Paint')
            if km:
                print("    Searching for RMB binding in 'Image Paint' keymap...")
                found_rmb = False
                for kmi in km.keymap_items:
                    if kmi.type == 'RIGHTMOUSE' and kmi.value == 'PRESS' and not kmi.shift and not kmi.ctrl and not kmi.alt:
                        print(f"      Found RMB binding: {kmi.idname}")
                        kmi.idname = 'paint_system.open_texpaint_menu'
                        addon_keymaps.append((km, kmi))
                        print(f"      ✓ Overridden to paint_system.open_texpaint_menu")
                        found_rmb = True
                        break
                
                if not found_rmb:
                    print("      RMB binding not found, creating new one...")
                    kmi = km.keymap_items.new('paint_system.open_texpaint_menu', type='RIGHTMOUSE', value='PRESS')
                    addon_keymaps.append((km, kmi))
                    print(f"      ✓ Created new RMB binding")
            else:
                print("    'Image Paint' keymap not found, creating new one...")
                km = kc.keymaps.new(name='Image Paint', space_type='EMPTY')
                kmi = km.keymap_items.new('paint_system.open_texpaint_menu', type='RIGHTMOUSE', value='PRESS')
                addon_keymaps.append((km, kmi))
                print(f"    ✓ Created new Image Paint keymap with RMB binding")
            
            # Also try 3D View Tool: Paint Draw
            km = kc.keymaps.get('3D View Tool: Paint Draw')
            if km:
                print("    Searching for RMB binding in '3D View Tool: Paint Draw' keymap...")
                found_rmb = False
                for kmi in km.keymap_items:
                    if kmi.type == 'RIGHTMOUSE' and kmi.value == 'PRESS' and not kmi.shift and not kmi.ctrl and not kmi.alt:
                        print(f"      Found RMB binding: {kmi.idname}")
                        kmi.idname = 'paint_system.open_texpaint_menu'
                        addon_keymaps.append((km, kmi))
                        print(f"      ✓ Overridden to paint_system.open_texpaint_menu")
                        found_rmb = True
                        break
                
                if not found_rmb:
                    print("      RMB binding not found, creating new one...")
                    kmi = km.keymap_items.new('paint_system.open_texpaint_menu', type='RIGHTMOUSE', value='PRESS')
                    addon_keymaps.append((km, kmi))
                    print(f"      ✓ Created new RMB binding")

    except Exception as e:
        print(f"✗ Keymap registration error: {e}")
        import traceback
        traceback.print_exc()


def unregister() -> None:
    for km, kmi in addon_keymaps:
        try:
            km.keymap_items.remove(kmi)
        except Exception:
            pass

    addon_keymaps.clear()
