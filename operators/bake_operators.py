import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty

from .common import PSContextMixin, PSImageCreateMixin, PSUVOptionsMixin

from ..paintsystem.data import get_global_layer, set_blend_type, get_blend_type
from ..panels.common import get_icon_from_channel


class BakeOperator(PSContextMixin, PSUVOptionsMixin, PSImageCreateMixin, Operator):
    """Bake the active channel"""
    bl_options = {'REGISTER', 'UNDO'}

    uv_map: StringProperty(
        name= "UV Map",
        default= "UVMap",
        options={'SKIP_SAVE'}
    )
    
    def invoke(self, context, event):
        """Invoke the operator to create a new channel."""
        ps_ctx = self.parse_context(context)
        self.get_coord_type(context)
        if self.coord_type == 'AUTO':
            self.uv_map = "PS_UVMap"
        else:
            self.uv_map = self.uv_map_name
        # Always set image_name to Group_Layer.png
        group = ps_ctx.active_group.name if ps_ctx.active_group else "Group"
        layer = ps_ctx.active_channel.name if ps_ctx.active_channel else "Layer"
        self.image_name = f"{group}_{layer}"
        if not self.image_name.lower().endswith('.png'):
            self.image_name += '.png'
        return context.window_manager.invoke_props_dialog(self)

class PAINTSYSTEM_OT_BakeChannel(BakeOperator):
    """Bake the active channel"""
    bl_idname = "paint_system.bake_channel"
    bl_label = "Bake Channel"
    bl_description = "Bake the active channel"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_map: StringProperty(
        name= "UV Map",
        default= "UVMap",
        options={'SKIP_SAVE'}
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel
    
    def draw(self, context):
        layout = self.layout
        self.image_create_ui(layout, context)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", context.object.data, "uv_layers", text="")
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        mat = ps_ctx.active_material
        bake_image = active_channel.bake_image
        active_channel.bake_uv_map = self.uv_map
        
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        
        if not bake_image:
            group = ps_ctx.active_group.name if ps_ctx.active_group else "Group"
            layer = ps_ctx.active_channel.name if ps_ctx.active_channel else "Layer"
            self.image_name = f"{group}_{layer}"
            if not self.image_name.lower().endswith('.png'):
                self.image_name += '.png'
            bake_image = self.create_image()
            bake_image.colorspace_settings.name = 'sRGB'
            active_channel.bake_image = bake_image
        elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
            bake_image.scale(self.image_width, self.image_height)
            
        active_channel.use_bake_image = False
        active_channel.bake(context, mat, bake_image, self.uv_map)
        active_channel.use_bake_image = True
        # Return to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
        return {'FINISHED'}


class PAINTSYSTEM_OT_BakeAllChannels(BakeOperator):
    bl_idname = "paint_system.bake_all_channels"
    bl_label = "Bake All Channels"
    bl_description = "Bake all channels"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_map: StringProperty(
        name= "UV Map",
        default= "UVMap",
        options={'SKIP_SAVE'}
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group
    
    def draw(self, context):
        layout = self.layout
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", context.object.data, "uv_layers", text="")
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        
        for channel in active_group.channels:
            mat = ps_ctx.active_material
            bake_image = channel.bake_image
            
            if not bake_image:
                self.image_name = f"{ps_ctx.active_group.name}_{channel.name}"
                bake_image = self.create_image()
                bake_image.colorspace_settings.name = 'sRGB'
                channel.bake_image = bake_image
            elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                bake_image.scale(self.image_width, self.image_height)
                
            channel.use_bake_image = False
            channel.bake_uv_map = self.uv_map
            channel.bake(context, mat, bake_image, self.uv_map)
            channel.use_bake_image = True
        # Return to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
        return {'FINISHED'}


class PAINTSYSTEM_OT_RebakeChannel(PSContextMixin, Operator):
    """Rebake the active channel with existing settings"""
    bl_idname = "paint_system.rebake_channel"
    bl_label = "Rebake Channel"
    bl_description = "Rebake the active channel using existing bake image and UV map"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel and ps_ctx.active_channel.bake_image and ps_ctx.active_channel.bake_uv_map
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        mat = ps_ctx.active_material
        bake_image = active_channel.bake_image
        uv_map = active_channel.bake_uv_map
        
        if not bake_image or not uv_map:
            self.report({'ERROR'}, "No baked image/UV map found. Please bake first.")
            return {'CANCELLED'}
        
        # Temporarily disable baked output to bake from live graph
        active_channel.use_bake_image = False
        active_channel.bake(context, mat, bake_image, uv_map)
        active_channel.use_bake_image = True
        
        bpy.ops.object.mode_set(mode="OBJECT")
        self.report({'INFO'}, f"Rebaked channel '{active_channel.name}'")
        return {'FINISHED'}


class PAINTSYSTEM_OT_ExportImage(PSContextMixin, Operator):
    bl_idname = "paint_system.export_image"
    bl_label = "Export Baked Image"
    bl_description = "Export the baked image"
    
    image_name: StringProperty(
        name="Image Name",
        options={'SKIP_SAVE'}
    )

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}

        image = bpy.data.images.get(self.image_name)
        if not image:
            self.report({'ERROR'}, "Image not found.")
            return {'CANCELLED'}

        with bpy.context.temp_override(**{'edit_image': image}):
            bpy.ops.image.save_as('INVOKE_DEFAULT', copy=True)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ExportAllImages(PSContextMixin, Operator):
    bl_idname = "paint_system.export_all_images"
    bl_label = "Export All Images"
    bl_description = "Export all images"
    
    directory: StringProperty(
        name="Directory",
        description="Directory to export images to",
        subtype='DIR_PATH',
        options={'SKIP_SAVE'}
    )
    
    as_copy: BoolProperty(
        name="As Copy",
        description="Export the images as copies",
        default=True
    )
    
    replace_whitespaces: BoolProperty(
        name="Replace Whitespaces",
        description="Replace whitespaces with underscores",
        default=True
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
    
    def draw(self, context):
        layout = self.layout
        # Show preview of what will be exported
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        box = layout.box()
        box.label(text="Images to export:", icon='IMAGE_DATA')
        export_box = box.box()
        export_col = export_box.column(align=True)
        exported_count = 0
        for channel in active_group.channels:
            row = export_col.row()
            if channel.bake_image:
                image_name = channel.bake_image.name
                if self.replace_whitespaces:
                    image_name = image_name.replace(" ", "_")
                row.label(text=f"{channel.name}: {image_name}.png", icon_value=get_icon_from_channel(channel))
                exported_count += 1
            else:
                row.label(text=f"{channel.name}: No baked image", icon_value=get_icon_from_channel(channel))
                row.enabled = False
        
        if exported_count == 0:
            box.label(text="No baked images found", icon='ERROR')
        else:
            box.label(text=f"Total: {exported_count} images")
        box.prop(self, "as_copy")
        box.prop(self, "replace_whitespaces")
    
    def execute(self, context):
        import os
        
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        
        if not active_group:
            self.report({'ERROR'}, "No active group found.")
            return {'CANCELLED'}
        
        if not self.directory:
            self.report({'ERROR'}, "No directory selected.")
            return {'CANCELLED'}
        
        # Ensure directory exists
        if not os.path.exists(self.directory):
            try:
                os.makedirs(self.directory, exist_ok=True)
            except Exception as e:
                self.report({'ERROR'}, f"Failed to create directory: {str(e)}")
                return {'CANCELLED'}
        
        exported_count = 0
        failed_count = 0
        
        for channel in active_group.channels:
            if channel.bake_image:
                try:
                    
                    # Save the image
                    image = channel.bake_image
                    # Create filename from channel name
                    filename = image.name
                    if self.replace_whitespaces:
                        filename = filename.replace(" ", "_")
                    filename = f"{filename}.png"
                    filepath = os.path.join(self.directory, filename)
                    image.save(filepath=filepath, save_copy=self.as_copy)
                    
                    exported_count += 1
                    
                except Exception as e:
                    self.report({'WARNING'}, f"Failed to export {channel.name}: {str(e)}")
                    failed_count += 1
        
        if exported_count > 0:
            self.report({'INFO'}, f"Exported {exported_count} images to {self.directory}")
        
        if failed_count > 0:
            self.report({'WARNING'}, f"Failed to export {failed_count} images")
        
        if exported_count == 0:
            self.report({'ERROR'}, "No baked images found to export.")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_DeleteBakedImage(PSContextMixin, Operator):
    bl_idname = "paint_system.delete_bake_image"
    bl_label = "Delete Baked Image"
    bl_description = "Delete the baked image"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return {'CANCELLED'}

        image = active_channel.bake_image
        if not image:
            self.report({'ERROR'}, "No baked image found.")
            return {'CANCELLED'}

        bpy.data.images.remove(image)
        active_channel.bake_image = None
        active_channel.use_bake_image = False
        active_channel.bake_uv_map = ""

        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        layout.label(
            text="Click OK to delete the baked image.")


class PAINTSYSTEM_OT_TransferImageLayerUV(PSContextMixin, PSUVOptionsMixin, Operator):
    bl_idname = "paint_system.transfer_image_layer_uv"
    bl_label = "Transfer Image Layer UV"
    bl_description = "Transfer the UV of the image layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_map: StringProperty(
        name= "UV Map",
        default="UVMap",
        options={'SKIP_SAVE'},
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel and ps_ctx.active_global_layer.type == 'IMAGE' and ps_ctx.active_global_layer.image
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", context.object.data, "uv_layers", text="")

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_global_layer = ps_ctx.active_global_layer
        if not active_channel:
            return {'CANCELLED'}
        
        transferred_image = bpy.data.images.new(name=f"{active_global_layer.image.name}_Transferred", width=active_global_layer.image.size[0], height=active_global_layer.image.size[1], alpha=True)
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            global_layer = get_global_layer(layer)
            if global_layer.enabled and global_layer != active_global_layer:
                to_be_enabled_layers.append(global_layer)
                global_layer.enabled = False
        
        original_blend_mode = get_blend_type(active_global_layer)
        set_blend_type(active_global_layer, 'MIX')
        active_channel.bake(context, ps_ctx.active_material, transferred_image, self.uv_map, use_group_tree=False)
        set_blend_type(active_global_layer, original_blend_mode)
        active_global_layer.coord_type = 'UV'
        active_global_layer.uv_map_name = self.uv_map
        active_global_layer.image = transferred_image
        # Restore the layers
        for layer in to_be_enabled_layers:
            layer.enabled = True
        return {'FINISHED'}


class PAINTSYSTEM_OT_ConvertToImageLayer(PSContextMixin, PSUVOptionsMixin, PSImageCreateMixin, Operator):
    bl_idname = "paint_system.convert_to_image_layer"
    bl_label = "Transfer Image Layer UV"
    bl_description = "Transfer the UV of the image layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_map: StringProperty(
        name= "UV Map",
        default="UVMap",
        options={'SKIP_SAVE'},
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer and ps_ctx.active_layer.type != 'IMAGE'
    
    def invoke(self, context, event):
        self.get_coord_type(context)
        if self.coord_type == 'AUTO':
            self.uv_map = "PS_UVMap"
        else:
            self.uv_map = self.uv_map_name
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        self.image_create_ui(layout, context)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", context.object.data, "uv_layers", text="")

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_global_layer = ps_ctx.active_global_layer
        if not active_channel:
            return {'CANCELLED'}
        
        image = self.create_image()
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            global_layer = get_global_layer(layer)
            if global_layer.enabled and global_layer != active_global_layer:
                to_be_enabled_layers.append(global_layer)
                global_layer.enabled = False
        original_blend_mode = get_blend_type(active_global_layer)
        set_blend_type(active_global_layer, 'MIX')
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map, use_group_tree=False)
        set_blend_type(active_global_layer, original_blend_mode)
        active_global_layer.type = 'IMAGE'
        active_global_layer.coord_type = 'UV'
        active_global_layer.uv_map_name = self.uv_map
        active_global_layer.image = image
        for layer in to_be_enabled_layers:
            layer.enabled = True
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_BakeChannel,
    PAINTSYSTEM_OT_RebakeChannel,
    PAINTSYSTEM_OT_BakeAllChannels,
    PAINTSYSTEM_OT_TransferImageLayerUV,
    PAINTSYSTEM_OT_ExportImage,
    PAINTSYSTEM_OT_ExportAllImages,
    PAINTSYSTEM_OT_DeleteBakedImage,
    PAINTSYSTEM_OT_ConvertToImageLayer,
)

register, unregister = register_classes_factory(classes)