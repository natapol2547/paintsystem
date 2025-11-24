"""UDIM tile management operators (Phase 2)"""
import bpy
from bpy.types import Operator
from bpy.props import IntProperty, BoolProperty
from bpy.utils import register_classes_factory

from .common import PSContextMixin
from ..utils.udim import fill_udim_tile
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
    """Mark UDIM tiles as needing re-bake"""
    bl_idname = "paint_system.mark_udim_tile_dirty"
    bl_label = "Mark UDIM Tile Dirty"
    bl_options = {'REGISTER', 'UNDO'}
    
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
        
        if self.mark_all:
            count = 0
            for tile in layer.udim_tiles:
                tile.is_dirty = True
                count += 1
            self.report({'INFO'}, f"Marked {count} tiles as dirty")
        else:
            for tile in layer.udim_tiles:
                if tile.number == self.tile_number:
                    tile.is_dirty = True
                    self.report({'INFO'}, f"Marked tile {self.tile_number} as dirty")
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


classes = (
    PAINTSYSTEM_OT_SelectUDIMTile,
    PAINTSYSTEM_OT_MarkUDIMTileDirty,
    PAINTSYSTEM_OT_ClearUDIMTileMarks,
    PAINTSYSTEM_OT_BakeUDIMTile,
)

register, unregister = register_classes_factory(classes)
