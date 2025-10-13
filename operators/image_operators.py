import bpy
from bpy.types import Menu, Operator
from bpy.props import StringProperty, IntProperty, EnumProperty, BoolProperty, FloatProperty
from bpy.utils import register_classes_factory
from .common import PSContextMixin, PSImageFilterMixin, get_unified_settings, get_icon
from .image_filters import (
    blender_image_to_numpy,
    numpy_to_blender_image,
    switch_image_content,
    gaussian_blur,
    sharpen_image,
    list_brush_presets,
    resolve_brush_preset_path,
    )
import numpy
from .image_filters.brush_painter.brush_painter_core import BrushPainterCore

import os

class PAINTSYSTEM_OT_InvertColors(PSImageFilterMixin, Operator):
    bl_idname = "paint_system.invert_colors"
    bl_label = "Invert Colors"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Invert the colors of the active image"

    invert_r: BoolProperty(default=True)
    invert_g: BoolProperty(default=True)
    invert_b: BoolProperty(default=True)
    invert_a: BoolProperty(default=False)

    def execute(self, context):
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        with bpy.context.temp_override(**{'edit_image': image}):
            bpy.ops.image.invert('INVOKE_DEFAULT', invert_r=self.invert_r,
                                 invert_g=self.invert_g, invert_b=self.invert_b, invert_a=self.invert_a)
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=200)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "invert_r", text="Red")
        layout.prop(self, "invert_g", text="Green")
        layout.prop(self, "invert_b", text="Blue")
        layout.prop(self, "invert_a", text="Alpha")


class PAINTSYSTEM_OT_ResizeImage(PSImageFilterMixin, Operator):
    bl_idname = "paint_system.resize_image"
    bl_label = "Resize Image"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Resize the active image"

    def update_width_height(self, context):
        relative_width = self.width / self.base_width
        relative_height = self.height / self.base_height
        if self.relative_scale != 'CUSTOM' and (relative_width != relative_height or relative_width != self.relative_scale or relative_height != self.relative_scale):
            scale = float(self.relative_scale)
            self.width = int(scale * self.base_width)
            self.height = int(scale * self.base_height)

    width: IntProperty(name="Width", default=1024, subtype='PIXEL')
    height: IntProperty(name="Height", default=1024, subtype='PIXEL')
    relative_scale: EnumProperty(
        name="Relative Scale",
        description="Scale the image by a factor",
        items=[
            ('0.5', "0.5x", "Half the size"),
            ('1.0', "1x", "Original size"),
            ('2.0', "2x", "Double the size"),
            ('3.0', "3x", "Triple the size"),
            ('4.0', "4x", "Quadruple the size"),
            ('CUSTOM', "Custom", "Custom Size"),
        ],
        default='1.0',
        update=update_width_height,
    )
    base_width: IntProperty()
    base_height: IntProperty()

    def execute(self, context):
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        image.scale(self.width, self.height)
        return {'FINISHED'}

    def invoke(self, context, event):
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        self.base_width, self.base_height = image.size
        self.relative_scale = '1.0'
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="Scale", icon='IMAGE_DATA')
        row = box.row()
        row.prop(self, "relative_scale", expand=True)
        if self.relative_scale == 'CUSTOM':
            col = box.column(align=True)
            col.prop(self, "width")
            col.prop(self, "height")
        else:
            box.label(text=f"{self.width} x {self.height}")


class PAINTSYSTEM_OT_ClearImage(PSImageFilterMixin, Operator):
    bl_idname = "paint_system.clear_image"
    bl_label = "Clear Image"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Clear the active image"

    def execute(self, context):
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        # Replace every pixel with a transparent pixel
        pixels = numpy.empty(len(image.pixels), dtype=numpy.float32)
        pixels[::4] = 0.0
        image.pixels.foreach_set(pixels)
        image.update()
        image.update_tag()
        return {'FINISHED'}
    
class PAINTSYSTEM_OT_FillImage(PSImageFilterMixin, Operator):
    bl_idname = "paint_system.fill_image"
    bl_label = "Fill Image"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Fill the active image with current color"
    
    def execute(self, context):
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        # Replace every pixel with a transparent pixel
        pixels = numpy.empty(len(image.pixels), dtype=numpy.float32)
        prop_owner = get_unified_settings(context, "use_unified_color")
        color = prop_owner.color
        
        # Fill the image with the current brush color
        pixels[::4] = color[0]  # R
        pixels[1::4] = color[1]  # G
        pixels[2::4] = color[2]  # B
        pixels[3::4] = 1.0  # A - full opacity
        
        image.pixels.foreach_set(pixels)
        image.update()
        image.update_tag()
        return {'FINISHED'}


class PAINTSYSTEM_OT_GaussianBlur(PSContextMixin, PSImageFilterMixin, Operator):
    bl_idname = "paint_system.gaussian_blur"
    bl_label = "Gaussian Blur"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply a Gaussian blur to the active image"
    
    gaussian_sigma: FloatProperty(name="Gaussian Sigma", default=3.0, min=0.1, max=10.0, step=0.1)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        np_image = blender_image_to_numpy(image)
        np_image = gaussian_blur(np_image, self.gaussian_sigma)
        new_image = numpy_to_blender_image(np_image, f"{image.name}_blurred")
        ps_ctx.active_global_layer.image = new_image
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "gaussian_sigma")


class PAINTSYSTEM_OT_SharpenImage(PSContextMixin, PSImageFilterMixin, Operator):
    bl_idname = "paint_system.sharpen_image"
    bl_label = "Sharpen Image"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Sharpen the active image"
    
    sharpen_amount: FloatProperty(name="Sharpen Amount", default=1.0, min=0.1, max=10.0, step=0.1)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        np_image = blender_image_to_numpy(image)
        np_image = sharpen_image(np_image, self.sharpen_amount)
        new_image = numpy_to_blender_image(np_image, f"{image.name}_sharpened")
        ps_ctx.active_global_layer.image = new_image
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.prop(self, "sharpen_amount")


class PAINTSYSTEM_OT_BrushPainter(PSContextMixin, PSImageFilterMixin, Operator):
    bl_idname = "paint_system.brush_painter"
    bl_label = "Brush Painter"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Paint the active image with the brushes"
    
    brush_coverage_density: FloatProperty(name="Brush Coverage Density", default=0.7, min=0.1, max=1.0)
    min_brush_scale: FloatProperty(name="Min Brush Scale", default=0.03, min=0.01, max=1.0)
    max_brush_scale: FloatProperty(name="Max Brush Scale", default=0.1, min=0.01, max=1.0)
    start_opacity: FloatProperty(name="Start Opacity", default=0.4, min=0.0, max=1.0)
    end_opacity: FloatProperty(name="End Opacity", default=1.0, min=0.0, max=1.0)
    steps: IntProperty(name="Steps", default=7, min=1, max=20)
    gradient_threshold: FloatProperty(name="Gradient Threshold", default=0.0, min=0.0, max=1.0)
    gaussian_sigma: IntProperty(name="Gaussian Sigma", default=3, min=1, max=10)
    
    brush_mode: EnumProperty(
        name="Brush Mode",
        description="Choose brush texture source",
        items=[
            ('PRESET', "Brush Preset", "Use a brush preset", "BRUSH_DATA", 1),
            ('FOLDER', "Brush Folder", "Use multiple brushes from a folder", get_icon('folder'), 2),
            ('SINGLE', "Single Brush", "Use a single brush texture", "GREASEPENCIL", 3),
            ('DEFAULT', "Circular", "Use default circular brush", get_icon('channel'), 4)
        ],
        default='PRESET'
    )
    
    presets: EnumProperty(
        name="Brush Presets",
        description="Choose a brush preset",
        items=[(preset, preset, "") for preset in list_brush_presets()],
    )
    
    # Brush texture settings
    brush_folder_path: StringProperty(
        name="Brush Folder",
        description="Path to folder containing brush textures",
        default="",
        subtype='DIR_PATH'
    )
    
    brush_texture_path: StringProperty(
        name="Single Brush Texture",
        description="Path to a single brush texture file",
        default="",
        subtype='FILE_PATH'
    )
    
    hue_shift: FloatProperty(name="Hue Shift", default=0.0, min=0.0, max=1.0)
    saturation_shift: FloatProperty(name="Saturation Shift", default=0.0, min=0.0, max=1.0)
    value_shift: FloatProperty(name="Value Shift", default=0.0, min=0.0, max=1.0)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        image = self.get_image(context)
        if not image:
            return {'CANCELLED'}
        painter = BrushPainterCore()
        # Set parameters from UI
        painter.brush_coverage_density = self.brush_coverage_density
        painter.min_brush_scale = self.min_brush_scale
        painter.max_brush_scale = self.max_brush_scale
        painter.start_opacity = self.start_opacity
        painter.end_opacity = self.end_opacity
        painter.steps = self.steps
        painter.gradient_threshold = self.gradient_threshold
        painter.gaussian_sigma = self.gaussian_sigma
        painter.hue_shift = self.hue_shift
        painter.saturation_shift = self.saturation_shift
        painter.value_shift = self.value_shift
        # Set brush paths based on mode
        brush_folder_path = None
        brush_texture_path = None
        
        if self.brush_mode == 'PRESET' and self.presets:
            brush_folder_path = os.path.join(resolve_brush_preset_path(), self.presets)
        elif self.brush_mode == 'FOLDER' and self.brush_folder_path:
            if os.path.exists(self.brush_folder_path):
                brush_folder_path = self.brush_folder_path
            else:
                self.report({'WARNING'}, f"Brush folder not found: {self.brush_folder_path}")
        elif self.brush_mode == 'SINGLE' and self.brush_texture_path:
            if os.path.exists(self.brush_texture_path):
                brush_texture_path = self.brush_texture_path
            else:
                self.report({'WARNING'}, f"Brush texture not found: {self.brush_texture_path}")
        
        new_image = painter.apply_brush_painting(image, brush_folder_path=brush_folder_path, brush_texture_path=brush_texture_path)
        ps_ctx.active_global_layer.image = new_image
        return {'FINISHED'}
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False
        box = layout.box()
        col = box.column()
        col.prop(self, "brush_mode")
        if self.brush_mode == 'PRESET':
            col.prop(self, "presets", text="Preset")
        elif self.brush_mode == 'FOLDER':
            col.prop(self, "brush_folder_path")
        elif self.brush_mode == 'SINGLE':
            col.prop(self, "brush_texture_path")
        box = layout.box()
        col = box.column()
        row = col.row()
        row.alignment = "CENTER"
        row.label(text="Brush Parameters", icon="BRUSH_DATA")
        col.prop(self, "brush_coverage_density", text="Coverage Density", slider=True)
        col.prop(self, "steps")
        col.prop(self, "hue_shift", slider=True)
        col.prop(self, "saturation_shift", slider=True)
        col.prop(self, "value_shift", slider=True)
        box = layout.box()
        col = box.column()
        row = col.row()
        row.alignment = "CENTER"
        row.label(text="Advanced Settings", icon="TOOL_SETTINGS")
        split = col.split(factor=0.5)
        split.use_property_split = False
        col = split.column()
        col.prop(self, "min_brush_scale", slider=True)
        col.prop(self, "max_brush_scale", slider=True)
        col.prop(self, "gradient_threshold", slider=True)
        col = split.column()
        col.prop(self, "start_opacity", slider=True)
        col.prop(self, "end_opacity", slider=True)
        col.prop(self, "gaussian_sigma")

classes = (
    PAINTSYSTEM_OT_InvertColors,
    PAINTSYSTEM_OT_ResizeImage,
    PAINTSYSTEM_OT_ClearImage,
    PAINTSYSTEM_OT_FillImage,
    PAINTSYSTEM_OT_GaussianBlur,
    PAINTSYSTEM_OT_SharpenImage,
    PAINTSYSTEM_OT_BrushPainter,
)
register, unregister = register_classes_factory(classes)