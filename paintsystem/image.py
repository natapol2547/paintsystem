import bpy
from bpy.types import Image
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None
import numpy as np
import time
from pathlib import Path
import os
import re
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

debug_mode = False

# --- UDIM helpers ---

_UDIM_SEPARATORS = ['.', '_', '-']


def parse_udim_filename(filename: str) -> Tuple[str, str]:
    """Extract the prefix and extension from a UDIM-style filename.

    Handles both the ``.<UDIM>.`` marker convention and plain filenames.
    
    Returns:
        (prefix, extension) -- e.g. ``("my_image", "png")`` or ``("my_image", ".png")``.
        For ``.<UDIM>.`` filenames the extension does **not** include a leading dot.
    """
    if '.<UDIM>.' in filename:
        prefix = filename.split('.<UDIM>.')[0]
        extension = filename.split('.<UDIM>.')[-1]
    else:
        prefix = os.path.splitext(filename)[0]
        extension = os.path.splitext(filename)[1]
    return prefix, extension


def find_udim_tile_files(directory: str, prefix: str) -> Dict[int, str]:
    """Scan *directory* for files matching the UDIM tile naming convention.
    
    Returns:
        A mapping of tile number to absolute file path.
    """
    tile_files: Dict[int, str] = {}
    if not os.path.exists(directory):
        return tile_files
    for f in os.listdir(directory):
        for sep in _UDIM_SEPARATORS:
            pattern = rf'^{re.escape(prefix)}{re.escape(sep)}(\d{{4}})(\..+)?$'
            match = re.match(pattern, f)
            if match:
                tile_num = int(match.group(1))
                tile_files[tile_num] = os.path.join(directory, f)
                break
    return tile_files


def _get_image_dir_and_filename(image: Image) -> Tuple[str, str]:
    """Return (directory, filename) for an image, falling back to temp dir."""
    if image.filepath:
        directory = os.path.dirname(bpy.path.abspath(image.filepath))
        filename = bpy.path.basename(image.filepath)
    else:
        directory = bpy.app.tempdir
        image_name = image.name.replace(' ', '_')
        filename = f"{image_name}.<UDIM>.png"
    return directory, filename


def _resolve_tile_path(directory: str, prefix: str, extension: str, tile_number: int) -> Optional[str]:
    """Try to find the file path for a specific UDIM tile number."""
    for sep in _UDIM_SEPARATORS:
        tile_filename = f"{prefix}{sep}{tile_number}{extension}"
        potential_path = os.path.join(directory, tile_filename)
        if os.path.exists(potential_path):
            return potential_path
    return None

@dataclass
class ImageTiles:
    """
    Represents image tiles from a Blender image.
    For non-UDIM images, contains a single tile (typically tile 1001).
    For UDIM images, contains multiple tiles.
    """
    tiles: Dict[int, np.ndarray]  # Mapping of tile number to numpy array
    ori_path: str
    ori_packed: bool
    
    @property
    def is_udim(self) -> bool:
        """Returns True if this represents a UDIM image with multiple tiles."""
        return len(self.tiles) > 1
    
    def get_single_tile(self) -> np.ndarray:
        """
        Get the single tile for non-UDIM images.
        For UDIM images, returns the first tile.
        """
        if not self.tiles:
            raise ValueError("No tiles available")
        return next(iter(self.tiles.values()))
    
    def get_tile(self, tile_number: int) -> np.ndarray:
        """Get a specific tile by number."""
        if tile_number not in self.tiles:
            raise KeyError(f"Tile {tile_number} not found")
        return self.tiles[tile_number]

def save_image(image: Image, force_save: bool = False):
    if not image.is_dirty and not force_save:
        return
    try:
        if image.packed_file or image.filepath == '':
            image.pack()
        else:
            image.save()
    except Exception as e:
        print(f"Failed to save image {image.name}: {e}. Use packing instead.")
        image.filepath_raw = ''
        image.pack()

def temp_save_image(image):
    """Save image to temporary directory, ensuring all UDIM tiles are saved."""
    if image.source != 'TILED' or len(image.tiles) <= 1:
        # Non-UDIM image, just save normally
        with bpy.context.temp_override(edit_image=image):
            bpy.ops.image.save_as(filepath=bpy.app.tempdir)
        return
    
    # For UDIM images, we need to save all tiles
    # Remember if image was packed
    was_packed = image.packed_file is not None
    
    # If packed, unpack first
    if was_packed:
        image.unpack(method='USE_ORIGINAL')
    
    # Save the image (this saves all tiles)
    if image.filepath and '.<UDIM>.' in image.filepath:
        # Already has a valid filepath with UDIM marker
        image.save()
    else:
        # No filepath or missing UDIM marker, save to temp directory with UDIM marker
        # Construct a filepath with UDIM marker
        temp_dir = bpy.app.tempdir
        # Use image name or a default name
        image_name = image.name.replace(' ', '_')
        temp_filepath = os.path.join(temp_dir, f"{image_name}.<UDIM>.png")
        with bpy.context.temp_override(edit_image=image):
            bpy.ops.image.save_as(filepath=temp_filepath)

def blender_image_to_numpy(image: Image) -> Optional[ImageTiles]:
    """
    Convert Blender image to ImageTiles dataclass.
    Always returns ImageTiles, even for non-UDIM images (which will have a single tile).
    """
    start_time = time.time()
    if image is None:
        return None
    
    # Check if this is a UDIM tiled image
    is_udim = image.source == 'TILED' and len(image.tiles) > 1
    
    if not is_udim:
        # Non-UDIM image - use the fast path
        width, height = image.size
        
        # Use foreach_get for much faster pixel access
        pixels = np.empty(len(image.pixels), dtype=np.float32)
        image.pixels.foreach_get(pixels)
        
        # Reshape to (height, width, channels)
        if image.channels == 4:  # RGBA
            pixels = pixels.reshape((height, width, 4))
        else:
            raise ValueError(f"Unsupported image format with {image.channels} channels")
        
        # Flip vertically (Blender uses bottom-left origin, numpy uses top-left)
        pixels = np.flipud(pixels)
        
        # For non-UDIM images, use tile number 1001 (standard default)
        tiles_dict = {1001: pixels}
        end_time = time.time()
        if debug_mode:
            print(f"Blender image to numpy took {(end_time - start_time)*1000} milliseconds")
        return ImageTiles(tiles=tiles_dict, ori_path=image.filepath, ori_packed=(image.packed_file or image.filepath == ''))
    
    # UDIM image - need to load all tiles from disk
    if not PIL_AVAILABLE:
        raise ImportError("PIL (Pillow) is required to process UDIM images. Please install Pillow.")
    
    # Remember original state
    was_packed = (image.packed_file or image.filepath == '')
    original_filepath = image.filepath
    
    # Save image to ensure all tiles are on disk
    temp_save_image(image)
    
    directory, filename = _get_image_dir_and_filename(image)
    prefix, extension = parse_udim_filename(filename)
    
    # Load all tiles
    tiles_dict = {}
    width, height = image.size
    
    # Build a map of tile numbers to file paths by searching the directory
    tile_files = find_udim_tile_files(directory, prefix)
    
    for tile in image.tiles:
        tile_number = tile.number
        
        # Try to find the tile file
        tile_path = tile_files.get(tile_number)
        if tile_path is None:
            tile_path = _resolve_tile_path(directory, prefix, extension, tile_number)
        
        if tile_path and os.path.exists(tile_path):
            # Load tile using PIL
            pil_img = PILImage.open(tile_path)
            if pil_img.mode != 'RGBA':
                pil_img = pil_img.convert('RGBA')
            
            # Convert to numpy
            img_uint8 = np.array(pil_img, dtype=np.uint8)
            pixels = img_uint8.astype(np.float32) / 255.0
            
            # Ensure correct dimensions
            if pixels.shape[:2] != (height, width):
                pil_img = pil_img.resize((width, height), PILImage.Resampling.LANCZOS)
                img_uint8 = np.array(pil_img, dtype=np.uint8)
                pixels = img_uint8.astype(np.float32) / 255.0
            
            # Flip vertically (Blender uses bottom-left origin, numpy uses top-left)
            pixels = np.flipud(pixels)
            
            tiles_dict[tile_number] = pixels
        else:
            # Tile file not found, try to get from Blender's pixel data (first tile only)
            if tile_number == image.tiles[0].number:
                pixels = np.empty(len(image.pixels), dtype=np.float32)
                image.pixels.foreach_get(pixels)
                if image.channels == 4:
                    pixels = pixels.reshape((height, width, 4))
                    pixels = np.flipud(pixels)
                    tiles_dict[tile_number] = pixels
            else:
                tiles_dict[tile_number] = np.zeros((height, width, 4), dtype=np.float32)
    
    end_time = time.time()
    if debug_mode:
        print(f"Blender UDIM image to numpy took {(end_time - start_time)*1000} milliseconds for {len(tiles_dict)} tiles")
    
    return ImageTiles(tiles=tiles_dict, ori_path=original_filepath, ori_packed=was_packed)

def numpy_to_blender_image(array, image_name="BrushPainted", create_new=True) -> Image:
    """Convert numpy array back to Blender image."""
    start_time = time.time()
    # Flip vertically back to Blender coordinate system
    array = np.flipud(array)
    
    # Ensure array is in [0, 1] range
    array = np.clip(array, 0, 1)
    
    # Get dimensions
    height, width = array.shape[:2]
    channels = array.shape[2] if len(array.shape) == 3 else 1
    
    # Flatten array and ensure it's float32 for Blender
    pixels = array.ravel().astype(np.float32)
    
    # Try to get the image
    if create_new:
        new_image = bpy.data.images.new(image_name, width=width, height=height, alpha=True)
    else:
        new_image = bpy.data.images.get(image_name)
        if new_image is None:
            raise ValueError(f"Image {image_name} not found")
    
    # Use foreach_set for much faster pixel setting
    if channels == 4:
        new_image.pixels.foreach_set(pixels)
    else:
        raise ValueError(f"Unsupported image format with {channels} channels")
    
    # Update image
    new_image.update()
    end_time = time.time()
    if debug_mode:
        print(f"Numpy to blender image took {(end_time - start_time)*1000} milliseconds")
    return new_image

def numpy_to_pil(numpy_array):
    if not PIL_AVAILABLE:
        raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
    img_uint8 = (np.clip(numpy_array, 0, 1) * 255).astype(np.uint8)
    img_pil = PILImage.fromarray(img_uint8, mode='RGBA')
    return img_pil

def pil_to_numpy(pil_image):
    """Convert a PIL image to a float32 numpy array in [0, 1] range."""
    if not PIL_AVAILABLE:
        raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
    img_uint8 = np.array(pil_image, dtype=np.uint8)
    img_float = img_uint8.astype(np.float32) / 255.0
    return img_float

def is_temp_filepath(filepath: str) -> bool:
    """
    Check if a filepath is in the temporary directory.
    """
    if not filepath:
        return False
    temp_dir = bpy.app.tempdir
    abs_filepath = bpy.path.abspath(filepath)
    abs_temp_dir = os.path.abspath(temp_dir)
    return abs_filepath.startswith(abs_temp_dir)

def delete_temp_image_files(image: Image):
    """
    Delete temporary files associated with an image if they are in the temp directory.
    Handles both UDIM (multiple tile files) and non-UDIM (single file) images.
    """
    if not image.filepath:
        return
    
    if not is_temp_filepath(image.filepath):
        return
    
    is_udim = image.source == 'TILED' and len(image.tiles) > 1
    
    if is_udim:
        directory, filename = _get_image_dir_and_filename(image)
        prefix, _extension = parse_udim_filename(filename)
        tile_files = find_udim_tile_files(directory, prefix)
        for tile_path in tile_files.values():
            try:
                if os.path.exists(tile_path):
                    os.remove(tile_path)
            except OSError as e:
                if debug_mode:
                    print(f"Failed to delete temp tile file {tile_path}: {e}")
    else:
        abs_filepath = bpy.path.abspath(image.filepath)
        try:
            if os.path.exists(abs_filepath):
                os.remove(abs_filepath)
        except OSError as e:
            if debug_mode:
                print(f"Failed to delete temp file {abs_filepath}: {e}")

def switch_image_content(image1: Image, image2: Image):
    """Switch the contents of two images."""
    start_time = time.time()
    # Use foreach_get for much faster pixel access
    pixels_1 = np.empty(len(image1.pixels), dtype=np.float32)
    pixels_2 = np.empty(len(image2.pixels), dtype=np.float32)
    image1.pixels.foreach_get(pixels_1)
    image2.pixels.foreach_get(pixels_2)
    image1.pixels.foreach_set(pixels_2)
    image2.pixels.foreach_set(pixels_1)
    image1.update()
    image1.update_tag()
    image2.update()
    image2.update_tag()
    end_time = time.time()
    if debug_mode:
        print(f"Switch image content took {(end_time - start_time)*1000} milliseconds")

def set_image_pixels(image: Image, image_tiles: ImageTiles):
    """
    Set image pixels from ImageTiles dataclass.
    """
    start_time = time.time()
    
    # Check if this is a UDIM tiled image
    is_udim = image.source == 'TILED' and len(image.tiles) > 1
    
    if image_tiles.is_udim or is_udim:
        # UDIM image - save tiles to disk
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is required to process UDIM images. Please install Pillow.")
        
        directory, filename = _get_image_dir_and_filename(image)
        prefix, extension = parse_udim_filename(filename)
        
        # Save each tile
        for tile_number, array in image_tiles.tiles.items():
            array = np.flipud(array.copy())
            array = np.clip(array, 0, 1)
            
            img_uint8 = (array * 255).astype(np.uint8)
            pil_img = PILImage.fromarray(img_uint8, mode='RGBA')
            
            # Construct tile filename, preferring existing file path
            tile_filename = f"{prefix}.{tile_number}.{extension}"
            tile_path = os.path.join(directory, tile_filename)
            
            # Try alternative separator patterns if file doesn't exist yet
            existing_path = _resolve_tile_path(directory, prefix, extension, tile_number)
            if existing_path:
                tile_path = existing_path
            
            pil_img.save(tile_path)
        
        # Reload image to update tiles
        image.reload()
        image.update()
        image.update_tag()
        
        # Repack if it was originally packed
        if image_tiles.ori_packed:
            image.pack()
            # Delete temp files if the current filepath is in temp directory
            if is_temp_filepath(image.filepath):
                delete_temp_image_files(image)
            image.filepath = image_tiles.ori_path
    else:
        # Single array (non-UDIM)
        array = image_tiles.get_single_tile()
        # Flip vertically back to Blender coordinate system
        array = np.flipud(array)
        
        # Ensure array is in [0, 1] range
        array = np.clip(array, 0, 1)
        array = array.ravel().astype(np.float32)
        # Set the pixels
        image.pixels.foreach_set(array)
        image.update()
        image.update_tag()
    
    end_time = time.time()
    if debug_mode:
        print(f"Set image pixels took {(end_time - start_time)*1000} milliseconds")