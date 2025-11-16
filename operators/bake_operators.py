import bpy
from bpy.types import Operator
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty

from .common import PSContextMixin, PSImageCreateMixin, PSUVOptionsMixin, DEFAULT_PS_UV_MAP_NAME

from ..paintsystem.data import set_layer_blend_type, get_layer_blend_type
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
        if self.use_paint_system_uv:
            self.uv_map = DEFAULT_PS_UV_MAP_NAME
        else:
            self.uv_map = self.uv_map_name
        self.image_name = f"{ps_ctx.active_group.name}_{ps_ctx.active_channel.name}"
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
    as_layer: BoolProperty(
        name="As Layer",
        description="Bake the channel as a layer",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", ps_ctx.ps_object.data, "uv_layers", text="")
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        mat = ps_ctx.active_material
        self.image_name = f"{active_channel.name}_Baked"
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        
        bake_image = None
        if self.as_layer:
            bake_image = self.create_image()
            bake_image.colorspace_settings.name = 'sRGB'
            active_channel.create_layer(
                context, 
                layer_name=self.image_name, 
                layer_type="IMAGE", 
                insert_at="START",
                image=bake_image,
                coord_type='UV',
                uv_map_name=self.uv_map
            )
            active_channel.bake(context, mat, bake_image, self.uv_map)
        else:
            bake_image = active_channel.bake_image
            if not bake_image:
                bake_image = self.create_image()
                bake_image.colorspace_settings.name = 'sRGB'
                active_channel.bake_image = bake_image
            elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                bake_image.scale(self.image_width, self.image_height)
            active_channel.bake_uv_map = self.uv_map
                
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
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", ps_ctx.ps_object.data, "uv_layers", text="")
    
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
            self.report({'ERROR'}, "Baked Image not found.")
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
        ps_ctx = self.parse_context(context)
        bake_image_num = 0
        for channel in ps_ctx.active_group.channels:
            if channel.bake_image:
                bake_image_num += 1
        if bake_image_num == 0:
            self.report({'ERROR'}, "No baked images found.")
            return {'CANCELLED'}
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
        return ps_ctx.active_channel and ps_ctx.active_layer.type == 'IMAGE' and ps_ctx.active_layer.image
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        if not active_channel:
            return {'CANCELLED'}
        
        transferred_image = bpy.data.images.new(name=f"{active_layer.image.name}_Transferred", width=active_layer.image.size[0], height=active_layer.image.size[1], alpha=True)
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            if layer.enabled and layer != active_layer:
                to_be_enabled_layers.append(layer)
                layer.enabled = False
        
        original_blend_mode = get_layer_blend_type(active_layer)
        set_layer_blend_type(active_layer, 'MIX')
        active_channel.bake(context, ps_ctx.active_material, transferred_image, self.uv_map, use_group_tree=False)
        set_layer_blend_type(active_layer, original_blend_mode)
        active_layer.coord_type = 'UV'
        active_layer.uv_map_name = self.uv_map
        active_layer.image = transferred_image
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
        if self.use_paint_system_uv:
            self.uv_map = DEFAULT_PS_UV_MAP_NAME
        else:
            self.uv_map = self.uv_map_name
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        if not active_channel:
            return {'CANCELLED'}
        
        image = self.create_image()
        
        children = active_channel.get_children(active_layer.id)
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            if layer.type != "FOLDER" and layer.enabled and layer != active_layer and layer not in children:
                to_be_enabled_layers.append(layer)
                layer.enabled = False
        original_blend_mode = get_layer_blend_type(active_layer)
        set_layer_blend_type(active_layer, 'MIX')
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map, use_group_tree=False)
        set_layer_blend_type(active_layer, original_blend_mode)
        active_layer.type = 'IMAGE'
        active_layer.coord_type = 'UV'
        active_layer.uv_map_name = self.uv_map
        active_layer.image = image
        for layer in to_be_enabled_layers:
            layer.enabled = True
        active_channel.remove_children(active_layer.id)
        return {'FINISHED'}


class PAINTSYSTEM_OT_MergeDown(PSContextMixin, PSUVOptionsMixin, PSImageCreateMixin, Operator):
    bl_idname = "paint_system.merge_down"
    bl_label = "Merge Down"
    bl_description = "Merge the down layers"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_map: StringProperty(
        name= "UV Map",
        default="UVMap",
        options={'SKIP_SAVE'},
    )
    
    def get_below_layer(self, context, unprocessed: bool = False):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.unlinked_layer if unprocessed else ps_ctx.active_layer
        flattened_layers = active_channel.flattened_unlinked_layers if unprocessed else active_channel.flattened_layers
        if active_layer and flattened_layers.index(active_layer) < len(flattened_layers) - 1:
            return flattened_layers[flattened_layers.index(active_layer) + 1]
        return None
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        below_layer = cls.get_below_layer(cls, context)
        if not below_layer:
            return False
        return (
            active_layer and 
            below_layer and 
            active_layer.type != "FOLDER" and 
            below_layer.type != "FOLDER" and
            active_layer.parent_id == below_layer.parent_id and
            active_layer.enabled and
            below_layer.enabled
            )
    
    def invoke(self, context, event):
        self.get_coord_type(context)
        below_layer = self.get_below_layer(context)
        if below_layer:
            if below_layer.uses_coord_type:
                if getattr(below_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map = DEFAULT_PS_UV_MAP_NAME
                else:
                    self.uv_map = below_layer.uv_map_name
            else:
                print("Using paint system UV")
                self.uv_map = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        if below_layer.type == "IMAGE":
            self.image_width = below_layer.image.size[0]
            self.image_height = below_layer.image.size[1]
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        below_layer = self.get_below_layer(context)
        unlinked_layer = ps_ctx.unlinked_layer
        below_unlinked_layer = self.get_below_layer(context, unprocessed=True)
        
        if not active_channel:
            return {'CANCELLED'}
        
        image = self.create_image()
        
        to_be_enabled_layers = []
        # Enable both active layer and below layer, disable all others
        for layer in active_channel.flattened_layers:
            if layer.type != "FOLDER" and layer.enabled and layer != active_layer and layer != below_layer:
                to_be_enabled_layers.append(layer)
                layer.enabled = False
        
        # Enable the below layer if it's not already enabled
        if not below_layer.enabled:
            below_layer.enabled = True
        
        # Store original blend modes
        original_active_blend_mode = get_layer_blend_type(active_layer)
        original_below_blend_mode = get_layer_blend_type(below_layer)
        
        # Set both layers to MIX for proper blending
        set_layer_blend_type(active_layer, 'MIX')
        set_layer_blend_type(below_layer, 'MIX')
        
        # Bake both layers into the new image
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map, use_group_tree=False)
        
        # Restore original blend modes
        set_layer_blend_type(active_layer, original_active_blend_mode)
        set_layer_blend_type(below_layer, original_below_blend_mode)
        
        # Restore other layers
        for layer in to_be_enabled_layers:
            layer.enabled = True
        
        # Remove the current layer since it's been merged
        active_channel.delete_layer(context, unlinked_layer)
        active_channel.delete_layer(context, below_unlinked_layer)
        
        active_channel.create_layer(context, "Merged Layer", "IMAGE", coord_type="UV", uv_map_name=self.uv_map, image=image)
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_MergeUp(PSContextMixin, PSUVOptionsMixin, PSImageCreateMixin, Operator):
    bl_idname = "paint_system.merge_up"
    bl_label = "Merge Up"
    bl_description = "Merge the layer into the one above"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map: StringProperty(
        name= "UV Map",
        default="UVMap",
        options={'SKIP_SAVE'},
    )

    def get_above_layer(self, context, unprocessed: bool = False):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.unlinked_layer if unprocessed else ps_ctx.active_layer
        flattened_layers = active_channel.flattened_unlinked_layers if unprocessed else active_channel.flattened_layers
        if active_layer and flattened_layers.index(active_layer) > 0:
            return flattened_layers[flattened_layers.index(active_layer) - 1]
        return None

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        active_layer = ps_ctx.active_layer
        above_layer = cls.get_above_layer(cls, context)
        if not above_layer:
            return False
        return (
            active_layer
            and above_layer
            and active_layer.type != "FOLDER"
            and above_layer.type != "FOLDER"
            and active_layer.parent_id == above_layer.parent_id
            and active_layer.enabled
            and above_layer.enabled
        )

    def invoke(self, context, event):
        self.get_coord_type(context)
        above_layer = self.get_above_layer(context)
        # Choose UV based on the layer above
        if above_layer:
            if above_layer.uses_coord_type:
                if getattr(above_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map = DEFAULT_PS_UV_MAP_NAME
                else:
                    self.uv_map = above_layer.uv_map_name
            else:
                self.uv_map = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        if above_layer.type == "IMAGE":
            self.image_width = above_layer.image.size[0]
            self.image_height = above_layer.image.size[1]
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        above_layer = self.get_above_layer(context)
        unlinked_layer = ps_ctx.unlinked_layer
        above_unlinked_layer = self.get_above_layer(context, unprocessed=True)

        if not active_channel:
            return {'CANCELLED'}

        image = self.create_image()

        to_be_enabled_layers = []
        # Enable both active layer and above layer, disable all others
        for layer in active_channel.flattened_layers:
            if layer.type != "FOLDER" and layer.enabled and layer != active_layer and layer != above_layer:
                to_be_enabled_layers.append(layer)
                layer.enabled = False

        # Ensure the above layer is enabled
        if not above_layer.enabled:
            above_layer.enabled = True

        # Store original blend modes
        original_active_blend_mode = get_layer_blend_type(active_layer)
        original_above_blend_mode = get_layer_blend_type(above_layer)

        # Set both layers to MIX for proper blending
        set_layer_blend_type(active_layer, 'MIX')
        set_layer_blend_type(above_layer, 'MIX')

        # Bake both layers into the new image
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map, use_group_tree=False)

        # Restore original blend modes
        set_layer_blend_type(active_layer, original_active_blend_mode)
        set_layer_blend_type(above_layer, original_above_blend_mode)

        # Restore other layers
        for layer in to_be_enabled_layers:
            layer.enabled = True

        # Remove the current layer since it's been merged into the layer above
        active_channel.delete_layer(context, unlinked_layer)
        active_channel.delete_layer(context, above_unlinked_layer)
        
        active_channel.create_layer(context, "Merged Layer", "IMAGE", coord_type="UV", uv_map_name=self.uv_map, image=image)
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_BakeChannel,
    PAINTSYSTEM_OT_BakeAllChannels,
    PAINTSYSTEM_OT_TransferImageLayerUV,
    PAINTSYSTEM_OT_ExportImage,
    PAINTSYSTEM_OT_ExportAllImages,
    PAINTSYSTEM_OT_DeleteBakedImage,
    PAINTSYSTEM_OT_ConvertToImageLayer,
    PAINTSYSTEM_OT_MergeDown,
    PAINTSYSTEM_OT_MergeUp,
)

register, unregister = register_classes_factory(classes)