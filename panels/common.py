import bpy
from bpy.types import Image, ImagePreview
import numpy as np

from ..utils.version import is_newer_than

# --
from ..paintsystem.data import Channel, Layer
from ..paintsystem.context import PSContextMixin
from ..custom_icons import get_icon, get_icon_from_socket_type
from ..preferences import get_preferences
from ..utils.nodes import find_node, get_material_output, traverse_connected_nodes

def scale_content(context, layout, scale_x=1.2, scale_y=1.2):
    """Scale the content of the panel."""
    prefs = get_preferences(context)
    if not prefs.use_compact_design:
        layout.scale_x = scale_x
        layout.scale_y = scale_y
    return layout

icons = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items.keys()

def icon_parser(icon: str, default="NONE") -> str:
    if icon in icons:
        return icon
    return default


def is_uv_edit_active(context) -> bool:
    return bool(
        context
        and context.scene
        and getattr(context.scene, "ps_scene_data", None)
        and context.scene.ps_scene_data.uv_edit_enabled
    )


def draw_uv_edit_alert(layout: bpy.types.UILayout, context: bpy.types.Context) -> bool:
    if not context or not context.scene or not context.scene.ps_scene_data:
        return False
    ps_scene_data = context.scene.ps_scene_data
    if not ps_scene_data.uv_edit_enabled:
        return False
    alert_box = layout.box()
    alert_box.alert = True
    current_uv = ps_scene_data.uv_edit_target_uv or "(not set)"
    alert_box.label(text="UV Edit Mode Active", icon="ERROR")
    alert_box.label(text=f"Editing UV: {current_uv}", icon="UV")
    alert_row = alert_box.row(align=True)
    alert_row.operator("paint_system.exit_uv_edit", text="Exit UV Edit", icon="CANCEL")
    alert_box.alert = False
    return True


def draw_uv_edit_checker(layout: bpy.types.UILayout, context: bpy.types.Context, show_apply: bool = True) -> None:
    if not context or not context.scene or not context.scene.ps_scene_data:
        return
    ps_scene_data = context.scene.ps_scene_data
    if not ps_scene_data.uv_edit_enabled:
        return
    checker_box = layout.box()
    checker_box.use_property_split = False
    checker_box.use_property_decorate = False
    checker_box.label(text="UV Checker", icon="GRID")
    toggle_row = checker_box.row(align=True)
    scale_content(context, toggle_row, 1.1, 1.1)
    toggle_row.prop(
        ps_scene_data,
        "uv_edit_checker_enabled",
        text="Enable Checker",
        toggle=True,
        icon="HIDE_OFF" if ps_scene_data.uv_edit_checker_enabled else "HIDE_ON",
    )
    if not ps_scene_data.uv_edit_checker_enabled:
        if show_apply:
            apply_row = layout.row(align=True)
            scale_content(context, apply_row, 1.1, 1.1)
            apply_row.operator("paint_system.apply_uv_edit", text="Apply UV Edit", icon="FILE_TICK")
        return
    row = checker_box.row(align=True)
    row.prop(ps_scene_data, "uv_edit_checker_type", expand=True)
    checker_box.label(text="Checker Resolution", icon="IMAGE")
    res_col = checker_box.column(align=True)
    res_col.scale_y = 1.1
    res_col.scale_x = 1.1
    res_grid = res_col.grid_flow(columns=3, align=True, even_columns=True, even_rows=True, row_major=True)
    res_grid.prop(ps_scene_data, "uv_edit_checker_resolution", expand=True)
    if show_apply:
        apply_row = layout.row(align=True)
        scale_content(context, apply_row, 1.1, 1.1)
        apply_row.operator("paint_system.apply_uv_edit", text="Apply UV Edit", icon="FILE_TICK")


def get_icon_from_channel(channel: Channel) -> int:
    type_to_icon = {
        'COLOR': 'color_socket',
        'VECTOR': 'vector_socket',
        'FLOAT': 'float_socket',
    }
    return get_icon(type_to_icon.get(channel.type, 'color_socket'))




def get_event_icons(kmi: bpy.types.KeyMapItem) -> list[str]:
    """Return a list of icons for a keymap item, including modifiers

    Args:
        kmi: KeyMapItem object

    Returns:
        list: List of Blender icon identifiers
    """
    
    if not kmi:
        return []
    # Create a list to store all icons
    icons = []

    # Add modifier icons first (in standard order)
    if kmi.ctrl:
        icons.append('EVENT_CTRL')
    if kmi.alt:
        icons.append('EVENT_ALT')
    if kmi.shift:
        icons.append('EVENT_SHIFT')
    if kmi.oskey:
        icons.append('EVENT_OS')

    # Dictionary mapping key types to icons
    key_icons = {
        # Mouse
        'LEFTMOUSE': 'MOUSE_LMB',
        'RIGHTMOUSE': 'MOUSE_RMB',
        'MIDDLEMOUSE': 'MOUSE_MMB',
        'WHEELUPMOUSE': 'MOUSE_LMB_DRAG',
        'WHEELDOWNMOUSE': 'MOUSE_LMB_DRAG',

        # Special keys
        'ESC': 'EVENT_ESC',
        'RET': 'EVENT_RETURN',
        'SPACE': 'EVENT_SPACEKEY',
        'TAB': 'EVENT_TAB',
        'DEL': 'EVENT_DELETEKEY',
        'BACK_SPACE': 'EVENT_BACKSPACEKEY',
        'COMMA': 'EVENT_COMMA',
        'PERIOD': 'EVENT_PERIOD',
        'SEMI_COLON': 'EVENT_SEMI_COLON',
        'QUOTE': 'EVENT_QUOTE',

        # Numbers
        '0': 'EVENT_0',
        '1': 'EVENT_1',
        '2': 'EVENT_2',
        '3': 'EVENT_3',
        '4': 'EVENT_4',
        '5': 'EVENT_5',
        '6': 'EVENT_6',
        '7': 'EVENT_7',
        '8': 'EVENT_8',
        '9': 'EVENT_9',

        # Letters
        'A': 'EVENT_A',
        'B': 'EVENT_B',
        'C': 'EVENT_C',
        'D': 'EVENT_D',
        'E': 'EVENT_E',
        'F': 'EVENT_F',
        'G': 'EVENT_G',
        'H': 'EVENT_H',
        'I': 'EVENT_I',
        'J': 'EVENT_J',
        'K': 'EVENT_K',
        'L': 'EVENT_L',
        'M': 'EVENT_M',
        'N': 'EVENT_N',
        'O': 'EVENT_O',
        'P': 'EVENT_P',
        'Q': 'EVENT_Q',
        'R': 'EVENT_R',
        'S': 'EVENT_S',
        'T': 'EVENT_T',
        'U': 'EVENT_U',
        'V': 'EVENT_V',
        'W': 'EVENT_W',
        'X': 'EVENT_X',
        'Y': 'EVENT_Y',
        'Z': 'EVENT_Z',

        # Function keys
        'F1': 'EVENT_F1',
        'F2': 'EVENT_F2',
        'F3': 'EVENT_F3',
        'F4': 'EVENT_F4',
        'F5': 'EVENT_F5',
        'F6': 'EVENT_F6',
        'F7': 'EVENT_F7',
        'F8': 'EVENT_F8',
        'F9': 'EVENT_F9',
        'F10': 'EVENT_F10',
        'F11': 'EVENT_F11',
        'F12': 'EVENT_F12',

        # Arrows
        'LEFT_ARROW': 'EVENT_LEFT_ARROW',
        'RIGHT_ARROW': 'EVENT_RIGHT_ARROW',
        'UP_ARROW': 'EVENT_UP_ARROW',
        'DOWN_ARROW': 'EVENT_DOWN_ARROW',

        # Numpad
        'NUMPAD_0': 'EVENT_0',
        'NUMPAD_1': 'EVENT_1',
        'NUMPAD_2': 'EVENT_2',
        'NUMPAD_3': 'EVENT_3',
        'NUMPAD_4': 'EVENT_4',
        'NUMPAD_5': 'EVENT_5',
        'NUMPAD_6': 'EVENT_6',
        'NUMPAD_7': 'EVENT_7',
        'NUMPAD_8': 'EVENT_8',
        'NUMPAD_9': 'EVENT_9',
        'NUMPAD_PLUS': 'EVENT_PLUS',
        'NUMPAD_MINUS': 'EVENT_MINUS',
        'NUMPAD_ASTERIX': 'EVENT_ASTERISK',
        'NUMPAD_SLASH': 'EVENT_SLASH',
        'NUMPAD_PERIOD': 'EVENT_PERIOD',
        'NUMPAD_ENTER': 'EVENT_RETURN',
    }

    # Add the key icon if it exists in our mapping
    if kmi.type in key_icons:
        icons.append(key_icons[kmi.type])
    else:
        # Fall back to a generic keyboard icon for unknown keys
        icons.append('KEYINGSET')

    return icons

def find_keymap(keymap_name):
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        for km in kc.keymaps:
            if km:
                kmi = km.keymap_items.get(keymap_name)
                if kmi:
                    return kmi
    return None

def find_keymap_by_name(keymap_name) -> list[bpy.types.KeyMapItem]:
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.user
    if kc:
        for km in kc.keymaps:
            if km:
                for kmi in km.keymap_items:
                    if kmi.name == keymap_name:
                        return kmi
    return None

def check_group_multiuser(group_node_tree: bpy.types.NodeTree) -> bool:
    user_count = 0
    for mat in bpy.data.materials:
        if hasattr(mat, "ps_mat_data") and mat.ps_mat_data.groups:
            for group in mat.ps_mat_data.groups:
                if group.node_tree == group_node_tree:
                    user_count += 1
    return user_count > 1


def image_node_settings(layout: bpy.types.UILayout, image_node: bpy.types.Node, data, propname="image", text="", icon="NONE", icon_value=None, default_closed=True, simple_ui=False):
    if simple_ui:
        box = layout
    else:
        box = layout.box()
    header, panel = box.panel("image_node_settings_panel", default_closed=default_closed)
    if data[propname]:
        row = header.row(align=True)
        row.prop(data, propname, text="")
        if simple_ui:
            row.operator("paint_system.export_image", text="", icon="EXPORT").image_name = image_node.image.name
            row.menu("MAT_MT_ImageMenu",
                    text="", icon='COLLAPSEMENU')
    else:
        header.template_ID(data, propname, text="", new="image.new", open="image.open")
    if panel:
        col = panel.column()
        if text or icon != "NONE" or icon_value:
            col.label(text=text, icon=icon)
            if icon_value:
                col.label(text=text, icon_value=icon_value)
            col.separator()
        col.use_property_split = True
        col.use_property_decorate = False
        image = image_node.image
        if not simple_ui and image:
            row = col.row(align=True)
            row.operator("paint_system.export_image", text="Export As...", icon="EXPORT").image_name = image.name
            row.menu("MAT_MT_ImageMenu",
                    text="", icon='COLLAPSEMENU')
            col.separator()
        if image:
            col.label(text="UDIM tiles: " + ", ".join(str(t.number) for t in image.tiles), icon='UV')
        col.prop(image_node, "interpolation",
                    text="")
        col.prop(image_node, "projection",
                    text="")
        col.prop(image_node, "extension",
                    text="")
        if image:
            col.prop(image, "source",
                        text="")
            # Color space settings
            col.prop(image.colorspace_settings, "name", text="Color Space")
            col.prop(image, "alpha_mode", text="Alpha")
    return panel


def is_basic_setup(node_tree: bpy.types.NodeTree) -> bool:
    material_output = get_material_output(node_tree)
    nodes = traverse_connected_nodes(material_output)
    is_basic_setup = True
    if len(nodes) <= 1:
        return True
    # Only first 3 nodes
    for check in ('ShaderNodeGroup', 'ShaderNodeMixShader', 'ShaderNodeBsdfTransparent'):
        if not any(node.bl_idname == check for node in nodes):
            is_basic_setup = False
            break
    return is_basic_setup


def toggle_paint_mode_ui(layout: bpy.types.UILayout, context: bpy.types.Context):
    if is_uv_edit_active(context):
        return
    current_mode = context.mode
    ps_ctx = PSContextMixin.parse_context(context)
    active_group = ps_ctx.active_group
    active_channel = ps_ctx.active_channel
    mat = ps_ctx.active_material
    col = layout.column(align=True)
    row = col.row(align=True)
    row.scale_y = 1.7
    row.scale_x = 1.7
    paint_row = row.row(align=True)
    paint_row.operator("paint_system.toggle_paint_mode",
        text="Toggle Paint Mode", depress=current_mode == 'PAINT_TEXTURE', icon_value=get_icon('paintbrush'))
    
    group_node = find_node(mat.node_tree, {
                                'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree})
    if (not is_basic_setup(mat.node_tree) or len(active_group.channels) > 1 or ps_ctx.ps_mat_data.preview_channel) and group_node:
                row.operator("paint_system.isolate_active_channel",
                            text="", depress=ps_ctx.ps_mat_data.preview_channel, icon_value=get_icon_from_channel(ps_ctx.active_channel) if ps_ctx.ps_mat_data.preview_channel else get_icon("channel"))
    row.operator("wm.save_mainfile",
                text="", icon_value=get_icon('save'))
    
    # Baking and Exporting
    
    if ps_ctx.ps_object.type == 'MESH':
        paint_row.enabled = not active_channel.use_bake_image
        if ps_ctx.ps_settings.show_tooltips and not ps_ctx.ps_settings.hide_norm_paint_tips and active_group.template in {'NORMAL', 'PBR'} and any(channel.name == 'Normal' for channel in active_group.channels) and active_channel.name == 'Normal':
            row = col.row(align=True)
            row.scale_y = 1.5
            row.scale_x = 1.5
            tip_box = col.box()
            tip_box.scale_x = 1.4
            tip_row = tip_box.row()
            tip_col = tip_row.column(align=True)
            tip_col.label(text="The button above will")
            tip_col.label(text="show object normal")
            tip_row.label(icon_value=get_icon('arrow_up'))
            tip_row.operator("paint_system.hide_painting_tips",
                        text="", icon='X').attribute_name = 'hide_norm_paint_tips'

        row = col.row(align=True)
        row.scale_y = 1.3
        row.scale_x = 1.5
        
        row.menu("MAT_MT_PaintSystemMergeAndExport",
                    text="Bake and Export")

def layer_settings_ui(layout: bpy.types.UILayout, context: bpy.types.Context):
    ps_ctx = PSContextMixin.parse_context(context)
    active_layer = ps_ctx.active_layer
    if not active_layer or not active_layer.node_tree:
        return
    color_mix_node = active_layer.mix_node
    
    if ps_ctx.ps_settings.use_legacy_ui:
        col = layout.column(align=True)
        row = col.row(align=True)
        row.scale_y = 1.2
        row.scale_x = 1.2
        scale_content(context, row, 1.7, 1.5)
        clip_row = row.row(align=True)
        clip_row.enabled = not active_layer.lock_layer
        clip_row.prop(active_layer, "is_clip", text="",
                icon="SELECT_INTERSECT")
        if active_layer.type == 'IMAGE':
            clip_row.prop(active_layer, "lock_alpha",
                    text="", icon='TEXTURE')
        lock_row = row.row(align=True)
        lock_row.prop(active_layer, "lock_layer",
                text="", icon=icon_parser('VIEW_LOCKED', 'LOCKED'))
        blend_type_row = row.row(align=True)
        blend_type_row.enabled = not active_layer.lock_layer
        blend_type_row.prop(active_layer, "blend_mode", text="")
        row = col.row(align=True)
        scale_content(context, row, scale_x=1.2, scale_y=1.5)
        row.enabled = not active_layer.lock_layer
        row.prop(active_layer.pre_mix_node.inputs['Opacity'], "default_value",
                text="Opacity", slider=True)
    else:
        ui_scale = context.preferences.view.ui_scale
        panel_width = context.region.width - 35*2 * ui_scale
        threshold_width = 170 * ui_scale
        use_wide_ui = panel_width > threshold_width
        if use_wide_ui:
            split = layout.split(factor = 0.7)
        else:
            split = layout.column(align=True)
        split.scale_y = 1.3
        split.scale_x = 1.3
        main_row = split.row(align=True)
        clip_row = main_row.row(align=True)
        clip_row.enabled = not active_layer.lock_layer
        clip_row.prop(active_layer, "is_clip", text="",
                icon="SELECT_INTERSECT")
        if active_layer.type == 'IMAGE':
            clip_row.prop(active_layer, "lock_alpha",
                    text="", icon='TEXTURE')
        lock_row = main_row.row(align=True)
        lock_row.prop(active_layer, "lock_layer",
                text="", icon=icon_parser('VIEW_LOCKED', 'LOCKED'))
        blend_type_row = main_row.row(align=True)
        blend_type_row.enabled = not active_layer.lock_layer
        blend_type_row.prop(active_layer, "blend_mode", text="")
        opacity_row = split.row(align=True)
        opacity_row.enabled = not active_layer.lock_layer
        if not use_wide_ui:
            opacity_row.scale_y = 0.8
        opacity_row.prop(active_layer.pre_mix_node.inputs['Opacity'], "default_value",
                text="" if use_wide_ui else "Opacity", slider=True)

def line_separator(layout: bpy.types.UILayout):
    if is_newer_than(4, 2):
        layout.separator(type = 'LINE')
    else:
        layout.separator()

def is_editor_open(context: bpy.types.Context, editor_type: str) -> bool:
    return any(area.type == editor_type for area in context.screen.areas)

def is_image_painted(image: Image | ImagePreview | None) -> bool:
    """Check if the image is painted

    Args:
        image (bpy.types.Image): The image to check

    Returns:
        bool: True if the image is painted, False otherwise
    """
    if not image:
        return False
    if isinstance(image, Image):
        pixels = np.zeros(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        return len(pixels) > 0 and any(pixels)
    elif isinstance(image, ImagePreview):
        pixels = np.zeros(len(image.image_pixels_float), dtype=np.float32)
        image.image_pixels_float.foreach_get(pixels)
        return len(pixels) > 0 and any(pixels)

def draw_enum_operator_menu(layout: bpy.types.UILayout, enum_items, operator_id: str, type_attr: str, first_icon: str, skip_types=None):
    """Draw a menu of operators from an enum, giving the first item a distinctive icon.

    Args:
        layout: The UILayout to draw into.
        enum_items: Iterable of (identifier, name, description) tuples.
        operator_id: The bl_idname of the operator to invoke.
        type_attr: The operator property name to set (e.g. 'gradient_type').
        first_icon: Icon string for the first item; others get 'NONE'.
        skip_types: Optional set of identifiers to skip.
    """
    for idx, (identifier, name, description) in enumerate(enum_items):
        if skip_types and identifier in skip_types:
            continue
        op = layout.operator(operator_id, text=name, icon=first_icon if idx == 0 else 'NONE')
        setattr(op, type_attr, identifier)


def draw_socket_grid(layout: bpy.types.UILayout, layer, include_inputs: bool = True):
    """Draw the Color/Alpha output (and optionally input) socket name grid.

    Args:
        layout: The UILayout to draw into.
        layer: The active layer whose socket properties are drawn.
        include_inputs: Whether to also draw Color/Alpha Input rows.
    """
    output_box = layout.box()
    grid = output_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
    grid_col = grid.column()
    grid_col.label(text="Color Output")
    grid_col.prop(layer, "color_output_name", text="")
    grid_col = grid.column()
    grid_col.label(text="Alpha Output")
    grid_col.prop(layer, "alpha_output_name", text="")
    if include_inputs:
        input_box = layout.box()
        grid = input_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
        grid_col = grid.column()
        grid_col.label(text="Color Input")
        grid_col.prop(layer, "color_input_name", text="")
        grid_col = grid.column()
        grid_col.label(text="Alpha Input")
        grid_col.prop(layer, "alpha_input_name", text="")


def ensure_invoke_context(layout: bpy.types.UILayout):
    """Ensure the layout uses INVOKE_REGION_WIN operator context.

    Menus opened via search may default to EXEC_REGION_WIN which skips
    invoke(); this helper normalises that.
    """
    if layout.operator_context == 'EXEC_REGION_WIN':
        layout.operator_context = 'INVOKE_REGION_WIN'
    layout.operator_context = 'INVOKE_REGION_WIN'


def get_settings_box(layout: bpy.types.UILayout, use_legacy_ui: bool, existing_box=None):
    """Return a box container for layer-type settings.

    In legacy UI the caller already has a ``box`` from the outer layout;
    in the modern UI a new nested box is created.

    Args:
        layout: Parent layout (used when a new box is needed).
        use_legacy_ui: Whether the legacy UI mode is active.
        existing_box: A pre-existing box to reuse in legacy mode.

    Returns:
        A UILayout suitable for drawing layer-type settings.
    """
    if not use_legacy_ui:
        return layout.box()
    return existing_box if existing_box is not None else layout


def draw_layer_sidebar(col: bpy.types.UILayout, use_legacy_ui: bool):
    """Draw the Add / Delete / Move sidebar buttons next to the layer list.

    Args:
        col: A column layout to draw the buttons in.
        use_legacy_ui: Switches between legacy and modern button sets.
    """
    col.scale_x = 1.2
    col.operator("wm.call_menu", text="", icon_value=get_icon('layer_add')).name = "MAT_MT_AddLayerMenu"
    if not use_legacy_ui:
        col.operator("paint_system.new_folder_layer",
                     icon_value=get_icon('folder'), text="")
    col.menu("MAT_MT_LayerMenu",
            text="", icon='DOWNARROW_HLT')
    if use_legacy_ui:
        col.separator()
    else:
        line_separator(col)
    col.operator("paint_system.delete_item",
                    text="", icon_value=get_icon('trash'))
    if use_legacy_ui:
        col.separator()
    else:
        line_separator(col)
    col.operator("paint_system.move_up", icon="TRIA_UP", text="")
    col.operator("paint_system.move_down", icon="TRIA_DOWN", text="")


def draw_warning_box(layout: bpy.types.UILayout, lines):
    """Draw an alert box with one or more warning lines.

    Args:
        layout: The parent UILayout.
        lines: Iterable of ``(text, icon)`` tuples.  The first line
            typically uses ``'ERROR'``; subsequent lines often use
            ``'BLANK1'`` for indentation.

    Returns:
        The column layout inside the warning box (for appending extra widgets).
    """
    warning_box = layout.box()
    warning_box.alert = True
    warning_col = warning_box.column(align=True)
    for text, icon in lines:
        warning_col.label(text=text, icon=icon)
    return warning_col

def draw_layer_icon(layer: "Layer", layout: bpy.types.UILayout):
    match layer.type:
        case 'IMAGE':
            if not layer.image:
                layout.label(icon_value=get_icon('image'))
                return
            else:
                if layer.image.preview and is_image_painted(layer.image.preview):
                    layout.label(
                        icon_value=layer.image.preview.icon_id)
                else:
                    if layer.image.is_dirty:
                        layer.image.asset_generate_preview()
                    layout.label(icon_value=get_icon('image'))
        case 'FOLDER':
            layout.prop(layer, "is_expanded", text="", icon_only=True, icon_value=get_icon(
                'folder_open') if layer.is_expanded else get_icon('folder'), emboss=False)
        case 'SOLID_COLOR':
            rgb_node = layer.source_node
            if rgb_node:
                layout.prop(
                    rgb_node.outputs[0], "default_value", text="", icon='IMAGE_RGB_ALPHA')
        case 'ADJUSTMENT':
            layout.label(icon='SHADERFX')
        case 'SHADER':
            layout.label(icon='SHADING_RENDERED')
        case 'NODE_GROUP':
            layout.label(icon='NODETREE')
        case 'ATTRIBUTE':
            layout.label(icon='MESH_DATA')
        case 'GRADIENT':
            if layer.gradient_type == 'FAKE_LIGHT':
                layout.label(icon='LIGHT')
            else:
                layout.label(icon='COLOR')
        case 'RANDOM':
            layout.label(icon='SEQ_HISTOGRAM')
        case 'TEXTURE':
            layout.label(icon='TEXTURE')
        case 'GEOMETRY':
            layout.label(icon='MESH_DATA')
        case _:
            layout.label(icon='BLANK1')
