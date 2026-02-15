import time
import bpy
from bpy.types import Context, Image, Material, Operator, UILayout
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty

from .common import PSContextMixin, PSImageCreateMixin, DEFAULT_PS_UV_MAP_NAME

from ..paintsystem.data import Layer, set_layer_blend_type, get_layer_blend_type
from ..paintsystem.context import parse_material
from ..panels.common import get_icon_from_channel


class BakeOperator(PSContextMixin, PSImageCreateMixin, Operator):
    """Bake the active channel"""
    bl_options = {'REGISTER', 'UNDO'}
    
    def update_bake_multiple_objects(self, context: Context):
        ps_ctx = PSContextMixin.parse_context(context)
        seen_materials = set()
        check_objects = ps_ctx.ps_objects if self.bake_multiple_objects else [ps_ctx.ps_object]
        if context.scene and hasattr(context.scene, 'ps_scene_data'):
            temp_materials = context.scene.ps_scene_data.temp_materials
            temp_materials.clear()
            for obj in check_objects:
                for mat in obj.data.materials:
                    if hasattr(mat, "ps_mat_data") and len(mat.ps_mat_data.groups) != 0 and mat.name not in seen_materials:
                        seen_materials.add(mat.name)
                        temp_material = temp_materials.add()
                        temp_material.material = mat
                        temp_material.enabled = mat == ps_ctx.active_material
    
    bake_multiple_objects: BoolProperty(
        name="Bake Multiple Objects",
        description="Run the operator on multiple objects",
        default=True,
        update=update_bake_multiple_objects
    )
    
    use_gpu: BoolProperty(
        name="Use GPU",
        description="Use the GPU to bake the image",
        default=True,
        options={'SKIP_SAVE'}
    )
    
    margin: IntProperty(
        name="Margin",
        description="Margin to use for baking",
        default=8,
        min=0,
        max=100,
        options={'SKIP_SAVE'}
    )
    margin_type: EnumProperty(
        name="Margin Type",
        description="Margin type to use for baking",
        items=[
            ('ADJACENT_FACES', "Adjacent Faces", "Adjacent Faces"),
            ('EXTEND', "Extend", "Extend")
        ],
        default='ADJACENT_FACES',
        options={'SKIP_SAVE'}
    )
    
    as_tangent_normal: BoolProperty(
        name="As Tangent Normal",
        description="Bake the channel as a tangent normal",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    def find_objects_with_materials(self, context: Context, materials: list[Material]) -> list[bpy.types.Object]:
        objects = []
        for mat in materials:
            for obj in context.scene.objects:
                if obj.type == 'MESH' and mat.name in obj.data.materials:
                    objects.append(obj)
        return objects
    
    def invoke(self, context, event):
        """Invoke the operator to create a new channel."""
        ps_ctx = self.parse_context(context)
        self.update_bake_multiple_objects(context)
        self.get_coord_type(context)
        if self.use_paint_system_uv:
            self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
        self.image_name = f"{ps_ctx.active_group.name}_{ps_ctx.active_channel.name}"
        return context.window_manager.invoke_props_dialog(self)
    
    def advanced_bake_settings_ui(self, layout: UILayout, context: Context):
        header, panel = layout.panel("advanced_bake_settings_panel", default_closed=True)
        header.label(text="Advanced Settings", icon='IMAGE_DATA')
        if panel:
            panel.prop(self, "use_gpu", text="Use GPU")
            split = panel.split(factor=0.4, align=True)
            split.prop(self, "margin", text="Margin")
            split.prop(self, "margin_type", text="")
    
    def other_objects_ui(self, layout: UILayout, context: Context):
        ps_ctx = self.parse_context(context)
        enabled_materials = self.get_enabled_materials(context)
        if not enabled_materials:
            return
        objects_with_mat = self.find_objects_with_materials(context, enabled_materials)
        objects_not_selected = set(objects_with_mat) - set(ps_ctx.ps_objects)
        if len(objects_with_mat) > 1:
            box = layout.box()
            if objects_not_selected:
                box.alert = True
                col = box.column(align=True)
                col.label(text=f"Detected other objects with the material{'s' if len(enabled_materials) > 1 else ''}.", icon='ERROR')
                col.label(text="They will not be baked", icon='BLANK1')
                box.alert = False
                box.operator(PAINTSYSTEM_OT_SelectAllBakedObjects.bl_idname, text="Select All Objects", icon='SELECT_EXTEND')
                header, panel = box.panel("other_objects_panel", default_closed=True)
                header.label(text="See Detected Objects")
                if panel:
                    grid = panel.grid_flow(columns=3, align=True, row_major=True, even_columns=True)
                    grid.alert = False
                    for obj in objects_not_selected:
                        grid.label(text=obj.name, icon='OBJECT_DATA')
            else:
                box.label(text="All objects with the material are selected", icon='CHECKMARK')
        
    def multi_object_ui(self, layout: UILayout, context: Context):
        ps_ctx = self.parse_context(context)
        enabled_materials = self.get_enabled_materials(context)
        
        box = layout.box()
        temp_materials = ps_ctx.ps_scene_data.temp_materials
        box.label(text=f"Materials to Bake ({len(enabled_materials)})", icon='MATERIAL')
        col = box.column(align=True)
        for temp_material in temp_materials:
            row = col.row(align=True)
            row.prop(temp_material, "enabled",
                     text=f"{temp_material.material.name} (Current Material)" if temp_material.material == ps_ctx.active_material else temp_material.material.name,
                     toggle=1,
                     icon="CHECKBOX_HLT" if temp_material.enabled else "CHECKBOX_DEHLT")
        
        self.other_objects_ui(box, context)
    
    def get_enabled_materials(self, context: Context) -> list[Material]:
        ps_ctx = self.parse_context(context)
        return [temp_material.material for temp_material in ps_ctx.ps_scene_data.temp_materials if temp_material.enabled]
    
    def bake_image_ui(self, layout: UILayout, context: Context):
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context, show_name=False, show_float=True)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
        if ps_ctx.active_channel.type == "VECTOR":
            box = layout.box()
            box.prop(self, "as_tangent_normal")
            if self.as_tangent_normal:
                import textwrap
                wrapp = textwrap.TextWrapper(width=48) #50 = maximum length
                info_box = box.box()
                col = info_box.column(align=True)
                wList = wrapp.wrap(text="Deform Modifiers such as Armature will be disabled")
                for i, chunk in enumerate(wList):
                    col.label(text=chunk, icon='INFO' if not i else 'BLANK1')


class PAINTSYSTEM_OT_SelectAllBakedObjects(BakeOperator):
    bl_idname = "paint_system.select_all_baked_objects"
    bl_label = "Select All Baked Objects"
    bl_description = "Select all objects with baked images"
    bl_options = {'REGISTER', 'UNDO'}
    
    def invoke(self, context, event):
        return self.execute(context)
    
    def execute(self, context):
        objects_with_mat = self.find_objects_with_materials(context, self.get_enabled_materials(context))
        for obj in objects_with_mat:
            obj.select_set(True)
        return {'FINISHED'}


class PAINTSYSTEM_OT_BakeChannel(BakeOperator):
    """Bake the active channel"""
    bl_idname = "paint_system.bake_channel"
    bl_label = "Bake Channel"
    bl_description = "Bake the active channel"
    bl_options = {'REGISTER', 'UNDO'}
    
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
        self.multi_object_ui(layout, context)
        self.bake_image_ui(layout, context)
        self.advanced_bake_settings_ui(layout, context)
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        self.as_tangent_normal = ps_ctx.active_channel.bake_vector_space == 'TANGENT'
        return super().invoke(context, event)
    
    def execute(self, context):
        start_time = time.time()
        bake_materials = self.get_enabled_materials(context)
        ps_ctx = self.parse_context(context)
        if not bake_materials:
            self.report({'ERROR'}, "No materials to bake.")
            return {'CANCELLED'}
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        
        for mat in bake_materials:
            # Get the active channel for the material
            _, _, active_channel, _ = parse_material(mat)
            self.image_name = f"{mat.name}_Baked"
            if self.image_resolution != 'CUSTOM':
                self.image_width = int(self.image_resolution)
                self.image_height = int(self.image_resolution)
            bake_image = None
            if self.as_layer:
                bake_image = self.create_image(context)
                bake_image.colorspace_settings.name = 'sRGB'
                active_channel.bake(
                    context,
                    mat,
                    bake_image,
                    self.uv_map_name,
                    force_alpha=True,
                    as_tangent_normal=self.as_tangent_normal,
                    use_gpu=self.use_gpu,
                    margin=self.margin,
                    margin_type=self.margin_type,
                    disable_deform_modifiers=self.as_tangent_normal and active_channel.type == 'VECTOR'
                )
                active_channel.create_layer(
                    context, 
                    layer_name=self.image_name, 
                    layer_type="IMAGE", 
                    insert_at="START",
                    image=bake_image,
                    coord_type='UV',
                    uv_map_name=self.uv_map_name
                )
            else:
                bake_image = active_channel.bake_image
                if not bake_image:
                    # No bake image exists yet, create one
                    bake_image = self.create_image(context)
                    active_channel.bake_image = bake_image
                elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                    bake_image.scale(self.image_width, self.image_height)
                bake_image.colorspace_settings.name = 'Non-Color' if active_channel.color_space == 'NONCOLOR' else 'sRGB'
                active_channel.bake_uv_map = self.uv_map_name
                    
                active_channel.use_bake_image = False
                active_channel.bake(
                    context,
                    mat,
                    bake_image,
                    self.uv_map_name,
                    as_tangent_normal=self.as_tangent_normal,
                    use_gpu=self.use_gpu,
                    margin=self.margin,
                    margin_type=self.margin_type,
                    disable_deform_modifiers=self.as_tangent_normal and active_channel.type == 'VECTOR'
                )
                if self.as_tangent_normal:
                    active_channel.bake_vector_space = 'TANGENT'
                else:
                    active_channel.bake_vector_space = active_channel.vector_space
                active_channel.use_bake_image = True
        # Return to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
        # Set cursor to default
        context.window.cursor_set('DEFAULT')
        
        end_time = time.time()
        # report the time taken
        self.report({'INFO'}, f"Baked {len(bake_materials)} materials in {round(end_time - start_time, 2)} seconds")
        return {'FINISHED'}


class PAINTSYSTEM_OT_BakeAllChannels(BakeOperator):
    bl_idname = "paint_system.bake_all_channels"
    bl_label = "Bake All Channels"
    bl_description = "Bake all channels"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group
    
    def draw(self, context):
        layout = self.layout
        self.multi_object_ui(layout, context)
        self.bake_image_ui(layout, context)
        self.advanced_bake_settings_ui(layout, context)
    
    def execute(self, context):
        start_time = time.time()
        # Set cursor to wait
        bake_materials = self.get_enabled_materials(context)
        if not bake_materials:
            self.report({'ERROR'}, "No materials to bake.")
            return {'CANCELLED'}
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        
        if self.image_resolution != 'CUSTOM':
            self.image_width = int(self.image_resolution)
            self.image_height = int(self.image_resolution)
        ps_ctx = self.parse_context(context)
        for mat in bake_materials:
            _, active_group, _, _ = parse_material(mat)
            for channel in active_group.channels:
                bake_image = channel.bake_image
                if not bake_image:
                    self.image_name = f"{active_group.name}_{channel.name}_Baked"
                    bake_image = self.create_image(context)
                    channel.bake_image = bake_image
                elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                    bake_image.scale(self.image_width, self.image_height)
                bake_image.colorspace_settings.name = 'Non-Color' if channel.color_space == 'NONCOLOR' else 'sRGB'
                channel.use_bake_image = False
                channel.bake_uv_map = self.uv_map_name
                channel.bake(context, mat, bake_image, self.uv_map_name)
                channel.use_bake_image = True
        # Return to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
        # Set cursor to default
        context.window.cursor_set('DEFAULT')
        end_time = time.time()
        # report the time taken
        self.report({'INFO'}, f"Baked {len(bake_materials)} materials in {round(end_time - start_time, 2)} seconds")
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
            bpy.ops.image.save_as('INVOKE_DEFAULT')
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
        default=False
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
                # If image has tiles, add UDIM marker to the image name
                if len(channel.bake_image.tiles) > 1:
                    image_name = f"{image_name}.<UDIM>"
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
                    # If image has tiles, add UDIM marker to the image name
                    if len(image.tiles) > 1:
                        filename = f"{filename}.<UDIM>"
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


class PAINTSYSTEM_OT_TransferImageLayerUV(BakeOperator):
    bl_idname = "paint_system.transfer_image_layer_uv"
    bl_label = "Transfer Image Layer UV"
    bl_description = "Transfer the UV of the image layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel and ps_ctx.active_layer.type == 'IMAGE' and ps_ctx.active_layer.image
    
    # def invoke(self, context, event):
    #     return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.label(text=f"Baking material: {ps_ctx.active_material.name}", icon='MATERIAL')
        self.other_objects_ui(layout, context)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
        self.advanced_bake_settings_ui(layout, context)

    def execute(self, context):
        start_time = time.time()
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        if not active_channel:
            return {'CANCELLED'}
        
        transferred_image = active_layer.image.copy()
        transferred_image.name = f"{active_layer.image.name}_Transferred"
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            if layer.enabled and layer != active_layer:
                to_be_enabled_layers.append(layer)
                layer.enabled = False
        
        original_blend_mode = get_layer_blend_type(active_layer)
        set_layer_blend_type(active_layer, 'MIX')
        orig_is_clip = bool(active_layer.is_clip)
        if active_layer.is_clip:
            active_layer.is_clip = False
        active_channel.bake(context, ps_ctx.active_material, transferred_image, self.uv_map_name, use_group_tree=False, force_alpha=True)
        if active_layer.is_clip != orig_is_clip:
            active_layer.is_clip = orig_is_clip
        set_layer_blend_type(active_layer, original_blend_mode)
        active_layer.coord_type = 'UV'
        active_layer.uv_map_name = self.uv_map_name
        active_layer.image = transferred_image
        # Restore the layers
        for layer in to_be_enabled_layers:
            layer.enabled = True
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        end_time = time.time()
        # report the time taken
        self.report({'INFO'}, f"Transferred image layer UV in {round(end_time - start_time, 2)} seconds")
        return {'FINISHED'}


class PAINTSYSTEM_OT_ConvertToImageLayer(BakeOperator):
    bl_idname = "paint_system.convert_to_image_layer"
    bl_label = "Transfer Image Layer UV"
    bl_description = "Transfer the UV of the image layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer and ps_ctx.active_layer.type != 'IMAGE'
    
    def invoke(self, context, event):
        self.get_coord_type(context)
        if self.use_paint_system_uv:
            self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
        return super().invoke(context, event)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        layout.label(text=f"Baking material: {ps_ctx.active_material.name}", icon='MATERIAL')
        self.other_objects_ui(layout, context)
        self.image_create_ui(layout, context, show_name=False, show_float=True)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
        self.advanced_bake_settings_ui(layout, context)

    def execute(self, context):
        start_time = time.time()
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        if not active_channel:
            return {'CANCELLED'}
        
        image = self.create_image(context)
        
        children = active_channel.get_children(active_layer.id)
        
        to_be_enabled_layers = []
        # Ensure all layers are disabled except the active layer
        for layer in active_channel.layers:
            if layer.type != "FOLDER" and layer.enabled and layer != active_layer and layer not in children:
                to_be_enabled_layers.append(layer)
                layer.enabled = False
        original_blend_mode = get_layer_blend_type(active_layer)
        set_layer_blend_type(active_layer, 'MIX')
        orig_is_clip = bool(active_layer.is_clip)
        if active_layer.is_clip:
            active_layer.is_clip = False
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map_name, use_group_tree=False, force_alpha=True)
        if active_layer.is_clip != orig_is_clip:
            active_layer.is_clip = orig_is_clip
        set_layer_blend_type(active_layer, original_blend_mode)
        active_layer.coord_type = 'UV'
        active_layer.uv_map_name = self.uv_map_name
        active_layer.image = image
        active_layer.type = 'IMAGE'
        for layer in to_be_enabled_layers:
            layer.enabled = True
        active_channel.remove_children(active_layer.id)
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        end_time = time.time()
        # report the time taken
        self.report({'INFO'}, f"Converted to image layer in {round(end_time - start_time, 2)} seconds")
        return {'FINISHED'}


def apply_merged_image_to_layer(merged_layer: "Layer", image: Image, uv_map_name: str):
    merged_layer.name = merged_layer.name + " Merged"
    merged_layer.type = "IMAGE"
    merged_layer.coord_type = "UV"
    merged_layer.uv_map_name = uv_map_name
    merged_layer.image = image
    merged_layer.linked_layer_uid = ""
    merged_layer.linked_material = None
    merged_layer.correct_image_aspect = False


class PAINTSYSTEM_OT_MergeDown(BakeOperator):
    bl_idname = "paint_system.merge_down"
    bl_label = "Merge Down"
    bl_description = "Merge the down layers"
    bl_options = {'REGISTER', 'UNDO'}
    
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
            active_layer
            and below_layer
            and active_layer.type != "FOLDER"
            and below_layer.type != "FOLDER"
            and active_layer.parent_id == below_layer.parent_id
            and active_layer.enabled
            and below_layer.enabled
            and not below_layer.modifies_color_data
            )
    
    def invoke(self, context, event):
        self.get_coord_type(context)
        self.update_bake_multiple_objects(context)
        below_layer = self.get_below_layer(context)
        if below_layer:
            if below_layer.uses_coord_type:
                if getattr(below_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            else:
                self.uv_map_name = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        if below_layer.type == "IMAGE":
            self.image_resolution = "CUSTOM"
            self.image_width = below_layer.image.size[0]
            self.image_height = below_layer.image.size[1]
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="This operation will convert the current layer", icon='INFO')
        col.label(text="into an image layer.", icon='BLANK1')
        self.other_objects_ui(layout, context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        start_time = time.time()
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        below_layer = self.get_below_layer(context)
        unlinked_layer = ps_ctx.unlinked_layer
        below_unlinked_layer = self.get_below_layer(context, unprocessed=True)
        
        if not active_channel:
            return {'CANCELLED'}
        
        image = self.create_image(context)
        
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
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map_name, use_group_tree=False, force_alpha=True)
        
        # Restore original blend modes
        set_layer_blend_type(active_layer, original_active_blend_mode)
        set_layer_blend_type(below_layer, original_below_blend_mode)
        
        # Restore other layers
        for layer in to_be_enabled_layers:
            layer.enabled = True
        
        # Remove the current layer since it's been merged
        apply_merged_image_to_layer(below_unlinked_layer, image, self.uv_map_name)
        active_channel.delete_layer(context, unlinked_layer)
        active_channel.set_active_index_to_layer(context, below_unlinked_layer)
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        end_time = time.time()
        # report the time taken
        self.report({'INFO'}, f"Merged down in {round(end_time - start_time, 2)} seconds")
        return {'FINISHED'}


class PAINTSYSTEM_OT_MergeUp(BakeOperator):
    bl_idname = "paint_system.merge_up"
    bl_label = "Merge Up"
    bl_description = "Merge the layer into the one above"
    bl_options = {'REGISTER', 'UNDO'}

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
            and not active_layer.modifies_color_data
        )

    def invoke(self, context, event):
        self.get_coord_type(context)
        self.update_bake_multiple_objects(context)
        above_layer = self.get_above_layer(context)
        # Choose UV based on the layer above
        if above_layer:
            if above_layer.uses_coord_type:
                if getattr(above_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            else:
                self.uv_map_name = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        if above_layer.type == "IMAGE":
            self.image_resolution = "CUSTOM"
            self.image_width = above_layer.image.size[0]
            self.image_height = above_layer.image.size[1]
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        box = layout.box()
        col = box.column(align=True)
        col.label(text="This operation will convert the current layer", icon='INFO')
        col.label(text="into an image layer.", icon='BLANK1')
        self.other_objects_ui(layout, context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        start_time = time.time()
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        above_layer = self.get_above_layer(context)
        unlinked_layer = ps_ctx.unlinked_layer
        above_unlinked_layer = self.get_above_layer(context, unprocessed=True)

        if not active_channel:
            return {'CANCELLED'}

        image = self.create_image(context)

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
        active_channel.bake(context, ps_ctx.active_material, image, self.uv_map_name, use_group_tree=False, force_alpha=True)

        # Restore original blend modes
        set_layer_blend_type(active_layer, original_active_blend_mode)
        set_layer_blend_type(above_layer, original_above_blend_mode)

        # Restore other layers
        for layer in to_be_enabled_layers:
            layer.enabled = True

        apply_merged_image_to_layer(above_unlinked_layer, image, self.uv_map_name)
        active_channel.delete_layer(context, unlinked_layer)
        active_channel.set_active_index_to_layer(context, above_unlinked_layer)
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        end_time = time.time()
        # report the time taken
        self.report({'INFO'}, f"Merged up in {round(end_time - start_time, 2)} seconds")
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_SelectAllBakedObjects,
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