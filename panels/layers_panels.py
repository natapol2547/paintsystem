import bpy
from bpy.types import UIList, Menu, Context, Image, ImagePreview, Panel, NodeTree
from bpy.utils import register_classes_factory
import numpy as np

from ..custom_icons import get_image_editor_icon

from ..utils.version import is_newer_than
from .common import (
    PSContextMixin,
    line_separator,
    scale_content,
    icon_parser,
    get_icon,
    get_icon_from_channel,
    check_group_multiuser,
    image_node_settings,
    toggle_paint_mode_ui,
    layer_settings_ui
)

from ..utils.nodes import find_node, traverse_connected_nodes, get_material_output
from ..paintsystem.data import (
    GlobalLayer,
    ADJUSTMENT_TYPE_ENUM, 
    GRADIENT_TYPE_ENUM, 
    TEXTURE_TYPE_ENUM,
    GEOMETRY_TYPE_ENUM,
    Layer,
    is_layer_linked,
    sort_actions
)

# Check if PIL is available for conditional UI display
try:
    from ..paintsystem.image import PIL_AVAILABLE
except ImportError:
    PIL_AVAILABLE = False

if is_newer_than(4,3):
    from bl_ui.properties_data_grease_pencil import (
        GreasePencil_LayerMaskPanel,
        DATA_PT_grease_pencil_onion_skinning,
    )


def is_image_painted(image: Image | ImagePreview) -> bool:
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
    return False


def draw_layer_icon(layer: Layer, layout: bpy.types.UILayout):
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

def draw_input_sockets(layout, context: Context, only_output: bool = False):
    ps_ctx = PSContextMixin.parse_context(context)
    active_layer = ps_ctx.active_layer
    header, panel = layout.panel("input_sockets_panel", default_closed=True)
    header.label(text="Sockets Settings:", icon_value=get_icon('float_socket'))
    if panel:
        row = panel.row(align=True)
        row.label(icon="BLANK1")
        if only_output:
            output_box = row
        else:
            input_box = row.box()
        grid = output_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
        grid_col = grid.column()
        grid_col.label(text="Color Output")
        grid_col.prop(active_layer, "color_output_name", text="")
        grid_col = grid.column()
        grid_col.label(text="Alpha Output")
        grid_col.prop(active_layer, "alpha_output_name", text="")
        if not only_output:
            input_box = panel.box()
            grid = input_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
            grid_col = grid.column()
            grid_col.label(text="Color Input")
            grid_col.prop(active_layer, "color_input_name", text="")
            grid_col = grid.column()
            grid_col.label(text="Alpha Input")
            grid_col.prop(active_layer, "alpha_input_name", text="")
class MAT_PT_UL_LayerList(PSContextMixin, UIList):
    def draw_item(self, context: Context, layout, data, item, icon, active_data, active_property, index):
        linked_item = item.get_layer_data()
        if not linked_item:
            return
        # The UIList passes channel as 'data'
        active_channel = data
        flattened = active_channel.flattened_layers
        if index < len(flattened):
            level = active_channel.get_item_level_from_id(item.id)
            main_row = layout.row()
            warnings = item.get_layer_warnings(context)
                # main_row.label(text="\n".join(warnings), icon='ERROR')
            # Check if parent of the current item is enabled
            parent_item = active_channel.get_item_by_id(
                item.parent_id)
            if parent_item and not parent_item.enabled:
                main_row.enabled = False

            row = main_row.row(align=True)
            for i in range(level):
                if i == level - 1:
                    row.label(icon_value=get_icon('folder_indent'))
                else:
                    row.label(icon='BLANK1')
            draw_layer_icon(linked_item, row)

            row = main_row.row(align=True)
            row.prop(linked_item, "layer_name", text="", emboss=False)
            if linked_item.is_clip:
                row.label(icon="SELECT_INTERSECT")
            if linked_item.lock_layer:
                row.label(icon=icon_parser('VIEW_LOCKED', 'LOCKED'))
            if len(linked_item.actions) > 0:
                row.label(icon="KEYTYPE_KEYFRAME_VEC")
            if is_layer_linked(linked_item):
                row.label(icon="LINKED")
            if warnings:
                op = row.operator("paint_system.show_layer_warnings", text="", icon='ERROR', emboss=False)
                op.layer_id = item.id
            row.prop(linked_item, "enabled", text="",
                     icon="HIDE_OFF" if linked_item.enabled else "HIDE_ON", emboss=False)
            self.draw_custom_properties(row, linked_item)

    def filter_items(self, context, data, propname):
        # This function gets the collection property (as the usual tuple (data, propname)), and must return two lists:
        # * The first one is for filtering, it must contain 32bit integers were self.bitflag_filter_item marks the
        #   matching item as filtered (i.e. to be shown). The upper 16 bits (including self.bitflag_filter_item) are
        #   reserved for internal use, the lower 16 bits are free for custom use. Here we use the first bit to mark
        #   VGROUP_EMPTY.
        # * The second one is for reordering, it must return a list containing the new indices of the items (which
        #   gives us a mapping org_idx -> new_idx).
        # Please note that the default UI_UL_list defines helper functions for common tasks (see its doc for more info).
        # If you do not make filtering and/or ordering, return empty list(s) (this will be more efficient than
        # returning full lists doing nothing!).
        layers = getattr(data, propname).values()
        flattened_layers = data.flattened_unlinked_layers

        # Default return values.
        flt_flags = []
        flt_neworder = []

        # Filtering by name
        flt_flags = [self.bitflag_filter_item] * len(layers)
        for idx, layer in enumerate(layers):
            flt_neworder.append(flattened_layers.index(layer))
            while layer.parent_id != -1:
                layer = data.get_item_by_id(layer.parent_id)
                if layer and not layer.is_expanded:
                    flt_flags[idx] &= ~self.bitflag_filter_item
                    break

        return flt_flags, flt_neworder

    def draw_custom_properties(self, layout, item):
        if hasattr(item, 'custom_int'):
            layout.label(text=str(item.order))


class MAT_MT_PaintSystemMergeAndExport(PSContextMixin, Menu):
    bl_label = "Baked and Export"
    bl_idname = "MAT_MT_PaintSystemMergeAndExport"
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if active_channel.bake_image:
            layout.prop(active_channel, "use_bake_image",
                    text="Use Baked Image", icon='CHECKBOX_HLT' if active_channel.use_bake_image else 'CHECKBOX_DEHLT')
            layout.separator()
        layout.label(text="Bake")
        layout.operator("paint_system.bake_channel", text="Bake Active Channel", icon_value=get_icon_from_channel(active_channel))
        layout.operator("paint_system.bake_channel", text=f"Bake Active Channel as Layer", icon_value=get_icon("image")).as_layer = True
        if not ps_ctx.ps_settings.use_legacy_ui:
            layout.operator("paint_system.bake_all_channels", text=f"Bake All Channels", icon_value=get_icon('channels'))
        layout.separator()
        layout.label(text="Export Baked Images")
        if active_channel.bake_image:
            layout.operator("paint_system.export_image", text="Export Active Channel", icon='EXPORT').image_name = active_channel.bake_image.name
            layout.operator("paint_system.delete_bake_image", text="Delete Active Channel", icon='TRASH')
        if not ps_ctx.ps_settings.use_legacy_ui:
            layout.operator("paint_system.export_all_images", text="Export All Channels", icon='EXPORT')

class MAT_PT_Layers(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_Layers'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Layers"
    bl_category = 'Paint System'
    # bl_parent_id = 'MAT_PT_PaintSystemMainPanel'

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if ps_ctx.active_group and check_group_multiuser(ps_ctx.active_group.node_tree):
            return False
        return ps_ctx.ps_object and (ps_ctx.active_channel is not None or ps_ctx.ps_object.type == 'GREASEPENCIL')
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon_value=get_icon('layers'))

    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        # if context.mode == 'PAINT_TEXTURE' and ps_ctx.active_channel:
        #     layout.popover(
        #         panel="MAT_PT_ChannelsSelect",
        #         text=ps_ctx.active_channel.name if ps_ctx.active_channel else "No Channel",
        #         icon_value=get_icon_from_channel(ps_ctx.active_channel)
        #     )
        # else:
        if ps_ctx.ps_object.type == 'MESH' and ps_ctx.active_channel.bake_image:
            layout.prop(ps_ctx.active_channel, "use_bake_image",
                    text="Use Baked", icon="TEXTURE_DATA")

    def draw(self, context):
        ps_ctx = self.parse_context(context)

        layout = self.layout
        if ps_ctx.ps_settings.use_legacy_ui:
            box = layout.box()
            toggle_paint_mode_ui(box, context)
        else:
            box = layout
        if ps_ctx.ps_object.type == 'GREASEPENCIL':
            grease_pencil = context.grease_pencil
            layers = grease_pencil.layers
            is_layer_active = layers.active is not None
            is_group_active = grease_pencil.layer_groups.active is not None
            row = box.row()
            scale_content(context, row, scale_x=1, scale_y=1.2)
            row.template_grease_pencil_layer_tree()
            col = row.column()
            sub = col.column(align=True)
            sub.operator_context = 'EXEC_DEFAULT'
            sub.operator("grease_pencil.layer_add", icon='ADD', text="")
            sub.operator("grease_pencil.layer_group_add", icon='NEWFOLDER', text="")
            sub.separator()

            if is_layer_active:
                sub.operator("grease_pencil.layer_remove", icon='REMOVE', text="")
            if is_group_active:
                sub.operator("grease_pencil.layer_group_remove", icon='REMOVE', text="").keep_children = True

            sub.separator()

            sub.menu("GREASE_PENCIL_MT_grease_pencil_add_layer_extra", icon='DOWNARROW_HLT', text="")

            col.separator()

            sub = col.column(align=True)
            sub.operator("grease_pencil.layer_move", icon='TRIA_UP', text="").direction = 'UP'
            sub.operator("grease_pencil.layer_move", icon='TRIA_DOWN', text="").direction = 'DOWN'
        elif ps_ctx.ps_object.type == 'MESH':
            if not ps_ctx.active_channel.use_bake_image:
                if not ps_ctx.ps_settings.use_legacy_ui:
                    main_row = layout.row()
                    box = main_row.box()
                    if ps_ctx.active_layer and ps_ctx.active_layer.node_tree:
                        settings_box = box.box()
                        layer_settings_ui(settings_box, context)
                else:
                    box = layout.box()
        
            active_group = ps_ctx.active_group
            active_channel = ps_ctx.active_channel
            mat = ps_ctx.active_material
            # contains_mat_setup = any([node.type == 'GROUP' and node.node_tree ==
            #                           active_channel.node_tree for node in mat.node_tree.nodes])

            layers = active_channel.layers

            # Toggle paint mode (switch between object and texture paint mode)
            group_node = find_node(mat.node_tree, {
                                'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree})
            if not group_node:
                warning_box = box.box()
                warning_box.alert = True
                warning_col = warning_box.column(align=True)
                warning_col.label(text="Paint System not connected", icon='ERROR')
                warning_col.label(text="to material output!", icon='BLANK1')

            if active_channel.use_bake_image:
                image_node = find_node(active_channel.node_tree, {'bl_idname': 'ShaderNodeTexImage', 'image': active_channel.bake_image})
                bake_box = layout.box()
                col = bake_box.column()
                # col.label(text="Baked Image", icon="TEXTURE_DATA")
                image_node_settings(col, image_node, active_channel, "bake_image", simple_ui=True, default_closed=True)
                col.operator("wm.call_menu", text="Apply Image Filters", icon="IMAGE_DATA").name = "MAT_MT_ImageFilterMenu"
                col.operator("paint_system.delete_bake_image", text="Delete", icon="TRASH")
                return


            row = box.row()
            layers_col = row.column()
            scale_content(context, row, scale_x=1, scale_y=1.5)
            layers_col.template_list(
                "MAT_PT_UL_LayerList", "", active_channel, "layers", active_channel, "active_index",
                rows=min(max(6, len(layers)), 7)
            )

            
            if ps_ctx.ps_settings.use_legacy_ui:
                col = row.column(align=True)
                col.scale_x = 1.2
                col.operator("wm.call_menu", text="", icon_value=get_icon('layer_add')).name = "MAT_MT_AddLayerMenu"
                col.menu("MAT_MT_LayerMenu",
                        text="", icon='COLLAPSEMENU')
                col.separator()
                col.operator("paint_system.delete_item",
                                text="", icon="TRASH")
                col.separator()
                col.operator("paint_system.move_up", icon="TRIA_UP", text="")
                col.operator("paint_system.move_down", icon="TRIA_DOWN", text="")
            else:
                # main_row
                col = row.column(align=True)
                col.scale_x = 1.2
                col.operator("wm.call_menu", text="", icon_value=get_icon('layer_add')).name = "MAT_MT_AddLayerMenu"
                col.operator("paint_system.new_folder_layer",
                     icon_value=get_icon('folder'), text="")
                col.menu("MAT_MT_LayerMenu",
                        text="", icon='COLLAPSEMENU')
                line_separator(col)
                col.operator("paint_system.delete_item",
                                text="", icon="TRASH")
                line_separator(col)
                col.operator("paint_system.move_up", icon="TRIA_UP", text="")
                col.operator("paint_system.move_down", icon="TRIA_DOWN", text="")


def get_image(context) -> bpy.types.Image:
    image = None
    ps_ctx = PSContextMixin.parse_context(context)
    if ps_ctx.active_channel and  ps_ctx.active_channel.use_bake_image:
        image = ps_ctx.active_channel.bake_image
    elif ps_ctx.active_layer and ps_ctx.active_layer.image:
        image = ps_ctx.active_layer.image
    return image

class MAT_MT_ImageFilterMenu(PSContextMixin, Menu):
    bl_label = "Image Filter Menu"
    bl_idname = "MAT_MT_ImageFilterMenu"

    @classmethod
    def poll(cls, context):
        return get_image(context)

    def draw(self, context):
        layout = self.layout
        
        layout.operator_context = 'INVOKE_REGION_WIN'
        if PIL_AVAILABLE:
            layout.operator("paint_system.brush_painter",
                            icon="BRUSH_DATA")
            layout.operator("paint_system.gaussian_blur",
                            icon="FILTER")
        layout.operator("paint_system.invert_colors",
                        icon="MOD_MASK")
        layout.operator("paint_system.fill_image", 
                        text="Fill Image", icon='SNAP_FACE')
        
class MAT_PT_LayerSettings(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_LayerSettings'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Layer Settings"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_Layers'

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if ps_ctx.ps_object.type == 'MESH':
            if ps_ctx.active_channel.use_bake_image:
                return False
            active_layer = ps_ctx.active_layer
            return active_layer is not None
        elif ps_ctx.ps_object.type == 'GREASEPENCIL':
            grease_pencil = context.grease_pencil
            active_layer = grease_pencil.layers.active
            return active_layer is not None
        else:
            return False

    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="PREFERENCES")
        
    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        if ps_ctx.ps_settings.use_legacy_ui:
            if ps_ctx.ps_object.type == 'MESH' and layer.type == 'IMAGE':
                layout.operator("wm.call_menu", text="Filters", icon="IMAGE_DATA").name = "MAT_MT_ImageFilterMenu"

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        if ps_ctx.ps_object.type == 'GREASEPENCIL':
            active_layer = context.grease_pencil.layers.active
            if active_layer:
                box = layout.box()
                col = box.column(align=True)
                row = col.row(align=True)
                row.scale_y = 1.2
                row.scale_x = 1.2
                scale_content(context, row, 1.7, 1.5)
                options_row = row.row(align=True)
                options_row.enabled = not active_layer.lock
                options_row.prop(active_layer, "use_masks", text="")
                # options_row.prop(active_layer, "use_lights", text="", icon='LIGHT')
                # options_row.prop(active_layer, "use_onion_skinning", text="")
                lock_row = row.row(align=True)
                lock_row.prop(active_layer, "lock", text="")
                blend_row = row.row(align=True)
                blend_row.enabled = not active_layer.lock
                blend_row.prop(active_layer, "blend_mode", text="")
                opacity_row = col.row(align=True)
                opacity_row.enabled = not active_layer.lock
                scale_content(context, opacity_row, 1.7, 1.5)
                opacity_row.prop(active_layer, "opacity")
                
                col = box.column()
                col.enabled = not active_layer.lock
                col.prop(active_layer, "use_lights", text="Use Lights", icon='LIGHT')
                # box.prop(active_layer, "use_onion_skinning", text="Use Onion Skinning")
            
        elif ps_ctx.ps_object.type == 'MESH':
            active_layer = ps_ctx.active_layer
            if not active_layer:
                return
                # Settings
            warnings = active_layer.get_layer_warnings(context)
            if warnings:
                warnings_box = layout.box()
                warnings_col = warnings_box.column(align=True)
                for warning in warnings:
                    # Split warning into chunks of 6 words
                    words = warning.split()
                    chunks = [' '.join(words[j:j+6]) for j in range(0, len(words), 6)]
                    for i, chunk in enumerate(chunks):
                        warnings_col.label(text=chunk, icon='ERROR' if not i else 'BLANK1')
            if ps_ctx.ps_settings.use_legacy_ui:
                box = layout.box()
                layer_settings_ui(box, context)
            if active_layer.type not in ('IMAGE', 'ADJUSTMENT', 'NODE_GROUP', 'ATTRIBUTE', 'GRADIENT', 'SOLID_COLOR', 'RANDOM', 'TEXTURE', 'GEOMETRY'):
                return
            elif not ps_ctx.ps_settings.use_legacy_ui:
                box = layout.box()
            match active_layer.type:
                case 'IMAGE':
                    col = box.column()
                    scale_content(context, col, 1.2, 1.2)
                    if not active_layer.external_image:
                        icon_value = get_image_editor_icon(context.preferences.filepaths.image_editor) or get_icon('image')
                        col.operator("paint_system.quick_edit", text="Edit Externally", icon_value=icon_value)
                    else:
                        if active_layer.edit_external_mode == 'IMAGE_EDIT':
                            row = col.row(align=True)
                            row.operator("paint_system.quick_edit", text="Open Image", icon_value=get_image_editor_icon(context.preferences.filepaths.image_editor))
                            row.operator("paint_system.reload_image", text="Reload Image", icon="FILE_REFRESH")
                        elif active_layer.edit_external_mode == 'VIEW_CAPTURE':
                            col.operator("paint_system.project_apply", text="Apply Edit")
                case 'ADJUSTMENT':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    adjustment_node = active_layer.source_node
                    if adjustment_node:
                        col.label(text="Adjustment Settings:", icon='SHADERFX')
                        col.template_node_inputs(adjustment_node)
                case 'NODE_GROUP':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    node_group = active_layer.source_node
                    inputs = [i for i in node_group.inputs if not i.is_linked and i.name not in (
                        'Color', 'Alpha')]
                    if not inputs:
                        return
                    col.label(text="Node Group Settings:", icon='NODETREE')
                    for socket in inputs:
                        col.prop(socket, "default_value",
                                text=socket.name)

                case 'ATTRIBUTE':
                    col = box.column()
                    output_box = col.box()
                    grid = output_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
                    grid_col = grid.column()
                    grid_col.label(text="Color Output")
                    grid_col.prop(active_layer, "color_output_name", text="")
                    grid_col = grid.column()
                    grid_col.label(text="Alpha Output")
                    grid_col.prop(active_layer, "alpha_output_name", text="")
                    col.enabled = not active_layer.lock_layer
                    attribute_node = active_layer.source_node
                    if attribute_node:
                        col.label(text="Attribute Settings:", icon='MESH_DATA')
                        col.template_node_inputs(attribute_node)
                case 'GRADIENT':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    gradient_node = active_layer.source_node
                    map_range_node = active_layer.find_node("map_range")
                    if gradient_node and map_range_node:
                        col.use_property_split = True
                        col.use_property_decorate = False
                        if active_layer.gradient_type in ('LINEAR', 'RADIAL', 'FAKE_LIGHT'):
                            if active_layer.empty_object and active_layer.empty_object.name in context.view_layer.objects:
                                empty_col = col.column(align=True)
                                empty_col.operator("paint_system.select_empty", text="Select Gradient Empty" if active_layer.gradient_type != 'FAKE_LIGHT' else "Select Light Empty", icon='OBJECT_ORIGIN')
                                empty_col.prop(active_layer, "empty_object", text="")
                            else:
                                err_box = col.box()
                                err_box.alert = True
                                err_col = err_box.column(align=True)
                                err_col.label(text="Gradient Empty not found", icon='ERROR')
                                err_col.operator("paint_system.fix_missing_gradient_empty", text="Fix Missing Gradient Empty")
                        box = layout.box()
                        header, panel = box.panel("gradient_node_settings_panel")
                        header.label(text="Gradient Settings:", icon='SHADERFX')
                        if panel:
                            panel.template_node_inputs(gradient_node)
                            header, panel = panel.panel("map_range_node_settings_panel", default_closed=True)
                            header.label(text="Map Range:", icon='SHADERFX')
                            if panel:
                                panel.prop(map_range_node, "interpolation_type", text="Interpolation")
                                if map_range_node.interpolation_type in ('STEPPED'):
                                    panel.prop(map_range_node.inputs[5], "default_value", text="Steps")
                                panel.prop(map_range_node.inputs[1], "default_value", text="Start Distance")
                                panel.prop(map_range_node.inputs[2], "default_value", text="End Distance")
                case 'SOLID_COLOR':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    rgb_node = active_layer.source_node
                    if rgb_node:
                        col.prop(rgb_node.outputs[0], "default_value", text="Color",
                                icon='IMAGE_RGB_ALPHA')

                case 'RANDOM':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    random_node = active_layer.find_node("add_2")
                    hue_math = active_layer.find_node("hue_multiply_add")
                    saturation_math = active_layer.find_node("saturation_multiply_add")
                    value_math = active_layer.find_node("value_multiply_add")
                    hue_saturation_value = active_layer.find_node("hue_saturation_value")
                    if random_node and hue_math and saturation_math and value_math and hue_saturation_value:
                        col.label(text="Random Settings:", icon='SHADERFX')
                        col.prop(
                            random_node.inputs[1], "default_value", text="Random Seed")
                        col = col.column()
                        col.use_property_split = True
                        col.use_property_decorate = False
                        col.prop(
                            hue_saturation_value.inputs['Color'], "default_value", text="Base Color")
                        col.prop(
                            hue_math.inputs[1], "default_value", text="Hue")
                        col.prop(
                            saturation_math.inputs[1], "default_value", text="Saturation")
                        col.prop(
                            value_math.inputs[1], "default_value", text="Value")
                case 'TEXTURE':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    col.use_property_decorate = False
                    col.use_property_split = True
                    col.prop(active_layer, "texture_type", text="Texture Type")
                    draw_input_sockets(col, context, only_output=True)
                    texture_node = active_layer.source_node
                    if texture_node:
                        box = layout.box()
                        header, panel = box.panel("texture_node_settings_panel")
                        header.label(text="Texture Settings:", icon='TEXTURE')
                        if panel:
                            panel.use_property_split = False
                            panel.template_node_inputs(texture_node)
                case 'GEOMETRY':
                    col = box.column()
                    col.enabled = not active_layer.lock_layer
                    geometry_type = active_layer.geometry_type
                    if geometry_type == 'VECTOR_TRANSFORM':
                        geometry_node = active_layer.source_node
                        if geometry_node:
                            col.label(text="Vector Transform:", icon='MESH_DATA')
                            col.template_node_inputs(geometry_node)
                    elif geometry_type == 'BACKFACING':
                        mat = ps_ctx.active_material
                        box = col.box()
                        col = box.column()
                        col.label(text="Material Settings:", icon='MESH_DATA')
                        col.prop(mat, "use_backface_culling", text="Backface Culling", icon='CHECKBOX_HLT' if mat.use_backface_culling else 'CHECKBOX_DEHLT')
                    elif geometry_type in ['WORLD_NORMAL', 'WORLD_TRUE_NORMAL', 'OBJECT_NORMAL']:
                        col.prop(active_layer, "normalize_normal", text="Normalize Normal", icon='MESH_DATA')
                case _:
                    pass
            
            # Draw ui for adjustable sockets
            if active_layer.type == 'NODE_GROUP':
                header, panel = layout.panel("node_group_panel")
                header.label(text="Sockets Settings:")
                if panel:
                    panel.use_property_split = True
                    panel.use_property_decorate = False
                    col = panel.column()
                    output_box = col.box()
                    grid = output_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
                    grid_col = grid.column()
                    grid_col.label(text="Color Output")
                    grid_col.prop(active_layer, "color_output_name", text="")
                    grid_col = grid.column()
                    grid_col.label(text="Alpha Output")
                    grid_col.prop(active_layer, "alpha_output_name", text="")
                    output_box = col.box()
                    grid = output_box.grid_flow(columns=2, align=True, even_columns=True, row_major=True)
                    grid_col = grid.column()
                    grid_col.label(text="Color Input")
                    grid_col.prop(active_layer, "color_input_name", text="")
                    grid_col = grid.column()
                    grid_col.label(text="Alpha Input")
                    grid_col.prop(active_layer, "alpha_input_name", text="")

# Grease Pencil Layer Settings

def disable_if_lock(self, context):
    active_layer = context.grease_pencil.layers.active
    layout = self.layout
    layout.enabled = not active_layer.lock

class MAT_PT_GreasePencilMaskSettings(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_GreasePencilMaskSettings'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Mask"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_LayerSettings'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object.type == 'GREASEPENCIL' and is_newer_than(4,3)

    def draw_header(self, context):
        GreasePencil_LayerMaskPanel.draw_header(self, context)
        disable_if_lock(self, context)
    
    def draw(self, context):
        GreasePencil_LayerMaskPanel.draw(self, context)
        disable_if_lock(self, context)

class MAT_PT_GreasePencilOnionSkinningSettings(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_GreasePencilOnionSkinningSettings'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Onion Skinning"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_LayerSettings'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object.type == 'GREASEPENCIL' and is_newer_than(4,3)
    
    def draw(self, context):
        DATA_PT_grease_pencil_onion_skinning.draw(self, context)
        disable_if_lock(self, context)
    
    def draw_header(self, context):
        layout = self.layout
        active_layer = context.grease_pencil.layers.active
        layout.prop(active_layer, "use_onion_skinning", text="", toggle=0)
        disable_if_lock(self, context)


# Paint System Layer Settings Advanced

class MAT_PT_LayerTransformSettings(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_LayerCoordinateSettings'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Transform"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_LayerSettings'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        if ps_ctx.ps_object.type != 'MESH' or active_layer.type not in ('IMAGE', 'TEXTURE'):
            return False
        return True
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="EMPTY_ARROWS")
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        layout.enabled = not active_layer.lock_layer
        box = layout.box()
        col = box.column()
        if active_layer.type == 'IMAGE':
            if active_layer.coord_type not in ['UV', 'AUTO']:
                info_box = col.box()
                info_box.alert = True
                info_col = info_box.column(align=True)
                info_col.label(text="Painting may not work", icon='ERROR')
        row = col.row(align=True)
        row.prop(active_layer, "coord_type", text="Coord Type")
        if active_layer.coord_type in ['UV', 'AUTO']:
                row.operator("paint_system.transfer_image_layer_uv", text="", icon='UV_DATA')
        if active_layer.coord_type == 'UV':
            col.prop_search(active_layer, "uv_map_name", text="UV Map",
                                search_data=ps_ctx.ps_object.data, search_property="uv_layers", icon='GROUP_UVS')
        elif active_layer.coord_type == 'DECAL':
            col.use_property_split = False
            empty_col = col.column(align=True)
            empty_col.prop(active_layer, "empty_object", text="")
            empty_col.operator("paint_system.select_empty", text="Select Empty", icon='OBJECT_ORIGIN')
            split = col.split(factor=0.35, align=True)
            split.prop(active_layer, "use_decal_depth_clip", text="Clip", toggle=1, icon='CHECKBOX_HLT' if active_layer.use_decal_depth_clip else 'CHECKBOX_DEHLT')
            decal_clip = active_layer.find_node("decal_depth_clip")
            if decal_clip:
                decal_clip_col = split.column(align=True)
                decal_clip_col.enabled = active_layer.use_decal_depth_clip
                decal_clip_col.prop(decal_clip.inputs[2], "default_value", text="Depth")
        elif active_layer.coord_type == 'PROJECT':
            proj_col = col.column(align=True)
            proj_col.scale_y = 2
            proj_col.operator("paint_system.projection_view_reset", text="View Current Projection", icon='CAMERA_DATA')
            col.operator("paint_system.set_projection_view", text="Set New Projection View", icon='FILE_REFRESH')
            proj_node = active_layer.find_node("proj_node")
            if proj_node:
                col.prop(proj_node.inputs["Scale"], "default_value", text="Scale")
                col.use_property_split = False
                header, panel = col.panel("proj_node_panel", default_closed=True)
                header.prop(proj_node.inputs["Enable"], "default_value", text="Normal Falloff")
                if panel:
                    panel.prop(proj_node.inputs["Falloff"], "default_value", text="Degree")
        elif active_layer.coord_type == 'PARALLAX':
            col.prop(active_layer, "parallax_space", text="Space", expand=True)
            if active_layer.parallax_space == 'UV':
                col.prop_search(active_layer, "parallax_uv_map_name", text="UV Map",
                                search_data=ps_ctx.ps_object.data, search_property="uv_layers", icon='GROUP_UVS')
            parallax_node = active_layer.find_node("parallax")
            if parallax_node:
                col.prop(parallax_node.inputs["Depth"], "default_value", text="Depth")
        
        mapping_node = active_layer.find_node("mapping")
        if mapping_node:
            box = layout.box()
            header, panel = box.panel("mapping_panel")
            header.label(text="Mapping Settings:", icon_value=get_icon('vector_socket'))
            if panel:
                panel.use_property_split = False
                col = panel.column()
                col.template_node_inputs(mapping_node)



class MAT_MT_ImageMenu(PSContextMixin, Menu):
    bl_label = "Image Menu"
    bl_idname = "MAT_MT_ImageMenu"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        return active_layer and active_layer.image

    def draw(self, context):
        layout = self.layout
        layout.operator("paint_system.resize_image",
                        icon="CON_SIZELIMIT")
        layout.operator("paint_system.clear_image",
                        icon="X")

class MAT_PT_ImageLayerSettings(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_ImageLayerSettings'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Image"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_LayerSettings'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        if ps_ctx.ps_object.type != 'MESH' or ps_ctx.active_channel.use_bake_image:
            return False
        return active_layer and active_layer.type == 'IMAGE'
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon_value=get_icon('image'))
        
    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        if not ps_ctx.ps_settings.use_legacy_ui:
            if ps_ctx.ps_object.type == 'MESH' and layer.type == 'IMAGE':
                layout.operator("wm.call_menu", text="Filters", icon="IMAGE_DATA").name = "MAT_MT_ImageFilterMenu"
    
    def draw(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        layout = self.layout
        layout.enabled = not active_layer.lock_layer
        box = layout.box()
        col = box.column()
        image_node = active_layer.source_node
        panel = image_node_settings(col, image_node, active_layer, "image", simple_ui=True)
        if panel:
            line_separator(col)
        draw_input_sockets(col, context, only_output=True)
        row = col.row(align=True)
        row.label(icon="BLANK1")
        row.prop(active_layer, "correct_image_aspect", text="Correct Aspect", toggle=1, icon='CHECKBOX_HLT' if active_layer.correct_image_aspect else 'CHECKBOX_DEHLT')

class MAT_MT_LayerMenu(PSContextMixin, Menu):
    bl_label = "Layer Menu"
    bl_idname = "MAT_MT_LayerMenu"

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout

        special_actions = False
        if ps_ctx.active_layer and ps_ctx.active_layer.type not in ('IMAGE', 'ADJUSTMENT'):
            special_actions = True
            layout.operator(
                "paint_system.convert_to_image_layer",
                text="Convert to Image Layer",
                icon_value=get_icon('image')
            )
        
        if ps_ctx.unlinked_layer and is_layer_linked(ps_ctx.unlinked_layer):
            special_actions = True
            layout.operator(
                "paint_system.unlink_layer",
                text="Unlink Layer",
                icon="UNLINKED"
            )
        
        if special_actions:
            layout.separator()

        layout.operator(
            "paint_system.copy_layer",
            text="Copy Layer",
            icon="COPYDOWN"
        )
        layout.operator(
            "paint_system.copy_all_layers",
            text="Copy All Layers",
            icon="COPYDOWN"
        )
        layout.operator(
            "paint_system.paste_layer",
            text="Paste Layer(s)",
            icon="PASTEDOWN"
        ).linked = False
        layout.operator(
            "paint_system.paste_layer",
            text="Paste Linked Layer(s)",
            icon="LINKED"
        ).linked = True

        # Divider before merge actions
        layout.separator()
        # Merge actions: Up above Down, both below the divider
        layout.operator(
            "paint_system.merge_up",
            text="Merge Up",
            icon="TRIA_UP_BAR"
        )
        layout.operator(
            "paint_system.merge_down",
            text="Merge Down",
            icon="TRIA_DOWN_BAR"
        )


class MAT_MT_AddImageLayerMenu(Menu):
    bl_label = "Add Image"
    bl_idname = "MAT_MT_AddImageLayerMenu"
    
    def draw(self, context):
        layout = self.layout
        layout.operator("paint_system.new_image_layer", text="New Image Layer", icon_value=get_icon('image')).image_add_type = 'NEW'
        layout.operator("paint_system.new_image_layer", text="Import Image Layer").image_add_type = 'IMPORT'
        layout.operator("paint_system.new_image_layer", text="Use Existing Image Layer").image_add_type = 'EXISTING'


class MAT_MT_AddGradientLayerMenu(Menu):
    bl_label = "Add Gradient"
    bl_idname = "MAT_MT_AddGradientLayerMenu"
    
    def draw(self, context):
        layout = self.layout
        for idx, (node_type, name, description) in enumerate(GRADIENT_TYPE_ENUM):
            if node_type == 'FAKE_LIGHT':
                continue
            layout.operator("paint_system.new_gradient_layer",
                text=name, icon='COLOR' if idx == 0 else 'NONE').gradient_type = node_type


class MAT_MT_AddAdjustmentLayerMenu(Menu):
    bl_label = "Add Adjustment"
    bl_idname = "MAT_MT_AddAdjustmentLayerMenu"
    
    def draw(self, context):
        layout = self.layout
        for idx, (node_type, name, description) in enumerate(ADJUSTMENT_TYPE_ENUM):
            layout.operator("paint_system.new_adjustment_layer",
                text=name, icon='SHADERFX' if idx == 0 else 'NONE').adjustment_type = node_type


class MAT_MT_AddTextureLayerMenu(Menu):
    bl_label = "Add Texture"
    bl_idname = "MAT_MT_AddTextureLayerMenu"
    
    def draw(self, context):
        layout = self.layout
        for idx, (node_type, name, description) in enumerate(TEXTURE_TYPE_ENUM):
            layout.operator("paint_system.new_texture_layer",
                text=name, icon='TEXTURE' if idx == 0 else 'NONE').texture_type = node_type


class MAT_MT_AddGeometryLayerMenu(Menu):
    bl_label = "Add Geometry"
    bl_idname = "MAT_MT_AddGeometryLayerMenu"
    
    def draw(self, context):
        layout = self.layout
        for idx, (node_type, name, description) in enumerate(GEOMETRY_TYPE_ENUM):
            layout.operator("paint_system.new_geometry_layer",
                text=name, icon='MESH_DATA' if idx == 0 else 'NONE').geometry_type = node_type

class MAT_MT_AddLayerMenu(Menu):
    bl_label = "Add Layer"
    bl_idname = "MAT_MT_AddLayerMenu"
    bl_options = {'SEARCH_ON_KEY_PRESS'}

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        
        if layout.operator_context == 'EXEC_REGION_WIN':
            layout.operator_context = 'INVOKE_REGION_WIN'
            col.operator(
                "WM_OT_search_single_menu",
                text="Search...",
                icon='VIEWZOOM',
            ).menu_idname = "MAT_MT_AddLayerMenu"
            col.separator()

        layout.operator_context = 'INVOKE_REGION_WIN'
        
        col.operator("paint_system.new_folder_layer",
                     icon_value=get_icon('folder'), text="Folder")
        col.separator()
        # col.label(text="Basic:")
        col.operator("paint_system.new_solid_color_layer", text="Solid Color",
                     icon=icon_parser('STRIP_COLOR_03', "SEQUENCE_COLOR_03"))
        col.menu("MAT_MT_AddImageLayerMenu", text="Image", icon_value=get_icon('image'))
        col.menu("MAT_MT_AddGradientLayerMenu", text="Gradient", icon='COLOR')
        col.menu("MAT_MT_AddTextureLayerMenu", text="Texture", icon='TEXTURE')
        col.menu("MAT_MT_AddAdjustmentLayerMenu", text="Adjustment", icon='SHADERFX')
        col.menu("MAT_MT_AddGeometryLayerMenu", text="Geometry", icon='MESH_DATA')
        col.separator()
        # col.label(text="Advanced:")
        col.operator("paint_system.new_gradient_layer",
                text="Fake Light", icon='LIGHT').gradient_type = 'FAKE_LIGHT'
        col.operator("paint_system.new_attribute_layer",
                     text="Attribute Color", icon='MESH_DATA')
        col.operator("paint_system.new_random_color_layer",
                     text="Random Color", icon='SEQ_HISTOGRAM')

        col.operator("paint_system.new_custom_node_group_layer",
                     text="Custom Layer", icon='NODETREE')


class PAINTSYSTEM_UL_Actions(PSContextMixin, UIList):
    bl_idname = "PAINTSYSTEM_UL_Actions"
    bl_label = "Actions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = 'Paint System'

    def draw_item(self, context, layout, data, item, icon, active_data, active_property, index):
        layout.prop(item, "action_bind", text="", icon_only=True, emboss=False)
        bind_to = 'Marker' if item.action_bind == 'MARKER' else 'Frame'
        bind_name = (item.marker_name if item.marker_name else "None") if item.action_bind == 'MARKER' else str(item.frame)
        layout.label(text=f"{bind_to} {bind_name} ({item.action_type.title()})")
    
    def filter_items(self, context, data, propname):
        actions = getattr(data, propname).values()
        flt_flags = [self.bitflag_filter_item] * len(data.actions)
        flt_neworder = []
        sorted_actions = sort_actions(context, data)
        for action in actions:
            flt_neworder.append(sorted_actions.index(action))
        return flt_flags, flt_neworder


class MAT_PT_Actions(PSContextMixin, Panel):
    bl_idname = "MAT_PT_Actions"
    bl_label = "Actions"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_LayerSettings'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        return active_layer is not None
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon="KEYTYPE_KEYFRAME_VEC")

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        layout = self.layout
        layout.use_property_split = True
        layout.alignment = 'LEFT'
        layout.use_property_decorate = False
        if ps_ctx.ps_settings.show_tooltips and not active_layer.actions:
            box = layout.box()
            col = box.column(align=True)
            col.label(text="Actions can control layer visibility", icon='INFO')
            col.label(text="with frame number or marker", icon='BLANK1')
        layout.label(text="Action Order:")
        row = layout.row()
        actions_col = row.column()
        actions_col.template_list("PAINTSYSTEM_UL_Actions", "", active_layer,
                          "actions", active_layer, "active_action_index", rows=5)
        col = row.column(align=True)
        col.operator("paint_system.add_action", icon="ADD", text="")
        col.operator("paint_system.delete_action", icon="REMOVE", text="")
        if not active_layer.actions:
            return
        active_action = active_layer.actions[active_layer.active_action_index]
        if not active_action:
            return
        actions_col.separator()
        actions_col.prop(active_action, "action_bind", text="Bind to")
        if active_action.action_bind == 'FRAME':
            actions_col.prop(active_action, "frame", text="Frame")
        elif active_action.action_bind == 'MARKER':
            actions_col.prop_search(active_action, "marker_name", context.scene, "timeline_markers", text="Once reach", icon="MARKER_HLT")
        actions_col.prop(active_action, "action_type", text="Action")


classes = (
    MAT_PT_UL_LayerList,
    MAT_MT_AddLayerMenu,
    MAT_MT_AddImageLayerMenu,
    MAT_MT_AddGradientLayerMenu,
    MAT_MT_AddAdjustmentLayerMenu,
    MAT_MT_AddTextureLayerMenu,
    MAT_MT_AddGeometryLayerMenu,
    MAT_MT_ImageFilterMenu,
    MAT_MT_LayerMenu,
    MAT_MT_PaintSystemMergeAndExport,
    MAT_PT_Layers,
    MAT_MT_ImageMenu,
    MAT_PT_LayerSettings,
    MAT_PT_GreasePencilMaskSettings,
    MAT_PT_GreasePencilOnionSkinningSettings,
    MAT_PT_ImageLayerSettings,
    MAT_PT_LayerTransformSettings,
    MAT_PT_Actions,
    PAINTSYSTEM_UL_Actions,
)

register, unregister = register_classes_factory(classes)
