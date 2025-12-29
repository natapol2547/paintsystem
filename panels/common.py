import bpy

from ..utils.version import is_newer_than

# --
from ..paintsystem.data import Channel
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