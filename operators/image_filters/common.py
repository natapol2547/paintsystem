import bpy
from bpy.types import Image
import numpy as np
import struct
import time
from pathlib import Path
import os
import math

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
            # Fallback to creating new if not found
            new_image = bpy.data.images.new(image_name, width=width, height=height, alpha=True)
    
    # Adjust buffer size if existing image has different dimensions
    if new_image.size[0] != width or new_image.size[1] != height:
        new_image.scale(width, height)

    # Use foreach_set for much faster pixel setting
    if channels == 4:
        if len(new_image.pixels) != len(pixels):
             # Double check size matches, if not, resize
             new_image.scale(width, height)
        new_image.pixels.foreach_set(pixels)
    else:
        # Handle case where we might be passing grayscale to RGBA image
        # But the caller usually handles this. 
        raise ValueError(f"Unsupported image format with {channels} channels")
    
    # Update image
    new_image.update()
    end_time = time.time()
    if debug_mode:
        print(f"Numpy to blender image took {(end_time - start_time)*1000} milliseconds")
    return new_image

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
    path = resolve_brush_preset_path()
    if os.path.exists(path):
        return os.listdir(path)
    return []

# --- Numpy Replacement Functions ---

def load_image_as_numpy(filepath):
    """Loads an image from disk using Blender's API and converts to numpy."""
    if not os.path.exists(filepath):
        return None
    
    try:
        # Load image datablock
        img = bpy.data.images.load(filepath, check_existing=True)
        # Convert to numpy
        arr = blender_image_to_numpy(img)
        
        # Cleanup: If the image has no users (fake user not set), we could remove it.
        # However, check_existing=True might return an image that is used elsewhere.
        # For now, we rely on Blender's garbage collection or user management.
        # But to avoid cluttering the list with temp brush images, we can check users.
        if img.users == 0:
             bpy.data.images.remove(img)
             
        return arr
    except Exception as e:
        print(f"Failed to load image {filepath}: {e}")
        return None

def resize_image_numpy(image, output_shape):
    """
    Resizes an image using bilinear interpolation.
    output_shape is (height, width)
    """
    h, w = image.shape[:2]
    new_h, new_w = output_shape
    
    if h == new_h and w == new_w:
        return image

    # Create grid
    x = np.linspace(0, w - 1, new_w)
    y = np.linspace(0, h - 1, new_h)
    
    xv, yv = np.meshgrid(x, y)
    
    # Calculate indices and weights
    x0 = np.floor(xv).astype(int)
    y0 = np.floor(yv).astype(int)
    x1 = np.clip(x0 + 1, 0, w - 1)
    y1 = np.clip(y0 + 1, 0, h - 1)
    
    wa = (x1 - xv) * (y1 - yv)
    wb = (xv - x0) * (y1 - yv)
    wc = (x1 - xv) * (yv - y0)
    wd = (xv - x0) * (yv - y0)
    
    # Interpolate
    if image.ndim == 3:
        # Broadcast weights to channels
        wa = wa[..., None]
        wb = wb[..., None]
        wc = wc[..., None]
        wd = wd[..., None]
        
    output = (image[y0, x0] * wa +
              image[y0, x1] * wb +
              image[y1, x0] * wc +
              image[y1, x1] * wd)
              
    return output.astype(image.dtype)

def rotate_image_numpy(image, angle_degrees, expand=True):
    """
    Rotates an image by angle_degrees (counter-clockwise).
    If expand is True, the output size is increased to fit the rotated image.
    """
    angle_rad = np.deg2rad(angle_degrees)
    h, w = image.shape[:2]
    
    # Center of the image
    cy, cx = h / 2.0, w / 2.0
    
    # Calculate new dimensions if expand is True
    if expand:
        cos_a, sin_a = np.abs(np.cos(angle_rad)), np.abs(np.sin(angle_rad))
        new_w = int((h * sin_a) + (w * cos_a))
        new_h = int((h * cos_a) + (w * sin_a))
    else:
        new_w, new_h = w, h
        
    new_cy, new_cx = new_h / 2.0, new_w / 2.0
    
    # Create grid for new image
    x = np.arange(new_w)
    y = np.arange(new_h)
    xv, yv = np.meshgrid(x, y)
    
    # Transform coordinates back to original image space
    # Inverse rotation
    # x_src = (x - new_cx)*cos - (y - new_cy)*sin + cx
    # y_src = (x - new_cx)*sin + (y - new_cy)*cos + cy
    
    cos_val = np.cos(angle_rad)
    sin_val = np.sin(angle_rad)
    
    x_centered = xv - new_cx
    y_centered = yv - new_cy
    
    x_src = x_centered * cos_val - y_centered * sin_val + cx
    y_src = x_centered * sin_val + y_centered * cos_val + cy
    
    # Mask for valid coordinates
    mask = (x_src >= 0) & (x_src < w - 1) & (y_src >= 0) & (y_src < h - 1)
    
    # Bilinear interpolation
    x0 = np.floor(x_src).astype(int)
    y0 = np.floor(y_src).astype(int)
    x1 = x0 + 1
    y1 = y0 + 1
    
    # Clip indices to avoid errors (masked out later anyway)
    x0_c = np.clip(x0, 0, w - 1)
    y0_c = np.clip(y0, 0, h - 1)
    x1_c = np.clip(x1, 0, w - 1)
    y1_c = np.clip(y1, 0, h - 1)
    
    wa = (x1 - x_src) * (y1 - y_src)
    wb = (x_src - x0) * (y1 - y_src)
    wc = (x1 - x_src) * (y_src - y0)
    wd = (x_src - x0) * (y_src - y0)
    
    # Handle channels
    if image.ndim == 3:
        wa = wa[..., None]
        wb = wb[..., None]
        wc = wc[..., None]
        wd = wd[..., None]
        mask = mask[..., None]
        
    output = (image[y0_c, x0_c] * wa +
              image[y0_c, x1_c] * wb +
              image[y1_c, x0_c] * wc +
              image[y1_c, x1_c] * wd)
    
    # Apply mask (pixels outside source image are 0)
    output = output * mask
    
    return output

def box_blur_pass(arr, radius):
    # 2D Box blur using separable 1D blurs
    # Axis 0
    if radius < 1: return arr
    # Simple convolution implementation for 2D
    # For each channel, convolve with box kernel
    
    h, w = arr.shape[:2]
    
    # Create integral image (summed area table)
    # Integral image allows calculating sum of any rectangle in O(1)
    # integral[y, x] = sum(img[0..y, 0..x])
    
    integral = np.cumsum(np.cumsum(arr, axis=0), axis=1)
    
    # Calculate box sum using integral image
    # S = I(y+r, x+r) - I(y-r-1, x+r) - I(y+r, x-r-1) + I(y-r-1, x-r-1)
    # Handle boundaries by padding or clipping indices
    
    # Efficient implementation:
    # Pad integral image with one row/col of zeros
    if arr.ndim == 3:
        padded_integral = np.zeros((h + 1, w + 1, arr.shape[2]))
        padded_integral[1:, 1:] = integral
    else:
        padded_integral = np.zeros((h + 1, w + 1))
        padded_integral[1:, 1:] = integral
        
    y, x = np.mgrid[0:h, 0:w]
    
    y0 = np.clip(y - radius, 0, h)
    y1 = np.clip(y + radius + 1, 0, h)
    x0 = np.clip(x - radius, 0, w)
    x1 = np.clip(x + radius + 1, 0, w)
    
    box_sum = (padded_integral[y1, x1] 
             - padded_integral[y0, x1] 
             - padded_integral[y1, x0] 
             + padded_integral[y0, x0])
             
    area = (y1 - y0) * (x1 - x0)
    if arr.ndim == 3:
        area = area[..., None]
        
    return box_sum / area

def box_blur_numpy(image, radius):
    """
    Applies a box blur to the image.
    """
    if radius <= 0:
        return image
    
    return box_blur_pass(image, int(radius))

def sobel_filter_numpy(image):
    """
    Applies Sobel filter to get gradients Gx, Gy.
    Sobel on grayscale.
    """
    if image.ndim == 3:
        # Convert to grayscale
        if image.shape[2] == 4:
            gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
        else:
            gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
    else:
        gray = image
        
    # Kernels
    # Kx = [[1, 0, -1], [2, 0, -2], [1, 0, -1]]
    # Ky = [[1, 2, 1], [0, 0, 0], [-1, -2, -1]]
    
    # Implement using slicing for speed (valid padding)
    # This is equivalent to convolution
    
    padded = np.pad(gray, 1, mode='edge')
    
    # Views
    p00 = padded[:-2, :-2]
    p01 = padded[:-2, 1:-1]
    p02 = padded[:-2, 2:]
    p10 = padded[1:-1, :-2]
    # p11 center
    p12 = padded[1:-1, 2:]
    p20 = padded[2:, :-2]
    p21 = padded[2:, 1:-1]
    p22 = padded[2:, 2:]
    
    Gx = (p00 + 2*p10 + p20) - (p02 + 2*p12 + p22)
    
    Gy = (p20 + 2*p21 + p22) - (p00 + 2*p01 + p02)
    
    return Gx, Gy
