import bpy
import numpy as np
from ...paintsystem.image import ImageTiles


def _gaussian_kernel_1d(sigma: float) -> np.ndarray:
    sigma = max(float(sigma), 1e-6)
    radius = max(1, int(sigma * 2.0))
    coords = np.arange(-radius, radius + 1, dtype=np.float32)
    kernel = np.exp(-0.5 * (coords / sigma) ** 2)
    kernel /= np.sum(kernel)
    return kernel.astype(np.float32)


def _convolve1d_axis(array: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
    radius = kernel.size // 2
    pad_width = [(0, 0)] * array.ndim
    pad_width[axis] = (radius, radius)
    padded = np.pad(array, pad_width, mode='edge')
    windows = np.lib.stride_tricks.sliding_window_view(padded, kernel.size, axis=axis)
    return np.tensordot(windows, kernel, axes=([-1], [0])).astype(np.float32, copy=False)


def _gaussian_blur_array(array: np.ndarray, sigma: float) -> np.ndarray:
    if sigma <= 0:
        return array.astype(np.float32, copy=True)
    kernel = _gaussian_kernel_1d(sigma)
    blurred = _convolve1d_axis(array, kernel, axis=0)
    blurred = _convolve1d_axis(blurred, kernel, axis=1)
    return blurred


def _gaussian_blur_alpha_safe(numpy_array: np.ndarray, gaussian_sigma: float) -> np.ndarray:
    array = np.clip(numpy_array, 0.0, 1.0).astype(np.float32, copy=False)
    if array.ndim != 3 or array.shape[2] != 4:
        return _gaussian_blur_array(array, gaussian_sigma)

    alpha = array[..., 3:4]
    premult_rgb = array[..., :3] * alpha
    premult_rgba = np.concatenate((premult_rgb, alpha), axis=2)
    blurred = _gaussian_blur_array(premult_rgba, gaussian_sigma)

    out_alpha = blurred[..., 3:4]
    safe_alpha = np.where(out_alpha > 1e-6, out_alpha, 1.0)
    out_rgb = blurred[..., :3] / safe_alpha
    out_rgb = np.where(out_alpha > 1e-6, out_rgb, 0.0)

    output = np.concatenate((out_rgb, out_alpha), axis=2)
    return np.clip(output, 0.0, 1.0).astype(np.float32, copy=False)

def _gaussian_blur_single(numpy_array, gaussian_sigma):
    """Apply gaussian blur to a single numpy array."""
    return _gaussian_blur_alpha_safe(numpy_array, gaussian_sigma)

def gaussian_blur(image_tiles: ImageTiles, gaussian_sigma) -> ImageTiles:
    """
    Apply gaussian blur to ImageTiles.
    """
    blurred_tiles = {
        tile_num: _gaussian_blur_single(tile_array, gaussian_sigma)
        for tile_num, tile_array in image_tiles.tiles.items()
    }
    return ImageTiles(tiles=blurred_tiles, ori_path=image_tiles.ori_path, ori_packed=image_tiles.ori_packed)


def _sharpen_image_single(numpy_array, sharpen_amount):
    """Apply sharpen to a single numpy array."""
    array = np.clip(numpy_array, 0.0, 1.0).astype(np.float32, copy=False)
    blurred = _gaussian_blur_alpha_safe(array, 1.0)
    sharpened = array + float(sharpen_amount) * (array - blurred)
    if array.ndim == 3 and array.shape[2] == 4:
        sharpened[..., 3] = array[..., 3]
    return np.clip(sharpened, 0.0, 1.0).astype(np.float32, copy=False)

def sharpen_image(image_tiles: ImageTiles, sharpen_amount) -> ImageTiles:
    """
    Apply sharpen to ImageTiles.
    """
    sharpened_tiles = {
        tile_num: _sharpen_image_single(tile_array, sharpen_amount)
        for tile_num, tile_array in image_tiles.tiles.items()
    }
    return ImageTiles(tiles=sharpened_tiles, ori_path=image_tiles.ori_path, ori_packed=image_tiles.ori_packed)


def _smooth_image_single(numpy_array, smooth_amount):
    """Apply smooth to a single numpy array."""
    sigma = max(float(smooth_amount), 0.0)
    sigma = 0.8 + sigma * 0.2
    return _gaussian_blur_alpha_safe(numpy_array, sigma)

def smooth_image(image_tiles: ImageTiles, smooth_amount) -> ImageTiles:
    """
    Apply smooth to ImageTiles.
    """
    smoothed_tiles = {
        tile_num: _smooth_image_single(tile_array, smooth_amount)
        for tile_num, tile_array in image_tiles.tiles.items()
    }
    return ImageTiles(tiles=smoothed_tiles, ori_path=image_tiles.ori_path, ori_packed=image_tiles.ori_packed)