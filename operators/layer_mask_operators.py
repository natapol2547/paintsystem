import bpy
from bpy.props import (
    StringProperty, IntProperty, EnumProperty,
    BoolProperty
)
from bpy.types import Operator, Context, NodeTree
from bpy.utils import register_classes_factory
import math
import mathutils

from ..paintsystem.list_manager import ListManager

from ..paintsystem.data import (
    ACTION_BIND_ENUM,
    ACTION_TYPE_ENUM,
    ADJUSTMENT_TYPE_ENUM,
    ATTRIBUTE_TYPE_ENUM,
    MASK_TYPE_ENUM,
    TEXTURE_TYPE_ENUM,
    GRADIENT_TYPE_ENUM,
    GEOMETRY_TYPE_ENUM,
    add_empty_to_collection,
    get_layer_by_uid,
    save_image,
)
from ..utils import get_next_unique_name
from ..utils.nodes import get_nodetree_socket_enum
from .common import (
    PSContextMixin,
    scale_content,
    get_icon_from_socket_type,
    MultiMaterialOperator,
    PSUVOptionsMixin,
    PSImageCreateMixin
    )
from .operators_utils import redraw_panel, intern_enum_items
from .layers_operators import PAINTSYSTEM_OT_NewImage

class PAINTSYSTEM_OT_NewImageMask(PAINTSYSTEM_OT_NewImage):
    """Create a new image mask"""
    bl_idname = "paint_system.new_image_mask"
    bl_label = "New Image Mask"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Create a new image mask"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer is not None
    
    def get_next_image_name(self, context):
        """Get the next image name from the active channel"""
        ps_ctx = self.parse_context(context)
        if ps_ctx.active_channel:
            return get_next_unique_name("Image Mask", [layer_mask.layer_name for layer_mask in ps_ctx.active_layer.layer_masks])
    
    def process_material(self, context):
        self.store_coord_type(context)
        ps_ctx = self.parse_context(context)
        if self.image_add_type == 'NEW':
            img = self.create_image(context)
        elif self.image_add_type == 'IMPORT':
            img = bpy.data.images.load(self.filepath, check_existing=True)
            if not img:
                self.report({'ERROR'}, "Failed to load image")
                return False
            self.image_name = img.name
        elif self.image_add_type == 'EXISTING':
            if not self.image_name:
                self.report({'ERROR'}, "No image selected")
                return False
            img = bpy.data.images.get(self.image_name)
            save_image(img)
            if not img:
                self.report({'ERROR'}, "Image not found")
                return False
        ps_ctx.active_layer.create_layer_mask(
            context,
            self.image_name,
            'IMAGE',
            image=img,
            coord_type=self.coord_type,
            uv_map_name=self.uv_map_name
        )
        return {'FINISHED'}


class PAINTSYSTEM_OT_DeleteLayerMask(PSContextMixin, Operator):
    """Delete the active layer mask"""
    bl_idname = "paint_system.delete_layer_mask"
    bl_label = "Delete Layer Mask"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Delete the active layer mask"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer and ps_ctx.active_layer.use_masks
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        lm = ListManager(active_layer, "layer_masks", active_layer, "active_layer_mask_index")
        lm.remove_active_item()
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_NewImageMask,
    PAINTSYSTEM_OT_DeleteLayerMask,
)

register, unregister = register_classes_factory(classes)