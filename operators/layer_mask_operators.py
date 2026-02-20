import bpy
import os
from array import array
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
    GRADIENT_TYPE_ENUM,
    GEOMETRY_TYPE_ENUM,
    add_empty_to_collection,
    get_layer_by_uid,
    save_image,
    get_udim_tiles,
    update_active_image,
)
from ..utils import get_next_unique_name
from ..utils.nodes import get_nodetree_socket_enum
from .common import (
    PSContextMixin,
    scale_content,
    get_icon_from_socket_type,
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
        active_layer = ps_ctx.active_layer
        return active_layer is not None and len(active_layer.layer_masks) == 0

    multiple_objects: BoolProperty(
        name="Multiple Objects",
        description="Run the operator on multiple objects",
        default=False,
    )

    @staticmethod
    def _sanitize_name_part(value: str) -> str:
        return str(value).replace("/", "_").replace("\\", "_").strip() or "Unnamed"

    @classmethod
    def _normalized_layer_name_part(cls, active_layer, material_name: str) -> str:
        raw_layer_name = (
            getattr(active_layer, "display_name", "")
            or getattr(active_layer, "layer_name", "")
            or getattr(active_layer, "name", "Layer")
        )
        cleaned_layer_name = cls._sanitize_name_part(raw_layer_name)
        cleaned_layer_name = os.path.splitext(cleaned_layer_name)[0] or "Layer"

        material_stem = os.path.splitext(material_name)[0].strip().lower()
        layer_stem = cleaned_layer_name.strip().lower()
        if material_stem and layer_stem.startswith(material_stem + "_"):
            cleaned_layer_name = cleaned_layer_name[len(material_name) + 1:]
        elif material_stem and layer_stem.startswith(material_stem + " "):
            cleaned_layer_name = cleaned_layer_name[len(material_name) + 1:]

        cleaned_layer_name = cleaned_layer_name.strip(" _-") or "Layer"
        return cleaned_layer_name

    @classmethod
    def build_mask_image_name(cls, context) -> str:
        ps_ctx = cls.parse_context(context)
        material_name = cls._sanitize_name_part(ps_ctx.active_material.name if ps_ctx.active_material else "Material")
        active_layer = ps_ctx.active_layer
        layer_name = cls._normalized_layer_name_part(active_layer, material_name)

        if layer_name.lower() == material_name.lower():
            base_name = f"{material_name}_mask.png"
        else:
            base_name = f"{material_name}_{layer_name}_mask.png"

        if base_name not in bpy.data.images:
            return base_name
        stem, ext = os.path.splitext(base_name)
        index = 1
        while True:
            candidate = f"{stem}_{index:03d}{ext}"
            if candidate not in bpy.data.images:
                return candidate
            index += 1
    
    def get_next_image_name(self, context):
        return self.build_mask_image_name(context)

    @classmethod
    def build_mask_name(cls, context) -> str:
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        if not active_layer:
            return "Mask"
        return get_next_unique_name("Mask", [layer_mask.layer_name for layer_mask in active_layer.layer_masks])

    def get_coord_type(self, context):
        PSUVOptionsMixin.get_coord_type(self, context)
        ps_ctx = PSContextMixin.parse_context(context)
        self.use_udim_tiles = get_udim_tiles(ps_ctx.ps_object, self.uv_map_name) != {1001}

    def _configure_mask_image(self, img: bpy.types.Image, fill_white: bool = False):
        if not img:
            return
        try:
            img.colorspace_settings.name = 'Non-Color'
        except Exception:
            pass
        if fill_white:
            try:
                img.generated_color = (1.0, 1.0, 1.0, 1.0)
            except Exception:
                pass
            try:
                pixel_count = len(img.pixels)
                if pixel_count:
                    img.pixels.foreach_set(array('f', [1.0]) * pixel_count)
                    img.update()
            except Exception:
                pass
        save_image(img)

    def invoke(self, context, event):
        self.get_coord_type(context)
        self.image_name = self.get_next_image_name(context)
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        if self.image_add_type == 'NEW' and active_layer and active_layer.image:
            width, height = active_layer.image.size
            if width > 0 and height > 0:
                self.image_resolution = 'CUSTOM'
                self.image_width = width
                self.image_height = height
        elif self.image_resolution != 'CUSTOM':
            self.image_width = int(self.image_resolution)
            self.image_height = int(self.image_resolution)
        if self.image_add_type == 'IMPORT':
            context.window_manager.fileselect_add(self)
            return {'RUNNING_MODAL'}
        if self.image_add_type == 'EXISTING':
            self.image_name = ""
        return context.window_manager.invoke_props_dialog(self)
    
    def process_material(self, context):
        self.store_coord_type(context)
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        if active_layer and len(active_layer.layer_masks) > 0:
            self.report({'WARNING'}, "Only one mask is supported per layer")
            return {'CANCELLED'}
        if self.image_add_type == 'NEW':
            img = self.create_image(context)
            self._configure_mask_image(img, fill_white=True)
        elif self.image_add_type == 'IMPORT':
            img = bpy.data.images.load(self.filepath, check_existing=True)
            if not img:
                self.report({'ERROR'}, "Failed to load image")
                return False
            self.image_name = img.name
            self._configure_mask_image(img)
        elif self.image_add_type == 'EXISTING':
            if not self.image_name:
                self.report({'ERROR'}, "No image selected")
                return False
            img = bpy.data.images.get(self.image_name)
            save_image(img)
            if not img:
                self.report({'ERROR'}, "Image not found")
                return False
            self._configure_mask_image(img)
        active_layer.use_masks = True
        mask_name = self.build_mask_name(context)
        ps_ctx.active_layer.create_layer_mask(
            context,
            mask_name,
            'IMAGE',
            mask_image=img,
            coord_type=self.coord_type,
            mask_uv_map=self.uv_map_name,
            enabled=True,
        )
        active_layer.active_layer_mask_index = max(0, len(active_layer.layer_masks) - 1)
        active_layer.edit_mask = True
        update_active_image(context=context)
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
        if not active_layer.layer_masks:
            active_layer.use_masks = False
            active_layer.edit_mask = False
        active_layer.update_node_tree(context)
        update_active_image(context=context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_NewImageMaskAuto(PAINTSYSTEM_OT_NewImageMask):
    """Create a new image mask using current layer size without opening a dialog"""
    bl_idname = "paint_system.new_image_mask_auto"
    bl_label = "Add Mask"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Create a new image mask from current layer size"

    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        self.image_add_type = 'NEW'
        self.image_name = self.build_mask_image_name(context)
        self.get_coord_type(context)

        image_width = 2048
        image_height = 2048
        if active_layer and active_layer.image:
            width, height = active_layer.image.size
            if width > 0 and height > 0:
                image_width = int(width)
                image_height = int(height)

        self.image_resolution = 'CUSTOM'
        self.image_width = max(1, image_width)
        self.image_height = max(1, image_height)
        return self.execute(context)


class PAINTSYSTEM_OT_EditLayerMask(PSContextMixin, Operator):
    """Edit the active image mask"""
    bl_idname = "paint_system.edit_layer_mask"
    bl_label = "Edit Mask"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Switch painting target to the active mask"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        if not active_layer or not active_layer.layer_masks:
            return False
        active_index = active_layer.active_layer_mask_index
        if active_index < 0 or active_index >= len(active_layer.layer_masks):
            return False
        layer_mask = active_layer.layer_masks[active_index]
        return layer_mask.type == 'IMAGE' and layer_mask.mask_image is not None

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        active_index = active_layer.active_layer_mask_index
        if active_index < 0 or active_index >= len(active_layer.layer_masks):
            self.report({'ERROR'}, "No active mask")
            return {'CANCELLED'}
        layer_mask = active_layer.layer_masks[active_index]
        if layer_mask.type != 'IMAGE' or not layer_mask.mask_image:
            self.report({'ERROR'}, "Active mask must be an image mask")
            return {'CANCELLED'}
        active_layer.use_masks = True
        active_layer.edit_mask = True
        update_active_image(context=context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_FinishEditLayerMask(PSContextMixin, Operator):
    """Finish editing mask and return to layer image"""
    bl_idname = "paint_system.finish_edit_layer_mask"
    bl_label = "Finish Edit"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Switch painting target back to the active layer image"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        return active_layer is not None and active_layer.edit_mask

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        active_layer.edit_mask = False
        update_active_image(context=context)
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_NewImageMask,
    PAINTSYSTEM_OT_NewImageMaskAuto,
    PAINTSYSTEM_OT_DeleteLayerMask,
    PAINTSYSTEM_OT_EditLayerMask,
    PAINTSYSTEM_OT_FinishEditLayerMask,
)


def _get_registered_class(cls):
    class_name = getattr(cls, "__name__", None)
    if class_name:
        registered = getattr(bpy.types, class_name, None)
        if registered is not None:
            return registered
    bl_idname = getattr(cls, "bl_idname", None)
    if bl_idname:
        parts = bl_idname.split(".", 1)
        if len(parts) == 2:
            rna_name = f"{parts[0].upper()}_OT_{parts[1]}"
            return getattr(bpy.types, rna_name, None)
    return None


def _safe_unregister_class(cls):
    if cls is None:
        return
    try:
        bpy.utils.unregister_class(cls)
    except Exception:
        pass

def register():
    for cls in classes:
        _safe_unregister_class(_get_registered_class(cls))
        _safe_unregister_class(cls)
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError as e:
            if "already registered" not in str(e):
                raise

def unregister():
    for cls in reversed(classes):
        _safe_unregister_class(_get_registered_class(cls))
        _safe_unregister_class(cls)