import bpy
import bmesh
import numpy as np
import os
import glob
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from ..common import blender_image_to_numpy
from ...paintsystem.image import set_image_pixels, ImageTiles

DEBUG_SEAM = False  # Set to False to disable seam duplication debug prints
DEBUG_CANCEL = False  # Set to False to disable brush cancellation debug prints
DEBUG_ROTATION = False  # Set to False to disable rotation debug prints (limited to first 20 samples)

@dataclass
class StepData:
    """Data structure for pre-calculated step information."""
    step: int
    scale: float
    opacity: float
    actual_brush_size: int
    scaled_brush_list: list
    num_samples: int
    random_y: np.ndarray
    random_x: np.ndarray


@dataclass
class UVSeamEdge:
    edge_key: Tuple[int, int]
    uv0: Tuple[float, float]
    uv1: Tuple[float, float]
    tile_num: int
    px0: Tuple[float, float]
    px1: Tuple[float, float]
    midpoint_uv: Tuple[float, float]
    length_uv: float
    vert0: int = -1
    vert1: int = -1
    face_side: int = 0  # +1 or -1: which side of edge (px0→px1) the face interior is on
    counterpart_index: int = -1


@dataclass
class UVSeamIndex:
    edges: List[UVSeamEdge]
    tile_to_edges: Dict[int, List[int]]


@dataclass
class TilePaintState:
    tile_num: int
    img_float: np.ndarray
    img_blurred: np.ndarray
    g_normalized: np.ndarray
    theta: np.ndarray
    has_alpha: bool
    canvas: np.ndarray
    extended_h: int
    extended_w: int
    offset_y: int
    offset_x: int
    height: int
    width: int
    min_size_px: int
    max_size_px: int

class BrushPainterCore:
    """Core functionality for applying brush strokes to Blender images."""
    
    def __init__(self):
        # Configuration parameters (can be adjusted via UI)
        self.brush_coverage_density = 0.7
        self.min_brush_scale = 0.03
        self.max_brush_scale = 0.1
        self.start_opacity = 0.4
        self.end_opacity = 1.0
        self.steps = 7
        self.gradient_threshold = 0.0
        self.gaussian_sigma = 3
        self.hue_shift = 0.0 # 0.0 to 1.0
        self.saturation_shift = 0.0 # 0.0 to 1.0
        self.value_shift = 0.0 # 0.0 to 1.0
        self.brush_rotation_offset = 0.0 # 0 to 360 degrees
        self.use_random_rotation = False  # Randomize rotation per stamp
        self.random_rotation_range = 360.0  # Range in degrees (full 360 by default)
        self.use_random_seed = False
        self.random_seed = 42
        self.rotation_bins = 180
        self._rotation_cache = {}
        self.enable_seam_duplication = True
        self._seam_index: Optional[UVSeamIndex] = None
        
        # Brush texture paths
        self.brush_texture_path = None
        self.brush_folder_path = None

    def _gaussian_kernel_1d(self, sigma: float) -> np.ndarray:
        sigma = max(float(sigma), 1e-6)
        radius = max(1, int(sigma * 2.0))
        coords = np.arange(-radius, radius + 1, dtype=np.float32)
        kernel = np.exp(-0.5 * (coords / sigma) ** 2)
        kernel /= np.sum(kernel)
        return kernel.astype(np.float32)

    def _convolve1d_axis(self, array: np.ndarray, kernel: np.ndarray, axis: int) -> np.ndarray:
        radius = kernel.size // 2
        pad_width = [(0, 0)] * array.ndim
        pad_width[axis] = (radius, radius)
        padded = np.pad(array, pad_width, mode='edge')
        windows = np.lib.stride_tricks.sliding_window_view(padded, kernel.size, axis=axis)
        return np.tensordot(windows, kernel, axes=([-1], [0])).astype(np.float32, copy=False)

    def _gaussian_blur_array(self, array: np.ndarray, sigma: float) -> np.ndarray:
        if sigma <= 0:
            return array.astype(np.float32, copy=True)
        kernel = self._gaussian_kernel_1d(sigma)
        blurred = self._convolve1d_axis(array, kernel, axis=0)
        blurred = self._convolve1d_axis(blurred, kernel, axis=1)
        return blurred

    def _rgb_to_gray(self, image: np.ndarray) -> np.ndarray:
        if image.ndim == 2:
            return image.astype(np.float32, copy=False)
        rgb = image[..., :3]
        gray = rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
        return gray.astype(np.float32, copy=False)

    def _resize_mask_bilinear(self, mask: np.ndarray, out_h: int, out_w: int) -> np.ndarray:
        src_h, src_w = mask.shape
        if src_h == out_h and src_w == out_w:
            return mask.astype(np.float32, copy=True)
        if out_h <= 1 or out_w <= 1:
            return np.full((max(1, out_h), max(1, out_w)), float(mask.mean()), dtype=np.float32)

        y = np.linspace(0, src_h - 1, out_h, dtype=np.float32)
        x = np.linspace(0, src_w - 1, out_w, dtype=np.float32)
        y0 = np.floor(y).astype(np.int32)
        x0 = np.floor(x).astype(np.int32)
        y1 = np.minimum(y0 + 1, src_h - 1)
        x1 = np.minimum(x0 + 1, src_w - 1)
        wy = y - y0
        wx = x - x0

        ia = mask[y0[:, None], x0[None, :]]
        ib = mask[y0[:, None], x1[None, :]]
        ic = mask[y1[:, None], x0[None, :]]
        id_ = mask[y1[:, None], x1[None, :]]

        wa = (1.0 - wy)[:, None] * (1.0 - wx)[None, :]
        wb = (1.0 - wy)[:, None] * wx[None, :]
        wc = wy[:, None] * (1.0 - wx)[None, :]
        wd = wy[:, None] * wx[None, :]

        result = ia * wa + ib * wb + ic * wc + id_ * wd
        return result.astype(np.float32, copy=False)

    def _load_image_path_to_numpy(self, path: str) -> np.ndarray:
        existing_names = set(bpy.data.images.keys())
        loaded = bpy.data.images.load(path, check_existing=True)

        try:
            width, height = loaded.size
            channels = loaded.channels
            pixels = np.empty(len(loaded.pixels), dtype=np.float32)
            loaded.pixels.foreach_get(pixels)
            pixels = pixels.reshape((height, width, channels))
            pixels = np.flipud(pixels)
            return pixels
        finally:
            if loaded.name not in existing_names and loaded.users == 0:
                bpy.data.images.remove(loaded)

    def _rotate_mask_bilinear(self, mask: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_rad = np.deg2rad(angle_deg)
        cos_v = float(np.cos(angle_rad))
        sin_v = float(np.sin(angle_rad))

        src_h, src_w = mask.shape
        cy = (src_h - 1) * 0.5
        cx = (src_w - 1) * 0.5

        corners = np.array([
            [-cy, -cx],
            [-cy, src_w - 1 - cx],
            [src_h - 1 - cy, -cx],
            [src_h - 1 - cy, src_w - 1 - cx],
        ], dtype=np.float32)

        rot_y = corners[:, 0] * cos_v - corners[:, 1] * sin_v
        rot_x = corners[:, 0] * sin_v + corners[:, 1] * cos_v
        out_h = int(np.ceil(rot_y.max() - rot_y.min() + 1.0))
        out_w = int(np.ceil(rot_x.max() - rot_x.min() + 1.0))
        out_h = max(out_h, 1)
        out_w = max(out_w, 1)

        oy = np.arange(out_h, dtype=np.float32) - (out_h - 1) * 0.5
        ox = np.arange(out_w, dtype=np.float32) - (out_w - 1) * 0.5
        grid_y, grid_x = np.meshgrid(oy, ox, indexing='ij')

        src_y = grid_y * cos_v + grid_x * sin_v + cy
        src_x = -grid_y * sin_v + grid_x * cos_v + cx

        valid = (src_y >= 0.0) & (src_y <= src_h - 1) & (src_x >= 0.0) & (src_x <= src_w - 1)

        y0 = np.floor(src_y).astype(np.int32)
        x0 = np.floor(src_x).astype(np.int32)
        y1 = np.minimum(y0 + 1, src_h - 1)
        x1 = np.minimum(x0 + 1, src_w - 1)

        wy = src_y - y0
        wx = src_x - x0

        wa = (1.0 - wy) * (1.0 - wx)
        wb = (1.0 - wy) * wx
        wc = wy * (1.0 - wx)
        wd = wy * wx

        rotated = np.zeros((out_h, out_w), dtype=np.float32)
        rotated[valid] = (
            mask[y0[valid], x0[valid]] * wa[valid]
            + mask[y0[valid], x1[valid]] * wb[valid]
            + mask[y1[valid], x0[valid]] * wc[valid]
            + mask[y1[valid], x1[valid]] * wd[valid]
        )
        return rotated

    def _quantize_angle(self, angle_deg: float) -> int:
        normalized = angle_deg % 360.0
        return int(round((normalized / 360.0) * self.rotation_bins)) % self.rotation_bins

    def _get_rotated_brush_cached(self, brush: np.ndarray, angle_deg: float) -> np.ndarray:
        angle_bin = self._quantize_angle(angle_deg)
        cache_key = (id(brush), angle_bin)
        cached = self._rotation_cache.get(cache_key)
        if cached is not None:
            return cached

        quantized_angle = (angle_bin / self.rotation_bins) * 360.0
        rotated = self._rotate_mask_bilinear(brush, quantized_angle)
        self._rotation_cache[cache_key] = rotated
        return rotated
    
    def create_circular_brush(self, size):
        """Creates a soft circular brush mask as a NumPy array."""
        center = size / 2
        y, x = np.ogrid[-center:size-center, -center:size-center]
        dist = np.sqrt(x**2 + y**2)
        max_dist = size / 2
        mask = np.clip(1.0 - (dist / max_dist), 0.0, 1.0)
        return mask.astype(np.float32)
    
    def load_brush_texture(self, path):
        """Loads a brush texture and converts it to a grayscale mask."""
        try:
            if not os.path.exists(path):
                return self.create_circular_brush(50)

            brush_img = self._load_image_path_to_numpy(path)

            if brush_img.ndim == 3 and brush_img.shape[2] >= 4:
                brush_mask = brush_img[..., 3]
            else:
                brush_mask = self._rgb_to_gray(brush_img)
            brush_mask = np.clip(brush_mask, 0.0, 1.0).astype(np.float32, copy=False)
            
            # Handle non-square brush textures
            original_h, original_w = brush_mask.shape
            if original_h != original_w:
                max_dim = max(original_h, original_w)
                square_brush = np.zeros((max_dim, max_dim), dtype=brush_mask.dtype)
                offset_y = (max_dim - original_h) // 2
                offset_x = (max_dim - original_w) // 2
                square_brush[offset_y:offset_y + original_h, offset_x:offset_x + original_w] = brush_mask
                brush_mask = square_brush
                
            return brush_mask
            
        except Exception as e:
            print(f"Error loading brush texture: {e}. Using fallback circular brush.")
            return self.create_circular_brush(50)
    
    def load_multiple_brushes(self, folder_path):
        """Loads all brush textures from a folder."""
        brush_list = []
        
        if not os.path.exists(folder_path):
            return [self.create_circular_brush(50)]
        
        image_extensions = ['*.png', '*.jpg', '*.jpeg', '*.bmp', '*.tiff']
        brush_files = []
        
        for ext in image_extensions:
            brush_files.extend(glob.glob(os.path.join(folder_path, ext)))
            brush_files.extend(glob.glob(os.path.join(folder_path, ext.upper())))
        
        if not brush_files:
            return [self.create_circular_brush(50)]
        
        for brush_file in brush_files:
            try:
                brush_mask = self.load_brush_texture(brush_file)
                brush_list.append(brush_mask)
            except Exception as e:
                print(f"Error loading brush '{brush_file}': {e}. Skipping.")
                continue
        
        if not brush_list:
            return [self.create_circular_brush(50)]
        
        return brush_list
    
    def resize_brushes(self, brush_list, size):
        """Resizes a list of brush masks to the specified size."""
        size = max(1, int(size))
        resized_brush_list = []
        for brush in brush_list:
            resized_array = self._resize_mask_bilinear(brush.astype(np.float32, copy=False), size, size)
            resized_brush_list.append(resized_array)
        return resized_brush_list
    
    def calculate_gaussian_blur(self, img_float):
        """Calculates Gaussian blur for the image using numpy."""
        if self.gaussian_sigma <= 0:
            return img_float.astype(np.float32, copy=True)

        image = np.clip(img_float, 0.0, 1.0).astype(np.float32, copy=False)
        if image.ndim == 3 and image.shape[2] == 4:
            alpha = image[..., 3:4]
            premult_rgb = image[..., :3] * alpha
            premult_rgba = np.concatenate((premult_rgb, alpha), axis=2)
            blurred = self._gaussian_blur_array(premult_rgba, float(self.gaussian_sigma))
            out_alpha = blurred[..., 3:4]
            safe_alpha = np.where(out_alpha > 1e-6, out_alpha, 1.0)
            out_rgb = np.where(out_alpha > 1e-6, blurred[..., :3] / safe_alpha, 0.0)
            return np.clip(np.concatenate((out_rgb, out_alpha), axis=2), 0.0, 1.0).astype(np.float32, copy=False)

        return self._gaussian_blur_array(image, float(self.gaussian_sigma))
    
    def calculate_sobel_filter(self, img_float):
        """Calculates Sobel filter for the image using numpy."""
        gray = self._rgb_to_gray(np.clip(img_float, 0.0, 1.0).astype(np.float32, copy=False))
        padded = np.pad(gray, ((1, 1), (1, 1)), mode='edge')

        Gx = (
            padded[:-2, 2:] + 2.0 * padded[1:-1, 2:] + padded[2:, 2:]
            - padded[:-2, :-2] - 2.0 * padded[1:-1, :-2] - padded[2:, :-2]
        )
        Gy = (
            padded[2:, :-2] + 2.0 * padded[2:, 1:-1] + padded[2:, 2:]
            - padded[:-2, :-2] - 2.0 * padded[:-2, 1:-1] - padded[:-2, 2:]
        )

        return Gx, Gy
    
    def calculate_gradients(self, img_float):
        """Calculates gradient magnitude and orientation for brush stroke direction."""
        gray = self._rgb_to_gray(np.clip(img_float, 0.0, 1.0).astype(np.float32, copy=False))
        img_smoothed = self._gaussian_blur_array(gray, float(self.gaussian_sigma))

        Gx, Gy = self.calculate_sobel_filter(img_smoothed)
        G = np.hypot(Gx, Gy)
        theta = np.arctan2(Gy, Gx)
        g_max = float(np.max(G))
        if g_max <= 1e-6:
            G_normalized = np.zeros_like(G, dtype=np.float32)
        else:
            G_normalized = (G / g_max).astype(np.float32, copy=False)
        
        return G_normalized, theta
    
    def calculate_brush_area_density(self, brush_list, H, W, brush_size):
        """Calculates the number of samples needed to achieve target coverage."""
        total_brush_area = 0
        for brush in brush_list:
            brush_area = np.sum(brush > 0)
            total_brush_area += brush_area
        
        avg_brush_area = total_brush_area / len(brush_list)
        image_area = H * W
        target_coverage_area = image_area * self.brush_coverage_density
        overlap_factor = 0.7
        num_samples = int(target_coverage_area / (avg_brush_area * overlap_factor))
        
        min_samples = 50
        max_samples = image_area // 8
        num_samples = max(min_samples, min(num_samples, max_samples))
        
        return num_samples
    
    def create_extended_canvas(self, img_float, H, W, overlay_on_input=True):
        """Creates an extended canvas to prevent rotation clipping."""
        sqrt2 = np.sqrt(2) * 2
        extended_H = int(H * sqrt2)
        extended_W = int(W * sqrt2)
        
        offset_y = (extended_H - H) // 2
        offset_x = (extended_W - W) // 2
        
        if overlay_on_input:
            canvas = np.zeros((extended_H, extended_W, 4), dtype=np.float32)
            canvas[offset_y:offset_y + H, offset_x:offset_x + W] = img_float
        else:
            canvas = np.zeros((extended_H, extended_W, 4), dtype=np.float32)
        
        return canvas, extended_H, extended_W, offset_y, offset_x
    
    def apply_color_shift(self, pixel):
        """Applies randomized HSV color shifts to a pixel based on shift parameters."""
        if len(pixel) < 3:
            return pixel
        
        # Convert RGB to HSV
        r, g, b = pixel[:3]
        
        # Convert to HSV using standard RGB to HSV conversion
        max_val = max(r, g, b)
        min_val = min(r, g, b)
        delta = max_val - min_val
        
        # Calculate Hue
        if delta == 0:
            h = 0
        elif max_val == r:
            h = 60 * ((g - b) / delta) % 360
        elif max_val == g:
            h = 60 * (2 + (b - r) / delta) % 360
        else:  # max_val == b
            h = 60 * (4 + (r - g) / delta) % 360
        
        # Calculate Saturation
        s = 0 if max_val == 0 else delta / max_val
        
        # Calculate Value
        v = max_val
        
        # Apply randomized shifts
        # Hue: randomize within the shift range
        if self.hue_shift > 0:
            hue_range = self.hue_shift * 360
            h_random = np.random.uniform(-hue_range/2, hue_range/2)
            h = (h + h_random) % 360
        
        # Saturation: randomize within the shift range
        if self.saturation_shift > 0:
            s_range = self.saturation_shift
            s_random = np.random.uniform(-s_range/2, s_range/2)
            s = np.clip(s + s_random, 0, 1)
        
        # Value: randomize within the shift range
        if self.value_shift > 0:
            v_range = self.value_shift
            v_random = np.random.uniform(-v_range/2, v_range/2)
            v = np.clip(v + v_random, 0, 1)
        
        # Convert back to RGB
        c = v * s
        x = c * (1 - abs((h / 60) % 2 - 1))
        m = v - c
        
        if 0 <= h < 60:
            r_new, g_new, b_new = c, x, 0
        elif 60 <= h < 120:
            r_new, g_new, b_new = x, c, 0
        elif 120 <= h < 180:
            r_new, g_new, b_new = 0, c, x
        elif 180 <= h < 240:
            r_new, g_new, b_new = 0, x, c
        elif 240 <= h < 300:
            r_new, g_new, b_new = x, 0, c
        else:  # 300 <= h < 360
            r_new, g_new, b_new = c, 0, x
        
        # Add back the offset and ensure values are in [0, 1]
        r_final = np.clip(r_new + m, 0, 1)
        g_final = np.clip(g_new + m, 0, 1)
        b_final = np.clip(b_new + m, 0, 1)
        
        # Return the modified pixel with original alpha if present
        if len(pixel) == 4:
            return np.array([r_final, g_final, b_final, pixel[3]])
        else:
            return np.array([r_final, g_final, b_final])

    def _tile_from_uv_int(self, tile_u: int, tile_v: int) -> int:
        return 1001 + tile_u + tile_v * 10

    def _uv_to_tile_and_local(self, uv: Tuple[float, float]) -> Tuple[int, float, float]:
        uv_u, uv_v = uv
        # Use ceil-1 (clamped to 0) to match get_udim_tiles convention:
        # boundary points (e.g. u=1.0) belong to the lower tile, not the higher one.
        tile_u = max(0, int(np.ceil(uv_u)) - 1)
        tile_v = max(0, int(np.ceil(uv_v)) - 1)
        tile_num = self._tile_from_uv_int(tile_u, tile_v)
        local_u = uv_u - tile_u
        local_v = uv_v - tile_v
        return tile_num, local_u, local_v

    def _tile_uv_local_to_px(self, local_u: float, local_v: float, height: int, width: int) -> Tuple[float, float]:
        scale_x = float(max(width - 1, 1))
        scale_y = float(max(height - 1, 1))
        px_x = local_u * scale_x
        px_y = (1.0 - local_v) * scale_y
        return px_x, px_y

    def _canonical_uv_pair_key(
        self,
        uv0: Tuple[float, float],
        uv1: Tuple[float, float],
    ) -> Tuple[Tuple[float, float], Tuple[float, float]]:
        if uv0 <= uv1:
            return uv0, uv1
        return uv1, uv0

    def _point_inside_rect(self, px: float, py: float, rect: Tuple[float, float, float, float]) -> bool:
        min_x, max_x, min_y, max_y = rect
        return min_x <= px <= max_x and min_y <= py <= max_y

    def _orientation(self, p0: Tuple[float, float], p1: Tuple[float, float], p2: Tuple[float, float]) -> float:
        return (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p1[1] - p0[1]) * (p2[0] - p0[0])

    def _segments_intersect(
        self,
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        q1: Tuple[float, float],
        q2: Tuple[float, float],
    ) -> bool:
        eps = 1e-6
        o1 = self._orientation(p1, p2, q1)
        o2 = self._orientation(p1, p2, q2)
        o3 = self._orientation(q1, q2, p1)
        o4 = self._orientation(q1, q2, p2)

        if (o1 * o2 < -eps) and (o3 * o4 < -eps):
            return True

        def on_segment(a: Tuple[float, float], b: Tuple[float, float], c: Tuple[float, float]) -> bool:
            return (
                min(a[0], b[0]) - eps <= c[0] <= max(a[0], b[0]) + eps
                and min(a[1], b[1]) - eps <= c[1] <= max(a[1], b[1]) + eps
            )

        if abs(o1) <= eps and on_segment(p1, p2, q1):
            return True
        if abs(o2) <= eps and on_segment(p1, p2, q2):
            return True
        if abs(o3) <= eps and on_segment(q1, q2, p1):
            return True
        if abs(o4) <= eps and on_segment(q1, q2, p2):
            return True
        return False

    def _segment_intersects_rect(
        self,
        seg0: Tuple[float, float],
        seg1: Tuple[float, float],
        rect: Tuple[float, float, float, float],
    ) -> bool:
        min_x, max_x, min_y, max_y = rect
        if self._point_inside_rect(seg0[0], seg0[1], rect) or self._point_inside_rect(seg1[0], seg1[1], rect):
            return True

        rect_edges = [
            ((min_x, min_y), (max_x, min_y)),
            ((max_x, min_y), (max_x, max_y)),
            ((max_x, max_y), (min_x, max_y)),
            ((min_x, max_y), (min_x, min_y)),
        ]
        for edge_start, edge_end in rect_edges:
            if self._segments_intersect(seg0, seg1, edge_start, edge_end):
                return True
        return False

    def _point_to_segment_distance_sq(
        self,
        px: float,
        py: float,
        seg0: Tuple[float, float],
        seg1: Tuple[float, float],
    ) -> float:
        sx = seg1[0] - seg0[0]
        sy = seg1[1] - seg0[1]
        denom = sx * sx + sy * sy
        if denom <= 1e-8:
            dx = px - seg0[0]
            dy = py - seg0[1]
            return dx * dx + dy * dy
        t = ((px - seg0[0]) * sx + (py - seg0[1]) * sy) / denom
        t = min(1.0, max(0.0, t))
        cx = seg0[0] + t * sx
        cy = seg0[1] + t * sy
        dx = px - cx
        dy = py - cy
        return dx * dx + dy * dy

    def _project_point_on_segment_t(
        self,
        px: float,
        py: float,
        seg0: Tuple[float, float],
        seg1: Tuple[float, float],
    ) -> float:
        sx = seg1[0] - seg0[0]
        sy = seg1[1] - seg0[1]
        denom = sx * sx + sy * sy
        if denom <= 1e-8:
            return 0.5
        t = ((px - seg0[0]) * sx + (py - seg0[1]) * sy) / denom
        return min(1.0, max(0.0, t))

    def _can_place_rotated_brush(
        self,
        state: TilePaintState,
        center_y: float,
        center_x: float,
        rotated_brush: np.ndarray,
    ) -> bool:
        """Returns True if any part of the brush overlaps the canvas (not entirely outside)."""
        brush_h, brush_w = rotated_brush.shape
        canvas_y = int(round(center_y)) + state.offset_y
        canvas_x = int(round(center_x)) + state.offset_x
        start_y = canvas_y - brush_h // 2
        start_x = canvas_x - brush_w // 2
        end_y = start_y + brush_h
        end_x = start_x + brush_w
        return start_y < state.extended_h and end_y > 0 and start_x < state.extended_w and end_x > 0

    def _blend_rotated_brush(
        self,
        state: TilePaintState,
        center_y: float,
        center_x: float,
        sampled_pixel: np.ndarray,
        sampled_alpha: float,
        opacity: float,
        rotated_brush: np.ndarray,
    ) -> bool:
        if rotated_brush.size == 0 or float(np.max(rotated_brush)) <= 1e-6:
            if DEBUG_CANCEL:
                print(f"[CANCEL] _blend_rotated_brush: brush is empty or zero "
                      f"(size={rotated_brush.size}, max={float(np.max(rotated_brush)) if rotated_brush.size > 0 else 0:.6f}) "
                      f"at center=({center_x:.1f},{center_y:.1f}) tile={state.tile_num}")
            return False

        brush_h, brush_w = rotated_brush.shape
        canvas_y = int(round(center_y)) + state.offset_y
        canvas_x = int(round(center_x)) + state.offset_x
        start_y = canvas_y - brush_h // 2
        start_x = canvas_x - brush_w // 2
        end_y = start_y + brush_h
        end_x = start_x + brush_w

        # Clip to canvas bounds — allow partial overlaps, cancel only if entirely outside
        clip_y0 = max(0, start_y)
        clip_x0 = max(0, start_x)
        clip_y1 = min(state.extended_h, end_y)
        clip_x1 = min(state.extended_w, end_x)

        if clip_y0 >= clip_y1 or clip_x0 >= clip_x1:
            if DEBUG_CANCEL:
                print(f"[CANCEL] _blend_rotated_brush: entirely outside canvas "
                      f"at center=({center_x:.1f},{center_y:.1f}) tile={state.tile_num} "
                      f"brush=({brush_w}x{brush_h}) "
                      f"brush_region=[{start_x}:{end_x}, {start_y}:{end_y}] "
                      f"canvas_size=({state.extended_w}x{state.extended_h})")
            return False

        # Corresponding slice into the brush array
        brush_y0 = clip_y0 - start_y
        brush_x0 = clip_x0 - start_x
        clip_h = clip_y1 - clip_y0
        clip_w = clip_x1 - clip_x0
        brush_y1 = brush_y0 + clip_h
        brush_x1 = brush_x0 + clip_w

        canvas_region = state.canvas[clip_y0:clip_y1, clip_x0:clip_x1]
        brush_slice = rotated_brush[brush_y0:brush_y1, brush_x0:brush_x1]
        brush_color_layer = np.tile(sampled_pixel[:3], (clip_h, clip_w, 1))
        final_alpha = brush_slice * sampled_alpha * opacity
        final_alpha_3d = final_alpha[..., np.newaxis]

        canvas_rgb = canvas_region[:, :, :3]
        canvas_alpha = canvas_region[:, :, 3:4]

        out_alpha = final_alpha_3d + canvas_alpha * (1.0 - final_alpha_3d)
        numerator = brush_color_layer * final_alpha_3d + canvas_rgb * canvas_alpha * (1.0 - final_alpha_3d)

        safe_alpha = np.copy(out_alpha)
        safe_alpha[safe_alpha < 0.0001] = 1.0

        canvas_region[:, :, :3] = numerator / safe_alpha
        canvas_region[:, :, 3:4] = out_alpha
        return True

    def _build_uv_seam_index(
        self,
        mesh_object: Optional[bpy.types.Object],
        uv_map_name: Optional[str],
        tile_shapes: Dict[int, Tuple[int, int]],
    ) -> Optional[UVSeamIndex]:
        """Build seam index using bmesh for reliable manifold edge detection."""
        if not mesh_object or mesh_object.type != 'MESH' or not uv_map_name:
            return None

        mesh = mesh_object.data
        if not mesh:
            return None

        bm = bmesh.new()
        bm.from_mesh(mesh)
        bm.verts.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.faces.ensure_lookup_table()

        uv_layer = bm.loops.layers.uv.get(uv_map_name)
        if uv_layer is None:
            bm.free()
            return None

        eps = 1e-5
        seam_edges: List[UVSeamEdge] = []

        for edge in bm.edges:
            # Only manifold edges (exactly 2 adjacent faces) can be seams
            if len(edge.link_faces) != 2:
                continue

            face_a, face_b = edge.link_faces[0], edge.link_faces[1]
            v0, v1 = edge.verts[0], edge.verts[1]
            v0_idx = v0.index
            v1_idx = v1.index

            # Gather UV coords from both faces for v0 and v1
            uv_a_v0 = uv_a_v1 = None
            third_loop_a = None
            for loop in face_a.loops:
                if loop.vert == v0:
                    uv_a_v0 = loop[uv_layer].uv
                elif loop.vert == v1:
                    uv_a_v1 = loop[uv_layer].uv
                else:
                    if third_loop_a is None:
                        third_loop_a = loop

            uv_b_v0 = uv_b_v1 = None
            third_loop_b = None
            for loop in face_b.loops:
                if loop.vert == v0:
                    uv_b_v0 = loop[uv_layer].uv
                elif loop.vert == v1:
                    uv_b_v1 = loop[uv_layer].uv
                else:
                    if third_loop_b is None:
                        third_loop_b = loop

            if uv_a_v0 is None or uv_a_v1 is None or uv_b_v0 is None or uv_b_v1 is None:
                continue

            # Skip non-seam edges (same UVs on both sides)
            if (abs(uv_a_v0.x - uv_b_v0.x) < eps and abs(uv_a_v0.y - uv_b_v0.y) < eps and
                abs(uv_a_v1.x - uv_b_v1.x) < eps and abs(uv_a_v1.y - uv_b_v1.y) < eps):
                continue

            edge_key = (v0_idx, v1_idx) if v0_idx < v1_idx else (v1_idx, v0_idx)

            # Process each face side of the seam edge
            sides_data = []
            for face_uv0, face_uv1, third_loop in [
                (uv_a_v0, uv_a_v1, third_loop_a),
                (uv_b_v0, uv_b_v1, third_loop_b),
            ]:
                fu0 = (float(face_uv0.x), float(face_uv0.y))
                fu1 = (float(face_uv1.x), float(face_uv1.y))

                tile0, local_u0, local_v0 = self._uv_to_tile_and_local(fu0)
                tile1, local_u1, local_v1 = self._uv_to_tile_and_local(fu1)
                if tile0 != tile1:
                    if DEBUG_SEAM:
                        print(f"[SEAM-BUILD] edge verts=({v0_idx},{v1_idx}): "
                              f"UV endpoints span different tiles ({tile0} vs {tile1}), skipping side")
                    sides_data.append(None)
                    continue

                tile_shape = tile_shapes.get(tile0)
                if tile_shape is None:
                    if DEBUG_SEAM:
                        print(f"[SEAM-BUILD] edge verts=({v0_idx},{v1_idx}): "
                              f"tile {tile0} not in tile_shapes, skipping side")
                    sides_data.append(None)
                    continue

                tile_h, tile_w = tile_shape
                px0 = self._tile_uv_local_to_px(local_u0, local_v0, tile_h, tile_w)
                px1 = self._tile_uv_local_to_px(local_u1, local_v1, tile_h, tile_w)

                # Face side via third vertex cross product
                face_side = 0
                if third_loop is not None:
                    third_uv = third_loop[uv_layer].uv
                    third_uv_t = (float(third_uv.x), float(third_uv.y))
                    t_tile, t_lu, t_lv = self._uv_to_tile_and_local(third_uv_t)
                    if t_tile == tile0:
                        t_px = self._tile_uv_local_to_px(t_lu, t_lv, tile_h, tile_w)
                        cross = ((px1[0] - px0[0]) * (t_px[1] - px0[1])
                                 - (px1[1] - px0[1]) * (t_px[0] - px0[0]))
                        face_side = 1 if cross > 0 else (-1 if cross < 0 else 0)

                sides_data.append({
                    'uv0': fu0,
                    'uv1': fu1,
                    'tile_num': tile0,
                    'px0': px0,
                    'px1': px1,
                    'face_side': face_side,
                    'length_uv': float(np.hypot(fu1[0] - fu0[0], fu1[1] - fu0[1])),
                })

            # Both sides must be valid to form a seam pair
            if sides_data[0] is None or sides_data[1] is None:
                if DEBUG_SEAM:
                    print(f"[SEAM-BUILD] edge verts=({v0_idx},{v1_idx}): "
                          f"one or both sides invalid (sides[0]={'None' if sides_data[0] is None else 'ok'}, "
                          f"sides[1]={'None' if sides_data[1] is None else 'ok'}), skipping pair")
                continue

            # Create paired seam edges (counterparts point to each other)
            idx_a = len(seam_edges)
            idx_b = idx_a + 1

            for side, counterpart_idx in [(sides_data[0], idx_b), (sides_data[1], idx_a)]:
                seam_edges.append(UVSeamEdge(
                    edge_key=edge_key,
                    uv0=side['uv0'],
                    uv1=side['uv1'],
                    tile_num=side['tile_num'],
                    px0=side['px0'],
                    px1=side['px1'],
                    midpoint_uv=((side['uv0'][0] + side['uv1'][0]) * 0.5,
                                 (side['uv0'][1] + side['uv1'][1]) * 0.5),
                    length_uv=side['length_uv'],
                    vert0=v0_idx,
                    vert1=v1_idx,
                    face_side=side['face_side'],
                    counterpart_index=counterpart_idx,
                ))

        bm.free()

        if not seam_edges:
            if DEBUG_SEAM:
                print("[SEAM-BUILD] No valid seam edges found — seam duplication disabled")
            return None

        tile_to_edges: Dict[int, List[int]] = {}
        for edge_index, seam_edge in enumerate(seam_edges):
            tile_to_edges.setdefault(seam_edge.tile_num, []).append(edge_index)

        # if DEBUG_SEAM:
        #     matched = sum(1 for e in seam_edges if e.counterpart_index >= 0)
        #     print(f"[SEAM] Built {len(seam_edges)} seam edges ({len(seam_edges)//2} pairs), "
        #           f"{matched}/{len(seam_edges)} matched")
        #     for ei, se in enumerate(seam_edges):
        #         cp = se.counterpart_index
        #         cp_tile = seam_edges[cp].tile_num if cp >= 0 else None
        #         print(f"  edge[{ei}] tile={se.tile_num} verts=({se.vert0},{se.vert1}) "
        #               f"px0=({se.px0[0]:.1f},{se.px0[1]:.1f}) px1=({se.px1[0]:.1f},{se.px1[1]:.1f}) "
        #               f"face_side={se.face_side} len_uv={se.length_uv:.4f} "
        #               f"counterpart={cp}(tile={cp_tile})")
        #     for tile_num, indices in tile_to_edges.items():
        #         print(f"  tile {tile_num}: {len(indices)} seam edges")

        return UVSeamIndex(edges=seam_edges, tile_to_edges=tile_to_edges)

    def _find_nearest_intersecting_edge(
        self,
        tile_num: int,
        center_x: float,
        center_y: float,
        brush_h: int,
        brush_w: int,
    ) -> int:
        if self._seam_index is None:
            return -1

        edge_indices = self._seam_index.tile_to_edges.get(tile_num, [])
        if not edge_indices:
            return -1

        half_w = brush_w * 0.5
        half_h = brush_h * 0.5
        rect = (
            center_x - half_w,
            center_x + half_w,
            center_y - half_h,
            center_y + half_h,
        )

        nearest_edge_index = -1
        nearest_dist_sq = float('inf')
        for edge_index in edge_indices:
            seam_edge = self._seam_index.edges[edge_index]
            if not self._segment_intersects_rect(seam_edge.px0, seam_edge.px1, rect):
                continue
            dist_sq = self._point_to_segment_distance_sq(center_x, center_y, seam_edge.px0, seam_edge.px1)
            if dist_sq < nearest_dist_sq:
                nearest_dist_sq = dist_sq
                nearest_edge_index = edge_index

        return nearest_edge_index

    def _compute_duplicate_size(
        self,
        source_size_px: int,
        source_edge_len: float,
        target_edge_len: float,
        min_size_px: int,
        max_size_px: int,
    ) -> int:
        if source_edge_len <= 1e-8:
            return source_size_px
        ratio = target_edge_len / source_edge_len
        duplicate_size = int(round(source_size_px * ratio))
        if duplicate_size < min_size_px or duplicate_size > max_size_px:
            return -1
        return max(1, duplicate_size)

    def _prepare_tile_state(
        self,
        tile_num: int,
        tile_array: np.ndarray,
        custom_tile_array: Optional[np.ndarray] = None,
    ) -> TilePaintState:
        img_float = np.clip(tile_array, 0.0, 1.0).astype(np.float32, copy=False)
        height, width = img_float.shape[:2]
        has_alpha = img_float.shape[2] == 4 if img_float.ndim == 3 else False
        img_blurred = self.calculate_gaussian_blur(img_float)

        if custom_tile_array is not None:
            custom_float = np.clip(custom_tile_array, 0.0, 1.0).astype(np.float32, copy=False)
            custom_blurred = self.calculate_gaussian_blur(custom_float)
            g_normalized, theta = self.calculate_gradients(custom_blurred)
        else:
            g_normalized, theta = self.calculate_gradients(img_float)

        canvas, extended_h, extended_w, offset_y, offset_x = self.create_extended_canvas(
            img_float,
            height,
            width,
            overlay_on_input=True,
        )

        base_dim = min(height, width)
        min_size_px = max(1, int(self.min_brush_scale * base_dim))
        max_size_px = max(1, int(self.max_brush_scale * base_dim))
        if min_size_px > max_size_px:
            min_size_px, max_size_px = max_size_px, min_size_px

        return TilePaintState(
            tile_num=tile_num,
            img_float=img_float,
            img_blurred=img_blurred,
            g_normalized=g_normalized,
            theta=theta,
            has_alpha=has_alpha,
            canvas=canvas,
            extended_h=extended_h,
            extended_w=extended_w,
            offset_y=offset_y,
            offset_x=offset_x,
            height=height,
            width=width,
            min_size_px=min_size_px,
            max_size_px=max_size_px,
        )

    def _apply_stamp_with_optional_duplicate(
        self,
        tile_states: Dict[int, TilePaintState],
        source_tile_num: int,
        y: int,
        x: int,
        opacity: float,
        selected_brush: np.ndarray,
        base_brush_size: int,
    ) -> bool:
        source_state = tile_states[source_tile_num]
        sampled_pixel = source_state.img_blurred[y, x]
        sampled_pixel = self.apply_color_shift(sampled_pixel)
        sampled_alpha = sampled_pixel[3] if source_state.has_alpha else 1.0
        if sampled_alpha <= 1e-6:
            # if DEBUG_CANCEL:
            #     print(f"[CANCEL] pos=({x},{y}) tile={source_tile_num}: "
            #           f"sampled_alpha {sampled_alpha:.6f} <= 1e-6 (pixel is fully transparent)")
            return False

        magnitude = source_state.g_normalized[y, x]
        if magnitude < self.gradient_threshold:
            if DEBUG_CANCEL:
                print(f"[CANCEL] pos=({x},{y}) tile={source_tile_num}: "
                      f"magnitude {magnitude:.4f} < threshold {self.gradient_threshold:.4f}")
            return False

        angle_deg = np.rad2deg(source_state.theta[y, x])
        brush_angle = angle_deg + self.brush_rotation_offset
        if self.use_random_rotation:
            half = self.random_rotation_range * 0.5
            brush_angle += float(np.random.uniform(-half, half))
        angle_bin = self._quantize_angle(brush_angle)
        
        if DEBUG_ROTATION and hasattr(self, '_debug_rotation_count'):
            if self._debug_rotation_count < 20:
                print(f"[ROTATION] pos=({x},{y}) tile={source_tile_num}: "
                      f"gradient_angle={angle_deg:.1f}° brush_angle={brush_angle:.1f}° "
                      f"bin={angle_bin}/{self.rotation_bins} quantized={(angle_bin/self.rotation_bins)*360:.1f}°")
                self._debug_rotation_count += 1
        
        source_rotated = self._get_rotated_brush_cached(selected_brush, brush_angle)
        if source_rotated.size == 0 or float(np.max(source_rotated)) <= 1e-6:
            if DEBUG_CANCEL:
                print(f"[CANCEL] pos=({x},{y}) tile={source_tile_num}: "
                      f"source_rotated empty or zero (size={source_rotated.size}, max={float(np.max(source_rotated)) if source_rotated.size > 0 else 0:.6f})")
            return False

        seam_triggered_edge = -1
        if self.enable_seam_duplication and self._seam_index is not None:
            source_h, source_w = source_rotated.shape
            seam_triggered_edge = self._find_nearest_intersecting_edge(
                source_tile_num,
                float(x),
                float(y),
                source_h,
                source_w,
            )

        if seam_triggered_edge < 0:
            return self._blend_rotated_brush(
                source_state,
                float(y),
                float(x),
                sampled_pixel,
                sampled_alpha,
                opacity,
                source_rotated,
            )

        source_edge = self._seam_index.edges[seam_triggered_edge]
        counterpart_index = source_edge.counterpart_index
        if counterpart_index < 0:
            if DEBUG_SEAM:
                print(f"[SEAM-STAMP] edge[{seam_triggered_edge}] has no counterpart, skip dup")
            return self._blend_rotated_brush(
                source_state,
                float(y),
                float(x),
                sampled_pixel,
                sampled_alpha,
                opacity,
                source_rotated,
            )

        counterpart_edge = self._seam_index.edges[counterpart_index]
        target_state = tile_states.get(counterpart_edge.tile_num)
        if target_state is None:
            if DEBUG_SEAM:
                print(f"[SEAM-STAMP] counterpart tile {counterpart_edge.tile_num} not in tile_states, skip dup")
            return self._blend_rotated_brush(
                source_state,
                float(y),
                float(x),
                sampled_pixel,
                sampled_alpha,
                opacity,
                source_rotated,
            )

        target_size_px = self._compute_duplicate_size(
            base_brush_size,
            source_edge.length_uv,
            counterpart_edge.length_uv,
            source_state.min_size_px,
            source_state.max_size_px,
        )
        if target_size_px < 0:
            if DEBUG_CANCEL:
                ratio = counterpart_edge.length_uv / source_edge.length_uv if source_edge.length_uv > 1e-8 else 1.0
                computed = int(round(base_brush_size * ratio))
                print(f"[CANCEL] pos=({x},{y}) tile={source_tile_num} edge[{seam_triggered_edge}]: "
                      f"duplicate size {computed} out of bounds [{source_state.min_size_px}, {source_state.max_size_px}] "
                      f"(base={base_brush_size}, ratio={ratio:.3f}) — source brush also not applied")
            return False

        # Project brush center onto source edge
        projected_t = self._project_point_on_segment_t(float(x), float(y), source_edge.px0, source_edge.px1)
        src_proj_x = source_edge.px0[0] + (source_edge.px1[0] - source_edge.px0[0]) * projected_t
        src_proj_y = source_edge.px0[1] + (source_edge.px1[1] - source_edge.px0[1]) * projected_t

        # Compute perpendicular offset from source edge
        src_dx = source_edge.px1[0] - source_edge.px0[0]
        src_dy = source_edge.px1[1] - source_edge.px0[1]
        src_len_px = float(np.hypot(src_dx, src_dy))
        signed_perp = 0.0
        if src_len_px > 1e-8:
            src_nx = -src_dy / src_len_px
            src_ny = src_dx / src_len_px
            signed_perp = (float(x) - src_proj_x) * src_nx + (float(y) - src_proj_y) * src_ny

        # Vertex-aligned counterpart endpoints to ensure correct t mapping
        swapped = source_edge.vert0 != counterpart_edge.vert0
        if not swapped:
            cpt_start = counterpart_edge.px0
            cpt_end = counterpart_edge.px1
        else:
            cpt_start = counterpart_edge.px1
            cpt_end = counterpart_edge.px0

        # Target projection at corresponding t
        tgt_proj_x = cpt_start[0] + (cpt_end[0] - cpt_start[0]) * projected_t
        tgt_proj_y = cpt_start[1] + (cpt_end[1] - cpt_start[1]) * projected_t

        # Determine whether faces are on opposite sides of their respective
        # aligned edge directions.  face_side is stored relative to each edge's
        # own px0→px1 direction.  When we vertex-align the counterpart (swap),
        # its effective side flips because the direction reverses.
        source_side = source_edge.face_side
        counterpart_effective_side = (
            -counterpart_edge.face_side if swapped else counterpart_edge.face_side
        )
        # Opposite face sides → reflect (preserve perpendicular + mirror angle).
        # Same face sides → rotate (negate perpendicular + rotate angle).
        # Default to reflection when face_side is unknown (0).
        need_reflection = True
        if source_side != 0 and counterpart_effective_side != 0:
            need_reflection = (source_side != counterpart_effective_side)

        # Apply perpendicular offset on counterpart.
        # The duplicate center must land on the OPPOSITE side of the counterpart
        # edge from the counterpart face interior for correct bleed-over.
        # Reflection (opposite face sides): counterpart normal points AWAY from
        #   its face, so preserving signed_perp lands the center away. → PRESERVE
        # Rotation (same face sides): counterpart normal points TOWARD its face,
        #   so we negate to land on the opposite side. → NEGATE
        cpt_dx = cpt_end[0] - cpt_start[0]
        cpt_dy = cpt_end[1] - cpt_start[1]
        cpt_len_px = float(np.hypot(cpt_dx, cpt_dy))
        if cpt_len_px > 1e-8 and src_len_px > 1e-8:
            cpt_nx = -cpt_dy / cpt_len_px
            cpt_ny = cpt_dx / cpt_len_px
            scale_ratio = cpt_len_px / src_len_px
            if need_reflection:
                mapped_perp = signed_perp * scale_ratio
            else:
                mapped_perp = -signed_perp * scale_ratio
            target_center_x = tgt_proj_x + mapped_perp * cpt_nx
            target_center_y = tgt_proj_y + mapped_perp * cpt_ny
        else:
            target_center_x = tgt_proj_x
            target_center_y = tgt_proj_y

        # Compute duplicate brush rotation.
        source_edge_angle_deg = float(np.rad2deg(np.arctan2(src_dy, src_dx)))
        target_edge_angle_deg = float(np.rad2deg(np.arctan2(cpt_dy, cpt_dx)))
        if need_reflection:
            # Reflect across source edge, then map to target edge:
            # dup_angle = target_edge_angle + source_edge_angle - brush_angle
            duplicate_angle = target_edge_angle_deg + source_edge_angle_deg - brush_angle
        else:
            # Pure rotation by the edge angle difference:
            # dup_angle = brush_angle + (target_edge_angle - source_edge_angle)
            duplicate_angle = brush_angle + (target_edge_angle_deg - source_edge_angle_deg)

        # if DEBUG_SEAM:
        #     print(f"[SEAM-STAMP] src=({x},{y}) tile={source_tile_num} "
        #           f"edge[{seam_triggered_edge}]→cpt[{counterpart_index}] "
        #           f"t={projected_t:.3f} perp={signed_perp:.1f}")
        #     print(f"  src_edge: px0=({source_edge.px0[0]:.1f},{source_edge.px0[1]:.1f}) "
        #           f"px1=({source_edge.px1[0]:.1f},{source_edge.px1[1]:.1f}) "
        #           f"verts=({source_edge.vert0},{source_edge.vert1}) face_side={source_edge.face_side}")
        #     print(f"  cpt_edge: px0=({counterpart_edge.px0[0]:.1f},{counterpart_edge.px0[1]:.1f}) "
        #           f"px1=({counterpart_edge.px1[0]:.1f},{counterpart_edge.px1[1]:.1f}) "
        #           f"verts=({counterpart_edge.vert0},{counterpart_edge.vert1}) face_side={counterpart_edge.face_side}")
        #     print(f"  swapped={swapped} src_side={source_side} cpt_eff_side={counterpart_effective_side} "
        #           f"need_reflection={need_reflection}")
        #     print(f"  src_edge_angle={source_edge_angle_deg:.1f}° cpt_edge_angle={target_edge_angle_deg:.1f}°")
        #     print(f"  brush_angle={brush_angle:.1f}° → dup_angle={duplicate_angle:.1f}°")
        #     print(f"  mapped_perp={mapped_perp if (cpt_len_px > 1e-8 and src_len_px > 1e-8) else 0:.1f} "
        #           f"target=({target_center_x:.1f},{target_center_y:.1f}) "
        #           f"target_tile={counterpart_edge.tile_num} target_size={target_size_px}")

        if target_size_px == base_brush_size:
            duplicate_brush = selected_brush
        else:
            duplicate_brush = self._resize_mask_bilinear(selected_brush, target_size_px, target_size_px)

        duplicate_rotated = self._get_rotated_brush_cached(duplicate_brush, duplicate_angle)
        if duplicate_rotated.size == 0 or float(np.max(duplicate_rotated)) <= 1e-6:
            if DEBUG_CANCEL:
                print(f"[CANCEL] pos=({x},{y}) tile={source_tile_num} edge[{seam_triggered_edge}]: "
                      f"duplicate_rotated empty or zero (size={duplicate_rotated.size}, max={float(np.max(duplicate_rotated)) if duplicate_rotated.size > 0 else 0:.6f}) "
                      f"— source brush also not applied")
            return False

        can_place_source = self._can_place_rotated_brush(source_state, float(y), float(x), source_rotated)
        can_place_target = self._can_place_rotated_brush(target_state, target_center_y, target_center_x, duplicate_rotated)
        if not (can_place_source and can_place_target):
            if DEBUG_CANCEL:
                print(f"[CANCEL] pos=({x},{y}) tile={source_tile_num} edge[{seam_triggered_edge}]: "
                      f"placement failed (can_place_source={can_place_source}, can_place_target={can_place_target}) "
                      f"src_brush={source_rotated.shape} tgt_brush={duplicate_rotated.shape} "
                      f"tgt_center=({target_center_x:.1f},{target_center_y:.1f}) tgt_tile={counterpart_edge.tile_num} "
                      f"— source brush also not applied")
            return False

        source_applied = self._blend_rotated_brush(
            source_state,
            float(y),
            float(x),
            sampled_pixel,
            sampled_alpha,
            opacity,
            source_rotated,
        )
        target_applied = self._blend_rotated_brush(
            target_state,
            target_center_y,
            target_center_x,
            sampled_pixel,
            sampled_alpha,
            opacity,
            duplicate_rotated,
        )
        return source_applied and target_applied
    
    def precalculate_step_data(self, brush_list, H, W):
        """Pre-calculates all step data for brush painting."""
        steps_data = []
        
        for step in range(self.steps):
            if self.steps == 1:
                scale = self.min_brush_scale
                opacity = self.end_opacity
            else:
                scale = self.max_brush_scale + (self.min_brush_scale - self.max_brush_scale) * step / (self.steps - 1)
                opacity = self.start_opacity + (self.end_opacity - self.start_opacity) * step / (self.steps - 1)
            
            actual_brush_size = max(1, int(scale * min(H, W)))
            scaled_brush_list = self.resize_brushes(brush_list, actual_brush_size)
            num_samples = self.calculate_brush_area_density(scaled_brush_list, H, W, actual_brush_size)
            
            # Generate random coordinates
            if self.use_random_seed:
                np.random.seed(self.random_seed + step)
            random_y = np.random.randint(0, H, num_samples)
            random_x = np.random.randint(0, W, num_samples)
            
            step_data = StepData(
                step=step,
                scale=scale,
                opacity=opacity,
                actual_brush_size=actual_brush_size,
                scaled_brush_list=scaled_brush_list,
                num_samples=num_samples,
                random_y=random_y,
                random_x=random_x
            )
            steps_data.append(step_data)
        
        return steps_data
    
    def apply_brush_painting(
        self,
        image,
        brush_folder_path=None,
        brush_texture_path=None,
        custom_image_gradient=None,
        brush_callback=None,
        mesh_object: Optional[bpy.types.Object] = None,
        uv_map_name: Optional[str] = None,
    ):
        """Main function to apply brush painting to a Blender image."""
        if image is None:
            return None

        self._rotation_cache.clear()
        self._seam_index = None

        if brush_folder_path and os.path.exists(brush_folder_path):
            brush_list = self.load_multiple_brushes(brush_folder_path)
        elif brush_texture_path and os.path.exists(brush_texture_path):
            brush_list = [self.load_brush_texture(brush_texture_path)]
        else:
            brush_list = [self.create_circular_brush(50)]
        
        # Convert Blender image to numpy
        image_tiles = blender_image_to_numpy(image)
        if image_tiles is None:
            return None

        custom_image_tiles = None
        if custom_image_gradient:
            custom_image_tiles = blender_image_to_numpy(custom_image_gradient)
            if custom_image_tiles is None:
                return None

        tile_states: Dict[int, TilePaintState] = {}
        steps_by_tile: Dict[int, List[StepData]] = {}
        tile_shapes: Dict[int, Tuple[int, int]] = {}
        total_strokes = 0

        for tile_num, tile_array in image_tiles.tiles.items():
            custom_tile_array = None
            if custom_image_tiles:
                custom_tile_array = custom_image_tiles.tiles.get(tile_num)

            tile_state = self._prepare_tile_state(tile_num, tile_array, custom_tile_array)
            tile_states[tile_num] = tile_state
            tile_shapes[tile_num] = (tile_state.height, tile_state.width)

            step_data = self.precalculate_step_data(brush_list, tile_state.height, tile_state.width)
            steps_by_tile[tile_num] = step_data
            total_strokes += sum(step.num_samples for step in step_data)

        if self.enable_seam_duplication:
            self._seam_index = self._build_uv_seam_index(mesh_object, uv_map_name, tile_shapes)

        # Initialize rotation debug tracking
        if DEBUG_ROTATION:
            self._debug_rotation_count = 0
            rotation_angles = []
        
        total_strokes_applied = 0
        for tile_num, step_data_list in steps_by_tile.items():
            for step_data in step_data_list:
                for sample_index in range(step_data.num_samples):
                    y = int(step_data.random_y[sample_index])
                    x = int(step_data.random_x[sample_index])
                    brush_index = np.random.randint(0, len(step_data.scaled_brush_list))
                    selected_brush = step_data.scaled_brush_list[brush_index]
                    
                    # Track rotation angles for statistics
                    if DEBUG_ROTATION and total_strokes_applied < 1000:
                        tile_state = tile_states[tile_num]
                        angle_rad = tile_state.theta[y, x]
                        angle_deg = float(np.rad2deg(angle_rad))
                        rotation_angles.append(angle_deg)
                    
                    self._apply_stamp_with_optional_duplicate(
                        tile_states,
                        tile_num,
                        y,
                        x,
                        step_data.opacity,
                        selected_brush,
                        step_data.actual_brush_size,
                    )
                    total_strokes_applied += 1
                    if brush_callback:
                        brush_callback(total_strokes, total_strokes_applied)
        
        # Print rotation statistics
        if DEBUG_ROTATION and rotation_angles:
            rotation_angles = np.array(rotation_angles)
            unique_angles = np.unique(np.round(rotation_angles, 1))
            bins_used = set()
            for angle in rotation_angles:
                bins_used.add(self._quantize_angle(angle + self.brush_rotation_offset))
            print(f"[ROTATION STATS] Sampled {len(rotation_angles)} angles:")
            print(f"  Range: [{rotation_angles.min():.1f}°, {rotation_angles.max():.1f}°]")
            print(f"  Mean: {rotation_angles.mean():.1f}° Std: {rotation_angles.std():.1f}°")
            print(f"  Unique angles (0.1° precision): {len(unique_angles)}")
            print(f"  Rotation bins used: {len(bins_used)}/{self.rotation_bins}")
            if len(bins_used) <= 10:
                print(f"  Bins: {sorted(bins_used)}")

        result_tiles = {}
        for tile_num, tile_state in tile_states.items():
            result_tiles[tile_num] = tile_state.canvas[
                tile_state.offset_y:tile_state.offset_y + tile_state.height,
                tile_state.offset_x:tile_state.offset_x + tile_state.width,
            ]

        # Update image tiles in place
        result_image_tiles = ImageTiles(tiles=result_tiles, ori_path=image_tiles.ori_path, ori_packed=image_tiles.ori_packed)
        set_image_pixels(image, result_image_tiles)
        return image
