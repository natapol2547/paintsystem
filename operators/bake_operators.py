import bpy
import inspect
from bpy.types import Operator
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty

from .common import PSContextMixin, PSImageCreateMixin, PSUVOptionsMixin, DEFAULT_PS_UV_MAP_NAME

from ..paintsystem.data import set_layer_blend_type, get_layer_blend_type
from ..panels.common import get_icon_from_channel


class BakeOperator(PSContextMixin, PSImageCreateMixin, Operator):
    """Bake the active channel"""
    bl_options = {'REGISTER', 'UNDO'}
    
    overwrite_image: BoolProperty(
        name="Overwrite Existing Image",
        description="Overwrite the existing baked image instead of creating a new one",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    bake_all_material_objects: BoolProperty(
        name="Bake All Material Objects",
        description="Bake all objects using this material, not just selected objects. Recommended for UDIM to capture all tiles",
        default=True,
        options={'SKIP_SAVE'}
    )
    
    def invoke(self, context, event):
        """Invoke the operator to create a new channel."""
        ps_ctx = self.parse_context(context)
        self.get_coord_type(context)
        if self.use_paint_system_uv:
            self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
        self.image_name = f"{ps_ctx.active_group.name}_{ps_ctx.active_channel.name}"
        return context.window_manager.invoke_props_dialog(self)

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
    
    as_tangent_normal: BoolProperty(
        name="As Tangent Normal",
        description="Bake the channel as a tangent normal",
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
        
        # Image options
        box = layout.box()
        box.label(text="Image Options", icon='IMAGE_DATA')
        if not self.as_layer:
            existing_image = ps_ctx.active_channel.bake_image if ps_ctx.active_channel else None
            if existing_image:
                box.prop(self, "overwrite_image")
                if self.overwrite_image:
                    box.label(text=f"Will overwrite: {existing_image.name}", icon='INFO')
        
        self.image_create_ui(layout, context)
        
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
        
        # Multi-object baking option
        box = layout.box()
        box.label(text="Object Selection", icon='OBJECT_DATA')
        box.prop(self, "bake_all_material_objects")
        
        if ps_ctx.active_channel.type == "VECTOR":
            box = layout.box()
            box.prop(self, "as_tangent_normal")
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        self.as_tangent_normal = ps_ctx.active_channel.bake_vector_space == 'TANGENT'
        return super().invoke(context, event)
    
    def execute(self, context):
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        mat = ps_ctx.active_material
        # Use clearer naming: Material_Channel for saved images
        mat_name = mat.name if mat else "Material"
        channel_name = active_channel.name
        self.image_name = f"{mat_name}_{channel_name}"
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        
        bake_image = None
        if self.as_layer:
            bake_image = self.create_image(context)
            bake_image.colorspace_settings.name = 'sRGB'
            
            # Get list of objects to bake
            mesh_objects = self._get_mesh_objects(context, ps_ctx)
            
            # Build bake kwargs based on signature to avoid unexpected-arg errors
            sig = inspect.signature(active_channel.bake)
            bake_kwargs = {}
            if 'force_alpha' in sig.parameters:
                bake_kwargs['force_alpha'] = True
            if 'as_tangent_normal' in sig.parameters:
                bake_kwargs['as_tangent_normal'] = self.as_tangent_normal
            if 'bake_objects' in sig.parameters:
                bake_kwargs['bake_objects'] = mesh_objects
            # Call bake safely
            active_channel.bake(context, mat, bake_image, self.uv_map_name, **bake_kwargs)
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
            if not bake_image or not self.overwrite_image:
                # Create new image if none exists or overwrite is disabled
                bake_image = self.create_image(context)
                bake_image.colorspace_settings.name = 'sRGB'
                active_channel.bake_image = bake_image
            else:
                # Overwrite existing image - resize if needed
                if bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                    bake_image.scale(self.image_width, self.image_height)
            active_channel.bake_uv_map = self.uv_map_name
            
            # Get list of objects to bake
            mesh_objects = self._get_mesh_objects(context, ps_ctx)
                
            active_channel.use_bake_image = False
            # Respect available kwargs
            sig = inspect.signature(active_channel.bake)
            bake_kwargs = {}
            if 'as_tangent_normal' in sig.parameters:
                bake_kwargs['as_tangent_normal'] = self.as_tangent_normal
            if 'bake_objects' in sig.parameters:
                bake_kwargs['bake_objects'] = mesh_objects
            active_channel.bake(context, mat, bake_image, self.uv_map_name, **bake_kwargs)
            if self.as_tangent_normal:
                active_channel.bake_vector_space = 'TANGENT'
            else:
                active_channel.bake_vector_space = active_channel.vector_space
            active_channel.use_bake_image = True
        # Return to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
        # Set cursor to default
        context.window.cursor_set('DEFAULT')
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
        ps_ctx = self.parse_context(context)
        
        # Image options
        box = layout.box()
        box.label(text="Image Options", icon='IMAGE_DATA')
        existing_count = sum(1 for ch in ps_ctx.active_group.channels if ch.bake_image)
        if existing_count > 0:
            box.prop(self, "overwrite_image")
            if self.overwrite_image:
                box.label(text=f"Will overwrite {existing_count} existing image(s)", icon='INFO')
        
        self.image_create_ui(layout, context, show_name=False)
        
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
        
        # Multi-object baking option
        box = layout.box()
        box.label(text="Object Selection", icon='OBJECT_DATA')
        box.prop(self, "bake_all_material_objects")
    
    def execute(self, context):
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        
        for channel in active_group.channels:
            mat = ps_ctx.active_material
            bake_image = channel.bake_image
            
            if not bake_image or not self.overwrite_image:
                # Create new image if none exists or overwrite is disabled
                self.image_name = f"{ps_ctx.active_group.name}_{channel.name}"
                bake_image = self.create_image(context)
                bake_image.colorspace_settings.name = 'sRGB'
                channel.bake_image = bake_image
            else:
                # Overwrite existing image - resize if needed
                if bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                    bake_image.scale(self.image_width, self.image_height)
                
            channel.use_bake_image = False
            channel.bake_uv_map = self.uv_map_name
            channel.bake(context, mat, bake_image, self.uv_map_name)
            channel.use_bake_image = True
        # Return to object mode
        bpy.ops.object.mode_set(mode="OBJECT")
        # Set cursor to default
        context.window.cursor_set('DEFAULT')
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


class PAINTSYSTEM_OT_SyncUVMaps(PSContextMixin, Operator):
    """Sync UV map names and settings across all objects using the active material"""
    bl_idname = "paint_system.sync_uv_maps"
    bl_label = "Sync UV Maps"
    bl_description = "Synchronize UV map names and settings across all objects sharing this material"
    bl_options = {'REGISTER', 'UNDO'}
    
    sync_all_material_objects: BoolProperty(
        name="Sync All Objects with Material",
        description="Sync UV on all objects using this material (if disabled, only sync selected objects)",
        default=True
    )
    
    cleanup_mode: bpy.props.EnumProperty(
        name="Cleanup Mode",
        description="How to clean up extra UV maps",
        items=[
            ('NONE', "Keep All UVs", "Don't remove any UV maps"),
            ('NON_PS', "Remove Non-PS UVs", "Remove UVs without PS_ prefix (except active)"),
            ('ALL_NON_ACTIVE', "Remove All Non-Active", "Remove all UVs except the active one"),
        ],
        default='NONE'
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_material and ps_ctx.ps_object
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        
        # Get target UV name to show in UI
        target_uv_name = self._get_target_uv_name(context, ps_ctx)
        
        box = layout.box()
        box.label(text="Sync Settings", icon='UV')
        if target_uv_name:
            box.label(text=f"Target UV: {target_uv_name}", icon='CHECKMARK')
        else:
            box.label(text="No target UV found", icon='ERROR')
        
        box.prop(self, "sync_all_material_objects")
        
        # Show object count
        if ps_ctx.active_material:
            objects_using_mat = self._get_objects_using_material(context, ps_ctx.active_material, self.sync_all_material_objects)
            box.label(text=f"Will sync {len(objects_using_mat)} object(s)")
        
        box = layout.box()
        box.label(text="UV Cleanup", icon='BRUSH_DATA')
        box.prop(self, "cleanup_mode", text="")
        
        if self.cleanup_mode == 'NON_PS':
            box.label(text="Keeps: Active UV + PS_* UVs", icon='INFO')
        elif self.cleanup_mode == 'ALL_NON_ACTIVE':
            box.label(text="Keeps: Active UV only", icon='INFO')
    
    def _get_target_uv_name(self, context, ps_ctx):
        """Determine target UV name based on context"""
        target_uv_name = ''
        
        # Priority: 1) Active layer's UV, 2) Scene transfer UV, 3) Active UV on object
        if ps_ctx.active_layer and hasattr(ps_ctx.active_layer, 'uv_map_name') and ps_ctx.active_layer.uv_map_name:
            target_uv_name = ps_ctx.active_layer.uv_map_name
        
        if not target_uv_name:
            target_uv_name = getattr(context.scene, 'ps_transfer_uv_map', '')
        
        if not target_uv_name and ps_ctx.ps_object and hasattr(ps_ctx.ps_object.data, 'uv_layers'):
            uv_layers = ps_ctx.ps_object.data.uv_layers
            if uv_layers.active:
                target_uv_name = uv_layers.active.name
        
        return target_uv_name
    
    def _get_objects_using_material(self, context, mat, all_objects):
        """Get list of objects using the material"""
        objects_using_mat = []
        
        if all_objects:
            # Check all scenes
            for scene in bpy.data.scenes:
                for obj in scene.objects:
                    if obj.type != 'MESH':
                        continue
                    if not hasattr(obj.data, 'uv_layers'):
                        continue
                    for slot in obj.material_slots:
                        if slot.material and slot.material == mat:
                            objects_using_mat.append(obj)
                            break
        else:
            # Only selected objects
            for obj in context.selected_objects:
                if obj.type != 'MESH':
                    continue
                if not hasattr(obj.data, 'uv_layers'):
                    continue
                for slot in obj.material_slots:
                    if slot.material and slot.material == mat:
                        objects_using_mat.append(obj)
                        break
        
        return objects_using_mat
    
    def _cleanup_uvs(self, obj, active_uv_name, cleanup_mode):
        """Clean up UV maps based on cleanup mode"""
        if cleanup_mode == 'NONE':
            return 0
        
        uv_layers = obj.data.uv_layers
        if len(uv_layers) <= 1:
            return 0  # Nothing to clean up
        
        removed_count = 0
        uvs_to_remove = []
        
        for uv in uv_layers:
            if uv.name == active_uv_name:
                continue  # Never remove active UV
            
            if cleanup_mode == 'NON_PS':
                # Remove if it doesn't start with PS_
                if not uv.name.startswith('PS_'):
                    uvs_to_remove.append(uv)
            elif cleanup_mode == 'ALL_NON_ACTIVE':
                # Remove all except active
                uvs_to_remove.append(uv)
        
        for uv in uvs_to_remove:
            try:
                uv_layers.remove(uv)
                removed_count += 1
            except Exception as e:
                print(f"  [PaintSystem] Failed to remove UV '{uv.name}': {e}")
        
        return removed_count
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        
        if not mat:
            self.report({'ERROR'}, "No active material")
            return {'CANCELLED'}
        
        target_uv_name = self._get_target_uv_name(context, ps_ctx)
        
        if not target_uv_name:
            self.report({'ERROR'}, "No target UV map to sync to. Set a UV map first.")
            return {'CANCELLED'}
        
        # Get objects to sync
        objects_using_mat = self._get_objects_using_material(context, mat, self.sync_all_material_objects)
        
        if not objects_using_mat:
            self.report({'WARNING'}, f"No mesh objects found using material: {mat.name}")
            return {'CANCELLED'}
        
        print(f"[PaintSystem] Syncing UV '{target_uv_name}' across {len(objects_using_mat)} object(s) using material '{mat.name}'")
        
        renamed_count = 0
        already_correct = 0
        skipped_count = 0
        total_cleaned = 0
        synced_objects = []
        
        for obj in objects_using_mat:
            uv_layers = obj.data.uv_layers
            if len(uv_layers) == 0:
                print(f"  [PaintSystem] Skipping {obj.name}: No UV layers")
                skipped_count += 1
                continue
            
            # Get currently active UV to rename, or check if target already exists
            current_active_uv = uv_layers.active
            existing_target = uv_layers.get(target_uv_name)
            
            if not existing_target:
                # Rename current active UV to target name
                if current_active_uv:
                    try:
                        old_name = current_active_uv.name
                        current_active_uv.name = target_uv_name
                        existing_target = uv_layers.get(target_uv_name)
                        print(f"  [PaintSystem] {obj.name}: Renamed '{old_name}' -> '{target_uv_name}'")
                        renamed_count += 1
                    except Exception as e:
                        print(f"  [PaintSystem] {obj.name}: Failed to rename UV: {e}")
                        skipped_count += 1
                        continue
                else:
                    print(f"  [PaintSystem] Skipping {obj.name}: No active UV to rename")
                    skipped_count += 1
                    continue
            else:
                already_correct += 1
            
            # Set as active AND active_render UV
            if existing_target:
                uv_layers.active = existing_target
                existing_target.active_render = True
                synced_objects.append(obj.name)
                print(f"  [PaintSystem] {obj.name}: Set '{target_uv_name}' as active and active_render")
                
                # Clean up extra UVs if requested
                if self.cleanup_mode != 'NONE':
                    cleaned = self._cleanup_uvs(obj, target_uv_name, self.cleanup_mode)
                    if cleaned > 0:
                        total_cleaned += cleaned
                        print(f"  [PaintSystem] {obj.name}: Removed {cleaned} UV map(s)")
        
        print(f"[PaintSystem] Synced objects: {', '.join(synced_objects)}")
        
        # Build result message
        total_synced = renamed_count + already_correct
        msg_parts = [f"Synced UV '{target_uv_name}' on {total_synced} object(s)"]
        
        if renamed_count > 0 or already_correct > 0:
            details = []
            if renamed_count > 0:
                details.append(f"{renamed_count} renamed")
            if already_correct > 0:
                details.append(f"{already_correct} already correct")
            if skipped_count > 0:
                details.append(f"{skipped_count} skipped")
            msg_parts.append(f"({', '.join(details)})")
        
        if total_cleaned > 0:
            msg_parts.append(f"Removed {total_cleaned} extra UV map(s)")
        
        if total_synced > 0:
            self.report({'INFO'}, ' | '.join(msg_parts))
        else:
            self.report({'WARNING'}, f"Could not sync UV on any objects ({skipped_count} skipped)")
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_ClearNonActiveUVs(PSContextMixin, Operator):
    """Clear all UV maps except the active one"""
    bl_idname = "paint_system.clear_non_active_uvs"
    bl_label = "Clear Non-Active UVs"
    bl_description = "Remove all UV maps except the active/render UV on all objects using this material"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_material and ps_ctx.ps_object
    
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        
        if not mat:
            self.report({'ERROR'}, "No active material")
            return {'CANCELLED'}
        
        # Find all objects using this material
        objects_using_mat = []
        for scene in bpy.data.scenes:
            for obj in scene.objects:
                if obj.type not in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}:
                    continue
                for slot in obj.material_slots:
                    if slot.material and slot.material == mat:
                        objects_using_mat.append(obj)
                        break
        
        if not objects_using_mat:
            self.report({'WARNING'}, f"No objects found using material: {mat.name}")
            return {'CANCELLED'}
        
        total_removed = 0
        objects_processed = 0
        
        for obj in objects_using_mat:
            if not hasattr(obj.data, 'uv_layers'):
                continue
            
            uv_layers = obj.data.uv_layers
            if len(uv_layers) <= 1:
                continue  # Nothing to remove
            
            # Get the active render UV (this is what baking uses)
            active_uv = None
            for uv in uv_layers:
                if uv.active_render:
                    active_uv = uv
                    break
            
            # Fallback to regular active if no active_render
            if not active_uv:
                active_uv = uv_layers.active
            
            if not active_uv:
                continue
            
            # Remove all UVs except the active one
            uvs_to_remove = [uv for uv in uv_layers if uv != active_uv]
            
            for uv in uvs_to_remove:
                try:
                    uv_layers.remove(uv)
                    total_removed += 1
                except:
                    pass
            
            if uvs_to_remove:
                objects_processed += 1
        
        if total_removed > 0:
            self.report({'INFO'}, f"Removed {total_removed} UV map(s) from {objects_processed} object(s)")
        else:
            self.report({'INFO'}, "No extra UV maps to remove")
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_SetActiveUVFromLayer(PSContextMixin, Operator):
    """Set Active UV from current layer's UV map"""
    bl_idname = "paint_system.set_active_uv_from_layer"
    bl_label = "Use Layer UV"
    bl_description = "Set Active UV to the UV map used by the current layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_layer and hasattr(ps_ctx.active_layer, 'uv_map_name') and ps_ctx.active_layer.uv_map_name
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        if ps_ctx.active_layer and hasattr(ps_ctx.active_layer, 'uv_map_name'):
            context.scene.ps_active_uv_map = ps_ctx.active_layer.uv_map_name
            self.report({'INFO'}, f"Active UV set to: {ps_ctx.active_layer.uv_map_name}")
        return {'FINISHED'}


class PAINTSYSTEM_OT_TransferImageLayerUVDirect(PSContextMixin, Operator):
    """Transfer UV of image layer without dialog"""
    bl_idname = "paint_system.transfer_uv_direct"
    bl_label = "Transfer UV"
    bl_description = "Transfer the UV of the image layer from Active UV to New UV"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel and ps_ctx.active_layer and ps_ctx.active_layer.type == 'IMAGE' and ps_ctx.active_layer.image

    def execute(self, context):
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        
        if not active_channel or not active_layer:
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        # Get UV mode
        uv_mode = getattr(context.scene, 'ps_uv_transfer_mode', 'USE_EXISTING')
        
        # Handle different UV modes
        if uv_mode == 'AUTO_UV':
            # Perform auto UV unwrap on the object
            if ps_ctx.ps_object and ps_ctx.ps_object.type == 'MESH':
                # Create or get UV map
                uv_layers = ps_ctx.ps_object.data.uv_layers
                if len(uv_layers) == 0:
                    uv_layers.new(name="UVMap")
                target_uv_map = uv_layers.active.name
                
                # Perform smart UV project
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(angle_limit=66.0, island_margin=0.02)
                bpy.ops.object.mode_set(mode='OBJECT')
            else:
                self.report({'ERROR'}, "Auto UV requires a mesh object")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
        elif uv_mode == 'CREATE_NEW':
            # Create a new UV map with the specified name
            target_uv_map = getattr(context.scene, 'ps_transfer_uv_map', '')
            if not target_uv_map:
                target_uv_map = "UVMap_New"
            
            if ps_ctx.ps_object and hasattr(ps_ctx.ps_object.data, 'uv_layers'):
                uv_layers = ps_ctx.ps_object.data.uv_layers
                # Check if it already exists
                if target_uv_map not in uv_layers:
                    new_uv = uv_layers.new(name=target_uv_map)
                    uv_layers.active = new_uv
                else:
                    self.report({'WARNING'}, f"UV map '{target_uv_map}' already exists, using it")
        else:  # USE_EXISTING
            # Get target UV map from scene property
            target_uv_map = getattr(context.scene, 'ps_transfer_uv_map', '')
            if not target_uv_map and ps_ctx.ps_object and hasattr(ps_ctx.ps_object.data, 'uv_layers'):
                uv_layers = ps_ctx.ps_object.data.uv_layers
                if len(uv_layers) > 0:
                    target_uv_map = uv_layers[0].name
            
            if not target_uv_map:
                self.report({'ERROR'}, "No target UV map selected")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
        
        # Get active/source UV map - use active_uv_map if set, otherwise fall back to layer's current UV
        source_uv_map = getattr(context.scene, 'ps_active_uv_map', '')
        if not source_uv_map and hasattr(active_layer, 'uv_map_name') and active_layer.uv_map_name:
            source_uv_map = active_layer.uv_map_name
        elif not source_uv_map:
            # Final fallback to first UV layer
            if ps_ctx.ps_object and hasattr(ps_ctx.ps_object.data, 'uv_layers'):
                uv_layers = ps_ctx.ps_object.data.uv_layers
                if len(uv_layers) > 0:
                    source_uv_map = uv_layers[0].name
        
        if not source_uv_map:
            self.report({'ERROR'}, "No active UV map to bake from")
            context.window.cursor_set('DEFAULT')
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
        orig_is_clip = bool(active_layer.is_clip)
        if active_layer.is_clip:
            active_layer.is_clip = False
        
        # Bake using the target UV map
        active_channel.bake(context, ps_ctx.active_material, transferred_image, target_uv_map, use_group_tree=False, force_alpha=True)
        
        if active_layer.is_clip != orig_is_clip:
            active_layer.is_clip = orig_is_clip
        set_layer_blend_type(active_layer, original_blend_mode)
        active_layer.coord_type = 'UV'
        active_layer.uv_map_name = target_uv_map
        active_layer.image = transferred_image
        # Restore the layers
        for layer in to_be_enabled_layers:
            layer.enabled = True
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        self.report({'INFO'}, f"Transferred from {source_uv_map} to {target_uv_map}")
        return {'FINISHED'}


class PAINTSYSTEM_OT_TransferImageLayerUV(PSContextMixin, PSUVOptionsMixin, Operator):
    bl_idname = "paint_system.transfer_image_layer_uv"
    bl_label = "Transfer Image Layer UV"
    bl_description = "Transfer the UV of the image layer"
    bl_options = {'REGISTER', 'UNDO'}
    
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
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
        # Set cursor to wait
        context.window.cursor_set('WAIT')
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
        return {'FINISHED'}


class PAINTSYSTEM_OT_ConvertToImageLayer(PSContextMixin, PSImageCreateMixin, Operator):
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
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
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
        return {'FINISHED'}


class PAINTSYSTEM_OT_MergeDown(PSContextMixin, PSImageCreateMixin, Operator):
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
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        self.get_coord_type(context)
        below_layer = self.get_below_layer(context)
        if below_layer:
            if below_layer.uses_coord_type:
                if getattr(below_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            else:
                print("Using paint system UV")
                self.uv_map_name = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        if below_layer.type == "IMAGE":
            self.image_width = below_layer.image.size[0]
            self.image_height = below_layer.image.size[1]
            return self.execute(context)
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        return context.window_manager.invoke_props_dialog(self)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        box = layout.box()
        box.alert = True
        col = box.column(align=True)
        col.label(text="This operation will convert the current layer", icon='INFO')
        col.label(text="into an image layer.", icon='BLANK1')
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
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
        active_channel.delete_layers(context, [unlinked_layer, below_unlinked_layer])
        
        active_channel.create_layer(context, "Merged Layer", "IMAGE", coord_type="UV", uv_map_name=self.uv_map_name, image=image)
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        return {'FINISHED'}


class PAINTSYSTEM_OT_MergeUp(PSContextMixin, PSImageCreateMixin, Operator):
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
        above_layer = self.get_above_layer(context)
        # Choose UV based on the layer above
        if above_layer:
            if above_layer.uses_coord_type:
                if getattr(above_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            else:
                self.uv_map_name = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        if above_layer.type == "IMAGE":
            self.image_width = above_layer.image.size[0]
            self.image_height = above_layer.image.size[1]
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self)

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        box = layout.box()
        box.alert = True
        col = box.column(align=True)
        col.label(text="This operation will convert the current layer", icon='INFO')
        col.label(text="into an image layer.", icon='BLANK1')
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")

    def execute(self, context):
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

        # Remove the current layer since it's been merged into the layer above
        active_channel.delete_layers(context, [unlinked_layer, above_unlinked_layer])
        
        active_channel.create_layer(context, "Merged Layer", "IMAGE", coord_type="UV", uv_map_name=self.uv_map_name, image=image)
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_BakeChannel,
    PAINTSYSTEM_OT_BakeAllChannels,
    PAINTSYSTEM_OT_SyncUVMaps,
    PAINTSYSTEM_OT_ClearNonActiveUVs,
    PAINTSYSTEM_OT_SetActiveUVFromLayer,
    PAINTSYSTEM_OT_TransferImageLayerUVDirect,
    PAINTSYSTEM_OT_TransferImageLayerUV,
    PAINTSYSTEM_OT_ExportImage,
    PAINTSYSTEM_OT_ExportAllImages,
    PAINTSYSTEM_OT_DeleteBakedImage,
    PAINTSYSTEM_OT_ConvertToImageLayer,
    PAINTSYSTEM_OT_MergeDown,
    PAINTSYSTEM_OT_MergeUp,
)

register, unregister = register_classes_factory(classes)