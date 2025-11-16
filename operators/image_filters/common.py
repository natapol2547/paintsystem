import bpy
from bpy.types import Image
try:
    from PIL import Image as PILImage
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    PILImage = None
import numpy as np
import struct
import time
from pathlib import Path
import os

debug_mode = False

def blender_image_to_numpy(image: Image):
    """Convert Blender image to numpy array."""
    start_time = time.time()
    if image is None:
        return None
        
    # Get image dimensions
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
    end_time = time.time()
    if debug_mode:
        print(f"Blender image to numpy took {(end_time - start_time)*1000} milliseconds")
    return pixels

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
    if not PIL_AVAILABLE:
        raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
    img_uint8 = np.array(pil_image, dtype=np.uint8)
    img_float = img_uint8.astype(np.float64) / 255.0
    return img_float

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


def resolve_brush_preset_path():
    """Resolve the path to the brush preset. A folder containing folders of brush images."""
    return os.path.join(Path(__file__).resolve().parent, "brush_painter", "brush_presets")


def list_brush_presets():
    """List the brush presets."""
    return os.listdir(resolve_brush_preset_path())