import bpy
from bpy.types import Menu, Panel, Operator

from ..paintsystem.data import parse_context


_APPENDED_MENUS = []
_RMB_FROM_OPERATOR = False  # internal flag to suppress extra popovers when helper operator is used

# Disable RMB override - we'll use menu appending instead
# This ensures users get native brush controls + our Paint System menu
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = False


class VIEW3D_PT_paintsystem_brush_color(Panel):
    """Quick brush color picker panel for RMB popover"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Brush Color"
    bl_ui_units_x = 12

    def draw(self, context):
        layout = self.layout
        
        tool_settings = context.tool_settings
        image_paint = getattr(tool_settings, 'image_paint', None)
        brush = getattr(image_paint, 'brush', None) if image_paint else None
        
        if not brush:
            layout.label(text="No brush active", icon='INFO')
            return
        
        # Determine if using unified color
        ups = tool_settings.unified_paint_settings
        use_unified = ups.use_unified_color if ups else False
        prop_owner = ups if use_unified else brush
        
        # Color picker with value slider
        layout.template_color_picker(prop_owner, "color", value_slider=True)
        
        # Color property for direct input
        row = layout.row()
        row.prop(prop_owner, "color", text="")

        # Common brush settings (respect unified toggles when available)
        layout.separator()
        settings_col = layout.column(align=True)

        # Size
        size_owner = ups if (ups and getattr(ups, 'use_unified_size', False)) else brush
        if size_owner and hasattr(size_owner, 'size'):
            settings_col.prop(size_owner, 'size', text='Radius')

        # Strength
        strength_owner = ups if (ups and getattr(ups, 'use_unified_strength', False)) else brush
        if strength_owner and hasattr(strength_owner, 'strength'):
            settings_col.prop(strength_owner, 'strength', text='Strength', slider=True)

        # Blend mode
        if hasattr(brush, 'blend'):
            settings_col.prop(brush, 'blend', text='Blend')

        # Alpha toggle (aka Lock Alpha)
        if hasattr(brush, 'use_alpha'):
            settings_col.prop(brush, 'use_alpha', text='Use Alpha')


class VIEW3D_PT_paintsystem_color_settings(Panel):
    """Extra brush/color options shown as a separate popover"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Color Picker Settings"
    bl_ui_units_x = 12

    def draw(self, context):
        layout = self.layout

        tool_settings = context.tool_settings
        image_paint = getattr(tool_settings, 'image_paint', None)
        brush = getattr(image_paint, 'brush', None) if image_paint else None
        ups = getattr(tool_settings, 'unified_paint_settings', None)

        if not brush:
            layout.label(text="No brush active", icon='INFO')
            return

        col = layout.column(align=True)
        if ups:
            col.prop(ups, 'use_unified_color', text='Unified Color')
            col.prop(ups, 'use_unified_size', text='Unified Size')
            col.prop(ups, 'use_unified_strength', text='Unified Strength')

        # A few extra brush controls when available
        if hasattr(brush, 'spacing'):
            col.prop(brush, 'spacing', text='Spacing')
        if hasattr(brush, 'falloff_curve'):  # show a button to edit curve if present
            col.prop(brush, 'curve_preset', text='Falloff')


class VIEW3D_MT_paintsystem_texture_paint_context(Menu):
    bl_label = "Paint System"
    bl_idname = "VIEW3D_MT_paintsystem_texture_paint_context"

    def draw(self, context):
        layout = self.layout
        # Only show the color wheel (brush color popover) and Layers popover
        layout.popover(panel="VIEW3D_PT_paintsystem_brush_color", text="Color Wheel")
        layout.popover(panel="MAT_PT_Layers", text="Layers")


class PAINTSYSTEM_OT_open_texpaint_menu(Operator):
    """Open Paint System menu and show brush color popup (RMB helper).

    This operator is used when the host doesn't provide a native Texture Paint
    RMB menu (e.g., Bforartists). It opens a compact brush color panel near the
    cursor and then the Paint System context menu.
    """
    bl_idname = "paint_system.open_texpaint_menu"
    bl_label = "Open Paint System Menu"
    bl_options = {"INTERNAL"}

    def invoke(self, context, event):
        # Record mouse position so we can place popups relative to it
        self._mouse_x = getattr(event, 'mouse_x', None)
        self._mouse_y = getattr(event, 'mouse_y', None)
        return self.execute(context)

    def execute(self, context):
        # Only act in texture paint-like contexts; otherwise do nothing
        is_texpaint = False
        try:
            is_texpaint = getattr(context, "mode", "") in {"PAINT_TEXTURE", "TEXTURE_PAINT"}
            if not is_texpaint:
                is_texpaint = bool(getattr(getattr(context, "tool_settings", None), "image_paint", None))
        except Exception:
            is_texpaint = False

        if is_texpaint:
            # Then open our Paint System context menu at the current cursor
            try:
                bpy.ops.wm.call_menu(name=VIEW3D_MT_paintsystem_texture_paint_context.bl_idname)
                return {'FINISHED'}
            except Exception:
                pass

        # Fallback: nothing to do
        return {'CANCELLED'}


def _append_to_texture_paint_context_menu():
    # Try multiple known RMB context menu class names across Blender/Bforartists
    candidate_menus = [
        "VIEW3D_MT_paint_texture_context_menu",  # Blender 3.x/4.x Texture Paint
        "VIEW3D_MT_context_menu",               # Generic View3D context menu (fallback)
        "VIEW3D_MT_paint_texture",              # Legacy/variant name
    ]
    print("\n=== Paint System: Attempting to append to RMB menus ===")
    for name in candidate_menus:
        menu_cls = getattr(bpy.types, name, None)
        if menu_cls is not None and menu_cls not in _APPENDED_MENUS:
            try:
                menu_cls.append(draw_entry)
                _APPENDED_MENUS.append(menu_cls)
                print(f"✓ Successfully appended to: {name}")
            except Exception as e:
                print(f"✗ Failed to append to {name}: {e}")
        elif menu_cls is None:
            print(f"✗ Menu class not found: {name}")
        else:
            print(f"⊙ Already appended to: {name}")

    # Additionally, scan active keymaps to discover the actual menu ID used for RIGHTMOUSE
    def _iter_keymaps():
        wm = bpy.context.window_manager
        if not wm:
            return []
        kcs = []
        for attr in ("user", "addon", "blender"):
            kc = getattr(wm.keyconfigs, attr, None)
            if kc:
                kcs.append(kc)
        return kcs

    discovered_ids = set()
    try:
        for kc in _iter_keymaps():
            for km in getattr(kc, "keymaps", []):
                # Look specifically for Image Paint and Texture Paint keymaps
                if "image" in km.name.lower() or "texture" in km.name.lower() or "paint" in km.name.lower():
                    print(f"    Found paint-related keymap: {km.name}")
                    for kmi in getattr(km, "keymap_items", []):
                        if kmi.type == 'RIGHTMOUSE' and kmi.value == 'PRESS':
                            print(f"      RMB keymap item: {kmi.idname}")
                            if kmi.idname in {'wm.call_menu', 'wm.call_menu_pie'}:
                                props = getattr(kmi, 'properties', None)
                                # Some builds may use 'menu' instead of 'name'
                                name = getattr(props, 'name', '') or getattr(props, 'menu', '')
                                if name:
                                    discovered_ids.add(name)
                                    print(f"        Menu: {name}")
        
        if discovered_ids:
            print(f"\n--- Discovered RMB menu IDs from keymaps: {discovered_ids}")
            for menu_id in discovered_ids:
                menu_cls = getattr(bpy.types, menu_id, None)
                if menu_cls is not None and menu_cls not in _APPENDED_MENUS:
                    try:
                        menu_cls.append(draw_entry)
                        _APPENDED_MENUS.append(menu_cls)
                        print(f"✓ Successfully appended to discovered menu: {menu_id}")
                    except Exception as e:
                        print(f"✗ Failed to append to {menu_id}: {e}")
        else:
            print("\n--- No texture/image paint RMB menus found in keymaps!")
            print("    Bforartists may not have a default RMB menu for Texture Paint mode.")
            print("    Will register our menu for manual keymap binding or toolbar access.")
    except Exception as e:
        print(f"✗ Error during keymap scanning: {e}")
        # Best-effort scanning; ignore if keymaps are not accessible at this stage
        pass

    # Broad compatibility: dynamically attach to any likely View3D context menus
    try:
        found_menus = []
        for attr_name in dir(bpy.types):
            cls = getattr(bpy.types, attr_name, None)
            if not cls or not isinstance(cls, type):
                continue
            # Only consider Menu subclasses
            try:
                is_menu = issubclass(cls, Menu)
            except Exception:
                is_menu = False
            if not is_menu:
                continue
            name_l = attr_name.lower()
            # Heuristic: any View3D context menu related to paint/texture
            if (
                "view3d" in name_l and "context" in name_l and ("paint" in name_l or "texture" in name_l)
            ) or (
                # Some variants may drop "context" but still be RMB paint menus
                "view3d" in name_l and ("paint_texture" in name_l or "texture_paint" in name_l)
            ):
                # Avoid appending to our own submenu to prevent recursion/duplicates
                if cls is VIEW3D_MT_paintsystem_texture_paint_context:
                    continue
                found_menus.append(attr_name)
                if cls not in _APPENDED_MENUS:
                    try:
                        cls.append(draw_entry)
                        _APPENDED_MENUS.append(cls)
                        print(f"✓ Successfully appended to heuristic match: {attr_name}")
                    except Exception as e:
                        print(f"✗ Failed to append to {attr_name}: {e}")
        if found_menus:
            print(f"\n--- Found menus via heuristic: {found_menus}")
        else:
            print("\n--- No menus found via heuristic search")
    except Exception as e:
        print(f"✗ Error during heuristic menu scanning: {e}")
        pass
    
    print(f"\n=== Total menus appended to: {len(_APPENDED_MENUS)} ===\n")


def _remove_from_texture_paint_context_menu():
    for menu_cls in _APPENDED_MENUS:
        try:
            menu_cls.remove(draw_entry)
        except Exception:
            pass
    _APPENDED_MENUS.clear()


def draw_entry(self, context):
    layout = self.layout
    
    # Only show in Texture Paint contexts
    is_texpaint = False
    try:
        is_texpaint = getattr(context, "mode", "") in {"PAINT_TEXTURE", "TEXTURE_PAINT"}
        if not is_texpaint:
            is_texpaint = bool(getattr(getattr(context, "tool_settings", None), "image_paint", None))
    except Exception:
        is_texpaint = False

    if is_texpaint:
        layout.separator()

        # Also add the full submenu for additional options
        layout.menu(
            VIEW3D_MT_paintsystem_texture_paint_context.bl_idname,
            text="Paint System",
            icon='BRUSH_DATA'
        )


def register():
    bpy.utils.register_class(VIEW3D_PT_paintsystem_brush_color)
    bpy.utils.register_class(VIEW3D_PT_paintsystem_color_settings)
    bpy.utils.register_class(VIEW3D_MT_paintsystem_texture_paint_context)
    bpy.utils.register_class(PAINTSYSTEM_OT_open_texpaint_menu)
    # Always append to built-in menus - this gives users native brush controls
    # plus our Paint System menu in the same RMB menu
    _append_to_texture_paint_context_menu()
    # Defer a second pass to catch menus registered late by host/other add-ons
    try:
        def _late_attach():
            _append_to_texture_paint_context_menu()
            # Run once
            return None
        bpy.app.timers.register(_late_attach, first_interval=0.6)
    except Exception:
        pass


def unregister():
    _remove_from_texture_paint_context_menu()
    try:
        bpy.utils.unregister_class(PAINTSYSTEM_OT_open_texpaint_menu)
        bpy.utils.unregister_class(VIEW3D_MT_paintsystem_texture_paint_context)
        bpy.utils.unregister_class(VIEW3D_PT_paintsystem_color_settings)
        bpy.utils.unregister_class(VIEW3D_PT_paintsystem_brush_color)
    except Exception:
        pass

