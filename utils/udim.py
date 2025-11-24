"""UDIM utility functions for Paint System"""
import bpy
import numpy as np
from typing import List, Tuple, Optional
import os


def detect_udim_from_uv(obj: bpy.types.Object) -> List[int]:
    """
    Detect which UDIM tiles are used by analyzing UV coordinates.
    
    Args:
        obj: Mesh object to analyze
        
    Returns:
        List of UDIM tile numbers (e.g., [1001, 1002, 1003])
    """
    if not obj or obj.type != 'MESH':
        return []
    
    mesh = obj.data
    if not mesh.uv_layers.active:
        return []
    
    # Get UV coordinates
    uv_layer = mesh.uv_layers.active.data
    uv_coords = np.zeros(len(uv_layer) * 2, dtype=np.float32)
    uv_layer.foreach_get('uv', uv_coords)
    
    # Reshape to (n, 2) for easier processing
    uvs = uv_coords.reshape(-1, 2)
    
    # Find unique tile numbers based on U coordinate
    # UDIM tile = 1000 + floor(U) + 1
    u_coords = uvs[:, 0]
    tile_u_offsets = np.floor(u_coords).astype(int)
    
    # Get unique tile numbers
    unique_tiles = np.unique(tile_u_offsets)
    tile_numbers = [1001 + offset for offset in unique_tiles if offset >= 0]
    
    return sorted(tile_numbers)


def is_udim_image(image: bpy.types.Image) -> bool:
    """
    Check if an image is a UDIM image.
    
    Args:
        image: Image to check
        
    Returns:
        True if image uses UDIM tiles
    """
    if not image:
        return False
    
    # Check if filepath contains <UDIM> token
    if '<UDIM>' in image.filepath or '<UDIM>' in image.name:
        return True
    
    # Check if image has tiles property (Blender 2.82+)
    if hasattr(image, 'source') and image.source == 'TILED':
        return True
    
    return False


def get_udim_tiles_from_image(image: bpy.types.Image) -> List[int]:
    """
    Get list of tile numbers from a UDIM image.
    
    Args:
        image: UDIM image
        
    Returns:
        List of tile numbers
    """
    if not image or not is_udim_image(image):
        return []
    
    # If image has tiles attribute (Blender 2.82+)
    if hasattr(image, 'tiles'):
        return [tile.number for tile in image.tiles]
    
    # Otherwise, scan filesystem for tiles
    if not image.filepath:
        return []
    
    base_path = bpy.path.abspath(image.filepath)
    if '<UDIM>' not in base_path:
        return []
    
    directory = os.path.dirname(base_path)
    if not os.path.exists(directory):
        return []
    
    # Extract filename pattern
    filename = os.path.basename(base_path)
    prefix, suffix = filename.split('<UDIM>')
    
    # Find matching files
    tiles = []
    for file in os.listdir(directory):
        if file.startswith(prefix) and file.endswith(suffix):
            # Extract tile number
            try:
                tile_str = file[len(prefix):len(file)-len(suffix)]
                tile_num = int(tile_str)
                if 1001 <= tile_num <= 2000:
                    tiles.append(tile_num)
            except ValueError:
                continue
    
    return sorted(tiles)


def create_udim_image(name: str, tiles: List[int], width: int = 2048, height: int = 2048, 
                     alpha: bool = True, float_buffer: bool = False) -> Optional[bpy.types.Image]:
    """
    Create a new UDIM image with specified tiles.
    
    Args:
        name: Base name for the image
        tiles: List of tile numbers to create (e.g., [1001, 1002])
        width: Width of each tile
        height: Height of each tile
        alpha: Whether to include alpha channel
        float_buffer: Whether to use float buffer
        
    Returns:
        Created UDIM image or None if failed
    """
    if not tiles:
        return None
    
    # Create base image with first tile
    image = bpy.data.images.new(
        name=name,
        width=width,
        height=height,
        alpha=alpha,
        float_buffer=float_buffer,
        tiled=True  # This creates a UDIM image in Blender 2.82+
    )
    
    # Add additional tiles
    for tile_num in tiles[1:]:
        if hasattr(image, 'tiles'):
            # Check if tile already exists
            if not any(t.number == tile_num for t in image.tiles):
                image.tiles.new(tile_number=tile_num)
    
    return image


def fill_udim_tile(image: bpy.types.Image, tile_number: int, color: Tuple[float, float, float, float]):
    """
    Fill a specific UDIM tile with a color.
    
    Args:
        image: UDIM image
        tile_number: Tile number to fill
        color: RGBA color tuple
    """
    if not image or not is_udim_image(image):
        return
    
    if not hasattr(image, 'tiles'):
        return
    
    # Find the tile
    tile = None
    for t in image.tiles:
        if t.number == tile_number:
            tile = t
            break
    
    if not tile:
        return
    
    # Calculate pixel offset for this tile
    # Blender stores UDIM tiles sequentially in the pixel buffer
    tile_index = list(image.tiles).index(tile)
    pixels_per_tile = image.size[0] * image.size[1] * 4  # RGBA
    start_pixel = tile_index * pixels_per_tile
    
    # Create color array
    color_array = np.array(color * (pixels_per_tile // 4), dtype=np.float32)
    
    # Update pixels
    pixels = np.zeros(len(image.pixels), dtype=np.float32)
    image.pixels.foreach_get(pixels)
    pixels[start_pixel:start_pixel + pixels_per_tile] = color_array
    image.pixels.foreach_set(pixels)
    image.update()


def get_udim_filepath_for_tile(base_path: str, tile_number: int) -> str:
    """
    Convert a UDIM filepath to a specific tile filepath.
    
    Args:
        base_path: Path with <UDIM> token (e.g., "texture_<UDIM>.png")
        tile_number: Tile number (e.g., 1001)
        
    Returns:
        Path for specific tile (e.g., "texture_1001.png")
    """
    if '<UDIM>' not in base_path:
        return base_path
    
    return base_path.replace('<UDIM>', str(tile_number))


def suggest_udim_for_object(obj: bpy.types.Object) -> bool:
    """
    Determine if UDIM should be suggested for an object.
    
    Args:
        obj: Object to check
        
    Returns:
        True if UDIM is recommended
    """
    if not obj or obj.type != 'MESH':
        return False
    
    tiles = detect_udim_from_uv(obj)
    return len(tiles) > 1


def get_udim_info_string(layer) -> str:
    """
    Get a user-friendly string describing UDIM usage.
    
    Args:
        layer: Layer with UDIM tiles
        
    Returns:
        Info string like "UDIM (3 tiles)" or ""
    """
    if not layer.is_udim:
        return ""
    
    tile_count = len(layer.udim_tiles)
    if tile_count == 0:
        return "UDIM"
    elif tile_count == 1:
        return f"UDIM ({layer.udim_tiles[0].number})"
    else:
        return f"UDIM ({tile_count} tiles)"
