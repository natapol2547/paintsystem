import bpy
from bpy.types import UIList, Menu, Context, Image, ImagePreview, Panel, NodeTree
from bpy.utils import register_classes_factory
import numpy as np
import logging

from ..utils.version import is_newer_than

logger = logging.getLogger("PaintSystem")
from .common import (
    PSContextMixin,
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
# Note: Import may fail if Pillow wheel isn't loaded yet or on unsupported platforms
try:
    from ..operators.image_filters.common import PIL_AVAILABLE
except (ImportError, ModuleNotFoundError, AttributeError):
    PIL_AVAILABLE = False

# Cache for image painted status to avoid repeated pixel buffer allocations
_image_painted_cache = {}

def invalidate_image_cache(image=None):
    """Invalidate cache for specific image or all images"""
    if image:
        _image_painted_cache.pop(id(image), None)
    else:
        _image_painted_cache.clear()

if is_newer_than(4,3):
    from bl_ui.properties_data_grease_pencil import (
        GreasePencil_LayerMaskPanel,
        DATA_PT_grease_pencil_onion_skinning,
    )


def is_image_painted(image: Image | ImagePreview) -> bool:
    """Check if the image is painted (cached)

    Args:
        image (bpy.types.Image): The image to check

    Returns:
        bool: True if the image is painted, False otherwise
    """
    if not image:
        return False
    
    # Check cache first
    image_id = id(image)
    if image_id in _image_painted_cache:
        return _image_painted_cache[image_id]
    
    # Fast path: check if image has pixels at all
    result = False
    try:
        if isinstance(image, Image):
            pixel_count = len(image.pixels)
            if pixel_count == 0:
                result = False
            else:
                # Sample first few pixels instead of all (much faster)
                # If first 100 pixels are all zero, likely unpainted
                sample_size = min(100, pixel_count)
                pixels = np.zeros(sample_size, dtype=np.float32)
                image.pixels.foreach_get(pixels)
                result = bool(np.any(pixels))
        elif isinstance(image, ImagePreview):
            pixel_count = len(image.image_pixels_float)
            if pixel_count == 0:
                result = False
            else:
                sample_size = min(100, pixel_count)
                pixels = np.zeros(sample_size, dtype=np.float32)
                image.image_pixels_float.foreach_get(pixels)
                result = bool(np.any(pixels))
    except Exception as e:
        # If sampling fails, assume not painted
        logger.debug(f"Error checking if image painted: {e}")
        result = False
    
    # Cache the result
    _image_painted_cache[image_id] = result
    return result


def draw_layer_icon(layer: Layer, layout: bpy.types.UILayout):
    match layer.type:
        case 'IMAGE':
            if not layer.image:
                layout.label(icon_value=get_icon('image'))
                return
            else:
                # Check if preview exists and is valid before expensive operations
                preview = layer.image.preview
                if preview and hasattr(preview, 'icon_id') and preview.icon_id > 0:
                    # Only check if painted when we actually have a preview
                    if is_image_painted(preview):
                        layout.label(icon_value=preview.icon_id)
                        return
                # Fallback to generic icon (don't regenerate preview every frame)
                layout.label(icon_value=get_icon('image'))
        case 'FOLDER':
            layout.prop(layer, "is_expanded", text="", icon_only=True, icon_value=get_icon(
                'folder_open') if layer.is_expanded else get_icon('folder'), emboss=False)
        case 'SOLID_COLOR':
            rgb_node = layer.find_node("rgb")
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
            layout.label(icon='COLOR')
        case 'RANDOM':
            layout.label(icon='SEQ_HISTOGRAM')
        case 'TEXTURE':
            layout.label(icon='TEXTURE')
        case 'GEOMETRY':
            layout.label(icon='MESH_DATA')
        case _:
            layout.label(icon='BLANK1')
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
            
            # Show UDIM badge if layer uses UDIM tiles
            if linked_item.is_udim:
                from ..utils.udim import get_udim_info_string
                udim_info = get_udim_info_string(linked_item)
                if udim_info:
                    sub = row.row(align=True)
                    sub.scale_x = 0.8
                    sub.label(text=udim_info, icon='UV')
            
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
        layout.operator("paint_system.bake_channel", text=f"Bake Active Channel ({active_channel.name})", icon_value=get_icon_from_channel(active_channel))
        layout.operator("paint_system.bake_channel", text=f"Bake Active Channel as Layer", icon_value=get_icon("image")).as_layer = True
        # layout.operator("paint_system.bake_all_channels", text="Bake all Channels")
        layout.separator()
        layout.label(text="Export")
        if not active_channel.bake_image:
            layout.label(text="Please bake the channel first!", icon='ERROR')
            return
        layout.operator("paint_system.export_image", text="Export Baked Image", icon='EXPORT').image_name = active_channel.bake_image.name
        layout.operator("paint_system.delete_bake_image", text="Delete Baked Image", icon='TRASH')

class MAT_PT_Layers(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_Layers'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Layers"
    bl_category = 'Paint System'

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        # Hide panel entirely if not a Paint System setup (no channel or multiuser group)
        if ps_ctx.active_group and check_group_multiuser(ps_ctx.active_group.node_tree):
            return False
        # Always allow for Grease Pencil (built-in layer system)
        if not ps_ctx.ps_object:
            return False
        if ps_ctx.ps_object.type == 'GREASEPENCIL':
            return True
        # Require an active channel to show the layers UI (but allow empty layers)
        if not ps_ctx.active_channel:
            return False
        # Show panel even with zero layers so users can add new layers
        return True
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon_value=get_icon('layers'))

    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        if context.mode == 'PAINT_TEXTURE' and ps_ctx.active_channel:
            layout.popover(
                panel="MAT_PT_ChannelsSelect",
                text=ps_ctx.active_channel.name if ps_ctx.active_channel else "No Channel",
                icon_value=get_icon_from_channel(ps_ctx.active_channel)
            )
        else:
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
            if not ps_ctx.ps_settings.use_legacy_ui:
                # col = layout.column()
                # row = col.row()
                # row.scale_y = 1.2
                # row.scale_x = 1.2
                # new_row = row.row(align=True)
                # new_row.operator("wm.call_menu", text="New", icon_value=get_icon('layer_add')).name = "MAT_MT_AddLayerMenu"
                # new_row.operator("paint_system.new_folder_layer",
                #      icon_value=get_icon('folder'), text="")
                # new_row.menu("MAT_MT_LayerMenu",
                #     text="", icon='COLLAPSEMENU')
                # move_row = row.row(align=True)
                # move_row.operator("paint_system.move_up", icon="TRIA_UP", text="")
                # move_row.operator("paint_system.move_down", icon="TRIA_DOWN", text="")
                # row.operator("paint_system.delete_item",
                #             text="", icon="TRASH")
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
                col.label(text="Baked Image", icon="TEXTURE_DATA")
                col.operator("wm.call_menu", text="Apply Image Filters", icon="IMAGE_DATA").name = "MAT_MT_ImageFilterMenu"
                col.operator("paint_system.delete_bake_image", text="Delete", icon="TRASH")
                image_node_settings(layout, image_node, active_channel, "bake_image")
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
                if is_newer_than(4, 2):
                    col.separator(type = 'LINE')
                else:
                    col.separator()
                col.operator("paint_system.delete_item",
                                text="", icon="TRASH")
                if is_newer_than(4, 2):
                    col.separator(type = 'LINE')
                else:
                    col.separator()
                col.operator("paint_system.move_up", icon="TRIA_UP", text="")
                col.operator("paint_system.move_down", icon="TRIA_DOWN", text="")


class MAT_MT_ImageFilterMenu(PSContextMixin, Menu):
    bl_label = "Image Filter Menu"
    bl_idname = "MAT_MT_ImageFilterMenu"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        layer = ps_ctx.active_layer
        return layer and layer.image

    def draw(self, context):
        layout = self.layout
        
        layout.operator_context = 'INVOKE_REGION_WIN'
        
        ps_ctx = self.parse_context(context)
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
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layer = getattr(ps_ctx, 'active_layer', None)
        icon_map = {
            'IMAGE': 'IMAGE_DATA',
            'GRADIENT': 'SHADERFX',
            'SOLID_COLOR': 'IMAGE_RGB_ALPHA',
            'TEXTURE': 'TEXTURE',
            'ADJUSTMENT': 'MODIFIER',
            'NODE_GROUP': 'NODETREE',
            'ATTRIBUTE': 'MESH_DATA',
            'GEOMETRY': 'MESH_DATA',
            'RANDOM': 'SHADERFX'
        }
        icon = icon_map.get(layer.type, 'PREFERENCES') if layer else 'PREFERENCES'
        layout.label(icon=icon)
        
    def draw_header_preset(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        # Always show Filters menu for IMAGE layers here (moved from Image panel)
        if ps_ctx.ps_object.type == 'MESH' and layer and layer.type == 'IMAGE':
            layout.operator("wm.call_menu", text="Filters", icon="IMAGE_DATA").name = "MAT_MT_ImageFilterMenu"

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
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
            
        elif ps_ctx.ps_object.type == 'MESH':
            active_layer = ps_ctx.active_layer
            if not active_layer:
                return
            
            layout.enabled = not active_layer.lock_layer
            
            # Image selector for IMAGE layers
            if active_layer.type == 'IMAGE':
                image_node = active_layer.find_node("image")
                # Single row: Coordinate type (icon + dropdown) BEFORE custom image selector (without unpack button)
                coord_image_row = layout.row(align=True)
                coord_icon_row = coord_image_row.row(align=True)
                coord_icon_row.label(icon='EMPTY_ARROWS')
                coord_dropdown = coord_icon_row.row(align=True)
                coord_dropdown.scale_x = 0.7
                coord_dropdown.prop(active_layer, "coord_type", text="")
                # Custom image selector (pointer only) + manual user count (no unpack button)
                if image_node:
                    image_row = coord_image_row.row(align=True)
                    # Minimal image selector (no fake user, no user count)
                    image_row.prop_search(image_node, "image", bpy.data, "images", text="")
                # Transfer UV button at end (only AUTO/UV)
                # Separate UV Map row when UV mode; move transfer button here
                if active_layer.coord_type == 'UV':
                    uv_row = layout.row(align=True)
                    uv_row.prop_search(active_layer, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="UV Map", icon='GROUP_UVS')
                    uv_row.operator("paint_system.transfer_image_layer_uv", text="", icon='UV_DATA')
                elif active_layer.coord_type == 'AUTO':
                    # For AUTO keep transfer button on coordinate/image row
                    coord_image_row.operator("paint_system.transfer_image_layer_uv", text="", icon='UV_DATA')

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
        col = layout.column()
        row = col.row(align=True)
        row.prop(active_layer, "coord_type", text="Coord Type")
        if active_layer.coord_type in ['AUTO', 'UV'] and active_layer.type == 'IMAGE':
            row.operator("paint_system.transfer_image_layer_uv", text="", icon='UV_DATA')
        if active_layer.coord_type == 'UV':
            row_uv = col.row(align=True)
            row_uv.prop_search(active_layer, "uv_map_name", text="UV Map",
                                search_data=ps_ctx.ps_object.data, search_property="uv_layers", icon='GROUP_UVS')
            row_uv.operator("paint_system.sync_layer_uv_name_to_users", text="", icon='FILE_REFRESH')
            row_uv.operator("paint_system.set_active_uv_for_selected", text="", icon='RADIOBUT_ON')
        elif active_layer.coord_type == 'DECAL':
            decal_clip = active_layer.find_node("decal_depth_clip")
            if decal_clip:
                decal_clip_col = col.column(align=True)
                decal_clip_col.prop(decal_clip.inputs[2], "default_value", text="Depth Clip")
            empty_col = col.column(align=True)
            empty_col.operator("paint_system.select_empty", text="Select Empty", icon='OBJECT_ORIGIN')
            empty_col.prop(active_layer, "empty_object", text="")
        if active_layer.coord_type not in ['UV', 'AUTO'] and active_layer.type == 'IMAGE':
            info_box = col.box()
            info_box.alert = True
            info_col = info_box.column(align=True)
            info_col.label(text="Painting may not work", icon='ERROR')
            info_col.label(text="as expected.", icon='BLANK1')
        
        mapping_node = active_layer.find_node("mapping")
        if mapping_node:
            box = col.box()
            box.use_property_split = False
            col = box.column()
            col.label(text="Mapping Settings:", icon="EMPTY_ARROWS")
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
        # Filter button moved to Layer Settings panel header; remove here.
        pass
    
    def draw(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        
        # UDIM detection display
        if active_layer.image:
            try:
                from ..utils.udim import is_udim_image, get_udim_tiles_from_image
                if is_udim_image(active_layer.image):
                    box = layout.box()
                    row = box.row()
                    row.label(text="UDIM", icon='UV')
                    tiles = get_udim_tiles_from_image(active_layer.image)
                    if tiles:
                        tile_count = len(tiles)
                        row.label(text=f"{tile_count} tile{'s' if tile_count != 1 else ''}")
                    # Per-tile UV sync utility helps keep meshes aligned across UDIMs
                    col = box.column(align=True)
                    col.operator_context = 'INVOKE_DEFAULT'
                    col.operator("paint_system.sync_uv_by_udim_tile", text="Sync UV by UDIM Tile", icon='GROUP_UVS')
            except Exception:
                pass
        
        row = layout.row(align=True)
        row.use_property_split = False
        row.prop(active_layer, "correct_image_aspect", text="Correct Aspect")
        edit_row = layout.row(align=True)
        if not active_layer.external_image:
            edit_row.operator("paint_system.quick_edit", text="Edit Externally (View Capture)")
        else:
            edit_row.operator("paint_system.project_apply", text="Apply")
        layout.enabled = not active_layer.lock_layer

        image_node = active_layer.find_node("image")
        image_node_settings(layout, image_node, active_layer, "image")

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
        layout.label(text=f"{bind_to} {bind_name} Action")
    
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
        row = layout.row()
        actions_col = row.column()
        scale_content(context, actions_col)
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


class MAT_PT_UDIMTileManagement(PSContextMixin, Panel):
    bl_idname = 'MAT_PT_UDIMTileManagement'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "UDIM Tiles"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_ImageLayerSettings'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx:
            return False
        ps_object = ps_ctx.ps_object
        if not ps_object or ps_object.type != 'MESH':
            return False
        active_channel = ps_ctx.active_channel
        if not active_channel or getattr(active_channel, 'use_bake_image', False):
            return False
        active_layer = ps_ctx.active_layer
        return bool(active_layer and active_layer.type == 'IMAGE' and getattr(active_layer, 'is_udim', False))
    
    def draw_header(self, context):
        layout = self.layout
        layout.label(icon='UV')
        
    def draw(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            return
        active_layer = ps_ctx.active_layer
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        if not active_layer or not active_layer.udim_tiles:
            layout.label(text="No tiles detected", icon='INFO')
            return
        
        # Summary info
        total_tiles = len(active_layer.udim_tiles)
        painted_tiles = sum(1 for t in active_layer.udim_tiles if t.is_painted)
        dirty_tiles = sum(1 for t in active_layer.udim_tiles if t.is_dirty)
        
        summary_box = layout.box()
        summary_row = summary_box.row()
        summary_row.label(text=f"Total: {total_tiles} tiles")
        summary_row.label(text=f"Painted: {painted_tiles}")
        summary_row.label(text=f"Dirty: {dirty_tiles}")
        
        # Tile grid visualization
        tiles_box = layout.box()
        tiles_box.label(text="Tile Status Grid", icon='GRID')
        
        # Display tiles in a grid (4 columns for readability)
        tiles_col = tiles_box.column()
        tiles_grid = tiles_col.grid_flow(row_major=True, columns=4, even_columns=True, even_rows=False)
        
        for tile in active_layer.udim_tiles:
            tile_row = tiles_grid.row(align=True)
            
            # Determine icon based on state
            if tile.is_dirty:
                icon = 'ERROR'
                color = (1.0, 0.3, 0.3)  # Red
            elif tile.is_painted:
                icon = 'CHECKMARK'
                color = (0.3, 1.0, 0.3)  # Green
            else:
                icon = 'BLANK1'
                color = (0.7, 0.7, 0.7)  # Gray
            
            # Display tile button
            tile_op = tile_row.operator("paint_system.select_udim_tile", text=f"  {tile.number}  ", icon=icon)
            tile_op.tile_number = tile.number
            
            # Color the button background (simulated with alert)
            if tile.is_dirty or tile.is_painted:
                tile_row.alert = tile.is_dirty
        
        # Tile controls
        controls_box = layout.box()
        col = controls_box.column(align=True)
        col.label(text="Tile Actions:", icon='TOOL_SETTINGS')
        row = col.row(align=True)
        row.operator("paint_system.bake_udim_tile", text="Bake Selected Tiles", icon='RENDER_RESULT')
        row = col.row(align=True)
        row.operator("paint_system.mark_udim_tile_dirty", text="Mark as Dirty", icon='ERROR').mark_all = False
        row.operator("paint_system.clear_udim_tile_marks", text="Clear Marks", icon='X')


class MAT_PT_UDIMTileList(PSContextMixin, Panel):
    """Detailed tile list with individual controls"""
    bl_idname = 'MAT_PT_UDIMTileList'
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_label = "Tile Details"
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_UDIMTileManagement'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx:
            return False
        ps_object = ps_ctx.ps_object
        if not ps_object or ps_object.type != 'MESH':
            return False
        active_channel = ps_ctx.active_channel
        if not active_channel or getattr(active_channel, 'use_bake_image', False):
            return False
        active_layer = ps_ctx.active_layer
        return bool(active_layer and active_layer.type == 'IMAGE' and getattr(active_layer, 'is_udim', False) and len(active_layer.udim_tiles) > 0)

    def draw(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            return
        active_layer = ps_ctx.active_layer
        if not active_layer:
            return
        layout = self.layout
        layout.use_property_split = False
        
        col = layout.column(align=True)
        for tile in active_layer.udim_tiles:
            row = col.row(align=True)
            row.scale_y = 0.9
            
            # Tile number label
            row.label(text=f"Tile {tile.number}", icon='UV')
            
            # Status flags
            painted_icon = 'CHECKMARK' if tile.is_painted else 'BLANK1'
            dirty_icon = 'ERROR' if tile.is_dirty else 'BLANK1'
            
            row.prop(tile, "is_painted", text="", icon_only=True, icon=painted_icon)
            row.prop(tile, "is_dirty", text="", icon_only=True, icon=dirty_icon)
            
            # Action buttons
            bake_op = row.operator("paint_system.bake_udim_tile", text="", icon='RENDER_RESULT')
            bake_op.tile_number = tile.number


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
    MAT_PT_UDIMTileManagement,
    MAT_PT_UDIMTileList,
    PAINTSYSTEM_UL_Actions,
)

register, unregister = register_classes_factory(classes)
