import bpy
import inspect
from bpy.types import Operator
from bpy.utils import register_classes_factory
from bpy.props import StringProperty, BoolProperty, IntProperty, EnumProperty

from .common import PSContextMixin, PSImageCreateMixin, PSUVOptionsMixin, DEFAULT_PS_UV_MAP_NAME

from ..paintsystem.data import set_layer_blend_type, get_layer_blend_type
from ..panels.common import get_icon_from_channel


class BakeOperator(PSContextMixin, PSImageCreateMixin, Operator):
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
        self.image_create_ui(layout, context)
        box = layout.box()
        box.label(text="UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
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
        layout.prop(self, "multi_object")
    
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


class PAINTSYSTEM_OT_TransferImageLayerUV(PSContextMixin, PSUVOptionsMixin, Operator):
    bl_idname = "paint_system.transfer_image_layer_uv"
    bl_label = "Bake to Different UV Layout"
    bl_description = "Re-bake this layer's texture using a different UV map layout"
    bl_options = {'REGISTER', 'UNDO'}

    bake_single_tile: BoolProperty(
        name="Single UDIM Tile",
        description="Bake only one UDIM tile to a new image while targeting the selected UV map",
        default=False,
        options={'SKIP_SAVE'}
    )
    tile_number: IntProperty(
        name="Tile Number",
        description="UDIM tile number to bake (1001 = first tile)",
        default=1001,
        min=1001,
        max=2000,
        options={'SKIP_SAVE'}
    )
    normalize_tile_uv: BoolProperty(
        name="Normalize Tile UVs",
        description="Remap tile UVs into 0-1 space (recommended)",
        default=True,
        options={'SKIP_SAVE'}
    )
    multi_object: BoolProperty(
        name="All Material Users",
        description="Include all mesh objects using the active material (shared UV space) in the bake",
        default=False,
        options={'SKIP_SAVE'}
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
        active_layer = ps_ctx.active_layer

        box = layout.box()
        col = box.column(align=True)
        col.label(text="This will re-bake the layer texture to a", icon='INFO')
        col.label(text="different UV map layout.", icon='BLANK1')

        if active_layer and active_layer.image:
            box = layout.box()
            box.label(text="Current Layer", icon='IMAGE_DATA')
            row = box.row()
            row.label(text=f"  Texture: {active_layer.image.name}")
            try:
                from ..utils.udim import is_udim_image, get_udim_tiles_from_image
                if is_udim_image(active_layer.image):
                    tiles = get_udim_tiles_from_image(active_layer.image)
                    row = box.row()
                    row.label(text=f"  UDIM: {len(tiles)} tiles", icon='UV')
            except Exception:
                pass

        # Target UV selection
        box = layout.box()
        box.label(text="Select Target UV Map", icon='UV')
        box.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="UV Map")

        # Optional single-tile bake
        try:
            from ..utils.udim import is_udim_image, get_udim_tiles_from_image
            if active_layer.image and is_udim_image(active_layer.image):
                tile_box = layout.box()
                tile_box.label(text="Optional: Bake Single UDIM Tile", icon='UV')
                tile_box.prop(self, "bake_single_tile")
                if self.bake_single_tile:
                    row = tile_box.row(align=True)
                    row.prop(self, "tile_number")
                    row.prop(self, "normalize_tile_uv")
                    tile_box.prop(self, "multi_object")
                    tiles = get_udim_tiles_from_image(active_layer.image)
                    if tiles:
                        prev = ', '.join(str(t) for t in tiles[:12])
                        tile_box.label(text=f"Available: {prev}{'...' if len(tiles) > 12 else ''}")
        except Exception:
            pass

        # Material users preview
        mat = ps_ctx.active_material
        if mat:
            mat_users = [o for o in context.scene.objects if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
            if len(mat_users) > 1:
                box = layout.box()
                box.label(text=f"Shared Material ({len(mat_users)} objects)", icon='MATERIAL')
                col = box.column(align=True)
                for obj in mat_users[:3]:
                    col.label(text=f"  • {obj.name}", icon='OBJECT_DATA')
                if len(mat_users) > 3:
                    col.label(text=f"  • ... {len(mat_users) - 3} more", icon='BLANK1')

    # Helpers
    def _get_targets(self, context, ps_ctx):
        mat = ps_ctx.active_material
        if self.multi_object and mat:
            return [o for o in context.scene.objects if o and o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        return [ps_ctx.ps_object] if ps_ctx.ps_object and ps_ctx.ps_object.type == 'MESH' else []

    def _ensure_uv_map(self, obj: bpy.types.Object, target_uv: str, source_uv: str | None = None):
        uvs = obj.data.uv_layers
        if target_uv in uvs.keys():
            return uvs[target_uv]
        layer = uvs.new(name=target_uv)
        if source_uv and source_uv in uvs.keys():
            src = uvs[source_uv]
            for i, loop in enumerate(src.data):
                layer.data[i].uv = loop.uv
        return layer

    def _dedupe_uvs(self, obj: bpy.types.Object, name: str):
        uvs = obj.data.uv_layers
        seen = False
        for layer in list(uvs):
            if layer.name == name:
                if not seen:
                    seen = True
                else:
                    try:
                        uvs.remove(layer)
                    except Exception:
                        pass

    def _make_temp_tile_uv(self, obj: bpy.types.Object, src_uv: str, tgt_uv: str, tile_number: int, normalize: bool = True) -> str:
        uvs = obj.data.uv_layers
        temp_name = "PS_TEMP_TILE"
        if temp_name in uvs.keys():
            try:
                uvs.remove(uvs[temp_name])
            except Exception:
                pass
        temp = uvs.new(name=temp_name)
        src = uvs[src_uv]
        tgt = uvs[tgt_uv]
        u_index = (tile_number - 1001) % 10
        v_index = (tile_number - 1001) // 10
        face_in_tile = [True] * len(obj.data.polygons)
        for poly in obj.data.polygons:
            inside = True
            for li in poly.loop_indices:
                suv = src.data[li].uv
                if int(suv.x) != u_index or int(suv.y) != v_index:
                    inside = False
                    break
            face_in_tile[poly.index] = inside
        for poly in obj.data.polygons:
            for li in poly.loop_indices:
                if face_in_tile[poly.index]:
                    tuv = tgt.data[li].uv
                    temp.data[li].uv = (tuv.x - u_index, tuv.y - v_index) if normalize else tuv
                else:
                    temp.data[li].uv = (2.5, 2.5)
        return temp_name

    def _cleanup_temp_uv(self, obj: bpy.types.Object, temp_name: str):
        uvs = obj.data.uv_layers
        if temp_name in uvs.keys():
            try:
                uvs.remove(uvs[temp_name])
            except Exception:
                pass

    def execute(self, context):
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        active_channel = ps_ctx.active_channel
        active_layer = ps_ctx.active_layer
        if not active_channel:
            return {'CANCELLED'}

        # Single UDIM tile bake path (non-destructive UV sync)
        if self.bake_single_tile:
            try:
                from ..utils.udim import is_udim_image
            except Exception:
                is_udim_image = lambda img: False
            img = active_layer.image
            if not (img and is_udim_image(img)):
                self.report({'ERROR'}, "Active layer image is not UDIM.")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}

            targets = self._get_targets(context, ps_ctx)
            if not targets:
                self.report({'ERROR'}, "No mesh targets found.")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}

            # Ensure target UV exists and dedupe on each target
            for obj in targets:
                if not obj or obj.type != 'MESH' or not obj.data:
                    continue
                uvs = obj.data.uv_layers
                src_uv = uvs.active.name if uvs.active else (list(uvs)[0].name if len(uvs) else None)
                self._ensure_uv_map(obj, self.uv_map_name, src_uv)
                self._dedupe_uvs(obj, self.uv_map_name)

            # Build temp masked UV per object (mask by source active UV's tile membership)
            temp_name = "PS_TEMP_TILE"
            built = []
            for obj in targets:
                uvs = obj.data.uv_layers
                # Prefer the layer's current UV (source) if available; fallback to object's active
                src_name = None
                try:
                    if getattr(active_layer, 'coord_type', 'UV') == 'UV' and getattr(active_layer, 'uv_map_name', '') in uvs.keys():
                        src_name = active_layer.uv_map_name
                except Exception:
                    src_name = None
                if not src_name:
                    src_name = uvs.active.name if uvs.active else (list(uvs)[0].name if len(uvs) else self.uv_map_name)
                if self.uv_map_name not in uvs.keys():
                    self._ensure_uv_map(obj, self.uv_map_name, src_name)
                self._make_temp_tile_uv(obj, src_name, self.uv_map_name, self.tile_number, self.normalize_tile_uv)
                built.append(obj)

            # Create target image and bake using temp UV name
            tile_image = bpy.data.images.new(name=f"{img.name}_Tile{self.tile_number}", width=img.size[0], height=img.size[1], alpha=True)
            tile_image.colorspace_settings.name = 'sRGB'

            to_be_enabled_layers = []
            for layer in active_channel.layers:
                if layer.enabled and layer != active_layer:
                    to_be_enabled_layers.append(layer)
                    layer.enabled = False
            original_blend_mode = get_layer_blend_type(active_layer)
            set_layer_blend_type(active_layer, 'MIX')
            orig_is_clip = bool(active_layer.is_clip)
            if active_layer.is_clip:
                active_layer.is_clip = False

            try:
                import inspect as _inspect
                sig = _inspect.signature(active_channel.bake)
                if 'multi_object' in sig.parameters:
                    active_channel.bake(context, ps_ctx.active_material, tile_image, temp_name, use_group_tree=False, force_alpha=True, multi_object=self.multi_object)
                else:
                    active_channel.bake(context, ps_ctx.active_material, tile_image, temp_name, use_group_tree=False, force_alpha=True)
            except Exception:
                active_channel.bake(context, ps_ctx.active_material, tile_image, temp_name, use_group_tree=False, force_alpha=True)

            if active_layer.is_clip != orig_is_clip:
                active_layer.is_clip = orig_is_clip
            set_layer_blend_type(active_layer, original_blend_mode)
            for layer in to_be_enabled_layers:
                layer.enabled = True

            # Cleanup temp UVs
            for obj in built:
                self._cleanup_temp_uv(obj, temp_name)

            # Build/replace into a proper UDIM image and assign
            try:
                from ..utils.udim import (
                    is_udim_image,
                    get_udim_tiles_from_image,
                    create_udim_image,
                    copy_image_to_udim_tile,
                    copy_udim_tile_to_udim_tile,
                )
            except Exception:
                is_udim_image = lambda img: False
                get_udim_tiles_from_image = lambda img: []
                create_udim_image = None
                copy_image_to_udim_tile = None
                copy_udim_tile_to_udim_tile = None

            tiles = []
            src_is_udim = bool(img and is_udim_image(img))
            if src_is_udim:
                try:
                    tiles = get_udim_tiles_from_image(img)
                except Exception:
                    tiles = []
            if not tiles:
                tiles = [self.tile_number]
            if self.tile_number not in tiles:
                tiles.append(self.tile_number)
            tiles = sorted(set(tiles))

            udim_image = None
            if create_udim_image:
                udim_name = f"{img.name}_UDIM"
                udim_image = create_udim_image(udim_name, tiles, width=img.size[0], height=img.size[1], alpha=True)

            if udim_image and copy_image_to_udim_tile:
                # If source was UDIM, preserve other tiles by copying from source
                if src_is_udim and copy_udim_tile_to_udim_tile:
                    for t in tiles:
                        if t == self.tile_number:
                            continue
                        try:
                            copy_udim_tile_to_udim_tile(img, t, udim_image)
                        except Exception:
                            pass
                # Replace baked tile
                try:
                    copy_image_to_udim_tile(udim_image, self.tile_number, tile_image)
                except Exception:
                    pass
                # Assign UDIM image to layer
                active_layer.coord_type = 'UV'
                active_layer.uv_map_name = self.uv_map_name
                active_layer.image = udim_image
            else:
                # Fallback: assign the baked single image
                active_layer.coord_type = 'UV'
                active_layer.uv_map_name = self.uv_map_name
                active_layer.image = tile_image
            context.window.cursor_set('DEFAULT')
            self.report({'INFO'}, f"Baked tile {self.tile_number} to {'UDIM' if udim_image else 'image'} using UV '{self.uv_map_name}'.")
            return {'FINISHED'}

        # Full bake (ensure target UV exists across targets and bake once)
        targets = self._get_targets(context, ps_ctx)
        for obj in targets:
            if not obj or obj.type != 'MESH' or not obj.data:
                continue
            uvs = obj.data.uv_layers
            src_uv = uvs.active.name if uvs.active else (list(uvs)[0].name if len(uvs) else None)
            if src_uv:
                self._ensure_uv_map(obj, self.uv_map_name, src_uv)
                self._dedupe_uvs(obj, self.uv_map_name)

        transferred_image = bpy.data.images.new(name=f"{active_layer.image.name}_Transferred", width=active_layer.image.size[0], height=active_layer.image.size[1], alpha=True)

        to_be_enabled_layers = []
        for layer in active_channel.layers:
            if layer.enabled and layer != active_layer:
                to_be_enabled_layers.append(layer)
                layer.enabled = False

        original_blend_mode = get_layer_blend_type(active_layer)
        set_layer_blend_type(active_layer, 'MIX')
        orig_is_clip = bool(active_layer.is_clip)
        if active_layer.is_clip:
            active_layer.is_clip = False

        try:
            import inspect as _inspect
            sig = _inspect.signature(active_channel.bake)
            if 'multi_object' in sig.parameters:
                active_channel.bake(context, ps_ctx.active_material, transferred_image, self.uv_map_name, use_group_tree=False, force_alpha=True, multi_object=self.multi_object)
            else:
                active_channel.bake(context, ps_ctx.active_material, transferred_image, self.uv_map_name, use_group_tree=False, force_alpha=True)
        except Exception:
            active_channel.bake(context, ps_ctx.active_material, transferred_image, self.uv_map_name, use_group_tree=False, force_alpha=True)

        if active_layer.is_clip != orig_is_clip:
            active_layer.is_clip = orig_is_clip
        set_layer_blend_type(active_layer, original_blend_mode)
        active_layer.coord_type = 'UV'
        active_layer.uv_map_name = self.uv_map_name
        active_layer.image = transferred_image
        for layer in to_be_enabled_layers:
            layer.enabled = True
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
    PAINTSYSTEM_OT_TransferImageLayerUV,
    PAINTSYSTEM_OT_ExportImage,
    PAINTSYSTEM_OT_ExportAllImages,
    PAINTSYSTEM_OT_DeleteBakedImage,
    PAINTSYSTEM_OT_ConvertToImageLayer,
    PAINTSYSTEM_OT_MergeDown,
    PAINTSYSTEM_OT_MergeUp,
)

register, unregister = register_classes_factory(classes)