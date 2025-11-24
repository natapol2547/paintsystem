# Paint System UDIM Implementation Plan

## Overview
Add UDIM (UV tile) support to Paint System while maintaining backward compatibility with existing projects.

## Phase 1: Core UDIM Infrastructure

### 1.1 Create UDIM Utility Module (`paintsystem/udim_utils.py`)
```python
# Core utilities:
- is_udim_supported() -> bool  # Check Blender version
- get_tile_numbers(obj, uv_name) -> list[int]  # Scan UV coords
- is_uvmap_udim(obj, uv_name) -> bool  # Detect if UVs use multiple tiles
- fill_tile(image, tilenum, color, width, height)  # Create/fill tiles
- initial_pack_udim(image, base_color)  # Setup UDIM image
- swap_tiles(image, swap_dict)  # Tile management
- get_udim_filepath(filename, directory) -> str  # Generate <UDIM> paths
```

### 1.2 Layer Property Extensions
```python
# Add to Layer class (data.py):
use_udim: BoolProperty(
    name="Use UDIM",
    description="Enable UDIM tile support for this layer",
    default=False
)

udim_base_color: FloatVectorProperty(
    name="UDIM Base Color",
    subtype='COLOR',
    size=4,
    default=(0, 0, 0, 0)
)
```

### 1.3 Image Creation with UDIM
```python
# Modify create_layer() in Channel class:
if layer_type == "IMAGE":
    # Detect if UV map uses UDIM
    is_udim = is_uvmap_udim(context.object, uv_map_name)
    
    if is_udim:
        # Create tiled image
        image = bpy.data.images.new(
            name=layer_name,
            width=2048, height=2048,
            alpha=True,
            tiled=True  # Enable UDIM
        )
        
        # Auto-detect and fill tiles based on UV islands
        tilenums = get_tile_numbers(context.object, uv_map_name)
        for tilenum in tilenums:
            fill_tile(image, tilenum, (0,0,0,0), 2048, 2048)
        
        # Setup filepath with <UDIM> token
        initial_pack_udim(image, base_color=(0,0,0,0))
    else:
        # Standard single-tile image
        image = bpy.data.images.new(...)
```

## Phase 2: UI Integration

### 2.1 Layer Panel UDIM Indicators
```python
# In layers_panels.py draw_layer_icon():
if layer.type == 'IMAGE' and layer.image:
    if layer.image.source == 'TILED':
        # Show UDIM badge icon
        row.label(text="", icon='UV')  # or custom UDIM icon
```

### 2.2 UDIM Settings in Layer Properties
```python
# Add to layer settings UI:
if layer.type == 'IMAGE':
    if layer.image and layer.image.source == 'TILED':
        box = layout.box()
        box.label(text="UDIM Tiles", icon='UV')
        
        # Show active tiles
        for tile in layer.image.tiles:
            row = box.row()
            row.label(text=f"Tile {tile.number}")
            row.operator("paint_system.remove_udim_tile").tile_number = tile.number
        
        # Auto-refill based on UV
        box.operator("paint_system.refill_udim_tiles", icon='FILE_REFRESH')
```

### 2.3 New Image Layer Dialog
```python
# In PAINTSYSTEM_OT_NewImageLayer:
def draw(self, context):
    layout = self.layout
    
    # Existing options...
    
    # UDIM detection
    obj = context.object
    if obj and obj.type == 'MESH':
        uv_layer = obj.data.uv_layers.active
        if uv_layer:
            is_udim = is_uvmap_udim([obj], uv_layer.name)
            if is_udim:
                box = layout.box()
                box.alert = True
                box.label(text="UDIM tiles detected in UV map", icon='INFO')
                box.prop(self, "create_udim", text="Create as UDIM Image")
```

## Phase 3: Operators

### 3.1 Refill UDIM Tiles
```python
class PAINTSYSTEM_OT_RefillUDIMTiles(Operator):
    """Refill UDIM tiles based on current UV islands"""
    bl_idname = "paint_system.refill_udim_tiles"
    bl_label = "Refill UDIM Tiles"
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        
        if not layer or layer.type != 'IMAGE':
            return {'CANCELLED'}
        
        image = layer.image
        if image.source != 'TILED':
            return {'CANCELLED'}
        
        # Get tiles from UV
        uv_name = layer.uv_map_name or "UVMap"
        tilenums = get_tile_numbers(context.object, uv_name)
        
        # Fill missing tiles
        for tilenum in tilenums:
            fill_tile(image, tilenum, layer.udim_base_color, 
                     image.size[0], image.size[1], empty_only=True)
        
        initial_pack_udim(image)
        return {'FINISHED'}
```

### 3.2 Convert to UDIM
```python
class PAINTSYSTEM_OT_ConvertToUDIM(Operator):
    """Convert existing single-tile image layer to UDIM"""
    bl_idname = "paint_system.convert_to_udim"
    bl_label = "Convert to UDIM"
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        
        old_image = layer.image
        if old_image.source == 'TILED':
            self.report({'INFO'}, "Already a UDIM image")
            return {'CANCELLED'}
        
        # Create new UDIM image
        new_image = bpy.data.images.new(
            old_image.name + "_UDIM",
            width=old_image.size[0],
            height=old_image.size[1],
            alpha=True,
            tiled=True
        )
        
        # Detect tiles from UV
        uv_name = layer.uv_map_name or "UVMap"
        tilenums = get_tile_numbers(context.object, uv_name)
        
        for tilenum in tilenums:
            fill_tile(new_image, tilenum, (0,0,0,0), 
                     old_image.size[0], old_image.size[1])
        
        # Copy pixels from 1001 tile
        tile_1001 = new_image.tiles.get(1001)
        if tile_1001:
            new_image.tiles.active = tile_1001
            new_image.pixels = list(old_image.pixels)
        
        initial_pack_udim(new_image)
        
        # Replace in layer
        layer.image = new_image
        layer.update_node_tree(context)
        
        return {'FINISHED'}
```

### 3.3 Remove UDIM Tile
```python
class PAINTSYSTEM_OT_RemoveUDIMTile(Operator):
    """Remove specific UDIM tile"""
    bl_idname = "paint_system.remove_udim_tile"
    bl_label = "Remove UDIM Tile"
    
    tile_number: IntProperty()
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        
        if not layer or not layer.image:
            return {'CANCELLED'}
        
        image = layer.image
        tile = image.tiles.get(self.tile_number)
        if tile and tile.number != 1001:  # Don't remove base tile
            image.tiles.remove(tile)
        
        return {'FINISHED'}
```

## Phase 4: Baking with UDIM

### 4.1 Channel Baking Extensions
```python
# In Channel.bake():
if self.bake_image and self.bake_image.source == 'TILED':
    # Bake each tile separately
    for tile in self.bake_image.tiles:
        # Set active tile
        self.bake_image.tiles.active = tile
        
        # Standard bake process but per-tile
        bpy.ops.object.bake(
            type='EMIT',
            use_clear=False,
            # ... other settings
        )
```

## Phase 5: Advanced Features (Optional)

### 5.1 UDIM Atlas System
- Implement Ucupaint's atlas concept for better memory management
- Pack multiple UDIM ranges into single image with Y-offset
- Useful for projects with many scattered tiles

### 5.2 Tile Management Tools
- Swap tile positions
- Copy tiles between images
- Batch tile operations
- Tile usage visualization

### 5.3 Smart Tile Detection
- Auto-detect when user paints outside 0-1 UV space
- Prompt to create new tiles on-demand
- Warn about missing tiles

## Implementation Strategy

### Priority Order:
1. **Phase 1** (Core) - Essential for basic UDIM support
2. **Phase 2** (UI) - Makes UDIM discoverable and usable
3. **Phase 3** (Operators) - User-facing functionality
4. **Phase 4** (Baking) - Critical for production workflow
5. **Phase 5** (Advanced) - Nice-to-have optimization

### Backward Compatibility:
- Existing projects with single-tile images: ✅ No changes
- New layers: Auto-detect UDIM from UV, user can override
- Migration: Optional "Convert to UDIM" operator
- File format: No changes to .blend structure

### Testing Checklist:
- [ ] Create UDIM layer from UV with multiple tiles
- [ ] Paint across multiple tiles
- [ ] Bake UDIM channel
- [ ] Convert single-tile to UDIM
- [ ] Refill tiles after UV changes
- [ ] Save/load project with UDIM images
- [ ] Pack/unpack UDIM images
- [ ] Export UDIM textures

## Benefits for Paint System Users

1. **Professional Workflow**: Industry-standard UDIM support
2. **High-Resolution Textures**: Paint on massive surfaces without memory issues
3. **Automatic Management**: Auto-detect tiles from UV layout
4. **Non-Breaking**: Existing projects continue working
5. **Blender Native**: Uses Blender's built-in UDIM system (3.3+)

## Technical Notes

- Requires Blender 3.3+ for `tiled=True` in image creation
- UDIM images use `<UDIM>` token in filepath (e.g., `texture.<UDIM>.png`)
- Individual tiles saved as `texture.1001.png`, `texture.1002.png`, etc.
- Tile numbering: 1001-1010 (first row), 1011-1020 (second row), etc.
- NumPy used for efficient UV coordinate analysis
- File I/O permission required in manifest (already present)
