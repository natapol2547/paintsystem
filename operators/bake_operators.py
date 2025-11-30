import bpy
import inspect
from bpy.types import Operator
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty, FloatProperty

from .common import PSContextMixin, PSImageCreateMixin, PSUVOptionsMixin, DEFAULT_PS_UV_MAP_NAME

from ..paintsystem.data import set_layer_blend_type, get_layer_blend_type, _sync_uv_map_to_name
from ..panels.common import get_icon_from_channel


class BakeOperator(PSContextMixin, PSImageCreateMixin, PSUVOptionsMixin, Operator):
    """Bake the active channel"""
    bl_options = {'REGISTER', 'UNDO'}
    multi_object: BoolProperty(
        name="All Material Users",
        description="Include all mesh objects using the active material (shared UV space) in the bake",
        default=False,
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

    show_advanced: BoolProperty(
        name="Advanced Settings",
        description="Show additional bake settings",
        default=False,
        options={'SKIP_SAVE'}
    )

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
        
        # Bake mode selection
        layout.prop(self, "as_layer", text="Bake as New Layer")
        layout.separator()
        
        self.image_create_ui(layout, context)

        # UV Map selector (always visible)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        if ps_ctx.ps_object and ps_ctx.ps_object.data and hasattr(ps_ctx.ps_object.data, "uv_layers"):
            box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
            if self.multi_object and self.uv_map_name:
                row = box.row()
                row.operator("paint_system.sync_uv_for_bake", text="Sync UV to All Objects").uv_map_name = self.uv_map_name
        else:
            box.label(text="No UV layers available", icon='ERROR')

        # Advanced settings toggle
        adv_box = layout.box()
        row = adv_box.row()
        row.prop(self, "show_advanced", icon='TRIA_DOWN' if self.show_advanced else 'TRIA_RIGHT', emboss=False)
        
        # Advanced settings content
        if self.show_advanced:
            # Tangent space normal option when applicable
            if ps_ctx.active_channel.type == "VECTOR":
                tangent_box = adv_box.box()
                tangent_box.prop(self, "as_tangent_normal")

            adv_box.prop(self, "multi_object")
        else:
            # Minimal essentials always visible
            if ps_ctx.active_channel.type == "VECTOR":
                tangent_box = layout.box()
                tangent_box.prop(self, "as_tangent_normal")
            layout.prop(self, "multi_object")

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

        # Sync UV map on all material users if multi-object baking
        if self.multi_object and mat:
            mat_users = [o for o in context.scene.objects 
                        if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
            for o in mat_users:
                if o.data.uv_layers and self.uv_map_name not in o.data.uv_layers:
                    _sync_uv_map_to_name(o, self.uv_map_name)

        # Build bake image name: "MaterialName_ChannelName"
        mat_name = mat.name if mat else "Material"
        channel_name = active_channel.name
        self.image_name = f"{mat_name}_{channel_name}"

        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)

        bake_image = None
        if self.as_layer:
            bake_image = self.create_image(context)
            bake_image.colorspace_settings.name = 'sRGB'
            sig = inspect.signature(active_channel.bake)
            bake_kwargs = {}
            if 'force_alpha' in sig.parameters:
                bake_kwargs['force_alpha'] = True
            if 'as_tangent_normal' in sig.parameters:
                bake_kwargs['as_tangent_normal'] = self.as_tangent_normal
            if 'multi_object' in sig.parameters:
                bake_kwargs['multi_object'] = self.multi_object
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
            if not bake_image:
                bake_image = self.create_image(context)
                bake_image.colorspace_settings.name = 'sRGB'
                active_channel.bake_image = bake_image
            elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                bake_image.scale(self.image_width, self.image_height)
            active_channel.bake_uv_map = self.uv_map_name

            active_channel.use_bake_image = False
            sig = inspect.signature(active_channel.bake)
            bake_kwargs = {}
            if 'as_tangent_normal' in sig.parameters:
                bake_kwargs['as_tangent_normal'] = self.as_tangent_normal
            if 'multi_object' in sig.parameters:
                bake_kwargs['multi_object'] = self.multi_object
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
        self.image_create_ui(layout, context, show_name=False)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
        if self.multi_object and self.uv_map_name:
            row = box.row()
            row.operator("paint_system.sync_uv_for_bake", text="Sync UV to All Objects").uv_map_name = self.uv_map_name
        layout.prop(self, "multi_object")
    
    def execute(self, context):
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        
        # Sync UV map on all material users if multi-object baking
        if self.multi_object:
            mat = ps_ctx.active_material
            if mat:
                mat_users = [o for o in context.scene.objects 
                            if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                for o in mat_users:
                    if o.data.uv_layers and self.uv_map_name not in o.data.uv_layers:
                        _sync_uv_map_to_name(o, self.uv_map_name)
        
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        
        for channel in active_group.channels:
            mat = ps_ctx.active_material
            bake_image = channel.bake_image
            
            if not bake_image:
                self.image_name = f"{ps_ctx.active_group.name}_{channel.name}"
                bake_image = self.create_image(context)
                bake_image.colorspace_settings.name = 'sRGB'
                channel.bake_image = bake_image
            elif bake_image.size[0] != self.image_width or bake_image.size[1] != self.image_height:
                bake_image.scale(self.image_width, self.image_height)
                
            channel.use_bake_image = False
            channel.bake_uv_map = self.uv_map_name
            sig = inspect.signature(channel.bake)
            if 'multi_object' in sig.parameters:
                channel.bake(context, mat, bake_image, self.uv_map_name, multi_object=self.multi_object)
            else:
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
            self.report({'ERROR'}, "No active channel found.")
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


class PAINTSYSTEM_OT_ConvertToImageLayer(PSContextMixin, PSImageCreateMixin, Operator):
    bl_idname = "paint_system.transfer_image_layer_uv"
    bl_label = "Bake to Different UV Layout"
    bl_description = "Re-bake this layer's texture using a different UV map layout"
    bl_options = {'REGISTER', 'UNDO'}

    # UV Target Mode
    uv_target_mode: EnumProperty(
        name="UV Target Mode",
        description="How to target the UV map",
        items=[
            ('NEW', "Create New UV", "Create a new UV map with auto unwrap"),
            ('EXISTING', "Use Existing UV", "Select an existing UV map to bake into"),
        ],
        default='EXISTING',
        options={'SKIP_SAVE'}
    )
    
    # Bake scope
    bake_all_layers: BoolProperty(
        name="Bake All Layers with Current UV",
        description="Bake all IMAGE layers that use the current UV layout (unchecked = only active layer)",
        default=True,
        options={'SKIP_SAVE'}
    )
    
    # Object scope
    all_material_users: BoolProperty(
        name="Bake All Objects",
        description="Include all mesh objects using the active material",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    # UDIM options
    bake_selected_tiles_only: BoolProperty(
        name="Bake Selected UDIM Tiles Only",
        description="Only bake tiles you've marked as dirty (all UVs will be updated, only selected tiles baked)",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    # Auto UV options (when NEW mode selected)
    smart_project_angle: FloatProperty(
        name="Angle Limit",
        description="Angle limit for smart UV project",
        default=66.0,
        min=1.0,
        max=89.0,
        subtype='ANGLE',
        options={'SKIP_SAVE'}
    )
    smart_project_margin: FloatProperty(
        name="Island Margin",
        description="Margin between UV islands",
        default=0.0,
        min=0.0,
        max=1.0,
        options={'SKIP_SAVE'}
    )
    
    # UI
    show_advanced: BoolProperty(
        name="Advanced Options",
        default=False,
        options={'SKIP_SAVE'}
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_channel and ps_ctx.active_layer.type == 'IMAGE' and ps_ctx.active_layer.image

    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.ps_object
        active_layer = ps_ctx.active_layer
        
        # Auto-detect UV mode: if PS_ UVs exist, default to EXISTING
        if obj and obj.type == 'MESH' and obj.data.uv_layers:
            ps_uvs = [uv.name for uv in obj.data.uv_layers if uv.name.startswith("PS_")]
            if ps_uvs:
                self.uv_target_mode = 'EXISTING'
                self.uv_map_name = ps_uvs[-1]  # Most recent PS_ UV
            else:
                self.uv_target_mode = 'NEW'
                # Generate new UV name
                from ..utils import get_next_unique_name
                existing_names = [uv.name for uv in obj.data.uv_layers]
                self.uv_map_name = get_next_unique_name("PS_UVMap", existing_names)
        
        return context.window_manager.invoke_props_dialog(self, width=450)

    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        obj = ps_ctx.ps_object

        # Info banner
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Re-bake layer texture to a different UV layout", icon='INFO')

        # Current layer info
        if active_layer and active_layer.image:
            box = layout.box()
            box.label(text="Current Layer", icon='IMAGE_DATA')
            row = box.row()
            row.label(text=f"  Texture: {active_layer.image.name}")
            
            # Show current UV
            if active_layer.uv_map_name:
                row = box.row()
                row.label(text=f"  Current UV: {active_layer.uv_map_name}")
            
            # Show UDIM info
            try:
                from ..utils.udim import is_udim_image, get_udim_tiles_from_image
                if is_udim_image(active_layer.image):
                    tiles = get_udim_tiles_from_image(active_layer.image)
                    row = box.row()
                    row.label(text=f"  UDIM: {len(tiles)} tiles", icon='UV')
            except Exception:
                pass

        # Target UV Mode Selection
        box = layout.box()
        box.label(text="Target UV Layout", icon='UV')
        row = box.row(align=True)
        row.prop(self, "uv_target_mode", expand=True)
        
        # UV selector (changes based on mode)
        if self.uv_target_mode == 'EXISTING':
            if obj and obj.type == 'MESH' and obj.data.uv_layers:
                box.prop_search(self, "uv_map_name", obj.data, "uv_layers", text="UV Map")
            else:
                box.label(text="No UV maps available", icon='ERROR')
        else:  # NEW
            box.prop(self, "uv_map_name", text="New UV Name")
            # Smart UV options
            col = box.column(align=True)
            col.prop(self, "smart_project_angle")
            col.prop(self, "smart_project_margin")

        # Bake scope
        box = layout.box()
        box.label(text="Bake Scope", icon='RENDER_RESULT')
        box.prop(self, "bake_all_layers")
        
        # Advanced options
        box = layout.box()
        row = box.row()
        row.prop(self, "show_advanced", icon='TRIA_DOWN' if self.show_advanced else 'TRIA_RIGHT', emboss=False)
        
        if self.show_advanced:
            col = box.column(align=True)
            col.prop(self, "all_material_users")
            
            # Show UDIM tile selection if applicable
            try:
                from ..utils.udim import is_udim_image
                if active_layer and active_layer.image and is_udim_image(active_layer.image):
                    col.separator()
                    col.prop(self, "bake_selected_tiles_only")
            except Exception:
                pass
            
            # Material users preview
            if self.all_material_users:
                mat = ps_ctx.active_material
                if mat:
                    mat_users = [o for o in context.scene.objects if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                    if len(mat_users) > 1:
                        sub_box = box.box()
                        sub_box.label(text=f"Material Users ({len(mat_users)} objects)", icon='MATERIAL')
                        col = sub_box.column(align=True)
                        for user_obj in mat_users[:3]:
                            col.label(text=f"  • {user_obj.name}", icon='OBJECT_DATA')
                        if len(mat_users) > 3:
                            col.label(text=f"  • ... {len(mat_users) - 3} more", icon='BLANK1')



    def execute(self, context):
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        obj = ps_ctx.ps_object
        
        if not active_channel or not active_layer:
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}

        # Determine target objects
        targets = self._get_target_objects(context, ps_ctx)
        if not targets:
            self.report({'ERROR'}, "No mesh objects found")
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}

        # Step 1: Create/Select target UV on all objects
        if self.uv_target_mode == 'NEW':
            # Create new UV with smart unwrap
            for target_obj in targets:
                if target_obj.type != 'MESH':
                    continue
                    
                # Create UV map
                uvs = target_obj.data.uv_layers
                if self.uv_map_name in uvs:
                    # Already exists, skip or warn
                    continue
                    
                uv_layer = uvs.new(name=self.uv_map_name)
                uvs.active = uv_layer
                
                # Perform smart unwrap
                bpy.ops.object.mode_set(mode='EDIT')
                bpy.ops.mesh.select_all(action='SELECT')
                bpy.ops.uv.smart_project(
                    angle_limit=self.smart_project_angle,
                    island_margin=self.smart_project_margin
                )
                bpy.ops.object.mode_set(mode='OBJECT')
        else:
            # EXISTING mode - just verify UV exists
            for target_obj in targets:
                if target_obj.type != 'MESH':
                    continue
                uvs = target_obj.data.uv_layers
                if self.uv_map_name not in uvs:
                    self.report({'WARNING'}, f"{target_obj.name}: UV '{self.uv_map_name}' not found")
                    continue
                uvs.active = uvs[self.uv_map_name]

        # Step 2: Determine which layers to bake
        layers_to_bake = []
        if self.bake_all_layers:
            # Find all IMAGE layers using same UV as active layer
            current_uv = active_layer.uv_map_name if hasattr(active_layer, 'uv_map_name') else None
            for layer in active_channel.layers:
                if layer.type == 'IMAGE' and layer.image:
                    layer_uv = layer.uv_map_name if hasattr(layer, 'uv_map_name') else None
                    if layer_uv == current_uv:
                        layers_to_bake.append(layer)
        else:
            # Just active layer
            layers_to_bake = [active_layer]

        # Step 3: Bake each layer
        baked_count = 0
        for layer in layers_to_bake:
            if layer.type != 'IMAGE' or not layer.image:
                continue
                
            # Check if UDIM
            try:
                from ..utils.udim import is_udim_image, get_udim_tiles_from_image
                is_udim = is_udim_image(layer.image)
            except Exception:
                is_udim = False

            if is_udim:
                # UDIM bake path
                success = self._bake_layer_udim(context, ps_ctx, layer, targets)
            else:
                # Regular bake path
                success = self._bake_layer_regular(context, ps_ctx, layer, targets)
                
            if success:
                baked_count += 1

        context.window.cursor_set('DEFAULT')
        self.report({'INFO'}, f"Baked {baked_count} layer(s) to UV '{self.uv_map_name}'")
        return {'FINISHED'}

    def _get_target_objects(self, context, ps_ctx):
        """Get list of target objects based on all_material_users setting"""
        mat = ps_ctx.active_material
        if self.all_material_users and mat:
            return [o for o in context.scene.objects 
                   if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        return [ps_ctx.ps_object] if ps_ctx.ps_object and ps_ctx.ps_object.type == 'MESH' else []

    def _bake_layer_regular(self, context, ps_ctx, layer, targets):
        """Bake a regular (non-UDIM) layer to new UV"""
        active_channel = ps_ctx.active_channel
        
        # Create new image for baked result
        new_image = bpy.data.images.new(
            name=f"{layer.image.name}_Rebaked",
            width=layer.image.size[0],
            height=layer.image.size[1],
            alpha=True
        )
        new_image.colorspace_settings.name = 'sRGB'

        # Temporarily disable other layers
        to_be_enabled_layers = []
        for other_layer in active_channel.layers:
            if other_layer.enabled and other_layer != layer:
                to_be_enabled_layers.append(other_layer)
                other_layer.enabled = False

        # Save layer state
        original_blend_mode = get_layer_blend_type(layer)
        set_layer_blend_type(layer, 'MIX')
        orig_is_clip = bool(layer.is_clip)
        if layer.is_clip:
            layer.is_clip = False

        # Bake
        try:
            import inspect as _inspect
            sig = _inspect.signature(active_channel.bake)
            if 'multi_object' in sig.parameters:
                active_channel.bake(context, ps_ctx.active_material, new_image, self.uv_map_name, 
                                   use_group_tree=False, force_alpha=True, multi_object=self.all_material_users)
            else:
                active_channel.bake(context, ps_ctx.active_material, new_image, self.uv_map_name,
                                   use_group_tree=False, force_alpha=True)
        except Exception as e:
            self.report({'WARNING'}, f"Bake failed for {layer.image.name}: {str(e)}")
            return False

        # Restore layer state
        if layer.is_clip != orig_is_clip:
            layer.is_clip = orig_is_clip
        set_layer_blend_type(layer, original_blend_mode)
        
        # Update layer to use new image and UV
        layer.coord_type = 'UV'
        layer.uv_map_name = self.uv_map_name
        layer.image = new_image
        
        # Re-enable other layers
        for other_layer in to_be_enabled_layers:
            other_layer.enabled = True

        return True

    def _bake_layer_udim(self, context, ps_ctx, layer, targets):
        """Bake a UDIM layer to new UV, with optional tile selection"""
        from ..utils.udim import get_udim_tiles_from_image, create_udim_image, copy_udim_tile_to_udim_tile
        
        active_channel = ps_ctx.active_channel
        
        # Get tiles to bake
        source_tiles = get_udim_tiles_from_image(layer.image)
        if self.bake_selected_tiles_only:
            # Only bake tiles marked as dirty
            tiles_to_bake = [t for t in source_tiles if layer.get_tile(t) and layer.get_tile(t).is_dirty]
            if not tiles_to_bake:
                self.report({'WARNING'}, f"No dirty tiles to bake for {layer.image.name}")
                return False
        else:
            tiles_to_bake = source_tiles

        # Create new UDIM image
        new_image = create_udim_image(
            name=f"{layer.image.name}_Rebaked",
            tiles=source_tiles,  # Create all tiles, even if not baking all
            width=layer.image.size[0],
            height=layer.image.size[1],
            alpha=True
        )

        # Temporarily disable other layers
        to_be_enabled_layers = []
        for other_layer in active_channel.layers:
            if other_layer.enabled and other_layer != layer:
                to_be_enabled_layers.append(other_layer)
                other_layer.enabled = False

        # Save layer state
        original_blend_mode = get_layer_blend_type(layer)
        set_layer_blend_type(layer, 'MIX')
        orig_is_clip = bool(layer.is_clip)
        if layer.is_clip:
            layer.is_clip = False

        # Bake each tile
        for tile_num in tiles_to_bake:
            try:
                # Bake to the tile in new UDIM image
                # Note: Channel.bake handles UDIM automatically
                import inspect as _inspect
                sig = _inspect.signature(active_channel.bake)
                if 'multi_object' in sig.parameters:
                    active_channel.bake(context, ps_ctx.active_material, new_image, self.uv_map_name,
                                       use_group_tree=False, force_alpha=True, multi_object=self.all_material_users)
                else:
                    active_channel.bake(context, ps_ctx.active_material, new_image, self.uv_map_name,
                                       use_group_tree=False, force_alpha=True)
                break  # Full UDIM bake happens in one call
            except Exception as e:
                self.report({'WARNING'}, f"Bake failed for {layer.image.name}: {str(e)}")
                return False

        # Copy un-baked tiles from source
        if self.bake_selected_tiles_only:
            for tile_num in source_tiles:
                if tile_num not in tiles_to_bake:
                    try:
                        copy_udim_tile_to_udim_tile(layer.image, tile_num, new_image)
                    except Exception:
                        pass

        # Restore layer state
        if layer.is_clip != orig_is_clip:
            layer.is_clip = orig_is_clip
        set_layer_blend_type(layer, original_blend_mode)
        
        # Update layer to use new image and UV
        layer.coord_type = 'UV'
        layer.uv_map_name = self.uv_map_name
        layer.image = new_image
        
        # Re-enable other layers
class PAINTSYSTEM_OT_ConvertToImageLayer(PSContextMixin, PSImageCreateMixin, Operator):
    bl_idname = "paint_system.convert_to_image_layer"
    bl_label = "Transfer Image Layer UV"
    bl_description = "Transfer the UV of the image layer"
    bl_options = {'REGISTER', 'UNDO'}
    multi_object: BoolProperty(
        name="All Material Users",
        description="Include all mesh objects using the active material (shared UV space) in the bake",
        default=False,
        options={'SKIP_SAVE'}
    )
    
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
        layout.prop(self, "multi_object")

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
        active_channel.bake(
            context,
            ps_ctx.active_material,
            image,
            self.uv_map_name,
            use_group_tree=False,
            force_alpha=True,
            multi_object=self.multi_object,
        )
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
    multi_object: BoolProperty(
        name="All Material Users",
        description="Include all mesh objects using the active material (shared UV space) in the bake",
        default=True,
        options={'SKIP_SAVE'}
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
        ps_ctx = self.parse_context(context)
        
        # Validate UV map exists on the object
        ps_object = ps_ctx.ps_object
        if ps_object and ps_object.data and ps_object.data.uv_layers:
            if self.uv_map_name and self.uv_map_name not in ps_object.data.uv_layers:
                # Stored UV no longer exists, fall back to active UV
                active_uv = ps_object.data.uv_layers.active
                self.uv_map_name = active_uv.name if active_uv else (ps_object.data.uv_layers[0].name if ps_object.data.uv_layers else "")
        
        if below_layer:
            if below_layer.uses_coord_type:
                if getattr(below_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            else:
                print("Using paint system UV")
                self.uv_map_name = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        
        # Check if we have a valid UV map before auto-executing
        has_valid_uv = False
        if ps_object and ps_object.data and ps_object.data.uv_layers:
            has_valid_uv = bool(self.uv_map_name and self.uv_map_name in ps_object.data.uv_layers)
        
        if below_layer.type == "IMAGE" and has_valid_uv:
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
        if self.multi_object and self.uv_map_name:
            row = box.row()
            row.operator("paint_system.sync_uv_for_bake", text="Sync UV to All Objects").uv_map_name = self.uv_map_name
        layout.prop(self, "multi_object")

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
        
        # Sync UV map on all material users if multi-object merging
        if self.multi_object:
            mat = ps_ctx.active_material
            if mat:
                mat_users = [o for o in context.scene.objects 
                            if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                for o in mat_users:
                    if o.data.uv_layers and self.uv_map_name not in o.data.uv_layers:
                        _sync_uv_map_to_name(o, self.uv_map_name)
        
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
        active_channel.bake(
            context,
            ps_ctx.active_material,
            image,
            self.uv_map_name,
            use_group_tree=False,
            force_alpha=True,
            multi_object=self.multi_object,
        )
        
        # Restore original blend modes
        set_layer_blend_type(active_layer, original_active_blend_mode)
        set_layer_blend_type(below_layer, original_below_blend_mode)
        
        # Restore other layers
        for layer in to_be_enabled_layers:
            layer.enabled = True
        
        # Update the below layer with the merged result and delete the active layer
        below_layer.type = 'IMAGE'
        below_layer.image = image
        below_layer.coord_type = 'UV'
        below_layer.uv_map_name = self.uv_map_name
        
        # Delete only the active layer (merged into below)
        active_channel.delete_layers(context, [unlinked_layer])
        
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        return {'FINISHED'}


class PAINTSYSTEM_OT_MergeUp(PSContextMixin, PSImageCreateMixin, Operator):
    bl_idname = "paint_system.merge_up"
    bl_label = "Merge Up"
    bl_description = "Merge the layer into the one above"
    bl_options = {'REGISTER', 'UNDO'}
    multi_object: BoolProperty(
        name="All Material Users",
        description="Include all mesh objects using the active material (shared UV space) in the bake",
        default=True,
        options={'SKIP_SAVE'}
    )

    def get_above_layer(self, context, unprocessed: bool = False):
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        if not active_channel:
            return None
        active_layer = ps_ctx.unlinked_layer if unprocessed else ps_ctx.active_layer
        flattened_layers = active_channel.flattened_unlinked_layers if unprocessed else active_channel.flattened_layers
        if active_layer and flattened_layers.index(active_layer) > 0:
            return flattened_layers[flattened_layers.index(active_layer) - 1]
        return None

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if not ps_ctx.active_channel:
            return False
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
        ps_ctx = self.parse_context(context)
        
        # Validate UV map exists on the object
        ps_object = ps_ctx.ps_object
        if ps_object and ps_object.data and ps_object.data.uv_layers:
            if self.uv_map_name and self.uv_map_name not in ps_object.data.uv_layers:
                # Stored UV no longer exists, fall back to active UV
                active_uv = ps_object.data.uv_layers.active
                self.uv_map_name = active_uv.name if active_uv else (ps_object.data.uv_layers[0].name if ps_object.data.uv_layers else "")
        
        # Choose UV based on the layer above
        if above_layer:
            if above_layer.uses_coord_type:
                if getattr(above_layer, 'coord_type', 'UV') == 'AUTO':
                    self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            else:
                self.uv_map_name = DEFAULT_PS_UV_MAP_NAME if self.use_paint_system_uv else self.uv_map_name
        
        # Check if we have a valid UV map before auto-executing
        has_valid_uv = False
        if ps_object and ps_object.data and ps_object.data.uv_layers:
            has_valid_uv = bool(self.uv_map_name and self.uv_map_name in ps_object.data.uv_layers)
        
        if above_layer.type == "IMAGE" and has_valid_uv:
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
        if self.multi_object and self.uv_map_name:
            row = box.row()
            row.operator("paint_system.sync_uv_for_bake", text="Sync UV to All Objects").uv_map_name = self.uv_map_name
        layout.prop(self, "multi_object")

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

        # Sync UV map on all material users if multi-object merging
        if self.multi_object:
            mat = ps_ctx.active_material
            if mat:
                mat_users = [o for o in context.scene.objects 
                            if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                for o in mat_users:
                    if o.data.uv_layers and self.uv_map_name not in o.data.uv_layers:
                        _sync_uv_map_to_name(o, self.uv_map_name)

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
        active_channel.bake(
            context,
            ps_ctx.active_material,
            image,
            self.uv_map_name,
            use_group_tree=False,
            force_alpha=True,
            multi_object=self.multi_object,
        )

        # Restore original blend modes
        set_layer_blend_type(active_layer, original_active_blend_mode)
        set_layer_blend_type(above_layer, original_above_blend_mode)

        # Restore other layers
        for layer in to_be_enabled_layers:
            layer.enabled = True

        # Update the above layer with the merged result and delete the active layer
        above_layer.type = 'IMAGE'
        above_layer.image = image
        above_layer.coord_type = 'UV'
        above_layer.uv_map_name = self.uv_map_name
        
        # Delete only the active layer (merged into above)
        active_channel.delete_layers(context, [unlinked_layer])
        
        # Set cursor back to default
        context.window.cursor_set('DEFAULT')
        return {'FINISHED'}


class PAINTSYSTEM_OT_SyncUVForBake(PSContextMixin, Operator):
    bl_idname = "paint_system.sync_uv_for_bake"
    bl_label = "Sync UV for Bake"
    bl_description = "Ensure the selected UV map exists on all material users"
    bl_options = {'REGISTER', 'UNDO'}

    uv_map_name: StringProperty(
        name="UV Map Name",
        options={'SKIP_SAVE'}
    )

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        if not mat or not self.uv_map_name:
            return {'CANCELLED'}

        mat_users = [o for o in context.scene.objects 
                    if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        synced_count = 0
        activated_count = 0
        for o in mat_users:
            if o.data.uv_layers:
                had_uv = self.uv_map_name in o.data.uv_layers
                _sync_uv_map_to_name(o, self.uv_map_name)
                if not had_uv:
                    synced_count += 1
                else:
                    activated_count += 1

        if synced_count > 0 and activated_count > 0:
            self.report({'INFO'}, f"Synced UV '{self.uv_map_name}' to {synced_count} objects, activated on {activated_count} objects")
        elif synced_count > 0:
            self.report({'INFO'}, f"Synced UV '{self.uv_map_name}' to {synced_count} objects")
        elif activated_count > 0:
            self.report({'INFO'}, f"Activated UV '{self.uv_map_name}' on {activated_count} objects")
        else:
            self.report({'INFO'}, f"UV '{self.uv_map_name}' already active on all objects")
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_BakeChannel,
    PAINTSYSTEM_OT_BakeAllChannels,
    PAINTSYSTEM_OT_ExportImage,
    PAINTSYSTEM_OT_ExportAllImages,
    PAINTSYSTEM_OT_DeleteBakedImage,
    PAINTSYSTEM_OT_ConvertToImageLayer,
    PAINTSYSTEM_OT_MergeDown,
    PAINTSYSTEM_OT_MergeUp,
    PAINTSYSTEM_OT_SyncUVForBake,
)

register, unregister = register_classes_factory(classes)