from dataclasses import dataclass
from typing import Dict, List
import re
import numpy as np

import bpy
from bpy.app.handlers import persistent
from bpy.props import (
    BoolProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    PointerProperty,
    StringProperty,
    FloatVectorProperty,
)
from bpy.types import (
    Context,
    Image,
    Node,
    NodeTree,
    Object,
    PropertyGroup,
    Material,
)
from bpy.utils import register_classes_factory
from bpy_extras.node_utils import connect_sockets
from typing import Optional
from mathutils import Color

# ---
from ..custom_icons import get_icon
from ..utils.version import is_newer_than
from ..utils.nodes import find_node, get_material_output
from ..preferences import get_preferences
from ..utils import get_next_unique_name
from .common import PaintSystemPreferences
from .graph import (
    NodeTreeBuilder,
    create_adjustment_graph,
    create_attribute_graph,
    create_custom_graph,
    create_folder_graph,
    create_gradient_graph,
    create_image_graph,
    create_random_graph,
    create_solid_graph,
    get_alpha_over_nodetree,
    create_texture_graph,
    create_geometry_graph,
)
from .graph.common import get_library_object
from .nested_list_manager import BaseNestedListManager, BaseNestedListItem

TEMPLATE_ENUM = [
    ('BASIC', "Basic", "Basic painting setup", "IMAGE", 0),
    ('PAINT_OVER', "Paint Over", "Paint over the existing material", "BRUSH_DATA", 1),
    ('PBR', "PBR", "PBR painting setup", "MATERIAL", 2),
    ('NORMAL', "Normals Painting", "Start off with a normal painting setup", "NORMALS_VERTEX_FACE", 3),
    ('CONVERT', "Convert to Paint System", "Convert existing material to Paint System with image support", "CHECKMARK", 4),
    ('NONE', "None", "Just add node group to material", "NONE", 5),
]

LAYER_TYPE_ENUM = [
    ('FOLDER', "Folder", "Folder layer"),
    ('IMAGE', "Image", "Image layer"),
    ('SOLID_COLOR', "Solid Color", "Solid Color layer"),
    ('ATTRIBUTE', "Attribute", "Attribute layer"),
    ('ADJUSTMENT', "Adjustment", "Adjustment layer"),
    ('NODE_GROUP', "Node Group", "Node Group layer"),
    ('GRADIENT', "Gradient", "Gradient layer"),
    ('RANDOM', "Random", "Random Color layer"),
    ('TEXTURE', "Texture", "Texture layer"),
    ('GEOMETRY', "Geometry", "Geometry layer"),
]

CHANNEL_TYPE_ENUM = [
    ('COLOR', "Color", "Color channel"),
    ('VECTOR', "Vector", "Vector channel"),
    ('FLOAT', "Value", "Value channel"),
]

GRADIENT_TYPE_ENUM = [
    ('GRADIENT_MAP', "Gradient Map", "Gradient map"),
    ('LINEAR', "Linear Gradient", "Linear gradient"),
    ('RADIAL', "Radial Gradient", "Radial gradient"),
    ('DISTANCE', "Distance Gradient", "Distance gradient"),
]

ADJUSTMENT_TYPE_ENUM = [
    ('BRIGHTCONTRAST', "Brightness and Contrast", ""),
    ('GAMMA', "Gamma", ""),
    ('HUE_SAT', "Hue Saturation Value", ""),
    ('INVERT', "Invert", ""),
    ('CURVE_RGB', "RGB Curves", ""),
    ('RGBTOBW', "RGB to BW", ""),
    ('MAP_RANGE', "Map Range", ""),
    # ('ShaderNodeAmbientOcclusion', "Ambient Occlusion", ""),
]

TEXTURE_TYPE_ENUM = [
    ('TEX_BRICK', "Brick Texture", ""),
    ('TEX_CHECKER', "Checker Texture", ""),
    # ('ShaderNodeTexGabor', "Gabor Texture", ""),
    ('TEX_GRADIENT', "Gradient Texture", ""),
    ('TEX_MAGIC', "Magic Texture", ""),
    ('TEX_NOISE', "Noise Texture", ""),
    ('TEX_VORONOI', "Voronoi Texture", ""),
    ('TEX_WAVE', "Wave Texture", ""),
    ('TEX_WHITE_NOISE', "White Noise Texture", ""),
]

COORDINATE_TYPE_ENUM = [
    ('AUTO', "Auto UV", "Automatically create a new UV Map"),
    ('UV', "UV", "Open an existing UV Map"),
    # ('GENERATED', "Generated", "Use a generated output of Texture Coordinate node"),
    ('OBJECT', "Object", "Use a object output of Texture Coordinate node"),
    ('CAMERA', "Camera", "Use a camera output of Texture Coordinate node"),
    ('WINDOW', "Window", "Use a window output of Texture Coordinate node"),
    ('REFLECTION', "Reflection", "Use a reflection output of Texture Coordinate node"),
    ('POSITION', "Position", "Use a position output of Geometry node"),
]

ATTRIBUTE_TYPE_ENUM = [
    ('GEOMETRY', "Geometry", "Geometry"),
    ('OBJECT', "Object", "Object"),
    ('INSTANCER', "Instancer", "Instancer"),
    ('VIEW_LAYER', "View Layer", "View Layer")
]

GEOMETRY_TYPE_ENUM = [
    ('WORLD_NORMAL', "World Space Normal", "World Space Normal"),
    ('WORLD_TRUE_NORMAL', "World Space True Normal", "World Space True Normal"),
    ('POSITION', "World Space Position", "World Space Position"),
    ('OBJECT_NORMAL', "Object Space Normal", "Object Space Normal"),
    ('OBJECT_POSITION', "Object Space Position", "Object Space Position"),
    ('BACKFACING', "Backfacing", "Backfacing"),
    ('VECTOR_TRANSFORM', "Vector Transform", "Vector Transform"),
]

ACTION_TYPE_ENUM = [
    ('ENABLE', "Enable Layer", "Enable the layer when reached"),
    ('DISABLE', "Disable Layer", "Disable the layer when reached"),
]

ACTION_BIND_ENUM = [
    ('FRAME', "Frame", "Enable/disable the layer on a frame", "KEYTYPE_KEYFRAME_VEC", 0),
    ('MARKER', "Marker", "Enable/disable the layer on a marker", "MARKER_HLT", 1),
]

COLOR_SPACE_ENUM = [
    ('COLOR', "Color", "Color"),
    ('NONCOLOR', "Non-Color", "Non-Color"),
]

FILTER_TYPE_ENUM = [
    ('BLUR', "Blur", "Blur"),
    ('EDGE_ENHANCE', "Edge Enhance", "Edge Enhance"),
    ('SHARPEN', "Sharpen", "Sharpen"),
]

def update_brush_settings(self=None, context: bpy.types.Context = bpy.context):
    if context.mode != 'PAINT_TEXTURE':
        return
    ps_ctx = parse_context(context)
    global_layer = ps_ctx.active_global_layer
    if not global_layer:
        return
    brush = context.tool_settings.image_paint.brush
    if not brush:
        return
    brush.use_alpha = not global_layer.lock_alpha

def update_active_image(self=None, context: bpy.types.Context = None):
    context = context or bpy.context
    ps_ctx = parse_context(context)
    image_paint = context.tool_settings.image_paint
    obj = ps_ctx.ps_object
    mat = ps_ctx.active_material
    active_channel = ps_ctx.active_channel
    if not obj.name == "PS Camera Plane":
        # print("Setting last selected PS object: ", obj.name)
        ps_ctx.ps_scene_data.last_selected_ps_object = obj
    if not mat or not active_channel:
        return
    global_layer = ps_ctx.active_global_layer
    update_brush_settings(self, context)

    if image_paint.mode == 'MATERIAL':
        image_paint.mode = 'IMAGE'
    if not global_layer or global_layer.lock_layer or active_channel.use_bake_image:
        image_paint.canvas = None
        # Unable to paint
        return
    
    selected_image: Image = global_layer.image
    image_paint.canvas = selected_image
    if global_layer.coord_type == 'UV' or global_layer.attached_to_camera_plane:
        if global_layer.uv_map_name and obj.data.uv_layers.get(global_layer.uv_map_name):
            obj.data.uv_layers[global_layer.uv_map_name].active = True
    elif global_layer.coord_type == 'AUTO' and obj.data.uv_layers.get("PS_UVMap"):
        obj.data.uv_layers["PS_UVMap"].active = True

    if not global_layer.attached_to_camera_plane:
        context.view_layer.objects.active = obj
        obj.select_set(True)
    else:
        ps_ctx.ps_object.select_set(False)
        ps_ctx.camera_plane.select_set(True)
        context.view_layer.objects.active = ps_ctx.camera_plane
        bpy.ops.object.mode_set(mode=ps_ctx.ps_object.mode)

def update_active_layer(self, context):
    ps_ctx = parse_context(context)
    active_layer = ps_ctx.active_layer
    if active_layer:
        active_layer.update_node_tree(context)

def update_active_channel(self, context):
    ps_ctx = parse_context(context)
    active_channel = ps_ctx.active_channel
    if active_channel:
        active_channel.update_node_tree(context)

def update_active_group(self, context):
    ps_ctx = parse_context(context)
    active_group = ps_ctx.active_group
    if active_group:
        active_group.update_node_tree(context)

def get_node_from_nodetree(node_tree: NodeTree, identifier: str) -> Node | None:
    for node in node_tree.nodes:
        if node.label == identifier:
            return node
    return None

def is_valid_ps_nodetree(node_tree: NodeTree) -> bool:
        # check if the node tree has both Color and Alpha inputs and outputs
        has_color_input = False
        has_alpha_input = False
        has_color_output = False
        has_alpha_output = False
        for interface_item in node_tree.interface.items_tree:
            if interface_item.item_type == "SOCKET":
                # print(interface_item.name, interface_item.socket_type, interface_item.in_out)
                if interface_item.name == "Color" and interface_item.socket_type == "NodeSocketColor":
                    if interface_item.in_out == "INPUT":
                        has_color_input = True
                    else:
                        has_color_output = True
                elif interface_item.name == "Alpha" and interface_item.socket_type == "NodeSocketFloat":
                    if interface_item.in_out == "INPUT":
                        has_alpha_input = True
                    else:
                        has_alpha_output = True
        return has_color_input and has_alpha_input and has_color_output and has_alpha_output


def get_paint_system_collection(context: bpy.types.Context) -> bpy.types.Collection:
    view_layer = context.view_layer
    if "Paint System Collection" not in view_layer.layer_collection.collection.children:
        collection = bpy.data.collections.new("Paint System Collection")
        view_layer.layer_collection.collection.children.link(collection)
    else:
        collection = view_layer.layer_collection.collection.children["Paint System Collection"]
    return collection

def blender_color_to_srgb_hex(color: Color):
    """
    Converts a Blender Color property (Linear R, G, B floats 0.0-1.0) 
    to the corresponding sRGB color, and then to an 8-character hex string (#RRGGBB).
    """
    
    # 3. Convert the sRGB floats to 0-255 integers
    r = int(color.r * 255)
    g = int(color.g * 255)
    b = int(color.b * 255)
    
    # 4. Format and return
    return "#{:02x}{:02x}{:02x}".format(r, g, b).upper()


HEX_PATTERN = re.compile(r'^[0-9a-fA-F]{6}$')

def _is_valid_hex_code(hex_str_6char):
    """
    Checks if a cleaned 6-character string is a valid hex code using regex.
    """
    return HEX_PATTERN.match(hex_str_6char) is not None


def hex_string_to_blender_color(hex_string):
    """
    Converts a hex string (e.g., #A3F5B4 or A3F5B4) into a Blender 
    (R, G, B) float tuple (linear color space).

    If the string is invalid, returns White (1.0, 1.0, 1.0).

    Args:
        hex_string (str): The input string to check.

    Returns:
        tuple: (R, G, B) float values in linear color space.
    """
    
    # Define the default return color (White)
    WHITE_COLOR = (1.0, 1.0, 1.0)
    
    # 1. Cleanup the input string (remove optional hash prefix)
    cleaned_hex = hex_string.lstrip('#')
    
    # 2. Validation Check
    if not _is_valid_hex_code(cleaned_hex):
        print(f"Warning: Invalid hex code received: {hex_string}. Returning white.")
        return WHITE_COLOR
        
    # --- If Valid, proceed to conversion ---
    
    try:
        # 3. Parse components (convert RR, GG, BB from base 16 to base 10)
        r = int(cleaned_hex[0:2], 16)
        g = int(cleaned_hex[2:4], 16)
        b = int(cleaned_hex[4:6], 16)

        # 4. Normalize to 0.0 - 1.0 float values (treating input as sRGB)
        r_norm = r / 255.0
        g_norm = g / 255.0
        b_norm = b / 255.0

        # 5. Convert from sRGB (the standard hex space) to Linear (Blender space)
        # We must use mathutils.Color for accurate color space conversion
        linear_color = Color((r_norm, g_norm, b_norm))
        
        # 6. Return as a standard tuple
        return (linear_color.r, linear_color.g, linear_color.b)

    except ValueError:
        # Failsafe for any unexpected parsing error during int() conversion
        return WHITE_COLOR

class MarkerAction(PropertyGroup):
    action_bind: EnumProperty(
        name="Action Bind",
        description="Action bind",
        items=ACTION_BIND_ENUM
    )
    action_type: EnumProperty(
        name="Action Type",
        description="Action type",
        items=ACTION_TYPE_ENUM
    )
    frame: IntProperty(
        name="Frame",
        description="Frame to enable/disable the layer",
        default=0
    )
    marker_name: StringProperty(
        name="Marker Name",
        description="Marker name",
        default=""
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Enable the layer on a specific frame",
        default=True
    )

class GlobalLayer(PropertyGroup):
            
    def update_node_tree(self, context):
        if not self.node_tree:
            return
        if self.layer_name:
            self.node_tree.name = f".PS_Layer ({self.layer_name})"
        
        match self.type:
            case "IMAGE":
                if self.image:
                    self.image.name = self.layer_name
                layer_graph = create_image_graph(self)
            case "FOLDER":
                layer_graph = create_folder_graph(self)
            case "SOLID_COLOR":
                layer_graph = create_solid_graph(self)
            case "ATTRIBUTE":
                layer_graph = create_attribute_graph(self)
            case "ADJUSTMENT":
                layer_graph = create_adjustment_graph(self)
            case "GRADIENT":
                def add_empty_to_collection(empty_object):
                    collection = get_paint_system_collection(context)
                    collection.objects.link(empty_object)
                    
                if self.gradient_type in ('LINEAR', 'RADIAL'):
                    if not self.empty_object:
                        ps_ctx = parse_context(context)
                        with bpy.context.temp_override():
                            empty_object = bpy.data.objects.new(f"{self.name}", None)
                            empty_object.parent = ps_ctx.ps_object
                            add_empty_to_collection(empty_object)
                        self.empty_object = empty_object
                        if self.gradient_type == 'LINEAR':
                            self.empty_object.empty_display_type = 'SINGLE_ARROW'
                        elif self.gradient_type == 'RADIAL':
                            self.empty_object.empty_display_type = 'SPHERE'
                    elif self.empty_object.name not in context.view_layer.objects:
                        add_empty_to_collection(self.empty_object)
                layer_graph = create_gradient_graph(self)
            case "RANDOM":
                layer_graph = create_random_graph(self)
            case "NODE_GROUP":
                layer_graph = create_custom_graph(self)
            case "TEXTURE":
                layer_graph = create_texture_graph(self)
            case "GEOMETRY":
                layer_graph = create_geometry_graph(self)
            case _:
                raise ValueError(f"Invalid layer type: {self.type}")
        
        # Clean up
        if self.empty_object and self.type != "GRADIENT":
            collection = get_paint_system_collection(context)
            if self.empty_object.name in collection.objects:
                collection.objects.unlink(self.empty_object)
        
        if not self.enabled:
            layer_graph.link("group_input", "group_output", "Color", "Color")
            layer_graph.link("group_input", "group_output", "Alpha", "Alpha")
        layer_graph.compile()
        update_active_image(self, context)
    
    # Not used anymore
    def update_layer_name(self, context):
        """Update the layer name to ensure uniqueness."""
        new_name = get_next_unique_name(self.layer_name, [layer.layer_name for layer in context.scene.ps_scene_data.layers if layer != self])
        if new_name != self.layer_name:
            self.layer_name = new_name
        self.update_node_tree(context)
    
    def update_camera_plane(self, context):
        ps_ctx = parse_context(context)
        camera_plane = ps_ctx.camera_plane
        if self.attached_to_camera_plane:
            # Add the layer to the camera plane
            # Always add to the end of the list
            mat = None
            if "PS Camera Plane Material" in bpy.data.materials:
                mat = bpy.data.materials["PS Camera Plane Material"]
            else:
                mat = bpy.data.materials.new(name="PS Camera Plane Material")
            if not camera_plane:
                # Create the camera plane if it doesn't exist
                if "PS Camera Plane" in bpy.data.objects:
                    camera_plane = bpy.data.objects["PS Camera Plane"]
                else:
                    camera_plane = get_library_object("Camera Plane")
                    ps_ctx.ps_scene_data.camera_plane = camera_plane
                    camera_plane.hide_select = True
                    camera_plane.data.materials.append(mat)
                    get_paint_system_collection(context).objects.link(camera_plane)
                    with context.temp_override(active_object=camera_plane, selected_objects=[camera_plane]):
                        bpy.ops.paint_system.new_group(template='BASIC', add_layers=False)
                    # Rename at the end of group creation
                    camera_plane.name = "PS Camera Plane"
            cam_channel = camera_plane.material_slots[0].material.ps_mat_data.groups[0].channels[0]
            # Always add to the end of the list
            cam_channel.active_index = len(cam_channel.layers) - 1
            cam_channel.add_global_layer_to_channel(self)
        else:
            # Remove the layer from the camera plane
            cam_channel = ps_ctx.camera_plane_channel
            if cam_channel:
                for i, layer in enumerate(cam_channel.layers):
                    if layer.ref_layer_id == self.name:
                        cam_channel.layers.remove(i)
        if cam_channel:
            cam_channel.update_node_tree(context)
            cam_channel.normalize_orders()
            ps_ctx.active_channel.update_node_tree(context)
            self.update_node_tree(context)
            update_active_image(self, context)
            
    def find_node(self, identifier: str) -> Node | None:
        return get_node_from_nodetree(self.node_tree, identifier)
            
    @property
    def mix_node(self) -> Node | None:
        return self.find_node("mix_rgb")
    
    @property
    def post_mix_node(self) -> Node | None:
        return self.find_node("post_mix")
    
    @property
    def pre_mix_node(self) -> Node | None:
        return self.find_node("pre_mix")
    
    # @property
    # def is_clip(self) -> bool:
    #     if self.post_mix_node:
    #         return self.post_mix_node.inputs["Clip"].default_value
    #     return False

    # @property
    # def mix_factor(self) -> float:
    #     if self.post_mix_node:
    #         return self.post_mix_node.inputs["Factor"].default_value
    #     return 1.0
    
    name: StringProperty()
    
    layer_name: StringProperty(
        name="Name",
        description="Layer name",
        update=update_node_tree
    )
    updating_name_flag: bpy.props.BoolProperty(
        default=False, 
        options={'SKIP_SAVE'} # Don't save this flag in the .blend file
    )
    image: PointerProperty(
        name="Image",
        type=Image,
        update=update_node_tree
    )
    actions: CollectionProperty(
        type=MarkerAction,
        name="Actions",
        description="Collection of actions for the layer"
    )
    active_action_index: IntProperty(
        name="Active Action Index",
        description="Active action index",
        default=0
    )
    custom_node_tree: PointerProperty(
        name="Custom Node Tree",
        type=NodeTree,
        update=update_node_tree
    )
    custom_color_input: IntProperty(
        name="Custom Color Input",
        description="Custom color input",
        default=-1,
        update=update_node_tree
    )
    custom_alpha_input: IntProperty(
        name="Custom Alpha Input",
        description="Custom alpha input",
        default=-1,
        update=update_node_tree
    )
    custom_color_output: IntProperty(
        name="Custom Color Output",
        description="Custom color output",
        default=-1,
        update=update_node_tree
    )
    custom_alpha_output: IntProperty(
        name="Custom Alpha Output",
        description="Custom alpha output",
        default=-1,
        update=update_node_tree
    )
    coord_type: EnumProperty(
        items=COORDINATE_TYPE_ENUM,
        name="Coordinate Type",
        description="Coordinate type",
        default='AUTO',
        update=update_node_tree
    )
    uv_map_name: StringProperty(
        name="UV Map",
        description="Name of the UV map to use",
        update=update_node_tree
    )
    adjustment_type: EnumProperty(
        items=ADJUSTMENT_TYPE_ENUM,
        name="Adjustment Type",
        description="Adjustment type",
        update=update_node_tree
    )
    empty_object: PointerProperty(
        name="Empty Object",
        type=Object,
        update=update_node_tree
    )
    gradient_type: EnumProperty(
        items=GRADIENT_TYPE_ENUM,
        name="Gradient Type",
        description="Gradient type",
        default='LINEAR',
        update=update_node_tree
    )
    texture_type: EnumProperty(
        items=TEXTURE_TYPE_ENUM,
        name="Texture Type",
        description="Texture type",
        update=update_node_tree
    )
    geometry_type: EnumProperty(
        items=GEOMETRY_TYPE_ENUM,
        name="Geometry Type",
        description="Geometry type",
        update=update_node_tree
    )
    normalize_normal: BoolProperty(
        name="Normalize Normal",
        description="Normalize the normal",
        default=False,
        update=update_node_tree
    )
    type: EnumProperty(
        items=LAYER_TYPE_ENUM,
        default='IMAGE'
    )
    lock_layer: BoolProperty(
        name="Lock Layer",
        description="Lock the layer",
        default=False,
        update=update_active_image
    )
    node_tree: PointerProperty(
        name="Node Tree",
        type=NodeTree
    )
    external_image: PointerProperty(
        name="Edit External Image",
        type=Image,
    )
    is_expanded: BoolProperty(
        name="Expanded",
        description="Expand the layer",
        default=True,
        # update=select_layer
    )
    is_clip: BoolProperty(
        name="Clip",
        description="Clip the layer",
        default=False,
        update=update_active_channel
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Toggle layer visibility",
        default=True,
        update=update_node_tree,
        options=set()
    )
    lock_alpha: BoolProperty(
        name="Lock Alpha",
        description="Lock the alpha channel",
        default=False,
        update=update_brush_settings
    )
    attached_to_camera_plane: BoolProperty(
        name="Attached to Camera Plane",
        description="Attached to camera plane",
        default=False,
        update=update_camera_plane
    )
    camera_plane_position: FloatVectorProperty(
        name="Camera Plane Position",
        description="Camera plane position",
        default=(0, 0, 0),
        update=update_camera_plane
    )
    camera_plane_rotation: FloatVectorProperty(
        name="Camera Plane Rotation",
        description="Camera plane rotation",
        default=(0, 0, 0),
        update=update_camera_plane
    )

class Layer(BaseNestedListItem):
    """Base class for material layers in the Paint System"""
    def update_node_tree(self, context):
        global_layer = get_global_layer(self)
        if global_layer == None:
            return
        if global_layer.type == "IMAGE" and global_layer.coord_type == "AUTO":
            bpy.ops.paint_system.create_paint_system_uv_map('EXEC_DEFAULT')
        if global_layer:
            global_layer.update_node_tree(context)
    
    ref_layer_id: StringProperty()
    
    # Name is deprecated, use GlobalLayer.layer_name instead
    name: StringProperty(
        name="Name",
        description="Layer name",
        default="Layer",
        update=update_node_tree
    )
    
def save_cycles_settings():
    settings = {}
    scene = bpy.context.scene
    settings['render_engine'] = scene.render.engine
    settings['device'] = scene.cycles.device
    settings['samples'] = scene.cycles.samples
    settings['preview_samples'] = scene.cycles.preview_samples
    settings['denoiser'] = scene.cycles.denoiser
    settings['use_denoising'] = scene.cycles.use_denoising
    settings['use_adaptive_sampling'] = scene.cycles.use_adaptive_sampling
    return settings

def restore_cycles_settings(settings):
    scene = bpy.context.scene
    scene.render.engine = settings['render_engine']
    scene.cycles.device = settings['device']
    scene.cycles.samples = settings['samples']
    scene.cycles.preview_samples = settings['preview_samples']
    scene.cycles.denoiser = settings['denoiser']
    scene.cycles.use_denoising = settings['use_denoising']
    scene.cycles.use_adaptive_sampling = settings['use_adaptive_sampling']

def ps_bake(context, obj, mat, uv_layer, bake_image, use_gpu=True):
    node_tree = mat.node_tree
    
    image_node = node_tree.nodes.new(type='ShaderNodeTexImage')
    image_node.image = bake_image
    
    cycles_settings = save_cycles_settings()
    # Switch to Cycles if needed
    
    with context.temp_override(active_object=obj, selected_objects=[obj]):
        bake_params = {
            "type": 'EMIT',
        }
        if context.scene.render.engine != 'CYCLES':
            context.scene.render.engine = 'CYCLES'
        cycles = context.scene.cycles
        cycles.device = 'GPU' if use_gpu else 'CPU'
        cycles.samples = 1
        cycles.use_denoising = False
        cycles.use_adaptive_sampling = False
        for node in node_tree.nodes:
            node.select = False

        image_node.select = True
        node_tree.nodes.active = image_node
        try:
            bpy.ops.object.bake(**bake_params, uv_layer=uv_layer, use_clear=True)
        except Exception as e:
            # Try baking with CPU if GPU fails
            cycles.device = 'CPU'
            bpy.ops.object.bake(**bake_params, uv_layer=uv_layer, use_clear=True)

    # Delete bake nodes
    node_tree.nodes.remove(image_node)
    
    restore_cycles_settings(cycles_settings)

    return bake_image

class Channel(BaseNestedListManager):
    """Custom data for material layers in the Paint System"""
    
    def get_item_name(self, item):
        return get_global_layer(item).layer_name if item else "root"
    
    def update_node_tree(self, context):
        if not self.node_tree:
            return
        self.node_tree.name = f"PS {self.name}"
        if len(self.node_tree.interface.items_tree) == 0:
            self.node_tree.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
            self.node_tree.interface.new_socket("Alpha", in_out="OUTPUT", socket_type="NodeSocketFloat")
            self.node_tree.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
            self.node_tree.interface.new_socket("Alpha", in_out="INPUT", socket_type="NodeSocketFloat")
        node_builder = NodeTreeBuilder(self.node_tree, frame_name="Channel Graph", node_width=200)
        node_builder.add_node("group_input", "NodeGroupInput")
        node_builder.add_node("group_output", "NodeGroupOutput")
        
        if self.bake_image:
            node_builder.add_node("uv_map", "ShaderNodeUVMap", {"uv_map": self.bake_uv_map})
            node_builder.add_node("bake_image", "ShaderNodeTexImage", {"image": self.bake_image})
            node_builder.link("uv_map", "bake_image", "UV", "Vector")
            if self.use_bake_image:
                node_builder.link("bake_image", "group_output", "Color", "Color")
                node_builder.link("bake_image", "group_output", "Alpha", "Alpha")
                node_builder.compile()
                return
        
        flattened_layers = self.flatten_hierarchy()
        @dataclass
        class PreviousLayer:
            color_name: str
            color_socket: str
            alpha_name: str
            alpha_socket: str
            clip_mode = False
            clip_color_name: str|None = None
            clip_alpha_name: str|None = None
            clip_color_socket: str|None = None
            clip_alpha_socket: str|None = None
            
        previous_dict: Dict[int, PreviousLayer] = {}
        if self.type == "VECTOR" and self.use_normalize:
            node_builder.add_node("normalize", "ShaderNodeVectorMath", {"operation": "MULTIPLY_ADD", "hide": True}, {1: (0.5, 0.5, 0.5), 2: (0.5, 0.5, 0.5)})
        if self.type == "VECTOR" and self.world_to_object_normal:
            node_builder.add_node("world_to_object_normal", "ShaderNodeVectorTransform")
        
        node_builder.add_node("alpha_clamp_end", "ShaderNodeClamp", {"hide": True})
        node_builder.link("alpha_clamp_end", "group_output", "Result", "Alpha")
        previous_dict[-1] = PreviousLayer(color_name="group_output", color_socket="Color", alpha_name="alpha_clamp_end", alpha_socket="Value")
            
        if len(flattened_layers) > 0:
            for layer, _ in flattened_layers:
                previous_data = previous_dict.get(layer.parent_id, None)
                global_layer = get_global_layer(layer)
                if not global_layer:
                    continue
                # If the global layer is attached to camera plane and the channel is not a camera plane channel, skip
                if global_layer.attached_to_camera_plane and not self.is_camera_plane_channel:
                    # print("Skipping layer: ", layer.name, " because it is attached to camera plane and the channel is not a camera plane channel")
                    continue
                layer_identifier = global_layer.name
                node_builder.add_node(layer_identifier, "ShaderNodeGroup", {"node_tree": global_layer.node_tree}, {"Clip": global_layer.is_clip}, force_default_values=True)
                # match global_layer.type:
                #     case "IMAGE":
                #         layer_name = layer.name
                #         node_builder.add_node(layer_name, "ShaderNodeGroup", {"node_tree": global_layer.node_tree})
                #     case _:
                #         pass
                if global_layer.is_clip and not previous_data.clip_mode:
                    previous_data.clip_mode = True
                    clip_nt = get_alpha_over_nodetree()
                    clip_nt_identifier = f"clip_nt_{layer.id}"
                    node_builder.add_node(clip_nt_identifier, "ShaderNodeGroup", {"node_tree": clip_nt}, {"Color": (0, 0, 0, 1), "Alpha": 0}, force_default_values=True)
                    node_builder.link(clip_nt_identifier, previous_data.color_name, "Color", previous_data.color_socket)
                    node_builder.link(clip_nt_identifier, previous_data.alpha_name, "Alpha", previous_data.alpha_socket)
                    previous_data.color_name = clip_nt_identifier
                    previous_data.color_socket = "Color"
                    previous_data.alpha_name = clip_nt_identifier
                    previous_data.alpha_socket = "Alpha"
                    previous_data.clip_color_name = clip_nt_identifier
                    previous_data.clip_color_socket = "Over Color"
                    previous_data.clip_alpha_name = clip_nt_identifier
                    previous_data.clip_alpha_socket = "Over Alpha"
                target_color = previous_data.clip_color_name if previous_data.clip_mode else previous_data.color_name
                target_color_socket = previous_data.clip_color_socket if previous_data.clip_mode else previous_data.color_socket
                target_alpha = previous_data.clip_alpha_name if previous_data.clip_mode else previous_data.alpha_name
                target_alpha_socket = previous_data.clip_alpha_socket if previous_data.clip_mode else previous_data.alpha_socket
                node_builder.link(layer_identifier,
                                target_color,
                                "Color",
                                target_color_socket)
                node_builder.link(layer_identifier,
                                target_alpha,
                                "Alpha",
                                target_alpha_socket)
                if previous_data.clip_mode:
                    previous_data.clip_color_name = layer_identifier
                    previous_data.clip_color_socket = "Color"
                    previous_data.clip_alpha_name = layer_identifier
                    previous_data.clip_alpha_socket = "Alpha"
                else:
                    previous_data.color_name = layer_identifier
                    previous_data.color_socket = "Color"
                    previous_data.alpha_name = layer_identifier
                    previous_data.alpha_socket = "Alpha"
                if global_layer.type == "FOLDER":
                    previous_dict[layer.id] = PreviousLayer(
                        color_name=layer_identifier,
                        color_socket="Over Color",
                        alpha_name=layer_identifier,
                        alpha_socket="Over Alpha"
                    )
                if previous_data.clip_mode and not global_layer.is_clip:
                    previous_data.clip_mode = False
        prev_layer = previous_dict[-1]
        if self.type == "VECTOR" and self.use_normalize:
            node_builder.link("normalize", prev_layer.color_name, "Vector", prev_layer.color_socket)
            prev_layer.color_name = "normalize"
            prev_layer.color_socket = "Vector"
        if self.type == "VECTOR" and self.world_to_object_normal:
            node_builder.link("world_to_object_normal", prev_layer.color_name, "Vector", prev_layer.color_socket)
            prev_layer.color_name = "world_to_object_normal"
            prev_layer.color_socket = "Vector"
        node_builder.link("group_input", prev_layer.color_name, "Color", prev_layer.color_socket)
        node_builder.add_node("alpha_clamp_start", "ShaderNodeClamp", {"hide": True})
        node_builder.link("alpha_clamp_start", prev_layer.alpha_name, "Result", prev_layer.alpha_socket)
        node_builder.link("group_input", "alpha_clamp_start", "Alpha", "Value")
        node_builder.compile()
    
    def update_channel_name(self, context):
        """Update the channel name to ensure uniqueness."""
        if self.updating_name_flag:
            return
        if not self.node_tree:
            return
        self.node_tree.name = f".PS_Channel ({self.name})"
        self.updating_name_flag = True
        parsed_context = parse_context(context)
        active_group = parsed_context.active_group
        new_name = get_next_unique_name(self.name, [channel.name for channel in active_group.channels if channel != self])
        if new_name != self.name:
            self.name = new_name
        self.updating_name_flag = False
        update_active_group(self, context)
    
    def add_global_layer_to_channel(self, global_layer: GlobalLayer) -> Layer:
        parent_id, insert_order = self.get_insertion_data()
        # Adjust existing items' order
        self.adjust_sibling_orders(parent_id, insert_order)
        layer = self.add_item(
                global_layer.name,
                "ITEM" if global_layer.type != 'FOLDER' else "FOLDER",
                parent_id=parent_id,
                order=insert_order
            )
        layer.ref_layer_id = global_layer.name
        # Update active index
        new_id = layer.id
        if new_id != -1:
            for i, item in enumerate(self.layers):
                if item.id == new_id:
                    self.active_index = i
                    break
        return layer
    
    def bake(self, context: Context, mat: Material, bake_image: Image, uv_layer: str, use_gpu: bool = True, use_group_tree: bool = True):
        """Bake the channel

        Args:
            context (Context): The context
            mat (Material): The material
            bake_image (Image): The bake image
            uv_layer (str): The UV layer
            use_gpu (bool, optional): Whether to use the GPU. Defaults to True.
            use_group_tree (bool, optional): Whether to use the group tree if found. Defaults to True.

        Raises:
            ValueError: If the node tree is not found
        """
        
        node_tree = mat.node_tree
        if not node_tree:
            raise ValueError("Node tree not found")
        ps_context = parse_context(context)
        obj = ps_context.ps_object
        
        material_output = get_material_output(node_tree)
        surface_socket = material_output.inputs['Surface']
        from_socket = surface_socket.links[0].from_socket if surface_socket.links else None
        
        # Bake as output of group ps if exists in the node tree
        bake_node = None
        to_be_deleted_nodes = []
        color_output = None
        alpha_output = None
        
        if not self.use_alpha:
            # Use the value node set to 1 as alpha output
            value_node = node_tree.nodes.new('ShaderNodeValue')
            value_node.outputs['Value'].default_value = 1.0
            alpha_output = value_node.outputs['Value']
            to_be_deleted_nodes.append(value_node)
        
        if hasattr(mat, "ps_mat_data") and mat.ps_mat_data.groups and use_group_tree:
            for group in mat.ps_mat_data.groups:
                if group.node_tree and self.name in group.channels:
                    bake_node = find_node(node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': group.node_tree})
                    color_output = bake_node.outputs[self.name]
                    if self.use_alpha:
                        alpha_output = bake_node.outputs[f'{self.name} Alpha']
                    break
        
        if not bake_node:
            # Use channel node group instead
            bake_node = node_tree.nodes.new(type='ShaderNodeGroup')
            bake_node.node_tree = self.node_tree
            color_output = bake_node.outputs['Color']
            if self.use_alpha:
                alpha_output = bake_node.outputs['Alpha']
            to_be_deleted_nodes.append(bake_node)
        
        # Bake image
        connect_sockets(surface_socket, color_output)
        bake_image = ps_bake(context, obj, mat, uv_layer, bake_image, use_gpu)
        
        temp_alpha_image = bake_image.copy()
        temp_alpha_image.colorspace_settings.name = 'Non-Color'
        connect_sockets(surface_socket, alpha_output)
        temp_alpha_image = ps_bake(context, obj, mat, uv_layer, temp_alpha_image, use_gpu)

        if bake_image and temp_alpha_image:
            pixels_bake = np.empty(len(bake_image.pixels), dtype=np.float32)
            pixels_temp_alpha = np.empty(len(temp_alpha_image.pixels), dtype=np.float32)
            bake_image.pixels.foreach_get(pixels_bake)
            temp_alpha_image.pixels.foreach_get(pixels_temp_alpha)
            pixels_bake[3::4] = pixels_temp_alpha[1::4]
            bake_image.pixels.foreach_set(pixels_bake)
            bake_image.update()
            bake_image.pack()
        bpy.data.images.remove(temp_alpha_image)

        for node in to_be_deleted_nodes:
            node_tree.nodes.remove(node)
        
        # Restore surface socket
        if from_socket:
            connect_sockets(surface_socket, from_socket)

    def update_bake_image(self, context):
        if self.use_bake_image:
            # Force to object mode
            bpy.ops.object.mode_set(mode="OBJECT")
        self.update_node_tree(context)
        
    @property
    def item_type(self):
        return Layer
    
    @property
    def collection_name(self):
        return "layers"
            
    name: StringProperty(
        name="Name",
        description="Channel name",
        default="Channel",
        update=update_channel_name
    )
    updating_name_flag: BoolProperty(
        default=False,
        options={'SKIP_SAVE'}  # Don't save this flag in the .blend file
    )
    node_tree: PointerProperty(
        name="Node Tree",
        type=NodeTree
    )
    layers: CollectionProperty(
        type=Layer,
        name="Material Layers",
        description="Collection of material layers in the Paint System"
    )
    active_index: IntProperty(name="Active Material Layer Index", update=update_active_image)
    type: EnumProperty(
        items=CHANNEL_TYPE_ENUM,
        name="Channel Type",
        description="Type of the channel",
        default='COLOR',
        update=update_active_group
    )
    color_space: EnumProperty(
        items=COLOR_SPACE_ENUM,
        name="Color Space",
        description="Color space",
        default='COLOR'
    )
    use_alpha: BoolProperty(
        name="Expose Alpha Socket",
        description="Expose alpha socket in the Paint System group",
        default=True,
        update=update_active_group
    )
    use_max_min: BoolProperty(
        name="Use Max Min",
        description="Use max min for the channel",
        default=False,
        update=update_active_group
    )
    factor_min: FloatProperty(
        name="Factor Min",
        description="Minimum factor value",
        default=0,
        update=update_active_group
    )
    factor_max: FloatProperty(
        name="Factor Max",
        description="Maximum factor value",
        default=1,
        update=update_active_group
    )
    use_normalize: BoolProperty(
        name="Normalize",
        description="Normalize the channel",
        default=False,
        update=update_node_tree
    )
    world_to_object_normal: BoolProperty(
        name="World to Object Normal",
        description="World to object normal",
        default=False,
        update=update_node_tree
    )
    bake_image: PointerProperty(
        name="Bake Image",
        type=Image,
        update=update_bake_image
    )
    bake_uv_map: StringProperty(
        name="Bake Image UV Map",
        default="UVMap",
        update=update_bake_image
    )
    use_bake_image: BoolProperty(
        name="Use Bake Image",
        default=False,
        update=update_bake_image
    )

    @property
    def is_camera_plane_channel(self) -> bool:
        camera_plane = parse_context(bpy.context).camera_plane
        if camera_plane and camera_plane.material_slots and camera_plane.material_slots[0].material:
            camera_plane_material = camera_plane.material_slots[0].material
            if camera_plane_material and camera_plane_material.ps_mat_data and camera_plane_material.ps_mat_data.groups and camera_plane_material.ps_mat_data.groups[0].channels:
                camera_plane_channel = camera_plane_material.ps_mat_data.groups[0].channels[0]
                return camera_plane_channel == self
        return False
    
    def get_movement_menu_items(self, item_id, direction):
        """
        Get menu items for movement options.
        Returns list of tuples (identifier, label, description)
        """
        options = self.get_movement_options(item_id, direction)
        menu_items = []

        # Map option identifiers to their operators
        operator_map = {
            'UP': 'paint_system.move_up',
            'DOWN': 'paint_system.move_down'
        }

        for identifier, description in options:
            menu_items.append((
                operator_map[direction],
                description,
                {'action': identifier}
            ))

        return menu_items


class Group(PropertyGroup):
    """Base class for Paint System groups"""
    
    def get_group_node(self, node_tree: NodeTree) -> bpy.types.Node:
        return find_node(node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': self.node_tree})
    
    def update_node_tree(self, context):
        if not self.node_tree:
            return
        node_tree = self.node_tree
        mat = None
        # Get the material that contains this group
        for material in bpy.data.materials:
            if material.ps_mat_data and material.ps_mat_data.groups:
                for group in material.ps_mat_data.groups:
                    if group.node_tree == node_tree:
                        mat = material
                        break
        if mat:
            node_tree.name = f"PS {self.name} ({mat.name})"
        else:
            node_tree.name = f"PS {self.name} (None)"
        # node_tree.name = f"Paint System ({self.name})"
        if not isinstance(node_tree, bpy.types.NodeTree):
            return
        
        # Ensure node sockets are in the correct order
        def detect_change(old, new):
            if len(new) > len(old):  # ADD
                for i in range(len(new)):
                    if i >= len(old) or old[i] != new[i]:
                        return "ADD", i

            elif len(new) < len(old):  # REMOVE
                for i in range(len(old)):
                    if i >= len(new) or old[i] != new[i]:
                        return "REMOVE", i

            else:  # Same length: MOVE or RENAME
                # Check if it's a MOVE
                for i in range(len(old)):
                    if old[i] != new[i]:
                        # MOVE: element exists in both lists but index changed
                        if old[i] in new and new[i] in old:
                            return "MOVE", i
                        else:
                            return "RENAME", i

            return None, None  # No change
        
        nt_interface = node_tree.interface
        nt_sockets = nt_interface.items_tree
        
        @dataclass
        class ExpectedSocket:
            name: str
            socket_type: str
            use_max_min: bool = False
            min_value: float = 0
            max_value: float = 1
        
        expected_sockets: List[ExpectedSocket] = []
        for channel in self.channels:
            expected_sockets.append(ExpectedSocket(channel.name, f"NodeSocket{channel.type.title()}", channel.use_max_min, channel.factor_min, channel.factor_max))
            if channel.use_alpha:
                expected_sockets.append(ExpectedSocket(f"{channel.name} Alpha", "NodeSocketFloat", True, 0, 1))
        
        def ensure_sockets(expected_sockets, in_out = "OUTPUT"):
            if in_out == "INPUT":
                offset_idx = len(expected_sockets)
            else:
                offset_idx = 0
            while True:
                output_sockets = [socket for socket in nt_sockets if socket.item_type == "SOCKET" and socket.in_out == in_out]
                output_sockets_names = [socket.name for socket in output_sockets]
                change, idx = detect_change(output_sockets_names, [socket.name for socket in expected_sockets])
                if change is None:
                    break
                match change:
                    case "ADD":
                        socket_name, socket_type, use_max_min = expected_sockets[idx].name, expected_sockets[idx].socket_type, expected_sockets[idx].use_max_min
                        socket = nt_interface.new_socket(name=socket_name, socket_type=socket_type, in_out=in_out)
                        if hasattr(socket, "subtype") and use_max_min:
                            socket.subtype = "FACTOR"
                            socket.min_value = expected_sockets[idx].min_value
                            socket.max_value = expected_sockets[idx].max_value
                        nt_interface.move(socket, idx + offset_idx)
                    case "REMOVE":
                        socket = output_sockets[idx]
                        nt_interface.remove(socket)
                    case "MOVE":
                        socket = output_sockets[idx]
                        expected_socket_idx = [socket.name for socket in expected_sockets].index(socket.name)
                        nt_interface.move(socket, expected_socket_idx + offset_idx + 1)
                    case "RENAME":
                        socket = output_sockets[idx]
                        socket.name = expected_sockets[idx].name
            
            # ensure socket type
            for idx, socket in enumerate(output_sockets):
                if socket.socket_type != expected_sockets[idx].socket_type:
                    socket.socket_type = expected_sockets[idx].socket_type
                
                if hasattr(socket, "subtype"):
                    expected_subtype = "FACTOR" if expected_sockets[idx].use_max_min else "NONE"
                    socket.subtype = expected_subtype
                    if expected_sockets[idx].use_max_min:
                        socket.min_value = expected_sockets[idx].min_value
                        socket.max_value = expected_sockets[idx].max_value
                    else:
                        socket.min_value = -1e39
                        socket.max_value = 1e39
        
        ensure_sockets(expected_sockets, "OUTPUT")
        ensure_sockets(expected_sockets, "INPUT")
        
        node_builder = NodeTreeBuilder(self.node_tree, frame_name="Group Graph", clear=True)
        node_builder.add_node("group_input", "NodeGroupInput")
        node_builder.add_node("group_output", "NodeGroupOutput")
        for channel in self.channels:
            if not channel.node_tree or len(channel.node_tree.interface.items_tree) == 0:
                # Channel is not valid, skip it
                continue
            channel_name = channel.name
            c_alpha_name = f"{channel.name} Alpha"
            node_builder.add_node(channel_name, "ShaderNodeGroup", {"node_tree": channel.node_tree}, {"Alpha": 1})
            node_builder.link("group_input", channel_name, channel_name, "Color")
                
            if channel.use_alpha:
                node_builder.link("group_input", channel_name, c_alpha_name, "Alpha")
            node_builder.link(channel_name, "group_output", "Color", channel_name)
            if channel.use_alpha:
                node_builder.link(channel_name, "group_output", "Alpha", c_alpha_name)
        node_builder.compile()
    
    name: StringProperty(
        name="Name",
        description="Group name",
        default="New Group",
        update=update_node_tree
    )
    channels: CollectionProperty(
        type=Channel,
        name="Channels",
        description="Collection of channels in the Paint System"
    )
    template: EnumProperty(
        name="Template",
        items=TEMPLATE_ENUM,
        default='BASIC'
    )
    coord_type: EnumProperty(
        items=COORDINATE_TYPE_ENUM,
        name="Coordinate Type",
        description="Coordinate type",
        default='AUTO'
    )
    uv_map_name: StringProperty(
        name="UV Map",
        description="UV map",
        default="UVMap"
    )
    
    def update_channel(self, context):
        ps_ctx = parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        if ps_mat_data.preview_channel:
            # Call paint_system.isolate_active_channel twice to ensure it's updated
            bpy.ops.paint_system.isolate_active_channel('EXEC_DEFAULT')
            bpy.ops.paint_system.isolate_active_channel('EXEC_DEFAULT')
        if ps_ctx.active_channel.use_bake_image:
            # Force to object mode
            bpy.ops.object.mode_set(mode="OBJECT")
        update_active_image(self, context)
        # After switching channel, sync the Image Editor to the active channel's image
        try:
            from ..operators.image_editor_sync import update_active_channel_on_switch
            update_active_channel_on_switch(self, context)
        except Exception as e:
            # Keep this silent to avoid breaking channel switching if editor is absent
            print(f"[PaintSystem] Image editor sync skipped: {e}")
    
    active_index: IntProperty(name="Active Channel Index", update=update_channel)
    node_tree: PointerProperty(
        name="Node Tree",
        type=NodeTree
    )

class PaintSystemGlobalData(PropertyGroup):
    """Custom data for the Paint System"""
    
    def get_brush_color(self, context):
        settings = context.tool_settings.image_paint
        brush = settings.brush
        if hasattr(context.tool_settings, "unified_paint_settings"):
            ups = context.tool_settings.unified_paint_settings
        else:
            ups = settings.unified_paint_settings
        prop_owner = ups if ups.use_unified_color else brush
        return prop_owner.color
    
    def update_unified_color(self, context):
        brush_color = self.get_brush_color(context)
        if brush_color.hsv != (self.hue, self.saturation, self.value):
            brush_color.hsv = (self.hue, self.saturation, self.value)
    
    def update_hex_color(self, context):
        brush_color = self.get_brush_color(context)
        brush_color_hex = blender_color_to_srgb_hex(brush_color)
        if brush_color_hex != self.hex_color:
            color = hex_string_to_blender_color(self.hex_color)
            brush_color.r = color[0]
            brush_color.g = color[1]
            brush_color.b = color[2]
    
    
    clipboard_layers: CollectionProperty(
        type=Layer,
        name="Clipboard Layers",
        description="Collection of layers in the clipboard"
    )
    active_clipboard_index: IntProperty(name="Active Clipboard Layer Index")
    layers: CollectionProperty(
        type=GlobalLayer,
        name="Paint System Layers",
        description="Collection of layers in the Paint System"
    )
    active_index: IntProperty(name="Active Layer Index")
    camera_plane: PointerProperty(
        name="Camera Plane Object",
        type=Object
    )
    last_selected_ps_object: PointerProperty(
        name="Last Selected Object",
        type=Object
    )
    last_selected_object: PointerProperty(
        name="Last Selected Object",
        type=Object
    )
    last_selected_material: PointerProperty(
        name="Last Selected Material",
        type=Material
    )
    hue: FloatProperty(
        name="Hue",
        description="Hue of the brush",
        default=0.0,
        update=update_unified_color,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    saturation: FloatProperty(
        name="Saturation",
        description="Saturation of the brush",
        default=0.0,
        update=update_unified_color,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    value: FloatProperty(
        name="Value",
        description="Value of the brush",
        default=0.0,
        update=update_unified_color,
        min=0.0,
        max=1.0,
        subtype='FACTOR'
    )
    hex_color: StringProperty(
        name="Hex Color",
        description="Hex color of the brush",
        default="#000000",
        update=update_hex_color,
    )

class MaterialData(PropertyGroup):
    """Custom data for channels in the Paint System"""
    groups: CollectionProperty(
        type=Group,
        name="Groups",
        description="Collection of groups in the Paint System"
    )
    active_index: IntProperty(name="Active Group Index")
    use_alpha: BoolProperty(
        name="Use Alpha",
        description="Use alpha channel in the Paint System",
        default=True
    )
    preview_channel: BoolProperty(
        name="Preview Channel",
        description="Preview the channel",
        default=False
    )
    original_node_name: StringProperty(
        name="Original Node Name",
        description="Original node name of the channel"
    )
    original_socket_name: StringProperty(
        name="Original Socket Name",
        description="Original socket name of the channel"
    )


class CameraPlaneData(PropertyGroup):
    position: FloatVectorProperty(
        name="Position",
        description="Position of the camera plane",
        default=(0, 0, 0)
    )
    rotation: FloatVectorProperty(
        name="Rotation",
        description="Rotation of the camera plane",
        default=(0, 0, 0)
    )
    ref_layer_id: StringProperty()


class Filter(PropertyGroup):
    name: StringProperty()
    type: EnumProperty(
        items=FILTER_TYPE_ENUM,
        name="Filter Type",
        description="Filter type"
    )
    radius: FloatProperty(
        name="Radius",
        description="Radius of the filter",
        default=1.0
    )
    iterations: IntProperty(
        name="Iterations",
        description="Iterations of the filter",
        default=1
    )


def get_global_layer(layer: Layer) -> GlobalLayer | None:
    """Get the global layer data from the context."""
    if not layer or not bpy.context.scene or not bpy.context.scene.ps_scene_data:
        return None
    # for global_layer in bpy.context.scene.ps_scene_data.layers[layer.ref_layer_id]:
    #     if global_layer.name == layer.ref_layer_id:
    #         return global_layer
    return bpy.context.scene.ps_scene_data.layers.get(layer.ref_layer_id, None)

def get_blend_type(global_layer: GlobalLayer) -> str:
    """Get the blend mode of the global layer"""
    node_tree = global_layer.node_tree
    if not node_tree:
        raise ValueError("Node tree is not found")
    mix_node = find_node(node_tree, {'label': 'mix_rgb', 'bl_idname': 'ShaderNodeMix'})
    if not mix_node:
        raise ValueError("Mix node is not found")
    return mix_node.blend_type

def set_blend_type(global_layer: GlobalLayer, blend_type: str) -> None:
    """Set the blend mode of the global layer"""
    node_tree = global_layer.node_tree
    if not node_tree:
        raise ValueError("Node tree is not found")
    mix_node = find_node(node_tree, {'label': 'mix_rgb', 'bl_idname': 'ShaderNodeMix'})
    if not mix_node:
        raise ValueError("Mix node is not found")
    mix_node.blend_type = blend_type

def is_global_layer_linked(global_layer: GlobalLayer) -> bool:
    """Check if the global layer is linked"""
    # Check all material in the scene and count the number of times the global layer is used
    count = 0
    for material in bpy.data.materials:
        if material.name == "PS Camera Plane Material":
            continue
        if hasattr(material, 'ps_mat_data'):
            for group in material.ps_mat_data.groups:
                for channel in group.channels:
                    for layer in channel.layers:
                        if layer.ref_layer_id == global_layer.name:
                            count += 1
    return count > 1

def sort_actions(context: bpy.types.Context, global_layer: GlobalLayer) -> list[MarkerAction]:
    sorted_actions = []
    if global_layer.actions:
        for action in global_layer.actions:
            if action.action_bind == 'FRAME':
                sorted_actions.append((action.frame, action))
            elif action.action_bind == 'MARKER':
                marker = context.scene.timeline_markers.get(action.marker_name)
                if marker:
                    sorted_actions.append((marker.frame, action))
                else:
                    sorted_actions.append((0, action))
        sorted_actions.sort(key=lambda x: x[0])
    return [x for _, x in sorted_actions]

def get_all_layers(material: bpy.types.Material) -> list[Layer]:
    layers = []
    if not material or not material.ps_mat_data:
        return layers
    for group in material.ps_mat_data.groups:
        for channel in group.channels:
            for layer in channel.layers:
                layers.append(layer)
    return layers
@dataclass
class PSContext:
    ps_settings: PaintSystemPreferences | None = None
    ps_scene_data: PaintSystemGlobalData | None = None
    active_object: bpy.types.Object | None = None
    ps_object: bpy.types.Object | None = None
    active_material: bpy.types.Material | None = None
    ps_mat_data: MaterialData | None = None
    active_group: Group | None = None
    active_channel: Channel | None = None
    active_layer: Layer | None = None
    active_global_layer: GlobalLayer | None = None
    camera_plane: bpy.types.Object | None = None
    camera_plane_material: bpy.types.Material | None = None
    camera_plane_channel: Channel | None = None

def parse_context(context: bpy.types.Context) -> PSContext:
    """Parse the context and return a PSContext object."""
    if not context:
        raise ValueError("Context cannot be None")
    if not isinstance(context, bpy.types.Context):
        raise TypeError("context must be of type bpy.types.Context")
    
    ps_settings = get_preferences(context)
    
    ps_scene_data = context.scene.ps_scene_data
    
    ps_object = None
    obj = context.active_object
    if obj:
        match obj.type:
            case 'EMPTY':
                if obj.parent and obj.parent.type == 'MESH' and hasattr(obj.parent.active_material, 'ps_mat_data'):
                    ps_object = obj.parent
            case 'MESH':
                ps_object = obj
            case 'GREASEPENCIL':
                if is_newer_than(4,3,0):
                    ps_object = obj
            case _:
                obj = None
                ps_object = None
        if obj and obj.name == "PS Camera Plane":
            obj = ps_scene_data.last_selected_ps_object
            ps_object = obj

    mat = ps_object.active_material if ps_object else None
    
    mat_data = None
    groups = None
    active_group = None
    if mat and hasattr(mat, 'ps_mat_data') and mat.ps_mat_data:
        mat_data = mat.ps_mat_data
        groups = mat_data.groups
        if groups and mat_data.active_index >= 0:
            active_group = groups[min(mat_data.active_index, len(groups) - 1)]
    
    channels = None
    active_channel = None
    if active_group:
        channels = active_group.channels
        if channels and active_group.active_index >= 0:
            active_channel = channels[min(active_group.active_index, len(channels) - 1)]

    layers = None
    active_layer = None
    if active_channel:
        layers = active_channel.layers
        if layers and active_channel.active_index >= 0:
            active_layer = layers[min(active_channel.active_index, len(layers) - 1)]
            
    camera_plane = None
    if ps_scene_data and ps_scene_data.camera_plane:
        camera_plane = ps_scene_data.camera_plane
    
    camera_plane_channel = None
    camera_plane_material = None
    if camera_plane and camera_plane.material_slots and camera_plane.material_slots[0].material:
        camera_plane_material = camera_plane.material_slots[0].material
        if camera_plane_material and camera_plane_material.ps_mat_data and camera_plane_material.ps_mat_data.groups and camera_plane_material.ps_mat_data.groups[0].channels:
            camera_plane_channel = camera_plane_material.ps_mat_data.groups[0].channels[0]
    
    return PSContext(
        ps_settings=ps_settings,
        ps_scene_data=ps_scene_data,
        active_object=obj,
        ps_object=ps_object,
        active_material=mat,
        ps_mat_data=mat_data,
        active_group=active_group,
        active_channel=active_channel,
        active_layer=active_layer,
        active_global_layer=get_global_layer(active_layer) if active_layer else None,
        camera_plane=camera_plane,
        camera_plane_material=camera_plane_material,
        camera_plane_channel=camera_plane_channel
    )

class PSContextMixin:
    """A mixin for classes that need access to the paint system context."""

    @staticmethod
    def parse_context(context: bpy.types.Context) -> PSContext:
        """Return a PSContext parsed from Blender context. Safe to call from class or instance methods."""
        return parse_context(context)


# Legacy properties (for backward compatibility)
class LegacyPaintSystemLayer(PropertyGroup):

    name: StringProperty(
        name="Name",
        description="Layer name",
        default="Layer",
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Toggle layer visibility",
        default=True,
    )
    image: PointerProperty(
        name="Image",
        type=Image
    )
    type: EnumProperty(
        items=[
        ('FOLDER', "Folder", "Folder layer"),
        ('IMAGE', "Image", "Image layer"),
        ('SOLID_COLOR', "Solid Color", "Solid Color layer"),
        ('ATTRIBUTE', "Attribute", "Attribute layer"),
        ('ADJUSTMENT', "Adjustment", "Adjustment layer"),
        ('SHADER', "Shader", "Shader layer"),
        ('NODE_GROUP', "Node Group", "Node Group layer"),
        ('GRADIENT', "Gradient", "Gradient layer"),
    ],
        default='IMAGE'
    )
    sub_type: StringProperty(
        name="Sub Type",
        default="",
    )
    clip: BoolProperty(
        name="Clip to Below",
        description="Clip the layer to the one below",
        default=False,
    )
    lock_alpha: BoolProperty(
        name="Lock Alpha",
        description="Lock the alpha channel",
        default=False,
    )
    lock_layer: BoolProperty(
        name="Lock Layer",
        description="Lock the layer",
        default=False,
    )
    node_tree: PointerProperty(
        name="Node Tree",
        type=NodeTree
    )
    edit_mask: BoolProperty(
        name="Edit Mask",
        description="Edit mask",
        default=False,
    )
    mask_image: PointerProperty(
        name="Mask Image",
        type=Image,
    )
    enable_mask: BoolProperty(
        name="Enabled Mask",
        description="Toggle mask visibility",
        default=False,
    )
    mask_uv_map: StringProperty(
        name="Mask UV Map",
        default="",
    )
    external_image: PointerProperty(
        name="Edit External Image",
        type=Image,
    )
    expanded: BoolProperty(
        name="Expanded",
        description="Expand the layer",
        default=True,
    )

class LegacyPaintSystemGroup(PropertyGroup):
# Define the collection property directly in the class
    items: CollectionProperty(type=LegacyPaintSystemLayer)
    name: StringProperty(
        name="Name",
        description="Group name",
        default="Group",
    )
    active_index: IntProperty(
        name="Active Index",
        description="Active layer index",
    )
    node_tree: PointerProperty(
        name="Node Tree",
        type=bpy.types.NodeTree
    )
    bake_image: PointerProperty(
        name="Bake Image",
        type=Image
    )
    bake_uv_map: StringProperty(
        name="Bake Image UV Map",
        default="UVMap",
    )
    use_bake_image: BoolProperty(
        name="Use Bake Image",
        default=False,
    )


class LegacyPaintSystemGroups(PropertyGroup):
    name: StringProperty(
        name="Name",
        description="Paint system name",
        default="Paint System"
    )
    groups: CollectionProperty(type=LegacyPaintSystemGroup)
    active_index: IntProperty(
        name="Active Index",
        description="Active group index",
    )
    use_paintsystem_uv: BoolProperty(
        name="Use Paint System UV",
        description="Use the Paint System UV Map",
        default=True
    )

class LegacyPaintSystemContextParser:
    def __init__(self, context: bpy.types.Context):
        self.context = context
        self.active_object = context.object
        self.groups = self.get_groups()
        # layer_node_tree = self.get_active_layer().node_tree
        # self.layer_node_group = self.get_active_layer_node_group()
        self.color_mix_node = self.find_color_mix_node()
        self.uv_map_node = self.find_uv_map_node()
        self.opacity_mix_node = self.find_opacity_mix_node()
        self.clip_mix_node = self.find_clip_mix_node()
        self.rgb_node = self.find_rgb_node()
        
    def get_active_material(self) -> Optional[Material]:
        if not self.active_object or self.active_object.type != 'MESH':
            return None

        return self.active_object.active_material

    def get_material_settings(self):
        mat = self.get_active_material()
        if not mat or not hasattr(mat, "paint_system"):
            return None
        return mat.paint_system

    def get_groups(self) -> Optional[PropertyGroup]:
        paint_system = self.get_material_settings()
        if not paint_system:
            return None
        return paint_system.groups

    def get_active_group(self) -> Optional[PropertyGroup]:
        paint_system = self.get_material_settings()
        if not paint_system or len(paint_system.groups) == 0:
            return None
        active_group_idx = int(paint_system.active_index)
        if active_group_idx >= len(paint_system.groups):
            return None  # handle cases where active index is invalid
        return paint_system.groups[active_group_idx]

    def get_active_layer(self) -> Optional[PropertyGroup]:
        active_group = self.get_active_group()
        if not active_group or len(active_group.items) == 0 or active_group.active_index >= len(active_group.items):
            return None

        return active_group.items[active_group.active_index]

    def get_layer_node_tree(self) -> Optional[NodeTree]:
        active_layer = self.get_active_layer()
        if not active_layer:
            return None
        return active_layer.node_tree

    def get_active_layer_node_group(self) -> Optional[Node]:
        active_group = self.get_active_group()
        layer_node_tree = self.get_layer_node_tree()
        if not layer_node_tree:
            return None
        node_details = {'type': 'GROUP', 'node_tree': layer_node_tree}
        node = self.find_node(active_group.node_tree, node_details)
        return node

    def find_color_mix_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'type': 'MIX', 'data_type': 'RGBA'}
        return self.find_node(layer_node_tree, node_details)

    def find_uv_map_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'type': 'UVMAP'}
        return self.find_node(layer_node_tree, node_details)

    def find_opacity_mix_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'type': 'MIX', 'name': 'Opacity'}
        return self.find_node(layer_node_tree, node_details) or self.find_color_mix_node()

    def find_clip_mix_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'type': 'MIX', 'name': 'Clip'}
        return self.find_node(layer_node_tree, node_details)

    def find_image_texture_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'type': 'TEX_IMAGE'}
        return self.find_node(layer_node_tree, node_details)

    def find_rgb_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'name': 'RGB'}
        return self.find_node(layer_node_tree, node_details)

    def find_adjustment_node(self) -> Optional[Node]:
        layer_node_tree = self.get_layer_node_tree()
        node_details = {'label': 'Adjustment'}
        return self.find_node(layer_node_tree, node_details)

    def find_node_group(self, node_tree: NodeTree) -> Optional[Node]:
        node_tree = self.get_active_group().node_tree
        for node in node_tree.nodes:
            if hasattr(node, 'node_tree') and node.node_tree and node.node_tree.name == node_tree.name:
                return node
        return None
    
    def find_attribute_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'type': 'ATTRIBUTE'}
        return self.find_node(layer_node_tree, node_details)
    
    def find_node(self, node_tree, node_details):
        if not node_tree:
            return None
        for node in node_tree.nodes:
            match = True
            for key, value in node_details.items():
                if getattr(node, key) != value:
                    match = False
                    break
            if match:
                return node
        return None

classes = (
    MarkerAction,
    GlobalLayer,
    Layer,
    Channel,
    Group,
    PaintSystemGlobalData,
    MaterialData,
    LegacyPaintSystemLayer,
    LegacyPaintSystemGroup,
    LegacyPaintSystemGroups,
    )

_register, _unregister = register_classes_factory(classes)

def register():
    """Register the Paint System data module."""
    _register()
    bpy.types.Scene.ps_scene_data = PointerProperty(
        type=PaintSystemGlobalData,
        name="Paint System Data",
        description="Data for the Paint System"
    )
    bpy.types.Material.ps_mat_data = PointerProperty(
        type=MaterialData,
        name="Paint System Material Data",
        description="Material Data for the Paint System"
    )
    bpy.types.Material.paint_system = PointerProperty(type=LegacyPaintSystemGroups)
    
def unregister():
    """Unregister the Paint System data module."""
    del bpy.types.Material.paint_system
    del bpy.types.Material.ps_mat_data
    del bpy.types.Scene.ps_scene_data
    _unregister()