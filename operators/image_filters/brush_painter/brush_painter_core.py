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
from dataclasses import dataclass
from ..common import blender_image_to_numpy, numpy_to_blender_image

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
        
        # Brush texture paths
        self.brush_texture_path = None
        self.brush_folder_path = None
    
    def create_circular_brush(self, size):
        """Creates a soft circular brush mask as a NumPy array."""
        center = size / 2
        y, x = np.ogrid[-center:size-center, -center:size-center]
        dist = np.sqrt(x**2 + y**2)
        max_dist = size / 2
        mask = np.clip(1.0 - (dist / max_dist), 0.0, 1.0)
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
            brush_mask = np.array(brush_mask_pil, dtype=np.float64) / 255.0
            
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
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        resized_brush_list = []
        for brush in brush_list:
            brush_uint8 = (brush * 255).astype(np.uint8)
            brush_pil = Image.fromarray(brush_uint8, mode='L')
            resized_pil = brush_pil.resize((size, size), Image.Resampling.LANCZOS)
            resized_array = np.array(resized_pil, dtype=np.float64) / 255.0
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
        img_smoothed = np.array(blurred_pil, dtype=np.float64) / 255.0
        
        return img_smoothed
    
    def calculate_sobel_filter(self, img_float):
        """Calculates Sobel filter for the image using PIL.ImageFilter.Kernel."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        
        # Use PIL's optimized grayscale conversion instead of manual numpy calculation
        img_uint8 = (np.clip(img_float, 0, 1) * 255).astype(np.uint8)
        
        if len(img_float.shape) == 3:
            if img_float.shape[2] == 4:
                img_pil = Image.fromarray(img_uint8, mode='RGBA')
            else:
                img_pil = Image.fromarray(img_uint8, mode='RGB')
            # Use PIL's optimized grayscale conversion
            img_pil = img_pil.convert('L')
        else:
            img_pil = Image.fromarray(img_uint8, mode='L')
        
        # Convert to 'I' mode (32-bit integer) for kernel filtering
        img_pil = img_pil.convert('I')
        
        # Sobel kernels
        sobel_x_pos = [0, 0, 1, 0, 0, 2, 0, 0, 1]
        sobel_x_neg = [1, 0, 0, 2, 0, 0, 1, 0, 0]
        sobel_y_pos = [0, 0, 0, 0, 0, 0, 1, 2, 1]
        sobel_y_neg = [1, 2, 1, 0, 0, 0, 0, 0, 0]
        
        sobel_x_pos_filter = ImageFilter.Kernel((3, 3), sobel_x_pos)
        sobel_x_neg_filter = ImageFilter.Kernel((3, 3), sobel_x_neg)
        sobel_y_pos_filter = ImageFilter.Kernel((3, 3), sobel_y_pos)
        sobel_y_neg_filter = ImageFilter.Kernel((3, 3), sobel_y_neg)
        
        Gx_pos = np.array(img_pil.filter(sobel_x_pos_filter), dtype=np.float64)
        Gx_neg = np.array(img_pil.filter(sobel_x_neg_filter), dtype=np.float64)
        Gy_pos = np.array(img_pil.filter(sobel_y_pos_filter), dtype=np.float64)
        Gy_neg = np.array(img_pil.filter(sobel_y_neg_filter), dtype=np.float64)
        
        Gx = Gx_pos - Gx_neg
        Gy = Gy_pos - Gy_neg
        
        return Gx, Gy
    
    def calculate_gradients(self, img_float):
        """Calculates gradient magnitude and orientation for brush stroke direction."""
        # Use PIL's optimized grayscale conversion instead of manual numpy calculation
        img_uint8 = (np.clip(img_float, 0, 1) * 255).astype(np.uint8)
        
        if len(img_float.shape) == 3:
            if img_float.shape[2] == 4:
                img_pil = Image.fromarray(img_uint8, mode='RGBA')
            else:
                img_pil = Image.fromarray(img_uint8, mode='RGB')
            # Use PIL's optimized grayscale conversion
            img_pil = img_pil.convert('L')
        else:
            img_pil = Image.fromarray(img_uint8, mode='L')
        
        radius = int(self.gaussian_sigma * 2)
        blurred_pil = img_pil.filter(ImageFilter.GaussianBlur(radius=radius))
        img_smoothed = np.array(blurred_pil, dtype=np.float64) / 255.0
        
        Gx, Gy = self.calculate_sobel_filter(img_smoothed)
        G = np.hypot(Gx, Gy)
        theta = np.arctan2(Gy, Gx)
        G_normalized = G / G.max()
        
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
            canvas = np.zeros((extended_H, extended_W, 4), dtype=np.float64)
            canvas[offset_y:offset_y + H, offset_x:offset_x + W] = img_float
        else:
            canvas = np.zeros((extended_H, extended_W, 4), dtype=np.float64)
        
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

    def apply_brush_stroke(self, canvas, y, x, img_float, img_blurred, has_alpha, G_normalized, theta, opacity,
                          brush_list, canvas_y, canvas_x, extended_H, extended_W):
        """Applies a single brush stroke at the specified location."""
        sampled_pixel = img_blurred[y, x]
        sampled_pixel = self.apply_color_shift(sampled_pixel)
        sampled_alpha = sampled_pixel[3] if has_alpha else 1.0
        
        if sampled_alpha < 1:
            return False
        
        magnitude = G_normalized[y, x]
        if magnitude < self.gradient_threshold:
            return False
        
        angle_rad = theta[y, x]
        angle_deg = np.rad2deg(angle_rad)
        brush_angle = angle_deg + self.brush_rotation_offset
        
        selected_brush = brush_list[np.random.randint(0, len(brush_list))]
        brush_H, brush_W = selected_brush.shape
        brush_center = brush_H // 2
        
        brush_uint8 = (selected_brush * 255).astype(np.uint8)
        brush_pil = Image.fromarray(brush_uint8, mode='L')
        rotated_pil = brush_pil.rotate(angle=brush_angle, expand=True, center=(brush_center, brush_center))
        rotated_brush = np.array(rotated_pil, dtype=np.float64) / 255.0
        
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
        brush_color_layer = np.tile(sampled_pixel[:3], (r_H, r_W, 1))
        final_alpha = rotated_brush * sampled_alpha * opacity
        final_alpha_3d = final_alpha[..., np.newaxis]
        
        stroke_rgb = brush_color_layer
        stroke_alpha = final_alpha_3d
        
        canvas_rgb = canvas_region[:, :, :3]
        canvas_alpha = canvas_region[:, :, 3:4]
        
        # Straight Alpha Blending:
        # A_out = A_src + A_dst * (1 - A_src)
        # C_out = (C_src * A_src + C_dst * A_dst * (1 - A_src)) / A_out
        
        out_alpha = stroke_alpha + canvas_alpha * (1 - stroke_alpha)
        
        # Numerator for color channels
        numerator = stroke_rgb * stroke_alpha + canvas_rgb * canvas_alpha * (1 - stroke_alpha)
        
        # Avoid division by zero
        safe_alpha = np.copy(out_alpha)
        safe_alpha[safe_alpha < 0.0001] = 1.0
        
        new_rgb = numerator / safe_alpha
        new_alpha = out_alpha
        
        canvas_region[:, :, :3] = new_rgb
        canvas_region[:, :, 3:4] = new_alpha
        
        return True
    
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
            
            actual_brush_size = int(scale * min(H, W))
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
    
    def apply_brush_painting(self, image, brush_folder_path=None, brush_texture_path=None, custom_image_gradient=None, brush_callback=None):
        """Main function to apply brush painting to a Blender image."""
        if not PIL_AVAILABLE:
            raise ImportError("PIL (Pillow) is not available. Please install Pillow to use this feature.")
        if image is None:
            return None
        
        # Convert Blender image to numpy
        img_float = blender_image_to_numpy(image)
        if img_float is None:
            return None
        
        H, W = img_float.shape[:2]
        has_alpha = img_float.shape[2] == 4 if len(img_float.shape) == 3 else False
        
        # Load brushes
        if brush_folder_path and os.path.exists(brush_folder_path):
            brush_list = self.load_multiple_brushes(brush_folder_path)
        elif brush_texture_path and os.path.exists(brush_texture_path):
            brush_list = [self.load_brush_texture(brush_texture_path)]
        else:
            brush_list = [self.create_circular_brush(50)]
        
        # Calculate blurred image and gradients
        img_blurred = self.calculate_gaussian_blur(img_float)
        
        if custom_image_gradient:
            custom_img_float = blender_image_to_numpy(image)
            if custom_img_float is None:
                return None
            custom_blurred = self.calculate_gaussian_blur(custom_img_float)
            G_normalized, theta = self.calculate_gradients(custom_blurred)
        else:
            G_normalized, theta = self.calculate_gradients(img_float)
        
        # Create extended canvas
        canvas, extended_H, extended_W, offset_y, offset_x = self.create_extended_canvas(
            img_float, H, W, overlay_on_input=True
        )
        
        # Pre-calculate all step data
        steps_data = self.precalculate_step_data(brush_list, H, W)
        
        # Apply brushes at multiple scales
        total_strokes = sum(step_data.num_samples for step_data in steps_data)
        total_strokes_applied = 0
        
        for step_data in steps_data:
            for i in range(step_data.num_samples):
                y, x = step_data.random_y[i], step_data.random_x[i]
                canvas_y = y + offset_y
                canvas_x = x + offset_x
                
                if self.apply_brush_stroke(canvas, y, x, img_float, img_blurred, has_alpha, G_normalized, theta, step_data.opacity,
                                         step_data.scaled_brush_list, canvas_y, canvas_x, extended_H, extended_W):
                    total_strokes_applied += 1
                    if brush_callback:
                        brush_callback(total_strokes, total_strokes_applied)
        
        # Crop back to original dimensions
        final_canvas = canvas[offset_y:offset_y + H, offset_x:offset_x + W]
        
        # Convert back to Blender image
        result_image = numpy_to_blender_image(final_canvas, f"{image.name}_brushed", create_new=True)
        
        return result_image
