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
        active_layer = ps_ctx.active_layer
        active_global_layer = ps_ctx.active_global_layer
        if not active_channel:
            return {'CANCELLED'}
        
        image = self.create_image()
        
        children = active_channel.get_children(active_layer.id)
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            global_layer = get_global_layer(layer)
            if global_layer.type != "FOLDER" and global_layer.enabled and global_layer != active_global_layer and layer not in children:
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
        active_channel.remove_children(active_layer.id)
        return {'FINISHED'}


class PAINTSYSTEM_OT_BakeObjectToLayer(PSContextMixin, PSImageCreateMixin, Operator):
    """Open baking window to bake textures from another object"""
    bl_idname = "paint_system.bake_object_to_layer"
    bl_label = "Bake Object to Layers"
    bl_description = "Bake textures from another object onto Paint System layers"
    bl_options = {'REGISTER', 'UNDO'}
    
    source_object: StringProperty(
        name="Source Object",
        description="Object to bake from",
        default=""
    )
    
    # Individual bake type buttons
    bake_combined: bpy.props.BoolProperty(name="Combined", default=False)
    bake_diffuse: bpy.props.BoolProperty(name="Diffuse", default=False)
    bake_glossy: bpy.props.BoolProperty(name="Glossy", default=False)
    bake_transmission: bpy.props.BoolProperty(name="Transmission", default=False)
    bake_subsurface: bpy.props.BoolProperty(name="Subsurface", default=False)
    bake_emit: bpy.props.BoolProperty(name="Emit", default=False)
    bake_ao: bpy.props.BoolProperty(name="AO", default=False)
    bake_shadow: bpy.props.BoolProperty(name="Shadow", default=False)
    bake_normal: bpy.props.BoolProperty(name="Normal", default=False)
    bake_roughness: bpy.props.BoolProperty(name="Roughness", default=False)
    bake_metallic: bpy.props.BoolProperty(name="Metallic", default=False)
    bake_environment: bpy.props.BoolProperty(name="Environment", default=False)
    bake_uv: bpy.props.BoolProperty(name="UV", default=False)
    bake_position: bpy.props.BoolProperty(name="Position", default=False)
    
    margin: bpy.props.IntProperty(
        name="Margin",
        description="Margin in pixels to extend the baked result",
        default=16,
        min=0,
        max=64
    )
    
    use_clear: bpy.props.BoolProperty(
        name="Clear Images",
        description="Clear images before baking",
        default=False
    )
    
    samples: bpy.props.IntProperty(
        name="Samples",
        description="Number of samples for baking",
        default=32,
        min=1,
        max=4096
    )
    
    # Advanced options
    use_selected_to_active: bpy.props.BoolProperty(
        name="Selected to Active",
        description="Bake shading on the surface of selected objects to the active object",
        default=False
    )
    
    cage_extrusion: bpy.props.FloatProperty(
        name="Ray Distance",
        description="Distance to use for the inward ray cast when using selected to active",
        default=0.0,
        min=0.0
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        
        # Set default image size
        if ps_ctx.active_global_layer and ps_ctx.active_global_layer.type == 'IMAGE' and ps_ctx.active_global_layer.image:
            target_image = ps_ctx.active_global_layer.image
            self.image_width = target_image.size[0]
            self.image_height = target_image.size[1]
            if self.image_width == self.image_height:
                size_str = str(self.image_width)
                if size_str in ['1024', '2048', '4096', '8192']:
                    self.image_resolution = size_str
                else:
                    self.image_resolution = 'CUSTOM'
            else:
                self.image_resolution = 'CUSTOM'
        else:
            self.image_resolution = '2048'
            self.image_width = 2048
            self.image_height = 2048
        
        return context.window_manager.invoke_props_dialog(self, width=500)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        
        # Source Object
        box = layout.box()
        box.label(text="Source Object", icon='OBJECT_DATA')
        box.prop_search(self, "source_object", bpy.data, "objects", text="")
        
        # Bake Types - organized in grid
        box = layout.box()
        box.label(text="Bake Types (Select Multiple)", icon='RENDERLAYERS')
        
        # Row 1: Main types
        split = box.split(factor=0.5)
        col1 = split.column(align=True)
        col1.prop(self, "bake_combined", toggle=True)
        col1.prop(self, "bake_diffuse", toggle=True)
        col1.prop(self, "bake_glossy", toggle=True)
        col1.prop(self, "bake_transmission", toggle=True)
        
        col2 = split.column(align=True)
        col2.prop(self, "bake_subsurface", toggle=True)
        col2.prop(self, "bake_emit", toggle=True)
        col2.prop(self, "bake_ao", toggle=True)
        col2.prop(self, "bake_shadow", toggle=True)
        
        # Row 2: Surface properties
        split = box.split(factor=0.5)
        col1 = split.column(align=True)
        col1.prop(self, "bake_normal", toggle=True)
        col1.prop(self, "bake_roughness", toggle=True)
        
        col2 = split.column(align=True)
        col2.prop(self, "bake_metallic", toggle=True)
        col2.prop(self, "bake_environment", toggle=True)
        
        # Row 3: Utility bakes
        split = box.split(factor=0.5)
        col1 = split.column(align=True)
        col1.prop(self, "bake_uv", toggle=True)
        
        col2 = split.column(align=True)
        col2.prop(self, "bake_position", toggle=True)
        
        # Image Settings
        self.image_create_ui(layout, context, show_name=False)
        
        # Bake Settings
        box = layout.box()
        box.label(text="Bake Settings", icon='SETTINGS')
        box.prop(self, "samples")
        box.prop(self, "margin")
        box.prop(self, "use_clear")
        
        # Advanced Options
        box = layout.box()
        box.label(text="Advanced Options", icon='PREFERENCES')
        box.prop(self, "use_selected_to_active")
        if self.use_selected_to_active:
            box.prop(self, "cage_extrusion")
    
    def find_channel_by_name(self, channels, keywords):
        """Find a channel that matches any of the keywords"""
        for ch in channels:
            ch_name = ch.name.lower()
            if any(keyword in ch_name for keyword in keywords):
                return ch
        return None
    
    def find_image_layer_in_channel(self, channel):
        """Find the first image layer in a channel"""
        from ..paintsystem.data import get_global_layer
        for layer in channel.layers:
            global_layer = get_global_layer(layer)
            if global_layer and global_layer.type == 'IMAGE' and global_layer.image:
                return global_layer.image
        return None
    
    def bake_to_image(self, context, source_obj, target_image, bake_type):
        """Bake source object to target image"""
        # Create temporary image node in source material
        mat = source_obj.active_material
        if not mat.use_nodes:
            mat.use_nodes = True
        
        node_tree = mat.node_tree
        temp_node = node_tree.nodes.new('ShaderNodeTexImage')
        temp_node.image = target_image
        
        # Deselect all nodes and make temp node active
        for node in node_tree.nodes:
            node.select = False
        temp_node.select = True
        node_tree.nodes.active = temp_node
        
        # Use temp_override to set proper context for baking
        with context.temp_override(active_object=source_obj, selected_objects=[source_obj]):
            # Bake
            bpy.ops.object.bake(
                type=bake_type,
                use_clear=self.use_clear,
                margin=self.margin
            )
        
        # Cleanup temp node
        node_tree.nodes.remove(temp_node)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        
        if not self.source_object:
            self.report({'ERROR'}, "Please select a source object")
            return {'CANCELLED'}
        
        source_obj = bpy.data.objects.get(self.source_object)
        if not source_obj:
            self.report({'ERROR'}, "Source object not found")
            return {'CANCELLED'}
        
        if not source_obj.active_material:
            self.report({'ERROR'}, "Source object has no active material")
            return {'CANCELLED'}
        
        # Build list of bake operations
        bake_operations = []
        
        # Map bake toggles to (bake_type, channel_keywords)
        bake_mapping = {
            'bake_combined': ('COMBINED', ['color', 'diffuse', 'base', 'albedo']),
            'bake_diffuse': ('DIFFUSE', ['color', 'diffuse', 'base', 'albedo']),
            'bake_glossy': ('GLOSSY', ['glossy', 'specular']),
            'bake_transmission': ('TRANSMISSION', ['transmission', 'refraction']),
            'bake_subsurface': ('SUBSURFACE', ['subsurface', 'sss']),
            'bake_emit': ('EMIT', ['emit', 'emission']),
            'bake_ao': ('AO', ['ao', 'occlusion', 'ambient']),
            'bake_shadow': ('SHADOW', ['shadow']),
            'bake_normal': ('NORMAL', ['normal']),
            'bake_roughness': ('ROUGHNESS', ['rough', 'roughness']),
            'bake_metallic': ('METALLIC', ['metal', 'metallic']),
            'bake_environment': ('ENVIRONMENT', ['environment', 'env']),
            'bake_uv': ('UV', ['uv']),
            'bake_position': ('POSITION', ['position', 'pos']),
        }
        
        for prop_name, (bake_type, keywords) in bake_mapping.items():
            if getattr(self, prop_name):
                bake_operations.append((bake_type, keywords))
        
        if not bake_operations:
            self.report({'ERROR'}, "Please select at least one bake type")
            return {'CANCELLED'}
        
        # Store original settings
        original_engine = context.scene.render.engine
        original_samples = context.scene.cycles.samples if context.scene.render.engine == 'CYCLES' else None
        
        baked_count = 0
        channels = ps_ctx.active_group.channels if ps_ctx.active_group else []
        
        try:
            # Setup for baking
            context.scene.render.engine = 'CYCLES'
            context.scene.cycles.samples = self.samples
            
            # Process each bake operation
            for bake_type, keywords in bake_operations:
                # Try to find matching channel
                channel = self.find_channel_by_name(channels, keywords)
                
                if channel:
                    # Found channel - bake to its image layer
                    target_image = self.find_image_layer_in_channel(channel)
                    if not target_image:
                        self.report({'WARNING'}, f"No image layer found in channel '{channel.name}' for {bake_type}")
                        continue
                    
                    # Resize if needed
                    if target_image.size[0] != self.image_width or target_image.size[1] != self.image_height:
                        target_image.scale(self.image_width, self.image_height)
                    
                    # Clear if requested
                    if self.use_clear:
                        pixels_count = self.image_width * self.image_height * 4
                        target_image.pixels = [0.0] * pixels_count
                    
                    self.bake_to_image(context, source_obj, target_image, bake_type)
                    baked_count += 1
                    self.report({'INFO'}, f"Baked {bake_type} to channel '{channel.name}'")
                else:
                    # No matching channel - bake to active layer if it's an image
                    if ps_ctx.active_global_layer and ps_ctx.active_global_layer.type == 'IMAGE':
                        target_image = ps_ctx.active_global_layer.image
                        if not target_image:
                            self.report({'WARNING'}, f"Active layer has no image for {bake_type}")
                            continue
                        
                        # Resize if needed
                        if target_image.size[0] != self.image_width or target_image.size[1] != self.image_height:
                            target_image.scale(self.image_width, self.image_height)
                        
                        # Clear if requested
                        if self.use_clear:
                            pixels_count = self.image_width * self.image_height * 4
                            target_image.pixels = [0.0] * pixels_count
                        
                        self.bake_to_image(context, source_obj, target_image, bake_type)
                        baked_count += 1
                        self.report({'INFO'}, f"Baked {bake_type} to active layer")
                    else:
                        self.report({'WARNING'}, f"No suitable target for {bake_type}")
            
            if baked_count > 0:
                self.report({'INFO'}, f"Successfully baked {baked_count} texture(s) ({self.image_width}x{self.image_height})")
            else:
                self.report({'WARNING'}, "No textures were baked")
            
        except Exception as e:
            self.report({'ERROR'}, f"Baking failed: {str(e)}")
            return {'CANCELLED'}
        
        finally:
            # Restore original settings
            context.scene.render.engine = original_engine
            if original_samples is not None:
                context.scene.cycles.samples = original_samples
        
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
    PAINTSYSTEM_OT_BakeObjectToLayer,
)

register, unregister = register_classes_factory(classes)