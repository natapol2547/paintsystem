# UDIM Support Implementation

## Overview
Paint System now supports UDIM (UV tile) workflows with automatic detection and beginner-friendly workflows.

## Phase 1: Foundation (COMPLETED)

### Data Model
**Location**: `paintsystem/data.py`

Added UDIM support to the Layer class:
```python
class UDIMTile(PropertyGroup):
    number: IntProperty(min=1001, max=2000)  # UDIM tile number
    is_painted: BoolProperty(default=False)   # Has user painted on this tile
    is_dirty: BoolProperty(default=False)     # Needs re-baking

class Layer(PropertyGroup):
    is_udim: BoolProperty(default=False)
    udim_tiles: CollectionProperty(type=UDIMTile)
```

### Utility Functions
**Location**: `utils/udim.py`

9 comprehensive utility functions for UDIM management:

1. **detect_udim_from_uv(obj)** - Scans UV coordinates with NumPy to find tiles
   - Returns sorted list of tile numbers (e.g., [1001, 1002, 1003])
   - Fast: Uses array operations instead of per-vertex loops

2. **is_udim_image(image)** - Checks if image is UDIM
   - Detects `<UDIM>` token in filepath
   - Checks for tiled source

3. **get_udim_tiles_from_image(image)** - Lists tile numbers from UDIM image
   - Returns list of integer tile numbers

4. **create_udim_image(name, tiles, width, height, alpha=True)** - Creates UDIM image
   - Uses Blender 2.82+ tiled image API
   - Automatically generates tiles for specified list
   - Returns image or None on failure

5. **fill_udim_tile(image, tile_number, color)** - Fills specific tile with color
   - Converts tile number (1001) to tile index (0)
   - Direct pixel manipulation for performance

6. **get_udim_filepath_for_tile(filepath, tile_number)** - Converts `<UDIM>` to specific tile
   - Example: `texture.<UDIM>.png` → `texture.1001.png`

7. **suggest_udim_for_object(obj)** - Returns True if object has multi-tile UVs
   - Quick check: calls detect_udim_from_uv and checks for >1 tile

8. **get_udim_info_string(layer)** - Generates user-friendly display text
   - Example: `"UDIM (3 tiles: 1001, 1002, 1003)"`
   - Handles edge cases (no tiles, many tiles with "...")

9. **update_layer_udim_status(layer, image)** - Syncs layer UDIM state with image
   - Populates udim_tiles collection from image
   - Sets is_udim flag

### UI Integration
**Location**: `panels/layers_panels.py`

Added UDIM badge in layer list:
```python
if layer.is_udim:
    from ..utils.udim import get_udim_info_string
    info_str = get_udim_info_string(layer)
    row = layout.row(align=True)
    row.label(text="", icon='UV')
    row.label(text=info_str)
```

Displays UV icon and tile count next to UDIM layers.

### Operator Integration
**Location**: `operators/common.py`, `operators/layers_operators.py`

#### PSImageCreateMixin Enhancements
Added UDIM properties:
```python
use_udim: BoolProperty(name="Use UDIM", default=False)
udim_auto_detect: BoolProperty(name="Auto-detect UDIM", default=True)
```

**Auto-detection UI**: When creating image layers, automatically detects UDIM tiles and shows:
```
┌─────────────────────────────────────────┐
│ ℹ UDIM tiles detected: 1001, 1002, 1003│
│   Create multi-tile UDIM image?        │
│   [✓] Create UDIM Image                │
└─────────────────────────────────────────┘
```

**create_image() method**: Now accepts context parameter and creates UDIM when:
- `use_udim=True` 
- Context has valid object with multi-tile UVs
- Automatically populates tiles from UV layout

#### Layer Creation Flow
1. User clicks "New Image Layer"
2. Operator detects UV layout with `suggest_udim_for_object()`
3. If multi-tile detected, shows UDIM option UI
4. User toggles "Create UDIM Image" (defaults to detected state)
5. Creates UDIM image with detected tiles
6. Layer properties automatically populated with tile info

### Bake Operator Updates
**Location**: `operators/bake_operators.py`

All `create_image()` calls updated to pass `context` parameter:
- `PAINTSYSTEM_OT_BakeChannel`
- `PAINTSYSTEM_OT_BakeAllChannels`
- `PAINTSYSTEM_OT_BakeNormalMap`
- `PAINTSYSTEM_OT_BakeCurvatureMap`
- `PAINTSYSTEM_OT_BakeAmbientOcclusion`

Enables UDIM support in baking workflows.

## User Experience

### For Beginners
- **Invisible complexity**: UDIM detection happens automatically
- **Clear prompts**: Simple Yes/No choice when tiles detected
- **Visual feedback**: UDIM badge shows tile count in layer list
- **No manual setup**: Tiles auto-populated from UV layout

### For Advanced Users
- **Manual control**: Toggle UDIM option even without auto-detection
- **Tile management**: Layer stores per-tile state (painted, dirty)
- **Future-ready**: Foundation for Phase 2 auto-management features

## Technical Details

### UDIM Tile Numbering
- Standard UDIM range: 1001-2000
- Tile 1001 = UV grid (0,0) to (1,1)
- Tile 1002 = UV grid (1,0) to (2,1)
- And so on...

### UV Coordinate Detection
Uses NumPy for efficient array operations:
```python
uv_data = np.array([(uv.x, uv.y) for uv in mesh.uv_layers.active.data])
tile_u = np.floor(uv_data[:, 0]).astype(int)
tile_v = np.floor(uv_data[:, 1]).astype(int)
tiles = np.unique(1001 + tile_v * 10 + tile_u)
```

### Image Creation
Uses Blender 2.82+ tiled image API:
```python
img = bpy.data.images.new(name, width, height, tiled=True)
for tile_num in tiles:
    img.tiles.new(tile_num)
```

## Testing Checklist

- [x] UDIM properties added to Layer class
- [x] Utility functions implemented with NumPy
- [x] UI badge displays for UDIM layers
- [x] Image creation detects multi-tile UVs
- [x] Create UDIM option shown when tiles detected
- [x] Layer udim_tiles collection populated on creation
- [ ] Test with actual UDIM objects (requires Blender runtime)
- [ ] Test with single-tile objects (should not show UDIM option)
- [ ] Test with imported UDIM images
- [ ] Test baking with UDIM layers

## Next Steps: Phase 2 (Auto-Management)

Planned features:
1. **Auto-tile creation**: Automatically create missing tiles when user paints
2. **Smart packing**: Suggest when to use UDIM vs single texture
3. **Tile baking**: Per-tile bake with parallel processing
4. **Tile cleanup**: Remove unused tiles to optimize memory

## Next Steps: Phase 3 (Advanced Features)

Planned features:
1. **Multi-object UDIM**: Share UDIM across multiple objects
2. **UDIM templates**: Pre-configured setups for characters, environments
3. **Tile preview**: Visual grid showing which tiles exist
4. **Import/Export**: Handle external UDIM texture sets

## Known Limitations

- Requires Blender 2.82+ for tiled image API
- NumPy dependency (already bundled in wheels/)
- UV layout must be pre-configured before layer creation
- Tile detection scans all UV coordinates (may be slow for high-poly meshes)

## Performance Considerations

- **UV scanning**: O(n) where n = vertex count, but uses NumPy arrays
- **Tile population**: O(t) where t = tile count (typically <10)
- **Image creation**: Blender API handles tile generation efficiently
- **Badge rendering**: Only renders when layer visible in UI

## Compatibility

- **Blender 4.2+**: Fully supported (extension system)
- **Blender 2.82-4.1**: Supported (tiled image API available)
- **Blender <2.82**: Not supported (lacks tiled image API)
- **Forward compatible**: Uses runtime detection for API changes
