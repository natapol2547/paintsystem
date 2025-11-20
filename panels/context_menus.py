import bpy
from bpy.types import Menu, Panel, Operator
from bpy.props import BoolProperty, EnumProperty

from ..paintsystem.data import parse_context
from ..preferences import get_preferences
from .common import PSContextMixin, scale_content, get_icon
from ..utils.nodes import find_node
from ..utils.unified_brushes import get_unified_settings
from bl_ui.properties_paint_common import UnifiedPaintPanel


_APPENDED_MENUS = []
_BRIDGE_MENUS = []

# Disable RMB override - we'll use menu appending instead
# This ensures users get native brush controls + our Paint System menu
ENABLE_RMB_OVERRIDE_IN_TEXPAINT = False


# --- Minimal palette picker helpers (no create/unlink/fake-user) ---
def _ps_palette_enum_items(self, context):
    try:
        items = [('NONE', 'None', '', 'X', 0)]
        for i, pal in enumerate(getattr(bpy.data, 'palettes', [])):
            # Use generic icon; palettes typically have no previews
            items.append((pal.name, pal.name, '', 'COLOR', i + 1))
        return items
    except Exception:
        return [('NONE', 'None', '', 'X', 0)]


def _ps_palette_enum_update(self, context):
    try:
        ts = getattr(context, 'tool_settings', None)
        ip = getattr(ts, 'image_paint', None) if ts else None
        if not ip:
            return
        wm = context.window_manager
        value = getattr(wm, 'ps_palette_picker', 'NONE')
        if value == 'NONE':
            ip.palette = None
        else:
            pal = bpy.data.palettes.get(value)
            if pal:
                ip.palette = pal
    except Exception:
        pass


class VIEW3D_PT_paintsystem_brush_color(UnifiedPaintPanel, Panel):
    """Quick brush color picker panel for RMB popover"""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Brush Color"
    bl_ui_units_x = 12

    def draw(self, context):
        layout = self.layout
        
        settings = self.paint_settings(context)
        brush = getattr(settings, 'brush', None)
        
        if not brush:
            layout.label(text="No brush active", icon='INFO')
            return
        
        # Color picker with unified binding (matches main Brush Color panel)
        row = layout.row()
        row.scale_y = 1.3
        self.prop_unified_color_picker(row, context, brush, "color", value_slider=True)

        # Swatches (primary/secondary) with unified binding
        row = layout.row(align=True)
        self.prop_unified_color(row, context, brush, "color", text="")
        # Secondary color may be from Unified or Brush depending on toggle
        try:
            self.prop_unified_color(row, context, brush, "secondary_color", text="")
        except Exception:
            pass
        row.operator("paint.brush_colors_flip", icon='FILE_REFRESH', text="")

        # Common brush settings (respect unified toggles when available)
        layout.separator()
        settings_col = layout.column(align=True)

        # Size
        try:
            self.prop_unified(settings_col, context, brush, "size", "use_unified_size", text='Radius')
        except Exception:
            pass

        # Strength
        try:
            self.prop_unified(settings_col, context, brush, "strength", "use_unified_strength", text='Strength', slider=True)
        except Exception:
            pass

        # Blend mode
        if hasattr(brush, 'blend'):
            settings_col.prop(brush, 'blend', text='Blend')

        # Alpha toggle (aka Lock Alpha)
        if hasattr(brush, 'use_alpha'):
            settings_col.prop(brush, 'use_alpha', text='Use Alpha')


class VIEW3D_PT_paintsystem_quick_layers(PSContextMixin, UnifiedPaintPanel, Panel):
    """Quick paint controls + layer stack for RMB popover (as in PinkSystem01)."""
    bl_idname = 'VIEW3D_PT_paintsystem_quick_layers'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Paint Tools"
    bl_options = {'INSTANCED'}
    bl_ui_units_x = 20
    bl_ui_units_y = 27

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_material is not None

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

        split = layout.split(factor=0.48)
        left_col = split.column()
        right_col = split.column()

        if brush:
            color_box = left_col.box()
            color_col = color_box.column()

            color_col.separator(factor=0.3)

            picker_row = color_col.row()
            picker_row.scale_y = 1.5
            self.prop_unified_color_picker(picker_row, context, brush, "color", value_slider=True)

            row = color_col.row(align=True)
            swatches = row.split(factor=0.5, align=True)
            # Primary/Secondary color swatches using unified binding
            self.prop_unified_color(swatches, context, brush, "color", text="")
            try:
                self.prop_unified_color(swatches, context, brush, "secondary_color", text="")
            except Exception:
                # Some modes may not expose secondary_color
                self.prop_unified_color(swatches, context, brush, "color", text="")

            row.operator("paint.brush_colors_flip", text="", icon='FILE_REFRESH')

            try:
                # Use the same dynamic owner selection as Unified helpers
                ups = getattr(context.tool_settings, 'unified_paint_settings', None)
                use_unified = bool(ups and getattr(ups, 'use_unified_color', False))
                data_path = "tool_settings.unified_paint_settings.color" if use_unified else "tool_settings.image_paint.brush.color"
                eyedrop = row.operator("ui.eyedropper_color", text="", icon='EYEDROPPER')
                eyedrop.prop_data_path = data_path
            except Exception:
                pass

            # Quick toggle for HSV sliders (mirrors preference)
            toggle_row = color_col.row(align=True)
            try:
                toggle_row.prop(prefs, "show_hsv_sliders_rmb", text="HSV", toggle=True)
            except Exception:
                pass

            if getattr(prefs, 'show_hsv_sliders_rmb', False):
                hsv_col = color_col.column(align=True)
                # Mirror main Brush Color panel: use ps_scene_data HSV so updates sync both ways
                try:
                    ps_ctx = self.parse_context(context)
                    if getattr(context.preferences.view, 'color_picker_type', '') != "SQUARE_SV":
                        hsv_col.prop(ps_ctx.ps_scene_data, "hue", text="Hue")
                    hsv_col.prop(ps_ctx.ps_scene_data, "saturation", text="Saturation")
                    hsv_col.prop(ps_ctx.ps_scene_data, "value", text="Value")
                except Exception:
                    pass

            if hasattr(brush, 'blend'):
                color_col.prop(brush, 'blend', text='Blend')

            row = color_col.row(align=True)
            try:
                self.prop_unified(row, context, brush, "size", "use_unified_size", text='Radius')
            except Exception:
                pass
            if hasattr(brush, 'use_pressure_size'):
                row.prop(brush, 'use_pressure_size', text="", icon='STYLUS_PRESSURE')

            row = color_col.row(align=True)
            try:
                self.prop_unified(row, context, brush, "strength", "use_unified_strength", text='Strength', slider=True)
            except Exception:
                pass
            if hasattr(brush, 'use_pressure_strength'):
                row.prop(brush, 'use_pressure_strength', text="", icon='STYLUS_PRESSURE')

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
                    swatch_col.template_palette(image_paint, "palette", color=True)
        else:
            left_col.label(text="No active brush", icon='INFO')

        layers_layout = right_col
        layers_layout.separator(factor=0.1)

        if not ps_ctx.active_material:
            layers_layout.label(text="No Paint System Material", icon='INFO')
            return
        if not ps_ctx.active_channel:
            layers_layout.label(text="No Active Channel", icon='INFO')
            return

        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        active_group = ps_ctx.active_group
        mat = ps_ctx.active_material
        layers = active_channel.layers

        group_node = None
        if mat and mat.node_tree and active_group:
            group_node = find_node(mat.node_tree, {
                'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree})

        if not group_node:
            warning_box = layers_layout.box()
            warning_box.alert = True
            warning_col = warning_box.column(align=True)
            warning_col.label(text="Paint System not connected", icon='ERROR')
            warning_col.label(text="to material output!", icon='BLANK1')

        layers_box = layers_layout.box()

        if active_layer and active_layer.node_tree:
            color_mix_node = active_layer.mix_node
            header_col = layers_box.column(align=True)

            main_row = header_col.row(align=True)
            main_row.scale_y = 1.3
            main_row.scale_x = 1.3

            clip_row = main_row.row(align=True)
            clip_row.enabled = not active_layer.lock_layer
            clip_row.prop(active_layer, "is_clip", text="", icon="SELECT_INTERSECT")
            if active_layer.type == 'IMAGE':
                clip_row.prop(active_layer, "lock_alpha", text="", icon='TEXTURE')

            lock_row = main_row.row(align=True)
            lock_row.prop(active_layer, "lock_layer", text="",
                          icon='LOCKED' if active_layer.lock_layer else 'UNLOCKED')

            blend_row = main_row.row(align=True)
            blend_row.enabled = not active_layer.lock_layer
            blend_row.prop(color_mix_node, "blend_type", text="")

            opacity_row = header_col.row(align=True)
            opacity_row.scale_y = 1.3
            opacity_row.enabled = not active_layer.lock_layer

            target_sock = None
            pre_mix = getattr(active_layer, 'pre_mix_node', None)
            if pre_mix and hasattr(pre_mix, 'inputs'):
                target_sock = pre_mix.inputs.get('Opacity')
            if target_sock is None:
                mix_node = getattr(active_layer, 'mix_node', None)
                if mix_node and hasattr(mix_node, 'inputs'):
                    target_sock = (
                        mix_node.inputs.get('Opacity') or
                        mix_node.inputs.get('Fac') or
                        mix_node.inputs.get('Factor')
                    )

            if target_sock is not None:
                opacity_row.prop(
                    target_sock,
                    "default_value",
                    text="Opacity",
                    slider=True,
                )

        row = layers_box.row()
        layers_col = row.column()
        scale_content(context, row, scale_x=1, scale_y=1.5)
        layers_col.template_list(
            "MAT_PT_UL_LayerList", "",
            active_channel, "layers",
            active_channel, "active_index",
            rows=min(max(6, len(layers)), 7)
        )

        col = row.column(align=True)
        col.scale_x = 1.2
        col.operator("wm.call_menu", text="", icon_value=get_icon('layer_add')).name = "MAT_MT_AddLayerMenu"
        col.operator("paint_system.new_folder_layer", icon_value=get_icon('folder'), text="")
        col.menu("MAT_MT_LayerMenu", text="", icon='COLLAPSEMENU')
        col.separator(type='LINE')
        col.operator("paint_system.delete_item", text="", icon="TRASH")
        col.separator(type='LINE')
        col.operator("paint_system.move_up", icon="TRIA_UP", text="")
        col.operator("paint_system.move_down", icon="TRIA_DOWN", text="")


class VIEW3D_PT_paintsystem_rmb_popover(Panel):
    """Custom Paint System popover for RMB - contains only selected PS functions."""
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'WINDOW'
    bl_label = "Paint System"
    bl_options = {'INSTANCED'}
    bl_ui_units_x = 12

    def draw(self, context):
        layout = self.layout
        ps_ctx = parse_context(context)
        
        if not ps_ctx.active_material:
            layout.label(text="No Paint System Material", icon='INFO')
            return
        
        # Get active layer for quick actions
        active_layer = ps_ctx.active_layer
        
        # Quick layer operations
        col = layout.column(align=True)
        col.label(text="Quick Layer Actions:", icon='RENDERLAYERS')
        
        row = col.row(align=True)
        row.operator("paint_system.add_layer", text="Add Layer", icon='ADD')
        if active_layer:
            row.operator("paint_system.duplicate_layer", text="Duplicate", icon='DUPLICATE')
        
        if active_layer:
            row = col.row(align=True)
            row.operator("paint_system.delete_layer", text="Delete Layer", icon='TRASH')
            
        col.separator()
        
        # Layer visibility toggle
        if active_layer:
            row = col.row(align=True)
            row.prop(active_layer, "visible", text="Layer Visible", toggle=True)
            row.prop(active_layer, "lock_alpha", text="Lock Alpha", toggle=True)
        
        col.separator()
        
        # Open full layers panel button
        col.operator("paint_system.open_layers_popover", text="Open Full Layers Panel", icon='WINDOW')


class VIEW3D_MT_paintsystem_texture_paint_context(Menu):
    bl_label = "Paint System"
    bl_idname = "VIEW3D_MT_paintsystem_texture_paint_context"

    def draw(self, context):
        layout = self.layout
        layout.operator("paint_system.open_texpaint_menu", text="Paint Tools Popover", icon='BRUSHES_ALL')
        layout.separator()
        layout.operator("paint_system.open_layers_popover", text="Paint System Layers", icon='RENDERLAYERS')


class PAINTSYSTEM_OT_open_texpaint_menu(Operator):
    """Open Quick Layers panel on RMB."""
    bl_idname = "paint_system.open_texpaint_menu"
    bl_label = "Open Paint System Quick Layers"
    bl_options = {"INTERNAL"}

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
            # Open Quick Layers panel as popover
            try:
                bpy.ops.wm.call_panel(name="VIEW3D_PT_paintsystem_quick_layers")
                return {'FINISHED'}
            except Exception as e:
                print(f"Paint System RMB: Error opening Quick Layers panel: {e}")
                return {'CANCELLED'}
        
        # Not in texture paint mode - pass through
        return {'PASS_THROUGH'}


class PAINTSYSTEM_OT_open_layers_popover(Operator):
    """Open the Layers panel as a floating popover near the mouse."""
    bl_idname = "paint_system.open_layers_popover"
    bl_label = "Open Layers Panel"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        try:
            # Set a transient flag so the Layers panel knows to hide inline settings in popover
            wm = context.window_manager
            setattr(wm, 'ps_layers_popover_only', True)

            # Schedule flag reset shortly after drawing
            def _reset_flag():
                try:
                    setattr(bpy.context.window_manager, 'ps_layers_popover_only', False)
                except Exception:
                    pass
                return None
            try:
                bpy.app.timers.register(_reset_flag, first_interval=0.25)
            except Exception:
                # If timers unavailable, we'll rely on next invocation to override
                pass

            # Opens panel near the mouse cursor
            bpy.ops.wm.call_panel(name="MAT_PT_Layers")
            return {'FINISHED'}
        except Exception:
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
                # Never append into our own menu class to avoid recursion/duplicates
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
                        if menu_cls is VIEW3D_MT_paintsystem_texture_paint_context:
                            continue
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

    # Only add entries when paint tools are relevant
    mode = getattr(context, "mode", "")
    has_paint_settings = bool(getattr(getattr(context, "tool_settings", None), "image_paint", None))
    if mode not in {"PAINT_TEXTURE", "TEXTURE_PAINT"} and not has_paint_settings:
        return

    layout.separator()
    layout.operator("paint_system.open_texpaint_menu", text="Paint Tools Popover", icon='BRUSHES_ALL')
    layout.operator("paint_system.open_layers_popover", text="Paint System Layers", icon='RENDERLAYERS')


def register():
    bpy.utils.register_class(VIEW3D_PT_paintsystem_brush_color)
    bpy.utils.register_class(VIEW3D_PT_paintsystem_quick_layers)
    bpy.utils.register_class(VIEW3D_PT_paintsystem_rmb_popover)
    bpy.utils.register_class(VIEW3D_MT_paintsystem_texture_paint_context)
    bpy.utils.register_class(PAINTSYSTEM_OT_open_texpaint_menu)
    bpy.utils.register_class(PAINTSYSTEM_OT_open_layers_popover)
    
    # Register WindowManager property for layers popover flag
    bpy.types.WindowManager.ps_layers_popover_only = BoolProperty(
        name="Layers Popover Only Mode",
        description="When True, only show layer list without settings panels",
        default=False
    )

    # Minimal palette picker (no buttons) for RMB popover
    bpy.types.WindowManager.ps_palette_picker = EnumProperty(
        name="Palette Picker",
        description="Select existing palette (no create/unlink controls)",
        items=_ps_palette_enum_items,
        update=_ps_palette_enum_update,
        options={'SKIP_SAVE'}
    )
    
    # Optionally provide bridges to standard Texture Paint RMB menu IDs when missing.
    # This makes our RMB menu "known as" the Texture Paint RMB menu for keymaps/scripts.
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
        # Legacy/variant ID sometimes used in builds
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
    # Unregister bridges if we registered any
    for cls in _BRIDGE_MENUS[::-1]:
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass
    _BRIDGE_MENUS.clear()
    
    # Delete WindowManager properties safely
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
    
    try:
        bpy.utils.unregister_class(PAINTSYSTEM_OT_open_layers_popover)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(PAINTSYSTEM_OT_open_texpaint_menu)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(VIEW3D_MT_paintsystem_texture_paint_context)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(VIEW3D_PT_paintsystem_rmb_popover)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(VIEW3D_PT_paintsystem_quick_layers)
    except Exception:
        pass
    try:
        bpy.utils.unregister_class(VIEW3D_PT_paintsystem_brush_color)
    except Exception:
        pass
