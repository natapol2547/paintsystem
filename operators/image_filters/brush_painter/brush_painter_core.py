import bpy
import numpy as np
from PIL import Image, ImageFilter
import os
import glob
from ..common import blender_image_to_numpy, numpy_to_blender_image

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
        try:
            if not os.path.exists(path):
                return self.create_circular_brush(50)
                
            brush_pil = Image.open(path)
            if brush_pil.mode != 'RGBA':
                brush_pil = brush_pil.convert('RGBA')
            
            brush_array = np.array(brush_pil, dtype=np.float64) / 255.0
            
            if brush_pil.mode == 'RGBA':
                brush_mask = brush_array[..., 3]
            else:
                rgb = brush_array[..., :3]
                brush_mask = 0.299 * rgb[..., 0] + 0.587 * rgb[..., 1] + 0.114 * rgb[..., 2]
            
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
        if len(img_float.shape) == 3:
            if img_float.shape[2] == 4:
                img_gray = img_float[..., :3]
            else:
                img_gray = img_float
            img_gray = 0.299 * img_gray[..., 0] + 0.587 * img_gray[..., 1] + 0.114 * img_gray[..., 2]
        else:
            img_gray = img_float
        
        img_uint8 = (img_gray * 255).astype(np.uint32)
        img_pil = Image.fromarray(img_uint8, mode='I')
        
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
        img_rgb_for_gray = img_float[..., :3] if img_float.shape[-1] == 4 else img_float
        if len(img_rgb_for_gray.shape) == 3:
            img_gray = 0.299 * img_rgb_for_gray[..., 0] + 0.587 * img_rgb_for_gray[..., 1] + 0.114 * img_rgb_for_gray[..., 2]
        else:
            img_gray = img_rgb_for_gray
        
        img_gray_uint8 = (img_gray * 255).astype(np.uint8)
        img_pil = Image.fromarray(img_gray_uint8, mode='L')
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
    
    def apply_brush_stroke(self, canvas, y, x, img_float, img_blurred, has_alpha, G_normalized, theta, opacity,
                          brush_list, canvas_y, canvas_x, extended_H, extended_W):
        """Applies a single brush stroke at the specified location."""
        sampled_pixel = img_blurred[y, x]
        sampled_alpha = sampled_pixel[3] if has_alpha else 1.0
        
        if sampled_alpha < 1:
            return False
        
        magnitude = G_normalized[y, x]
        if magnitude <= self.gradient_threshold:
            return False
        
        angle_rad = theta[y, x]
        angle_deg = np.rad2deg(angle_rad)
        brush_angle = angle_deg + 90
        
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
        
        new_rgb = (1 - stroke_alpha) * canvas_rgb + stroke_alpha * stroke_rgb
        new_alpha = (1 - stroke_alpha) * canvas_alpha + stroke_alpha
        
        canvas_region[:, :, :3] = new_rgb
        canvas_region[:, :, 3:4] = new_alpha
        
        return True
    
    def apply_brush_painting(self, image, brush_folder_path=None, brush_texture_path=None):
        """Main function to apply brush painting to a Blender image."""
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
        G_normalized, theta = self.calculate_gradients(img_float)
        
        # Create extended canvas
        canvas, extended_H, extended_W, offset_y, offset_x = self.create_extended_canvas(
            img_float, H, W, overlay_on_input=True
        )
        
        # Apply brushes at multiple scales
        total_strokes_applied = 0
        
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
            np.random.seed(42 + step)
            random_y = np.random.randint(0, H, num_samples)
            random_x = np.random.randint(0, W, num_samples)
            
            strokes_applied = 0
            for i in range(num_samples):
                y, x = random_y[i], random_x[i]
                canvas_y = y + offset_y
                canvas_x = x + offset_x
                
                if self.apply_brush_stroke(canvas, y, x, img_float, img_blurred, has_alpha, G_normalized, theta, opacity,
                                         scaled_brush_list, canvas_y, canvas_x, extended_H, extended_W):
                    strokes_applied += 1
            
            total_strokes_applied += strokes_applied
        
        # Crop back to original dimensions
        final_canvas = canvas[offset_y:offset_y + H, offset_x:offset_x + W]
        
        # Convert back to Blender image
        result_image = numpy_to_blender_image(final_canvas, f"{image.name}_brushed", create_new=True)
        
        return result_image
