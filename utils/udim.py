"""UDIM utility functions for Paint System

Robust creation & detection helpers. A GPU upload failure ("Failed to create GPU texture from Blender image")
has been reported sporadically when freshly-created tiled images have not had their pixel buffer
initialized yet or when the active tile index is invalid. We defensively ensure:
    * At least one tile exists and is active (index 0)
    * Colorspace is set to a common value ('Linear') before any potential GPU upload
    * Pixel buffer is touched once so Blender allocates it
    * Graceful fallback to a non-tiled image if UDIM creation raises an exception
"""
import bpy
import numpy as np
from typing import List, Tuple, Optional
import os
import logging

logger = logging.getLogger("PaintSystem")


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
    """Create a new UDIM image with specified tiles, with defensive GPU upload safeguards.

    If UDIM creation fails (rare driver / context issues) we fall back to a non-tiled image so the
    caller still receives a usable texture instead of None.
    """
    if not tiles:
        return None

    try:
        image = bpy.data.images.new(
            name=name,
            width=width,
            height=height,
            alpha=alpha,
            float_buffer=float_buffer,
            tiled=True
        )
    except Exception as e:
        logger.warning(f"UDIM creation failed for '{name}' ({e}); falling back to single tile image.")
        try:
            return bpy.data.images.new(
                name=f"{name}_fallback",
                width=width,
                height=height,
                alpha=alpha,
                float_buffer=float_buffer,
                tiled=False
            )
        except Exception as e2:
            logger.error(f"Fallback image creation also failed: {e2}")
            return None

    # Ensure at least the first requested tile number is present & active
    if hasattr(image, 'tiles'):
        existing_numbers = {t.number for t in image.tiles}
        # Blender creates an initial tile numbered 1001 by default; add missing ones.
        for tile_num in tiles:
            if tile_num not in existing_numbers:
                try:
                    image.tiles.new(tile_number=tile_num)
                except Exception as e:
                    logger.debug(f"Failed adding UDIM tile {tile_num}: {e}")
        # Set active index to first tile to prevent downstream GPU upload errors.
        try:
            image.tiles.active_index = 0
        except Exception as e:
            logger.debug(f"Could not set active UDIM tile index: {e}")

    # Standardize colorspace early (inconsistent spaces sometimes trip GPU conversions)
    try:
        if hasattr(image, 'colorspace_settings'):  # runtime guard
            image.colorspace_settings.name = 'Linear'
    except Exception as e:
        logger.debug(f"Failed to set colorspace for '{name}': {e}")

    # Touch pixel buffer to ensure allocation (prevents lazy allocation failures)
    try:
        if len(image.pixels) == 0:
            # Force an update; writing a single pixel triggers allocation.
            pixel_count = image.size[0] * image.size[1]
            # Only allocate minimal RGBA data for first tile (safe default)
            image.pixels[0:4] = (0.0, 0.0, 0.0, 0.0)
        image.update()
    except Exception as e:
        logger.debug(f"Pixel buffer init skipped for '{name}': {e}")

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


def _get_tile_index(image: bpy.types.Image, tile_number: int) -> int:
    if not hasattr(image, 'tiles'):
        return -1
    for idx, t in enumerate(image.tiles):
        if t.number == tile_number:
            return idx
    return -1


def copy_image_to_udim_tile(dest_udim: bpy.types.Image, tile_number: int, src_image: bpy.types.Image) -> bool:
    """Copy pixels from a non-UDIM image into a specific UDIM tile of destination image.

    Returns True on success.
    """
    if not dest_udim or not is_udim_image(dest_udim) or not src_image:
        return False
    if not hasattr(dest_udim, 'tiles'):
        return False

    # Ensure tile exists on destination
    if _get_tile_index(dest_udim, tile_number) == -1:
        try:
            dest_udim.tiles.new(tile_number=tile_number)
        except Exception:
            return False

    # Match resolution
    try:
        w, h = dest_udim.size
        if src_image.size[0] != w or src_image.size[1] != h:
            src_image.scale(w, h)
    except Exception:
        pass

    # Prepare buffers
    try:
        src_pixels = np.zeros(len(src_image.pixels), dtype=np.float32)
        src_image.pixels.foreach_get(src_pixels)

        dest_pixels = np.zeros(len(dest_udim.pixels), dtype=np.float32)
        dest_udim.pixels.foreach_get(dest_pixels)

        tile_index = _get_tile_index(dest_udim, tile_number)
        if tile_index < 0:
            return False
        pixels_per_tile = dest_udim.size[0] * dest_udim.size[1] * 4
        start = tile_index * pixels_per_tile
        dest_pixels[start:start + pixels_per_tile] = src_pixels[:pixels_per_tile]
        dest_udim.pixels.foreach_set(dest_pixels)
        dest_udim.update()
        return True
    except Exception:
        return False


def copy_udim_tile_to_udim_tile(src_udim: bpy.types.Image, tile_number: int, dest_udim: bpy.types.Image) -> bool:
    """Copy pixels from a specific UDIM tile in source image to same-number tile in destination UDIM image.

    Returns True on success.
    """
    if not (src_udim and dest_udim) or not (is_udim_image(src_udim) and is_udim_image(dest_udim)):
        return False
    if not hasattr(src_udim, 'tiles') or not hasattr(dest_udim, 'tiles'):
        return False

    # Ensure destination has the tile
    if _get_tile_index(dest_udim, tile_number) == -1:
        try:
            dest_udim.tiles.new(tile_number=tile_number)
        except Exception:
            return False

    try:
        w, h = dest_udim.size
        # Ensure sizes match by scaling a temp copy from the source tile
        # Read source UDIM pixel buffer
        src_pixels_all = np.zeros(len(src_udim.pixels), dtype=np.float32)
        src_udim.pixels.foreach_get(src_pixels_all)
        src_tile_index = _get_tile_index(src_udim, tile_number)
        if src_tile_index < 0:
            return False
        pixels_per_tile = src_udim.size[0] * src_udim.size[1] * 4
        src_start = src_tile_index * pixels_per_tile
        src_tile_pixels = src_pixels_all[src_start:src_start + pixels_per_tile]

        # If source and destination resolutions differ, attempt simple resample using Blender image scale
        if src_udim.size[0] != w or src_udim.size[1] != h:
            # Create a temp image to resample
            temp = bpy.data.images.new(name="PS_TempTileCopy", width=src_udim.size[0], height=src_udim.size[1], alpha=True)
            try:
                temp.pixels.foreach_set(src_tile_pixels)
                temp.update()
                temp.scale(w, h)
                src_tile_pixels = np.zeros(w * h * 4, dtype=np.float32)
                temp.pixels.foreach_get(src_tile_pixels)
            finally:
                try:
                    bpy.data.images.remove(temp)
                except Exception:
                    pass

        dest_pixels = np.zeros(len(dest_udim.pixels), dtype=np.float32)
        dest_udim.pixels.foreach_get(dest_pixels)
        dest_tile_index = _get_tile_index(dest_udim, tile_number)
        if dest_tile_index < 0:
            return False
        dest_start = dest_tile_index * (w * h * 4)
        dest_pixels[dest_start:dest_start + (w * h * 4)] = src_tile_pixels[:(w * h * 4)]
        dest_udim.pixels.foreach_set(dest_pixels)
        dest_udim.update()
        return True
    except Exception:
        return False


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
