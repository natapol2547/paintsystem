import bpy
import logging
from bpy.types import Menu, Panel, Operator
from bpy.props import BoolProperty, EnumProperty

from ..paintsystem.data import parse_context
from ..preferences import get_preferences
from .common import PSContextMixin, scale_content, get_icon
from ..utils.nodes import find_node
from bl_ui.properties_paint_common import UnifiedPaintPanel

logger = logging.getLogger("PaintSystem")

_APPENDED_MENUS = []
_BRIDGE_MENUS = []
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = False  # kept for clarity; not used

# ---------------- Palette Enum Helpers -----------------
def _ps_palette_enum_items(self, context):
    try:
        items = [('NONE', 'No Active Palette', '', 'X', 0)]
        for i, pal in enumerate(getattr(bpy.data, 'palettes', [])):
            items.append((pal.name, pal.name, '', 'COLOR', i + 1))
        return items
    except Exception as e:
        logger.debug(f"Error loading palette enum: {e}")
        return [('NONE', 'No Active Palette', '', 'X', 0)]


def _ps_palette_enum_update(self, context):
    """Apply selected palette to image paint settings (no creation/removal)."""
    try:
        ts = getattr(context, 'tool_settings', None)
        ip = getattr(ts, 'image_paint', None) if ts else None
        if not ip:
            return
        wm = context.window_manager
        val = getattr(wm, 'ps_palette_picker', 'NONE')
        if val == 'NONE':
            try:
                ip.palette = None
            except Exception as e:
                logger.warning(f"Failed to clear palette: {e}")
            return
        pal = bpy.data.palettes.get(val)
        if pal:
            try:
                ip.palette = pal
            except Exception as e:
                logger.warning(f"Failed to set palette {val}: {e}")
    except Exception as e:
        logger.error(f"Palette update error: {e}")


# ---------------- Quick Layers Panel (Adaptive) -----------------
class VIEW3D_PT_paintsystem_quick_layers(PSContextMixin, UnifiedPaintPanel, Panel):
    """Compact RMB popover panel: brush controls and palette only (no layers)."""
    bl_idname = 'VIEW3D_PT_paintsystem_quick_layers'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Paint Tools"
    bl_options = {'INSTANCED'}
    bl_ui_units_x = 12
    bl_ui_units_y = 20

    @classmethod
    def poll(cls, context):
        # Always allow in paint contexts so brush tools accessible even before PS setup
        mode = getattr(context, 'mode', '')
        ts = getattr(context, 'tool_settings', None)
        ip = getattr(ts, 'image_paint', None) if ts else None
        return mode in {'PAINT_TEXTURE', 'TEXTURE_PAINT'} or bool(ip)

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = False
        layout.use_property_decorate = False

        ps_ctx = self.parse_context(context)
        prefs = get_preferences(context)
        settings = self.paint_settings(context)
        brush = getattr(settings, 'brush', None)
        tool_settings = context.tool_settings
        image_paint = getattr(tool_settings, 'image_paint', None)
        wm = context.window_manager

        # Compact mode: only brush controls, no layers UI
        picker_scale = 1.2
        left_col = layout.column()

        # ------------- Brush & Color Section -------------
        if brush:
            color_box = left_col.box()
            color_col = color_box.column(align=True)

            picker_row = color_col.row()
            picker_row.scale_y = picker_scale
            try:
                self.prop_unified_color_picker(picker_row, context, brush, "color", value_slider=True)
            except Exception:
                pass

            swatch_row = color_col.row(align=True)
            swatches = swatch_row.split(factor=0.5, align=True)
            try:
                self.prop_unified_color(swatches, context, brush, "color", text="")
            except Exception:
                pass
            try:
                self.prop_unified_color(swatches, context, brush, "secondary_color", text="")
            except Exception:
                # Fallback: duplicate primary if secondary unavailable
                try:
                    self.prop_unified_color(swatches, context, brush, "color", text="")
                except Exception:
                    pass
            swatch_row.operator("paint.brush_colors_flip", text="", icon='FILE_REFRESH')
            try:
                ups = getattr(context.tool_settings, 'unified_paint_settings', None)
                use_unified = bool(ups and getattr(ups, 'use_unified_color', False))
                data_path = "tool_settings.unified_paint_settings.color" if use_unified else "tool_settings.image_paint.brush.color"
                eyedrop = swatch_row.operator("ui.eyedropper_color", text="", icon='EYEDROPPER')
                eyedrop.prop_data_path = data_path
            except Exception:
                pass

            if getattr(prefs, 'show_hsv_sliders_rmb', False):
                hsv_col = color_col.column(align=True)
                try:
                    # Skip Hue slider if square picker already provides it separately
                    if getattr(context.preferences.view, 'color_picker_type', '') != "SQUARE_SV":
                        hsv_col.prop(ps_ctx.ps_scene_data, "hue", text="Hue")
                    hsv_col.prop(ps_ctx.ps_scene_data, "saturation", text="Saturation")
                    hsv_col.prop(ps_ctx.ps_scene_data, "value", text="Value")
                except Exception:
                    pass

            # Separator between HSV and brush settings
            color_col.separator()

            # Basic brush params
            size_row = color_col.row(align=True)
            try:
                self.prop_unified(size_row, context, brush, "size", "use_unified_size", text='Radius')
            except Exception:
                pass
            if hasattr(brush, 'use_pressure_size'):
                size_row.prop(brush, 'use_pressure_size', text='', icon='STYLUS_PRESSURE')
            strength_row = color_col.row(align=True)
            try:
                self.prop_unified(strength_row, context, brush, "strength", "use_unified_strength", text='Strength', slider=True)
            except Exception:
                pass
            if hasattr(brush, 'use_pressure_strength'):
                strength_row.prop(brush, 'use_pressure_strength', text='', icon='STYLUS_PRESSURE')

            # Palette section (optional)
            if image_paint and getattr(prefs, 'show_active_palette_rmb', True):
                palette_box = color_col.box()
                palette_col = palette_box.column(align=True)
                if wm and hasattr(wm, 'ps_palette_picker'):
                    try:
                        palette = getattr(image_paint, 'palette', None)
                        target_value = palette.name if palette else 'NONE'
                        if getattr(wm, 'ps_palette_picker', 'NONE') != target_value:
                            setattr(wm, 'ps_palette_picker', target_value)
                        palette_col.prop(wm, 'ps_palette_picker', text="")
                    except Exception:
                        pass
                palette = getattr(image_paint, 'palette', None)
                if palette:
                    swatch_col = palette_col.column()
                    swatch_col.scale_x = 0.8
                    swatch_col.scale_y = 0.8
                    try:
                        swatch_col.template_palette(image_paint, "palette", color=True)
                    except Exception:
                        pass
        else:
            left_col.label(text="No active brush", icon='INFO')


# ---------------- RMB Menu (Context) -----------------
class VIEW3D_MT_paintsystem_texture_paint_context(Menu):
    bl_label = "Paint System"
    bl_idname = "VIEW3D_MT_paintsystem_texture_paint_context"

    def draw(self, context):
        layout = self.layout
        layout.operator("paint_system.open_texpaint_menu", text="Paint Tools Popover", icon='BRUSHES_ALL')
        layout.separator()
        layout.operator("paint_system.open_layers_popover", text="Paint System Layers", icon='RENDERLAYERS')


class PAINTSYSTEM_OT_open_texpaint_menu(Operator):
    bl_idname = "paint_system.open_texpaint_menu"
    bl_label = "Open Paint System Quick Layers"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        is_texpaint = False
        try:
            is_texpaint = getattr(context, "mode", "") in {"PAINT_TEXTURE", "TEXTURE_PAINT"}
            if not is_texpaint:
                is_texpaint = bool(getattr(getattr(context, "tool_settings", None), "image_paint", None))
        except Exception:
            is_texpaint = False
        if is_texpaint:
            try:
                bpy.ops.wm.call_panel(name="VIEW3D_PT_paintsystem_quick_layers")
                return {'FINISHED'}
            except Exception as e:
                print(f"Paint System RMB: Error opening Quick Layers panel: {e}")
                return {'CANCELLED'}
        return {'PASS_THROUGH'}


class PAINTSYSTEM_OT_open_layers_popover(Operator):
    bl_idname = "paint_system.open_layers_popover"
    bl_label = "Open Layers Panel"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        try:
            wm = context.window_manager
            setattr(wm, 'ps_layers_popover_only', True)

            def _reset_flag():
                try:
                    setattr(bpy.context.window_manager, 'ps_layers_popover_only', False)
                except Exception:
                    pass
                return None
            try:
                bpy.app.timers.register(_reset_flag, first_interval=0.25)
            except Exception:
                pass
            bpy.ops.wm.call_panel(name="MAT_PT_Layers")
            return {'FINISHED'}
        except Exception:
            return {'CANCELLED'}


# ---------------- Menu Attachment Helpers -----------------
def _append_to_texture_paint_context_menu():
    candidate_menus = [
        "VIEW3D_MT_paint_texture_context_menu",
        "VIEW3D_MT_context_menu",
        "VIEW3D_MT_paint_texture",
    ]
    print("\n=== Paint System: Attempting to append to RMB menus ===")
    for name in candidate_menus:
        menu_cls = getattr(bpy.types, name, None)
        if menu_cls is not None and menu_cls not in _APPENDED_MENUS:
            try:
                if menu_cls is VIEW3D_MT_paintsystem_texture_paint_context:
                    continue
                menu_cls.append(draw_entry)
                _APPENDED_MENUS.append(menu_cls)
                print(f"✓ Successfully appended to: {name}")
            except Exception as e:
                print(f"✗ Failed to append to {name}: {e}")
        elif menu_cls is None:
            print(f"✗ Menu class not found: {name}")
        else:
            print(f"⊙ Already appended to: {name}")

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
                if any(word in km.name.lower() for word in ("image", "texture", "paint")):
                    print(f"    Found paint-related keymap: {km.name}")
                    for kmi in getattr(km, "keymap_items", []):
                        if kmi.type == 'RIGHTMOUSE' and kmi.value == 'PRESS':
                            print(f"      RMB keymap item: {kmi.idname}")
                            if kmi.idname in {'wm.call_menu', 'wm.call_menu_pie'}:
                                props = getattr(kmi, 'properties', None)
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
                        if menu_cls is VIEW3D_MT_paintsystem_texture_paint_context:
                            continue
                        menu_cls.append(draw_entry)
                        _APPENDED_MENUS.append(menu_cls)
                        print(f"✓ Successfully appended to discovered menu: {menu_id}")
                    except Exception as e:
                        print(f"✗ Failed to append to {menu_id}: {e}")
        else:
            print("\n--- No texture/image paint RMB menus found in keymaps!")
            print("    Will register our menu for manual keymap binding or toolbar access.")
    except Exception as e:
        print(f"✗ Error during keymap scanning: {e}")
        pass

    try:
        found_menus = []
        for attr_name in dir(bpy.types):
            cls = getattr(bpy.types, attr_name, None)
            if not cls or not isinstance(cls, type):
                continue
            try:
                is_menu = issubclass(cls, Menu)
            except Exception:
                is_menu = False
            if not is_menu:
                continue
            name_l = attr_name.lower()
            if ("view3d" in name_l and "context" in name_l and ("paint" in name_l or "texture" in name_l)) or ("view3d" in name_l and ("paint_texture" in name_l or "texture_paint" in name_l)):
                found_menus.append(attr_name)
                if cls not in _APPENDED_MENUS:
                    try:
                        if cls is VIEW3D_MT_paintsystem_texture_paint_context:
                            continue
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
    layout = getattr(self, 'layout', None)
    if layout is None:
        return
    mode = getattr(context, "mode", "")
    has_paint_settings = bool(getattr(getattr(context, "tool_settings", None), "image_paint", None))
    if mode not in {"PAINT_TEXTURE", "TEXTURE_PAINT"} and not has_paint_settings:
        return
    prefs = get_preferences(context)
    layout.separator()
    layout.operator("paint_system.open_texpaint_menu", text="Paint Tools Popover", icon='BRUSHES_ALL')
    if getattr(prefs, 'show_rmb_layers_panel', True):
        layout.operator("paint_system.open_layers_popover", text="Paint System Layers", icon='RENDERLAYERS')


def register():
    bpy.utils.register_class(VIEW3D_PT_paintsystem_quick_layers)
    bpy.utils.register_class(VIEW3D_MT_paintsystem_texture_paint_context)
    bpy.utils.register_class(PAINTSYSTEM_OT_open_texpaint_menu)
    bpy.utils.register_class(PAINTSYSTEM_OT_open_layers_popover)

    bpy.types.WindowManager.ps_layers_popover_only = BoolProperty(
        name="Layers Popover Only Mode",
        description="When True, only show layer list without settings panels",
        default=False
    )

    bpy.types.WindowManager.ps_palette_picker = EnumProperty(
        name="Palette Picker",
        description="Select existing palette (no create/unlink controls)",
        items=_ps_palette_enum_items,
        update=_ps_palette_enum_update,
        options={'SKIP_SAVE'}
    )

    try:
        if not hasattr(bpy.types, 'VIEW3D_MT_paint_texture_context_menu'):
            class VIEW3D_MT_PaintSystem_TexturePaintMenuBridge(Menu):
                bl_space_type = 'VIEW_3D'
                bl_region_type = 'WINDOW'
                bl_label = "Texture Paint"
                bl_idname = "VIEW3D_MT_paint_texture_context_menu"
                def draw(self, context):
                    draw_entry(self, context)
            bpy.utils.register_class(VIEW3D_MT_PaintSystem_TexturePaintMenuBridge)
            _BRIDGE_MENUS.append(VIEW3D_MT_PaintSystem_TexturePaintMenuBridge)
        if not hasattr(bpy.types, 'VIEW3D_MT_paint_texture'):
            class VIEW3D_MT_PaintSystem_TexturePaintMenuBridgeLegacy(Menu):
                bl_space_type = 'VIEW_3D'
                bl_region_type = 'WINDOW'
                bl_label = "Texture Paint"
                bl_idname = "VIEW3D_MT_paint_texture"
                def draw(self, context):
                    draw_entry(self, context)
            bpy.utils.register_class(VIEW3D_MT_PaintSystem_TexturePaintMenuBridgeLegacy)
            _BRIDGE_MENUS.append(VIEW3D_MT_PaintSystem_TexturePaintMenuBridgeLegacy)
    except Exception:
        pass

    _append_to_texture_paint_context_menu()
    try:
        def _late_attach():
            _append_to_texture_paint_context_menu(); return None
        bpy.app.timers.register(_late_attach, first_interval=0.6)
    except Exception:
        pass


def unregister():
    _remove_from_texture_paint_context_menu()
    for cls in _BRIDGE_MENUS[::-1]:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _BRIDGE_MENUS.clear()
    try:
        if hasattr(bpy.types.WindowManager, 'ps_layers_popover_only'):
            del bpy.types.WindowManager.ps_layers_popover_only
    except Exception:
        pass
    try:
        if hasattr(bpy.types.WindowManager, 'ps_palette_picker'):
            del bpy.types.WindowManager.ps_palette_picker
    except Exception:
        pass
    for cls in [PAINTSYSTEM_OT_open_layers_popover, PAINTSYSTEM_OT_open_texpaint_menu, VIEW3D_MT_paintsystem_texture_paint_context, VIEW3D_PT_paintsystem_quick_layers]:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
