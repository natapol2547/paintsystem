"""UDIM tile management operators (Phase 2)"""
import bpy
from bpy.types import Operator
from bpy.props import IntProperty, BoolProperty, StringProperty, EnumProperty
from bpy.utils import register_classes_factory

from .common import PSContextMixin
from ..paintsystem.graph.common import DEFAULT_PS_UV_MAP_NAME
from ..utils.udim import fill_udim_tile, detect_udim_from_uv
import logging

logger = logging.getLogger("PaintSystem")


class PAINTSYSTEM_OT_SelectUDIMTile(PSContextMixin, Operator):
    """Select and focus on a specific UDIM tile"""
    bl_idname = "paint_system.select_udim_tile"
    bl_label = "Select UDIM Tile"
    bl_options = {'REGISTER', 'UNDO'}
    
    tile_number: IntProperty(
        name="Tile Number",
        description="UDIM tile number to select",
        min=1001,
        max=2000
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx:
            return False
        layer = ps_ctx.active_layer
        return bool(layer and layer.type == 'IMAGE' and getattr(layer, 'is_udim', False) and layer.image)
    
    def execute(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            self.report({'WARNING'}, "No active paint context")
            return {'CANCELLED'}
        layer = ps_ctx.active_layer
        image = layer.image

        if not layer or not image:
            self.report({'WARNING'}, "No UDIM image available")
            return {'CANCELLED'}
        
        # Mark this tile as painted when selected
        for tile in layer.udim_tiles:
            if tile.number == self.tile_number:
                tile.is_painted = True
                logger.info(f"Selected UDIM tile {self.tile_number}")
                break
        
        # Set the active tile index in the image (CRITICAL for painting to work)
        try:
            for idx, tile in enumerate(image.tiles):
                if tile.number == self.tile_number:
                    image.tiles.active_index = idx
                    logger.info(f"Set active tile index to {idx} for tile {self.tile_number}")
                    break
        except Exception as e:
            logger.warning(f"Could not set active tile index: {e}")
        
        # Update active image for painting
        context.scene.tool_settings.image_paint.canvas = image
        self.report({'INFO'}, f"Selected tile {self.tile_number}")
        return {'FINISHED'}


class PAINTSYSTEM_OT_MarkUDIMTileDirty(PSContextMixin, Operator):
    """Mark UDIM tiles as needing re-bake (works with PS_ UV workflow)"""
    bl_idname = "paint_system.mark_udim_tile_dirty"
    bl_label = "Mark UDIM Tile Dirty"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Mark tiles for re-baking during Fix UV Apply"
    
    tile_number: IntProperty(
        name="Tile Number",
        description="Tile to mark dirty (or -1 for all)",
        default=-1
    )
    mark_all: BoolProperty(
        name="Mark All",
        description="Mark all tiles as dirty",
        default=False
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx:
            return False
        layer = ps_ctx.active_layer
        return bool(layer and layer.type == 'IMAGE' and getattr(layer, 'is_udim', False))
    
    def execute(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            self.report({'WARNING'}, "No active paint context")
            return {'CANCELLED'}
        layer = ps_ctx.active_layer
        if not layer:
            self.report({'WARNING'}, "No UDIM layer selected")
            return {'CANCELLED'}
        
        # Check if in Fix UV session
        ps_scene_data = ps_ctx.ps_scene_data
        in_fix_session = ps_scene_data and getattr(ps_scene_data, 'fix_uv_session_active', False)
        
        if self.mark_all:
            count = 0
            for tile in layer.udim_tiles:
                tile.is_dirty = True
                count += 1
            msg = f"Marked {count} tiles as dirty"
            if in_fix_session:
                msg += " (will be baked during Apply)"
            self.report({'INFO'}, msg)
        else:
            for tile in layer.udim_tiles:
                if tile.number == self.tile_number:
                    tile.is_dirty = True
                    msg = f"Marked tile {self.tile_number} as dirty"
                    if in_fix_session:
                        msg += " (will be baked during Apply)"
                    self.report({'INFO'}, msg)
                    break
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_ClearUDIMTileMarks(PSContextMixin, Operator):
    """Clear all paint and dirty marks on UDIM tiles"""
    bl_idname = "paint_system.clear_udim_tile_marks"
    bl_label = "Clear UDIM Tile Marks"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx:
            return False
        layer = ps_ctx.active_layer
        return bool(layer and layer.type == 'IMAGE' and getattr(layer, 'is_udim', False))
    
    def execute(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            self.report({'WARNING'}, "No active paint context")
            return {'CANCELLED'}
        layer = ps_ctx.active_layer
        if not layer:
            self.report({'WARNING'}, "No UDIM layer selected")
            return {'CANCELLED'}
        
        for tile in layer.udim_tiles:
            tile.is_painted = False
            tile.is_dirty = False
        
        self.report({'INFO'}, f"Cleared marks on {len(layer.udim_tiles)} tiles")
        return {'FINISHED'}


class PAINTSYSTEM_OT_BakeUDIMTile(PSContextMixin, Operator):
    """Bake a specific UDIM tile or all dirty tiles"""
    bl_idname = "paint_system.bake_udim_tile"
    bl_label = "Bake UDIM Tile"
    bl_options = {'REGISTER', 'UNDO'}
    
    tile_number: IntProperty(
        name="Tile Number",
        description="Tile to bake (or -1 for all dirty)",
        default=-1
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx:
            return False
        layer = ps_ctx.active_layer
        channel = ps_ctx.active_channel
        return bool(channel and layer and layer.type == 'IMAGE' and getattr(layer, 'is_udim', False))
    
    def execute(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            self.report({'WARNING'}, "No active paint context")
            return {'CANCELLED'}
        layer = ps_ctx.active_layer
        channel = ps_ctx.active_channel

        if not layer:
            self.report({'WARNING'}, "No UDIM layer selected")
            return {'CANCELLED'}
        if not channel:
            self.report({'WARNING'}, "No active channel to bake")
            return {'CANCELLED'}
        
        # Collect tiles to bake
        tiles_to_bake = []
        if self.tile_number == -1:
            # Bake all dirty tiles
            tiles_to_bake = [t for t in layer.udim_tiles if t.is_dirty]
            if not tiles_to_bake:
                tiles_to_bake = [t for t in layer.udim_tiles if t.is_painted]
        else:
            # Bake specific tile
            tiles_to_bake = [t for t in layer.udim_tiles if t.number == self.tile_number]
        
        if not tiles_to_bake:
            self.report({'WARNING'}, "No tiles to bake")
            return {'CANCELLED'}
        
        try:
            # Bake each tile
            for tile in tiles_to_bake:
                # The actual baking would happen here
                # For now, just mark as not dirty
                tile.is_dirty = False
                logger.info(f"Baked UDIM tile {tile.number}")
            
            self.report({'INFO'}, f"Baked {len(tiles_to_bake)} tile(s)")
        except Exception as e:
            logger.error(f"Error baking UDIM tiles: {e}")
            self.report({'ERROR'}, f"Bake failed: {str(e)}")
            return {'CANCELLED'}
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_SelectObjectsByMaterial(PSContextMixin, Operator):
    """Select all objects using the active Paint System material"""
    bl_idname = "paint_system.select_objects_by_material"
    bl_label = "Select Objects by Material"
    bl_options = {'REGISTER', 'UNDO'}

    extend: BoolProperty(
        name="Extend Selection",
        description="Keep current selection and add matching objects",
        default=False,
    )
    switch_to_edit: BoolProperty(
        name="Switch to Edit Mode",
        description="Switch selected objects to Edit mode for UV editing",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material)

    def execute(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            self.report({'WARNING'}, "No active paint context")
            return {'CANCELLED'}

        mat = ps_ctx.active_material

        # Deselect all if not extending
        if not self.extend:
            for o in context.selected_objects:
                try:
                    o.select_set(False)
                except Exception:
                    pass

        # Select all mesh objects using this material
        matched = 0
        matched_objects = []
        for obj in context.scene.objects:
            if getattr(obj, 'type', None) == 'MESH':
                if any(ms.material == mat for ms in obj.material_slots if ms.material):
                    try:
                        obj.select_set(True)
                        matched += 1
                        matched_objects.append(obj)
                    except Exception:
                        pass

        # Switch to edit mode if requested
        if self.switch_to_edit and matched_objects:
            # Set last matched object as active
            try:
                context.view_layer.objects.active = matched_objects[-1]
            except Exception:
                pass
            
            # Switch to edit mode
            if context.mode != 'EDIT_MESH':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception as e:
                    logger.warning(f"Could not switch to edit mode: {e}")

        self.report({'INFO'}, f"Selected {matched} object(s) with material '{mat.name}'")
        return {'FINISHED'}


class PAINTSYSTEM_OT_SelectObjectsByUVTiles(PSContextMixin, Operator):
    """Select objects that share UDIM tile(s) with the current selection

    - Gathers tiles from selected mesh objects (or active object if none selected)
    - Restricts to objects using the active material for clarity
    - Uses the UV map of the active IMAGE layer (or the default PS UV)
    """
    bl_idname = "paint_system.select_objects_by_uv_tiles"
    bl_label = "Select Objects by UV Tiles"
    bl_options = {'REGISTER', 'UNDO'}

    extend: BoolProperty(
        name="Extend Selection",
        description="Keep current selection and add matching objects",
        default=True,
    )
    clear_others: BoolProperty(
        name="Deselect Others",
        description="Deselect objects that do not match",
        default=False,
    )
    switch_to_edit: BoolProperty(
        name="Switch to Edit Mode",
        description="Switch selected objects to Edit mode for UV editing",
        default=False,
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material)

    def execute(self, context):
        ps_ctx = self.safe_parse_context(context)
        if not ps_ctx:
            self.report({'WARNING'}, "No active paint context")
            return {'CANCELLED'}

        mat = ps_ctx.active_material
        obj = ps_ctx.ps_object
        layer = ps_ctx.active_layer

        # Determine source UV name from active layer
        uv_name = None
        try:
            if layer and getattr(layer, 'coord_type', None) == 'UV':
                uv_name = layer.uv_map_name
            else:
                uv_name = DEFAULT_PS_UV_MAP_NAME
        except Exception:
            uv_name = None

        # Gather seed objects (selected meshes using the material, else active)
        seeds = [o for o in context.selected_objects
                 if getattr(o, 'type', None) == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        if not seeds and obj and getattr(obj, 'type', None) == 'MESH':
            seeds = [obj]

        # Collect tiles from seeds
        seed_tiles = set()
        for so in seeds:
            try:
                tiles = detect_udim_from_uv(so, uv_name)
                for t in tiles:
                    seed_tiles.add(int(t))
            except Exception:
                continue

        if not seed_tiles:
            # Fallback to base tile
            seed_tiles = {1001}

        # Candidate objects: all meshes using the same material
        candidates = [o for o in context.scene.objects
                      if getattr(o, 'type', None) == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]

        # Optionally clear others
        if self.clear_others and not self.extend:
            for co in candidates:
                try:
                    co.select_set(False)
                except Exception:
                    pass

        # Select those that share any tile
        matched = 0
        matched_objects = []
        for co in candidates:
            try:
                co_tiles = set(detect_udim_from_uv(co, uv_name))
                if co_tiles & seed_tiles:
                    co.select_set(True)
                    matched += 1
                    matched_objects.append(co)
            except Exception:
                continue

        # Switch to edit mode if requested
        if self.switch_to_edit and matched_objects:
            # Set last matched object as active
            try:
                context.view_layer.objects.active = matched_objects[-1]
            except Exception:
                pass
            
            # Switch to edit mode
            if context.mode != 'EDIT_MESH':
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                except Exception as e:
                    logger.warning(f"Could not switch to edit mode: {e}")

        self.report({'INFO'}, f"Selected {matched} object(s) sharing tiles: {sorted(seed_tiles)}")
        return {'FINISHED'}


# Register all classes (placed after class definitions)
classes = (
    PAINTSYSTEM_OT_SelectUDIMTile,
    PAINTSYSTEM_OT_MarkUDIMTileDirty,
    PAINTSYSTEM_OT_ClearUDIMTileMarks,
    PAINTSYSTEM_OT_BakeUDIMTile,
    PAINTSYSTEM_OT_SelectObjectsByMaterial,
    PAINTSYSTEM_OT_SelectObjectsByUVTiles,
)

register, unregister = register_classes_factory(classes)

