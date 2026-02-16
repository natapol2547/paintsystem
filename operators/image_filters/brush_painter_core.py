import bpy
import numpy as np
try:
    from PIL import Image, ImageFilter
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    Image = None
    ImageFilter = None
import os
import glob
from dataclasses import dataclass, field
from ..common import blender_image_to_numpy
from ...paintsystem.image import set_image_pixels, ImageTiles

# Rotation quantization for brush caching
ANGLE_STEP = 5  # degrees
NUM_ANGLES = 360 // ANGLE_STEP  # 72 pre-rotated versions per brush

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
    brush_indices: np.ndarray = None  # Pre-selected brush index per sample
    rotation_cache: dict = field(default_factory=dict)  # {(brush_idx, angle_idx): rotated_array}

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
        self.use_random_seed = False
        self.random_seed = 42
        self.preserve_alpha = False
        self.uv_seam_painting = False
        
        # Brush texture paths
        self.brush_texture_path = None
        self.brush_folder_path = None
    
    def create_circular_brush(self, size):
        """Creates a soft circular brush mask as a NumPy array."""
        center = size / 2
        y, x = np.ogrid[-center:size-center, -center:size-center]
        dist = np.sqrt(x**2 + y**2)
        max_dist = size / 2
        mask = np.clip(1.0 - (dist / max_dist), 0.0, 1.0).astype(np.float32)
        return mask
    
    def load_brush_texture(self, path):
        """Loads a brush texture and converts it to a grayscale mask."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        try:
            if not os.path.exists(path):
                return self.create_circular_brush(50)
                
            brush_pil = Image.open(path)
            
            # Use PIL's optimized methods for alpha extraction or grayscale conversion
            if brush_pil.mode == 'RGBA':
                # Extract alpha channel directly using PIL
                brush_mask_pil = brush_pil.split()[3]  # Get alpha channel
            else:
                # Convert to grayscale using PIL's optimized conversion (directly to L mode)
                brush_mask_pil = brush_pil.convert('L')
            
            # Convert to numpy array
            brush_mask = np.array(brush_mask_pil, dtype=np.float32) / 255.0
            
            # Handle non-square brush textures
            original_h, original_w = brush_mask.shape
            if original_h != original_w:
                max_dim = max(original_h, original_w)
                square_brush = np.zeros((max_dim, max_dim), dtype=np.float32)
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
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        resized_brush_list = []
        for brush in brush_list:
            brush_uint8 = (brush * 255).astype(np.uint8)
            brush_pil = Image.fromarray(brush_uint8, mode='L')
            resized_pil = brush_pil.resize((size, size), Image.Resampling.LANCZOS)
            resized_array = np.array(resized_pil, dtype=np.float32) / 255.0
            resized_brush_list.append(resized_array)
        return resized_brush_list
    
    def calculate_gaussian_blur(self, img_float):
        """Calculates Gaussian blur for the image using Pillow."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        if self.gaussian_sigma <= 0:
            return img_float
        
        img_uint8 = (np.clip(img_float, 0, 1) * 255).astype(np.uint8)
        
        if len(img_float.shape) == 3:
            if img_float.shape[2] == 4:
                img_pil = Image.fromarray(img_uint8, mode='RGBA')
            else:
                img_pil = Image.fromarray(img_uint8, mode='RGB')
        else:
            img_pil = Image.fromarray(img_uint8, mode='L')
        
        radius = int(self.gaussian_sigma * 2)
        blurred_pil = img_pil.filter(ImageFilter.GaussianBlur(radius=radius))
        img_smoothed = np.array(blurred_pil, dtype=np.float32) / 255.0
        
        return img_smoothed
    
    def _sobel_from_pil(self, gray_pil):
        """Calculates Sobel filter from a PIL grayscale ('L') image.
        
        Avoids redundant numpy<->PIL conversions when called from calculate_gradients.
        """
        img_i = gray_pil.convert('I')
        
        sobel_x_pos = [0, 0, 1, 0, 0, 2, 0, 0, 1]
        sobel_x_neg = [1, 0, 0, 2, 0, 0, 1, 0, 0]
        sobel_y_pos = [0, 0, 0, 0, 0, 0, 1, 2, 1]
        sobel_y_neg = [1, 2, 1, 0, 0, 0, 0, 0, 0]
        
        Gx_pos = np.array(img_i.filter(ImageFilter.Kernel((3, 3), sobel_x_pos)), dtype=np.float32)
        Gx_neg = np.array(img_i.filter(ImageFilter.Kernel((3, 3), sobel_x_neg)), dtype=np.float32)
        Gy_pos = np.array(img_i.filter(ImageFilter.Kernel((3, 3), sobel_y_pos)), dtype=np.float32)
        Gy_neg = np.array(img_i.filter(ImageFilter.Kernel((3, 3), sobel_y_neg)), dtype=np.float32)
        
        Gx = Gx_pos - Gx_neg
        Gy = Gy_pos - Gy_neg
        
        return Gx, Gy
    
    def calculate_sobel_filter(self, img_float):
        """Calculates Sobel filter for the image using PIL.ImageFilter.Kernel."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        
        img_uint8 = (np.clip(img_float, 0, 1) * 255).astype(np.uint8)
        
        if len(img_float.shape) == 3:
            if img_float.shape[2] == 4:
                img_pil = Image.fromarray(img_uint8, mode='RGBA')
            else:
                img_pil = Image.fromarray(img_uint8, mode='RGB')
            img_pil = img_pil.convert('L')
        else:
            img_pil = Image.fromarray(img_uint8, mode='L')
        
        return self._sobel_from_pil(img_pil)
    
    def calculate_gradients(self, img_float):
        """Calculates gradient magnitude and orientation for brush stroke direction.
        
        Optimized to avoid redundant grayscale/blur conversions by passing the
        already-blurred PIL grayscale image directly to the Sobel step.
        """
        img_uint8 = (np.clip(img_float, 0, 1) * 255).astype(np.uint8)
        
        if len(img_float.shape) == 3:
            if img_float.shape[2] == 4:
                img_pil = Image.fromarray(img_uint8, mode='RGBA')
            else:
                img_pil = Image.fromarray(img_uint8, mode='RGB')
            img_pil = img_pil.convert('L')
        else:
            img_pil = Image.fromarray(img_uint8, mode='L')
        
        radius = int(self.gaussian_sigma * 2)
        blurred_pil = img_pil.filter(ImageFilter.GaussianBlur(radius=radius))
        
        # Pass the blurred PIL image directly to Sobel (avoids numpy->uint8->PIL roundtrip)
        Gx, Gy = self._sobel_from_pil(blurred_pil)
        G = np.hypot(Gx, Gy)
        theta = np.arctan2(Gy, Gx)
        g_max = G.max()
        G_normalized = G / g_max if g_max > 0 else G
        
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
    
    def apply_color_shifts_batch(self, pixels):
        """Vectorized HSV color shift for a batch of pixels.
        
        Args:
            pixels: (N, C) float32 array where C >= 3
        
        Returns:
            Modified pixels array with shifted colors.
        """
        if pixels.shape[0] == 0 or pixels.shape[1] < 3:
            return pixels
        
        # Skip if no shifts needed
        if self.hue_shift <= 0 and self.saturation_shift <= 0 and self.value_shift <= 0:
            return pixels
        
        result = pixels.copy()
        N = pixels.shape[0]
        r = result[:, 0].copy()
        g = result[:, 1].copy()
        b = result[:, 2].copy()
        
        # Vectorized RGB to HSV
        max_val = np.maximum(np.maximum(r, g), b)
        min_val = np.minimum(np.minimum(r, g), b)
        delta = max_val - min_val
        
        # Hue calculation
        h = np.zeros(N, dtype=np.float32)
        nonzero = delta > 0
        
        mask_r = nonzero & (max_val == r)
        mask_g = nonzero & (max_val == g) & ~mask_r
        mask_b = nonzero & ~mask_r & ~mask_g
        
        h[mask_r] = (60.0 * ((g[mask_r] - b[mask_r]) / delta[mask_r])) % 360.0
        h[mask_g] = (60.0 * (2.0 + (b[mask_g] - r[mask_g]) / delta[mask_g])) % 360.0
        h[mask_b] = (60.0 * (4.0 + (r[mask_b] - g[mask_b]) / delta[mask_b])) % 360.0
        
        # Saturation
        s = np.where(max_val > 0, delta / max_val, np.float32(0))
        
        # Value
        v = max_val.copy()
        
        # Apply random shifts
        if self.hue_shift > 0:
            hue_range = self.hue_shift * 360.0
            h = (h + np.random.uniform(-hue_range / 2, hue_range / 2, N).astype(np.float32)) % 360.0
        
        if self.saturation_shift > 0:
            s = np.clip(
                s + np.random.uniform(-self.saturation_shift / 2, self.saturation_shift / 2, N).astype(np.float32),
                0, 1
            )
        
        if self.value_shift > 0:
            v = np.clip(
                v + np.random.uniform(-self.value_shift / 2, self.value_shift / 2, N).astype(np.float32),
                0, 1
            )
        
        # Vectorized HSV to RGB
        c = v * s
        h_prime = h / 60.0
        x_val = c * (1.0 - np.abs(h_prime % 2.0 - 1.0))
        m = v - c
        
        r_new = np.zeros(N, dtype=np.float32)
        g_new = np.zeros(N, dtype=np.float32)
        b_new = np.zeros(N, dtype=np.float32)
        
        idx0 = (h_prime >= 0) & (h_prime < 1)
        r_new[idx0] = c[idx0]; g_new[idx0] = x_val[idx0]
        
        idx1 = (h_prime >= 1) & (h_prime < 2)
        r_new[idx1] = x_val[idx1]; g_new[idx1] = c[idx1]
        
        idx2 = (h_prime >= 2) & (h_prime < 3)
        g_new[idx2] = c[idx2]; b_new[idx2] = x_val[idx2]
        
        idx3 = (h_prime >= 3) & (h_prime < 4)
        g_new[idx3] = x_val[idx3]; b_new[idx3] = c[idx3]
        
        idx4 = (h_prime >= 4) & (h_prime < 5)
        r_new[idx4] = x_val[idx4]; b_new[idx4] = c[idx4]
        
        idx5 = (h_prime >= 5) & (h_prime < 6)
        r_new[idx5] = c[idx5]; b_new[idx5] = x_val[idx5]
        
        result[:, 0] = np.clip(r_new + m, 0, 1)
        result[:, 1] = np.clip(g_new + m, 0, 1)
        result[:, 2] = np.clip(b_new + m, 0, 1)
        
        return result
    
    def apply_color_shift(self, pixel):
        """Applies randomized HSV color shifts to a single pixel. Legacy wrapper."""
        batch = self.apply_color_shifts_batch(pixel[np.newaxis, :])
        return batch[0]
    
    def _build_rotation_cache(self, scaled_brush_list):
        """Pre-rotate all brushes at quantized angles and cache the results.
        
        Eliminates per-stroke PIL conversion and rotation during painting.
        """
        cache = {}
        for brush_idx, brush in enumerate(scaled_brush_list):
            brush_uint8 = (brush * 255).astype(np.uint8)
            brush_pil = Image.fromarray(brush_uint8, mode='L')
            brush_center = brush.shape[0] // 2
            for angle_idx in range(NUM_ANGLES):
                angle = angle_idx * ANGLE_STEP
                rotated_pil = brush_pil.rotate(
                    angle=angle, expand=True,
                    center=(brush_center, brush_center)
                )
                rotated = np.array(rotated_pil, dtype=np.float32) / 255.0
                cache[(brush_idx, angle_idx)] = rotated
        return cache
    
    def _get_cached_brush(self, rotation_cache, brush_idx, angle_deg):
        """Look up a pre-rotated brush from the cache, snapping to nearest quantized angle."""
        angle_deg = angle_deg % 360
        if angle_deg < 0:
            angle_deg += 360
        angle_idx = int(round(angle_deg / ANGLE_STEP)) % NUM_ANGLES
        return rotation_cache[(brush_idx, angle_idx)]

    def apply_brush_stroke(self, canvas, sampled_pixel, sampled_alpha, opacity,
                          rotated_brush, canvas_y, canvas_x, extended_H, extended_W):
        """Applies a single brush stroke at the specified location.
        
        Optimized version: receives pre-shifted pixel color and pre-rotated brush.
        """
        r_H, r_W = rotated_brush.shape
        rotated_center_y = r_H // 2
        rotated_center_x = r_W // 2
        
        start_y = canvas_y - rotated_center_y
        end_y = start_y + r_H
        start_x = canvas_x - rotated_center_x
        end_x = start_x + r_W
        
        if not (start_y >= 0 and end_y <= extended_H and 
                start_x >= 0 and end_x <= extended_W):
            return False
        
        canvas_region = canvas[start_y:end_y, start_x:end_x]
        
        # Use broadcast instead of np.tile for the color layer (avoids full copy)
        brush_color = np.broadcast_to(sampled_pixel[:3], (r_H, r_W, 3))
        final_alpha = rotated_brush * sampled_alpha * opacity
        final_alpha_3d = final_alpha[..., np.newaxis]
        
        stroke_rgb = brush_color
        stroke_alpha = final_alpha_3d
        
        canvas_rgb = canvas_region[:, :, :3]
        canvas_alpha = canvas_region[:, :, 3:4]
        
        # Straight Alpha Blending:
        # A_out = A_src + A_dst * (1 - A_src)
        # C_out = (C_src * A_src + C_dst * A_dst * (1 - A_src)) / A_out
        
        one_minus_stroke = 1.0 - stroke_alpha
        out_alpha = stroke_alpha + canvas_alpha * one_minus_stroke
        
        # Numerator for color channels
        numerator = stroke_rgb * stroke_alpha + canvas_rgb * canvas_alpha * one_minus_stroke
        
        # Avoid division by zero
        safe_alpha = np.where(out_alpha < 0.0001, np.float32(1.0), out_alpha)
        
        canvas_region[:, :, :3] = numerator / safe_alpha
        canvas_region[:, :, 3:4] = out_alpha
        
        return True
    
    def precalculate_step_data(self, brush_list, H, W):
        """Pre-calculates all step data for brush painting.
        
        Includes rotation cache and pre-selected brush indices per sample.
        """
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
            
            # Generate random coordinates and brush selections
            if self.use_random_seed:
                np.random.seed(self.random_seed + step)
            random_y = np.random.randint(0, H, num_samples)
            random_x = np.random.randint(0, W, num_samples)
            brush_indices = np.random.randint(0, len(scaled_brush_list), num_samples)
            
            # Pre-rotate all brushes at quantized angles
            rotation_cache = self._build_rotation_cache(scaled_brush_list)
            
            step_data = StepData(
                step=step,
                scale=scale,
                opacity=opacity,
                actual_brush_size=actual_brush_size,
                scaled_brush_list=scaled_brush_list,
                num_samples=num_samples,
                random_y=random_y,
                random_x=random_x,
                brush_indices=brush_indices,
                rotation_cache=rotation_cache
            )
            steps_data.append(step_data)
        
        return steps_data
    
    def _apply_brush_painting_single(self, img_float, brush_folder_path=None, brush_texture_path=None,
                                      custom_img_float=None, brush_callback=None,
                                      seam_map=None, seam_spatial=None):
        """Apply brush painting to a single numpy array."""
        if img_float is None:
            return None
        
        H, W = img_float.shape[:2]
        has_alpha = img_float.shape[2] == 4 if len(img_float.shape) == 3 else False
        
        # Save original alpha for preserve_alpha option
        original_alpha = None
        if self.preserve_alpha and has_alpha:
            original_alpha = img_float[:, :, 3].copy()
        
        # Load brushes
        if brush_folder_path and os.path.exists(brush_folder_path):
            brush_list = self.load_multiple_brushes(brush_folder_path)
        elif brush_texture_path and os.path.exists(brush_texture_path):
            brush_list = [self.load_brush_texture(brush_texture_path)]
        else:
            brush_list = [self.create_circular_brush(50)]
        
        # Calculate blurred image and gradients
        img_blurred = self.calculate_gaussian_blur(img_float)
        
        if custom_img_float is not None:
            custom_blurred = self.calculate_gaussian_blur(custom_img_float)
            G_normalized, theta = self.calculate_gradients(custom_blurred)
        else:
            G_normalized, theta = self.calculate_gradients(img_float)
        
        # Create extended canvas
        canvas, extended_H, extended_W, offset_y, offset_x = self.create_extended_canvas(
            img_float, H, W, overlay_on_input=True
        )
        
        # Pre-calculate all step data (includes rotation cache and brush indices)
        steps_data = self.precalculate_step_data(brush_list, H, W)
        
        # Apply brushes at multiple scales
        total_strokes = sum(sd.num_samples for sd in steps_data)
        total_strokes_applied = 0
        
        for step_data in steps_data:
            # --- Vectorized pre-filter: skip positions that would fail early checks ---
            if has_alpha:
                sampled_alphas = img_blurred[step_data.random_y, step_data.random_x, 3]
            else:
                sampled_alphas = np.ones(step_data.num_samples, dtype=np.float32)
            
            magnitudes = G_normalized[step_data.random_y, step_data.random_x]
            valid_mask = (sampled_alphas >= 1.0) & (magnitudes >= self.gradient_threshold)
            valid_indices = np.where(valid_mask)[0]
            
            # Batch sample pixels and apply color shifts for all valid positions at once
            valid_ys = step_data.random_y[valid_indices]
            valid_xs = step_data.random_x[valid_indices]
            sampled_pixels = img_blurred[valid_ys, valid_xs]  # (N_valid, C)
            shifted_pixels = self.apply_color_shifts_batch(sampled_pixels)
            
            # Pre-compute brush angles for all valid positions
            angles_rad = theta[valid_ys, valid_xs]
            angles_deg = np.rad2deg(angles_rad) + self.brush_rotation_offset
            
            for vi, idx in enumerate(valid_indices):
                y = step_data.random_y[idx]
                x = step_data.random_x[idx]
                canvas_y = y + offset_y
                canvas_x = x + offset_x
                
                pixel = shifted_pixels[vi]
                alpha = sampled_alphas[idx]
                brush_idx = step_data.brush_indices[idx]
                angle = angles_deg[vi]
                
                # Get pre-rotated brush from cache
                rotated_brush = self._get_cached_brush(step_data.rotation_cache, brush_idx, angle)
                
                success = self.apply_brush_stroke(
                    canvas, pixel, alpha, step_data.opacity,
                    rotated_brush, canvas_y, canvas_x, extended_H, extended_W
                )
                
                # UV seam painting: apply mirrored strokes at seam boundaries
                if success and seam_map is not None:
                    self._apply_seam_strokes(
                        canvas, seam_map, seam_spatial, y, x, pixel, alpha,
                        rotated_brush, step_data.opacity,
                        brush_idx, angle, step_data,
                        offset_y, offset_x, extended_H, extended_W, H, W
                    )
                
                total_strokes_applied += 1
                if brush_callback:
                    brush_callback(total_strokes, total_strokes_applied)
            
            # Count skipped strokes for progress
            skipped = step_data.num_samples - len(valid_indices)
            total_strokes_applied += skipped
            if brush_callback and skipped > 0:
                brush_callback(total_strokes, total_strokes_applied)
        
        # Crop back to original dimensions
        final_canvas = canvas[offset_y:offset_y + H, offset_x:offset_x + W]
        
        # Restore original alpha if preserve_alpha is enabled
        if self.preserve_alpha and original_alpha is not None:
            final_canvas[:, :, 3] = original_alpha
        
        return final_canvas
    
    def _apply_seam_strokes(self, canvas, seam_map, seam_spatial, y, x, pixel, alpha,
                            rotated_brush, opacity, brush_idx, angle_deg, step_data,
                            offset_y, offset_x, extended_H, extended_W, H, W):
        """Apply continuation brush strokes at UV seam boundaries.

        Uses a spatial index for fast candidate retrieval and picks only
        the nearest seam edge to avoid duplicate strokes at corners.
        """
        from .uv_boundary import find_seam_overlaps
        
        r_H, r_W = rotated_brush.shape
        brush_radius = max(r_H, r_W) / 2.0
        # Brush bounding box in image pixel space
        brush_bbox = (
            x - r_W // 2,
            y - r_H // 2,
            x + r_W // 2,
            y + r_H // 2
        )
        
        # Valid brush size range in pixels
        img_dim = min(H, W)
        min_brush_px = max(1, int(self.min_brush_scale * img_dim))
        max_brush_px = max(1, int(self.max_brush_scale * img_dim))
        
        overlaps = find_seam_overlaps(
            seam_map, brush_bbox, float(x), float(y), brush_radius,
            spatial_index=seam_spatial,
        )
        
        for overlap in overlaps:
            mirror_x = int(round(overlap.mirror_x))
            mirror_y = int(round(overlap.mirror_y))
            
            # Skip if mirror lands outside the image
            if mirror_x < 0 or mirror_x >= W or mirror_y < 0 or mirror_y >= H:
                continue
            
            mirror_canvas_y = mirror_y + offset_y
            mirror_canvas_x = mirror_x + offset_x
            
            # Correct brush rotation for the target edge orientation
            mirror_angle = angle_deg + overlap.rotation_diff
            mirror_brush = self._get_cached_brush(step_data.rotation_cache, brush_idx, mirror_angle)
            
            # Check scaled size falls within the allowed brush range
            final_size = int(mirror_brush.shape[0] * overlap.length_ratio)
            if final_size < min_brush_px or final_size > max_brush_px:
                continue
            
            # Scale brush if edges have different lengths
            if abs(overlap.length_ratio - 1.0) > 0.01:
                scaled_size = max(1, final_size)
                brush_uint8 = (mirror_brush * 255).astype(np.uint8)
                brush_pil = Image.fromarray(brush_uint8, mode='L')
                scaled_pil = brush_pil.resize((scaled_size, scaled_size), Image.Resampling.LANCZOS)
                mirror_brush = np.array(scaled_pil, dtype=np.float32) / 255.0
            
            self.apply_brush_stroke(
                canvas, pixel, alpha, opacity,
                mirror_brush, mirror_canvas_y, mirror_canvas_x, extended_H, extended_W
            )
    
    def apply_brush_painting(self, image, brush_folder_path=None, brush_texture_path=None,
                             custom_image_gradient=None, brush_callback=None,
                             obj=None, uv_layer_name=None):
        """Main function to apply brush painting to a Blender image."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        if image is None:
            return None
        
        # Convert Blender image to numpy
        image_tiles = blender_image_to_numpy(image)
        if image_tiles is None:
            return None
        
        # Build UV seam map if enabled
        seam_map = None
        seam_spatial = None
        if self.uv_seam_painting and obj is not None and uv_layer_name is not None:
            from .uv_boundary import build_uv_seam_map
            # Use first tile dimensions for seam map
            first_tile = next(iter(image_tiles.tiles.values()))
            tile_H, tile_W = first_tile.shape[:2]
            seam_map, seam_spatial = build_uv_seam_map(obj, uv_layer_name, tile_W, tile_H)
        
        # Process each tile separately
        result_tiles = {}
        custom_image_tiles = None
        
        if custom_image_gradient:
            custom_image_tiles = blender_image_to_numpy(custom_image_gradient)
            if custom_image_tiles is None:
                return None
        
        for tile_num, tile_array in image_tiles.tiles.items():
            custom_tile_array = None
            if custom_image_tiles:
                custom_tile_array = custom_image_tiles.tiles.get(tile_num)
            
            result_tile = self._apply_brush_painting_single(
                tile_array, 
                brush_folder_path, 
                brush_texture_path, 
                custom_tile_array,
                brush_callback,
                seam_map,
                seam_spatial,
            )
            result_tiles[tile_num] = result_tile
        
        # Update image tiles in place
        result_image_tiles = ImageTiles(tiles=result_tiles, ori_path=image_tiles.ori_path, ori_packed=image_tiles.ori_packed)
        set_image_pixels(image, result_image_tiles)
        return image
