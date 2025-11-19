import bpy
import numpy as np
from .common import blender_image_to_numpy, numpy_to_blender_image, box_blur_numpy

def box_blur(numpy_array, radius):
    return box_blur_numpy(numpy_array, radius)

def sharpen_image(numpy_array, sharpen_amount):
    # Unsharp mask implementation: Original + (Original - Blurred) * Amount
    # Radius 1.0 corresponds to standard unsharp mask radius
    blurred = box_blur_numpy(numpy_array, 1.0)
    mask = numpy_array - blurred
    sharpened = numpy_array + mask * sharpen_amount
    return np.clip(sharpened, 0, 1)

def smooth_image(numpy_array, smooth_amount):
    # Simple smoothing using Gaussian blur
    # We use sigma=1.0 as a replacement for PIL's fixed SMOOTH kernel
    return box_blur_numpy(numpy_array, 1.0)
