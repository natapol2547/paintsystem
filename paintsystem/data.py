from dataclasses import dataclass
from typing import Dict, List, Literal
import re
import mathutils
import numpy as np
import uuid
from collections import Counter
import math

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
    NodeSocket,
    NodeTree,
    Object,
    PropertyGroup,
    Material,
)
from bpy.utils import register_classes_factory
from bpy_extras.node_utils import connect_sockets
from typing import Optional
from mathutils import Color, Euler, Vector

from .image import blender_image_to_numpy, set_image_pixels, save_image, ImageTiles

from .list_manager import ListManager

# ---
from ..custom_icons import get_icon
from ..utils.version import is_newer_than
from ..utils.nodes import find_node, get_material_output, get_node_socket_enum, get_nodetree_socket_enum
from ..preferences import get_preferences
from ..utils import get_next_unique_name
from .context import get_legacy_global_layer, parse_context
from .graph import (
    NodeTreeBuilder,
    Add_Node,
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
    get_layer_blend_type,
    set_layer_blend_type,
)
from .graph.common import get_library_nodetree, get_library_object, DEFAULT_PS_UV_MAP_NAME
from .nested_list_manager import BaseNestedListManager, BaseNestedListItem

BLEND_MODE_ENUM = []
for blend_mode in bpy.types.ShaderNodeMixRGB.bl_rna.properties['blend_type'].enum_items:
    BLEND_MODE_ENUM.append((blend_mode.identifier, blend_mode.name, blend_mode.description))
    if blend_mode.identifier in ["MIX", "COLOR_BURN", "ADD", "LINEAR_LIGHT", "DIVIDE"]:
        if blend_mode.identifier == "MIX":
            BLEND_MODE_ENUM.append(("PASSTHROUGH", "Pass Through", "Pass Through"))
        BLEND_MODE_ENUM.append((None))

MASK_BLEND_MODE_ENUM = [
    ('SUBTRACT', "Subtract", "Subtract"),
    ('ADD', "Add", "Add"),
    ('MULTIPLY', "Multiply", "Multiply"),
]

TEMPLATE_ENUM = [
    ('BASIC', "Basic", "Basic painting setup", "IMAGE", 0),
    ('PAINT_OVER', "Paint Over", "Paint over the existing material", get_icon('paintbrush'), 1),
    ('PBR', "PBR", "PBR painting setup", "MATERIAL", 2),
    ('NORMAL', "Normals Painting", "Start off with a normal painting setup", "NORMALS_VERTEX_FACE", 3),
    ('NONE', "None", "Just add node group to material", "NONE", 4),
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
    ('BLANK', "Blank", "Blank layer"),
]

CHANNEL_TYPE_ENUM = [
    ('COLOR', "Color", "Color channel", get_icon('color_socket'), 1),
    ('VECTOR', "Vector", "Vector channel", get_icon('vector_socket'), 2),
    ('FLOAT', "Value", "Value channel", get_icon('float_socket'), 3),
]

GRADIENT_TYPE_ENUM = [
    ('GRADIENT_MAP', "Gradient Map", "Gradient map"),
    ('LINEAR', "Linear Gradient", "Linear gradient"),
    ('RADIAL', "Radial Gradient", "Radial gradient"),
    ('DISTANCE', "Distance Gradient", "Distance gradient"),
    ('FAKE_LIGHT', "Fake Light", "Fake light"),
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
    ('OBJECT', "Object", "Use a object output of Texture Coordinate node"),
    ('CAMERA', "Camera", "Use a camera output of Texture Coordinate node"),
    ('WINDOW', "Window", "Use a window output of Texture Coordinate node"),
    ('REFLECTION', "Reflection", "Use a reflection output of Texture Coordinate node"),
    ('POSITION', "Position", "Use a position output of Geometry node"),
    ('GENERATED', "Generated", "Use a generated output of Texture Coordinate node"),
    ('DECAL', "Decal", "Use a decal output of Geometry node"),
    ('PROJECT', "Projection", "Define a projection coordinate"),
    ('PARALLAX', 'Parallax', 'Use a parallax coordinate'),
]

MASK_COORDINATE_TYPE_ENUM = [
    ('LAYER', "Layer", "Use the layer's coordinate type"),
    ('AUTO', "Auto UV", "Automatically create a new UV Map"),
    ('UV', "UV", "Open an existing UV Map"),
    ('OBJECT', "Object", "Use a object output of Texture Coordinate node"),
    ('CAMERA', "Camera", "Use a camera output of Texture Coordinate node"),
    ('WINDOW', "Window", "Use a window output of Texture Coordinate node"),
    ('REFLECTION', "Reflection", "Use a reflection output of Texture Coordinate node"),
    ('POSITION', "Position", "Use a position output of Geometry node"),
    ('GENERATED', "Generated", "Use a generated output of Texture Coordinate node"),
    ('DECAL', "Decal", "Use a decal output of Geometry node"),
    ('PROJECT', "Projection", "Define a projection coordinate"),
    ('PARALLAX', 'Parallax', 'Use a parallax coordinate'),
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

PARALLAX_TYPE_ENUM = [
    ('UV', "UV", "UV"),
    ('Object', "Object", "Object"),
]

EDIT_EXTERNAL_MODE_ENUM = [
    ('IMAGE_EDIT', "Image Edit", "Edit Image in external editor", "IMAGE", 0),
    ('VIEW_CAPTURE', "View Capture", "Capture view and edit in external editor", "CAMERA_DATA", 1),
]

def is_valid_uuidv4(uuid_string):
    """
    Checks if a given string is a valid UUIDv4.

    Args:
        uuid_string (str): The string to validate.

    Returns:
        bool: True if the string is a valid UUIDv4, False otherwise.
    """
    try:
        uuid_obj = uuid.UUID(uuid_string, version=4)
        # Ensure the string representation of the object matches the original string
        # to catch cases where a valid UUID string might have been padded or altered
        return str(uuid_obj) == uuid_string
    except ValueError:
        return False


def update_brush_settings(self=None, context: bpy.types.Context = bpy.context):
    if context.mode != 'PAINT_TEXTURE':
        return
    ps_ctx = parse_context(context)
    active_layer = ps_ctx.active_layer
    if not active_layer:
        return
    brush = context.tool_settings.image_paint.brush
    if not brush:
        return
    brush.use_alpha = not active_layer.lock_alpha

def update_active_image(self=None, context: bpy.types.Context = None):
    context = context or bpy.context
    ps_ctx = parse_context(context)
    image_paint = context.tool_settings.image_paint
    obj = ps_ctx.ps_object
    mat = ps_ctx.active_material
    active_channel = ps_ctx.active_channel
    if not mat or not active_channel:
        return
    active_layer = ps_ctx.active_layer
    update_brush_settings(self, context)

    if image_paint.mode == 'MATERIAL':
        image_paint.mode = 'IMAGE'
    if not active_layer or active_layer.lock_layer or active_channel.use_bake_image:
        image_paint.canvas = None
        # Unable to paint
        return
    
    selected_image: Image = active_layer.image
    image_paint.canvas = selected_image
    if active_layer.coord_type == 'UV':
        if active_layer.uv_map_name and obj.data.uv_layers.get(active_layer.uv_map_name):
            obj.data.uv_layers[active_layer.uv_map_name].active = True
    elif active_layer.coord_type == 'AUTO' and obj.data.uv_layers.get(DEFAULT_PS_UV_MAP_NAME):
        obj.data.uv_layers[DEFAULT_PS_UV_MAP_NAME].active = True

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

def find_channels_containing_layer(check_layer: "Layer") -> list["Channel"]:
    channels = []
    for material in bpy.data.materials:
        if hasattr(material, 'ps_mat_data'):
            for group in material.ps_mat_data.groups:
                for channel in group.channels:
                    for layer in channel.layers:
                        if layer == check_layer or layer.linked_layer_uid == check_layer.uid:
                            channels.append(channel)
    return channels

def get_node_from_nodetree(node_tree: NodeTree, identifier: str) -> Node | None:
    if not node_tree or not node_tree.nodes:
        return None
    # for node in node_tree.nodes:
    #     if node.label == identifier:
    #         return node
    return find_node(node_tree, {'label': identifier})
    # return None

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

@dataclass
class ExpectedSocket:
    name: str
    socket_type: str
    use_max_min: bool = False
    min_value: float = 0
    max_value: float = 1
        
def ensure_sockets(node_tree: NodeTree, expected_sockets: List[ExpectedSocket], in_out = "OUTPUT"):
    nt_interface = node_tree.interface
    nt_sockets = nt_interface.items_tree
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

def get_udim_tiles(object: bpy.types.Object, uv_layer_name: str):
    uv_layer = object.data.uv_layers.get(uv_layer_name)
    if not uv_layer:
        return {1001}
    udim_tiles = set()
    uv_data = np.empty((len(uv_layer.uv), 2), dtype=np.float32)
    for idx, uv_loop in enumerate(uv_layer.uv):
        uv_data[idx] = uv_loop.vector
    for coord in uv_data:
        row = max(1, math.ceil(coord[1])) - 1
        col = max(1, math.ceil(coord[0]))
        udim_tiles.add(1000 + row * 10 + col)
    return udim_tiles

def ensure_udim_tiles(image: bpy.types.Image, objects: list[bpy.types.Object], uv_layer_name: str):
    # Check position the data in uv_layer, create a list of number for UDIM tiles
    udim_tiles = set()
    for object in objects:
        udim_tiles.update(get_udim_tiles(object, uv_layer_name))
    width, height = image.size
    
    # Clean up tiles that does not have image
    for tile in image.tiles:
        if tile.channels == 0:
            image.tiles.remove(tile)

    for tile_number in udim_tiles:
        if any(tile_number == tile.number for tile in image.tiles):
            continue
        with bpy.context.temp_override(edit_image=image):
            bpy.ops.image.tile_add(number=tile_number, color=(0, 0, 0, 0), width=width, height=height)
    # Delete unused tiles
    for tile in image.tiles:
        if tile.number not in udim_tiles:
            print(f"Removing tile {tile.number}")
            image.tiles.remove(tile)
    save_image(image)

def create_ps_image(name: str, width: int = 2048, height: int = 2048, use_udim_tiles: bool = False, objects: list[bpy.types.Object] = None, uv_layer_name: str = None, use_float: bool = False):
    img = bpy.data.images.new(
        name=name, width=width, height=height, alpha=True, float_buffer=use_float)
    img.generated_color = (0, 0, 0, 0)
    save_image(img)
    if use_udim_tiles:
        img.source = "TILED"
        if objects and uv_layer_name:
            ensure_udim_tiles(img, objects, uv_layer_name)
        else:
            raise ValueError("Objects and UV layer name are required for UDIM tiles")
    return img

def ensure_paint_system_uv_map(context: bpy.types.Context):
    selection = context.selected_objects

    # Get the active object
    ps_object = parse_context(context).ps_object
    
    if ps_object.data.uv_layers.get(DEFAULT_PS_UV_MAP_NAME):
        return

    # Deselect all objects
    for obj in selection:
        if obj != ps_object:
            obj.select_set(False)
    # Make it active
    context.view_layer.objects.active = ps_object
    original_mode = str(ps_object.mode)
    bpy.ops.object.mode_set(mode='EDIT')
    obj.update_from_editmode()
    bpy.ops.mesh.select_all(action='SELECT')
    # Apply to only the active object
    uv_layers = ps_object.data.uv_layers
    uvmap = uv_layers.new(name=DEFAULT_PS_UV_MAP_NAME)
    ps_object.data.uv_layers.active = uvmap
    bpy.ops.uv.smart_project(angle_limit=30/180*math.pi, island_margin=0.005)
    bpy.ops.object.mode_set(mode=original_mode)
    # Deselect the object
    ps_object.select_set(False)
    # Restore the selection
    for obj in selection:
        obj.select_set(True)
    context.view_layer.objects.active = ps_object

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
    
    name: StringProperty()
    
    layer_name: StringProperty(
        name="Name",
        description="Layer name",
    )
    updating_name_flag: bpy.props.BoolProperty(
        default=False, 
        options={'SKIP_SAVE'} # Don't save this flag in the .blend file
    )
    image: PointerProperty(
        name="Image",
        type=Image,
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
    )
    custom_color_input: IntProperty(
        name="Custom Color Input",
        description="Custom color input",
        default=-1,
    )
    custom_alpha_input: IntProperty(
        name="Custom Alpha Input",
        description="Custom alpha input",
        default=-1,
    )
    custom_color_output: IntProperty(
        name="Custom Color Output",
        description="Custom color output",
        default=-1,
    )
    custom_alpha_output: IntProperty(
        name="Custom Alpha Output",
        description="Custom alpha output",
        default=-1,
    )
    coord_type: EnumProperty(
        items=COORDINATE_TYPE_ENUM,
        name="Coordinate Type",
        description="Coordinate type",
        default='UV',
    )
    uv_map_name: StringProperty(
        name="UV Map",
        description="Name of the UV map to use",
    )
    adjustment_type: EnumProperty(
        items=ADJUSTMENT_TYPE_ENUM,
        name="Adjustment Type",
        description="Adjustment type",
    )
    empty_object: PointerProperty(
        name="Empty Object",
        type=Object,
    )
    gradient_type: EnumProperty(
        items=GRADIENT_TYPE_ENUM,
        name="Gradient Type",
        description="Gradient type",
        default='LINEAR',
    )
    texture_type: EnumProperty(
        items=TEXTURE_TYPE_ENUM,
        name="Texture Type",
        description="Texture type",
    )
    geometry_type: EnumProperty(
        items=GEOMETRY_TYPE_ENUM,
        name="Geometry Type",
        description="Geometry type",
    )
    normalize_normal: BoolProperty(
        name="Normalize Normal",
        description="Normalize the normal",
        default=False,
    )
    type: EnumProperty(
        items=LAYER_TYPE_ENUM,
        default='IMAGE'
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
    external_image: PointerProperty(
        name="Edit External Image",
        type=Image,
    )
    is_expanded: BoolProperty(
        name="Expanded",
        description="Expand the layer",
        default=True,
    )
    is_clip: BoolProperty(
        name="Clip",
        description="Clip the layer",
        default=False,
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Toggle layer visibility",
        default=True,
        options=set()
    )
    lock_alpha: BoolProperty(
        name="Lock Alpha",
        description="Lock the alpha channel",
        default=False,
    )

class LayerMask(PropertyGroup):
    uid: StringProperty()
    name: StringProperty(
        name="Name",
        description="Name of the mask",
        default="Mask",
    )
    type: EnumProperty(
        items=[
            ('IMAGE', "Image", "Image mask"),
            ('GEOMETRY', "Geometry", "Geometry mask"),
        ],
        name="Mask Type",
        description="Mask type",
        default='IMAGE',
    )
    coord_type: EnumProperty(
        items=COORDINATE_TYPE_ENUM,
        name="Coordinate Type",
        description="Coordinate type",
        default='UV',
    )
    blend_mode: EnumProperty(
        items=MASK_BLEND_MODE_ENUM,
        name="Blend Mode",
        description="Blend mode",
        default='MULTIPLY',
    )
    mask_image: PointerProperty(
        name="Mask Image",
        type=Image,
    )
    mask_uv_map: StringProperty(
        name="Mask UV Map",
        description="Mask UV map",
        default="",
    )

def add_empty_to_collection(context: bpy.types.Context, empty_object: bpy.types.Object):
    collection = get_paint_system_collection(context)
    if empty_object.name not in collection.objects:
        collection.objects.link(empty_object)

class Layer(BaseNestedListItem):
    """Base class for material layers in the Paint System"""
    
    # Deprecated
    ref_layer_id: StringProperty()
    
    def update_name(self, context):
        if self.layer_name != self.name:
            self.layer_name = self.name
        self.update_node_tree(context)
    
    name: StringProperty(
        name="Name",
        description="Layer name",
        default="Layer",
        update=update_name
    )
    
    def update_node_tree(self, context):
        if not self.auto_update_node_tree:
            return
        # Ensure the paint system UV map even if it's linked
        if self.get_layer_data().coord_type == 'AUTO':
            ensure_paint_system_uv_map(context)
        
        if self.is_linked:
            return
        if not is_valid_uuidv4(self.uid):
            self.uid = str(uuid.uuid4())
        if self.type == "BLANK":
            return
        
        if self.blend_mode == "PASSTHROUGH" and self.type != "FOLDER":
            self.blend_mode = "MIX"
        
        if not self.node_tree and not self.is_linked:
            node_tree = bpy.data.node_groups.new(name=f"PS_Layer ({self.name})", type='ShaderNodeTree')
            self.node_tree = node_tree
            expected_input = [
                ExpectedSocket(name="Clip", socket_type="NodeSocketBool"),
                ExpectedSocket(name="Color", socket_type="NodeSocketColor"),
                ExpectedSocket(name="Alpha", socket_type="NodeSocketFloat"),
            ]
            if self.type == "FOLDER":
                expected_input.append(ExpectedSocket(name="Over Color", socket_type="NodeSocketColor"))
                expected_input.append(ExpectedSocket(name="Over Alpha", socket_type="NodeSocketFloat"))
            expected_output = [
                ExpectedSocket(name="Color", socket_type="NodeSocketColor"),
                ExpectedSocket(name="Alpha", socket_type="NodeSocketFloat"),
            ]
            ensure_sockets(node_tree, expected_input, "INPUT")
            ensure_sockets(node_tree, expected_output, "OUTPUT")
        if self.name:
            self.node_tree.name = f"PS {self.name} ({self.uid[:8]})"
        
        if self.coord_type == "DECAL":
            if not self.empty_object:
                self.ensure_empty_object()
                self.empty_object.empty_display_type = 'SINGLE_ARROW'
            elif self.empty_object.name not in context.view_layer.objects:
                add_empty_to_collection(context, self.empty_object)
        
        match self.type:
            case "IMAGE":
                if self.image:
                    self.image.name = self.name
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
                if self.gradient_type in ('LINEAR', 'RADIAL', 'FAKE_LIGHT'):
                    if not self.empty_object:
                        self.ensure_empty_object()
                        if self.gradient_type == 'LINEAR':
                            self.empty_object.empty_display_type = 'SINGLE_ARROW'
                        elif self.gradient_type == 'RADIAL':
                            self.empty_object.empty_display_type = 'SPHERE'
                        elif self.gradient_type == 'FAKE_LIGHT':
                            self.empty_object.location += Vector((0, 0, 2))
                            self.empty_object.rotation_euler = Euler((3*math.pi/4, math.pi/4, 0))
                            self.empty_object.empty_display_type = 'SINGLE_ARROW'
                    elif self.empty_object.name not in context.view_layer.objects:
                        add_empty_to_collection(context, self.empty_object)
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
        if self.empty_object and self.type not in ["GRADIENT", "IMAGE", "TEXTURE", "FAKE_LIGHT"]:
            collection = get_paint_system_collection(context)
            if self.empty_object.name in collection.objects:
                collection.objects.unlink(self.empty_object)
        elif self.type == "IMAGE" and self.empty_object and self.coord_type != "DECAL":
            collection = get_paint_system_collection(context)
            if self.empty_object.name in collection.objects:
                collection.objects.unlink(self.empty_object)

        if not self.enabled:
            layer_graph.link("group_input", "group_output", "Color", "Color")
            layer_graph.link("group_input", "group_output", "Alpha", "Alpha")
        layer_graph.compile()
        
        # For fake light, we need to update the empty object rotation via drivers
        object_rot_node = self.find_node("object_rotation")
        def add_rot_driver_to_socket(socket: NodeSocket, transform_type: str = "ROT_X"):
            # Try to delete the driver first
            try:
                socket.driver_remove("default_value")
            except:
                pass
            curve = socket.driver_add("default_value")
            curve.driver.type = "AVERAGE"
            driver_var = curve.driver.variables.new()
            driver_var.name = "rotation_euler"
            driver_var.type = "TRANSFORMS"
            driver_var.targets[0].id = self.empty_object
            driver_var.targets[0].transform_type = transform_type
            return curve
        if object_rot_node:
            add_rot_driver_to_socket(object_rot_node.inputs["X"], "ROT_X")
            add_rot_driver_to_socket(object_rot_node.inputs["Y"], "ROT_Y")
            add_rot_driver_to_socket(object_rot_node.inputs["Z"], "ROT_Z")
        
        update_active_image(self, context)
    
            
    def find_node(self, identifier: str) -> Node | None:
        self = self.get_layer_data()
        return get_node_from_nodetree(self.node_tree, identifier)
            
    @property
    def mix_node(self) -> Node | None:
        self = self.get_layer_data()
        return self.find_node("mix_rgb")
    
    @property
    def post_mix_node(self) -> Node | None:
        self = self.get_layer_data()
        return self.find_node("post_mix")
    
    @property
    def source_node(self) -> Node | None:
        if not self.node_tree:
            return None
        source_node = self.node_tree.nodes.get("source")
        if source_node:
            return source_node
        # Backup
        source_node = self.find_node("source")
        if source_node:
            return source_node
        # Legacy source node
        match self.type:
            case "IMAGE":
                return self.find_node("image")
            case "TEXTURE":
                return self.find_node("texture")
            case "ATTRIBUTE":
                return self.find_node("attribute")
            case "ADJUSTMENT":
                return self.find_node("adjustment")
            case "GRADIENT":
                return self.find_node("gradient")
            case "NODE_GROUP":
                return self.find_node("custom_node_tree")
            case "SOLID_COLOR":
                return self.find_node("rgb")
            case _:
                return None
        return None
    
    @property
    def pre_mix_node(self) -> Node | None:
        self = self.get_layer_data()
        return self.find_node("pre_mix")
    
    uid: StringProperty()
    
    def update_layer_name(self, context):
        if self.layer_name != self.name:
            self.name = self.layer_name
        self.update_node_tree(context)
    
    layer_name: StringProperty(
        name="Name",
        description="Layer name",
        update=update_layer_name
    )
    updating_name_flag: BoolProperty(
        default=False, 
        options={'SKIP_SAVE'} # Don't save this flag in the .blend file
    )
    image: PointerProperty(
        name="Image",
        type=Image,
        update=update_node_tree
    )
    correct_image_aspect: BoolProperty(
        name="Correct Image Aspect",
        description="Correct the image aspect",
        default=True,
        update=update_node_tree
    )
    
    # Layer actions
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
    
    # For NODE_GROUP type
    custom_node_tree: PointerProperty(
        name="Custom Node Tree",
        type=NodeTree,
        update=update_node_tree
    )
    def get_inputs_enum(self, context: Context):
        inputs = []
        if self.type == "NODE_GROUP" and self.custom_node_tree:
            custom_node_tree = bpy.data.node_groups.get(self.custom_node_tree.name)
            if custom_node_tree:
                inputs = get_nodetree_socket_enum(custom_node_tree, in_out='INPUT', include_none=True)
        elif self.source_node:
            inputs = get_node_socket_enum(self.source_node, in_out='INPUT', include_none=True)
        else:
            inputs = [('_NONE_', 'None', '', 'BLANK1', 0)]
        return inputs
    def get_color_enum(self, context: Context):
        outputs = []
        if self.type == "NODE_GROUP" and self.custom_node_tree:
            custom_node_tree = bpy.data.node_groups.get(self.custom_node_tree.name)
            if custom_node_tree:
                outputs = get_nodetree_socket_enum(custom_node_tree, in_out='OUTPUT', include_none=False)
        elif self.source_node:
            outputs = get_node_socket_enum(self.source_node, in_out='OUTPUT', favor_socket_name='Color', include_none=False, none_at_start=False)
        else:
            outputs = [('_NONE_', 'None', '', 'BLANK1', 0)]
        return outputs
    def get_alpha_enum(self, context: Context):
        outputs = []
        if self.type == "NODE_GROUP" and self.custom_node_tree:
            custom_node_tree = bpy.data.node_groups.get(self.custom_node_tree.name)
            if custom_node_tree:
                outputs = get_nodetree_socket_enum(custom_node_tree, in_out='OUTPUT', include_none=True)
        elif self.source_node:
            outputs = get_node_socket_enum(self.source_node, in_out='OUTPUT', favor_socket_name='Alpha', include_none=True, none_at_start=False)
        else:
            outputs = [('_NONE_', 'None', '', 'BLANK1', 0)]
        return outputs
    color_input_name: EnumProperty(
        name="Color Input Socket Name",
        description="Color input socket",
        items=get_inputs_enum,
        update=update_node_tree
    )
    alpha_input_name: EnumProperty(
        name="Alpha Input Socket Name",
        description="Alpha input socket",
        items=get_inputs_enum,
        update=update_node_tree
    )
    color_output_name: EnumProperty(
        name="Color Output Socket Name",
        description="Color output socket",
        items=get_color_enum,
        update=update_node_tree
    )
    alpha_output_name: EnumProperty(
        name="Alpha Output Socket Name",
        description="Alpha output socket",
        items=get_alpha_enum,
        update=update_node_tree
    )
    
    # Deprecated. Use color_input_socket
    custom_color_input: IntProperty(
        name="Custom Color Input",
        description="Custom color input",
        default=-1,
        update=update_node_tree
    )
    # Deprecated. Use alpha_input_socket instead
    custom_alpha_input: IntProperty(
        name="Custom Alpha Input",
        description="Custom alpha input",
        default=-1,
        update=update_node_tree
    )
    # Deprecated. Use color_output_socket instead
    custom_color_output: IntProperty(
        name="Custom Color Output",
        description="Custom color output",
        default=-1,
        update=update_node_tree
    )
    # Deprecated. Use alpha_output_socket instead
    custom_alpha_output: IntProperty(
        name="Custom Alpha Output",
        description="Custom alpha output",
        default=-1,
        update=update_node_tree
    )
    def set_projection_view(self, context: Context):
        ps_ctx = parse_context(context)
        active_space = context.area.spaces.active
        if active_space.type == 'VIEW_3D':
            region_3d = active_space.region_3d
            if region_3d:
                match region_3d.view_perspective:
                    case 'PERSP':
                        view_mat = region_3d.view_matrix.copy()
                        if self.projection_space == "OBJECT":
                            view_mat = view_mat @ ps_ctx.ps_object.matrix_world
                        view_mat.invert()
                        loc, rot, sca = view_mat.decompose()
                        self.projection_position = loc
                        self.projection_rotation = rot.to_euler()
                        self.projection_fov = 2*math.atan(0.5*72/active_space.lens)
                    case 'ORTHO':
                        # TODO: Implement orthographic projection
                        pass
                    case "CAMERA":
                        active_camera = bpy.context.scene.camera
                        view_mat = active_camera.matrix_world.copy()
                        if self.projection_space == "OBJECT":
                            view_mat = ps_ctx.ps_object.matrix_world.inverted() @ view_mat
                        loc, rot, sca = view_mat.decompose()
                        self.projection_position = loc
                        self.projection_rotation = rot.to_euler()
                        self.projection_fov = active_camera.data.angle
                    case _:
                        pass
    def update_coord_type(self, context: Context):
        if self.coord_type in ['DECAL', 'PROJECT']:
            if self.type == "IMAGE":
                image_node = self.source_node
                if image_node:
                    image_node.extension = "CLIP"
        if self.coord_type == "PROJECT" and not self.find_node("proj_node"):
            # Capture the camera position
            self.set_projection_view(context)
        self.update_node_tree(context)
    coord_type: EnumProperty(
        items=COORDINATE_TYPE_ENUM,
        name="Coordinate Type",
        description="Coordinate type",
        default='UV',
        update=update_coord_type,
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
        default='GRADIENT_MAP',
        update=update_node_tree
    )
    def update_texture_type(self, context: Context):
        self.auto_update_node_tree = False
        try:
            if self.type == "TEXTURE":
                self.color_output_name = "Color"
                self.alpha_output_name = "_NONE_"
        except:
            pass
        self.auto_update_node_tree = True
        self.update_node_tree(context)
    texture_type: EnumProperty(
        items=TEXTURE_TYPE_ENUM,
        name="Texture Type",
        description="Texture type",
        update=update_texture_type
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
    def update_type(self, context: Context):
        try:
            if self.type == "IMAGE":
                self.color_output_name = "Color"
                self.alpha_output_name = "Alpha"
        except:
            pass
        self.update_node_tree(context)
    type: EnumProperty(
        items=LAYER_TYPE_ENUM,
        default='IMAGE',
        update=update_type
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
    edit_external_mode: EnumProperty(
        items=EDIT_EXTERNAL_MODE_ENUM,
        name="Edit External Mode",
        description="Edit external mode",
        default='IMAGE_EDIT'
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
    
    # For parallax coordinate type
    parallax_space: EnumProperty(
        items=PARALLAX_TYPE_ENUM,
        name="Parallax Type",
        description="Parallax type",
        default='UV',
        update=update_node_tree
    )
    parallax_uv_map_name: StringProperty(
        name="Parallax UV Map",
        description="Name of the UV map to use for parallax",
        update=update_node_tree
    )
    
    # Decal properties
    use_decal_depth_clip: BoolProperty(
        name="Use Decal Depth Clip",
        description="Use the decal depth clip",
        default=True,
        update=update_node_tree
    )
    
    # Projection properties
    projection_position: FloatVectorProperty(
        name="Projection Position",
        description="Projection position",
        default=(0, 0, 0),
        update=update_node_tree,
        subtype='TRANSLATION'
    )
    projection_rotation: FloatVectorProperty(
        name="Projection Rotation",
        description="Projection rotation",
        default=(0, 0, 0),
        update=update_node_tree,
        subtype='EULER'
    )
    projection_fov: FloatProperty(
        name="Projection FOV",
        description="Projection FOV",
        default=40/180*math.pi,
        update=update_node_tree,
        subtype='ANGLE'
    )
    projection_space: EnumProperty(
        items=[
            ("WORLD", "World", "World Space Coordinates", "WORLD", 0),
            ("OBJECT", "Object", "Object Space Coordinates", "OBJECT_DATA", 1),
        ],
        name="Projection Mode",
        description="Projection mode",
        default="WORLD",
        update=update_node_tree
    )
    
    def update_blend_mode(self, context: Context):
        layer_data = self.get_layer_data()
        layer_data.update_node_tree(context)
        for channel in find_channels_containing_layer(layer_data):
            channel.update_node_tree(context)
    def get_blend_mode_items(self, context: Context) -> list[tuple[str, str, str]]:
        return BLEND_MODE_ENUM if self.type == "FOLDER" else [blend_mode for blend_mode in BLEND_MODE_ENUM if blend_mode == None or blend_mode[0] != "PASSTHROUGH"]
    blend_mode: EnumProperty(
        items=get_blend_mode_items,
        name="Blend Mode",
        description="Blend mode",
        update=update_blend_mode
    )
    
    auto_update_node_tree: BoolProperty(
        name="Update Node Tree",
        description="Update the node tree",
        default=True,
        options={'SKIP_SAVE'}
    )
    
    # Linked layer data
    @property
    def is_linked(self) -> bool:
        # print(f"Linked layer {self.linked_layer_uid} to material {self.linked_material.name if self.linked_material else 'None'}")
        return bool(self.linked_layer_uid and self.linked_material)
    
    linked_layer_uid: StringProperty(
        name="Linked Layer ID",
        description="Linked layer ID",
        default="",
        update=update_node_tree
    )
    linked_material: PointerProperty(
        name="Linked Material",
        type=Material,
        update=update_node_tree
    )
    
    update_node_tree_flag: BoolProperty(
        name="Update Node Tree Flag",
        description="Update the node tree flag",
        default=True,
        options={'SKIP_SAVE'}
    )
    
    def add_action(self, name: str, action_bind: str, action_type: str, frame: int|None = None, marker_name: str|None = None):
        action = self.actions.add()
        action.name = name
        action.action_bind = action_bind
        action.action_type = action_type
        if action_bind == 'FRAME':
            if frame is None:
                raise ValueError("Frame is required")
            action.frame = frame
        elif action_bind == 'MARKER':
            if marker_name is None:
                raise ValueError("Marker name is required")
            action.marker_name = marker_name
        return action
    
    def remove_action(self, index: int):
        self.actions.remove(index)
    
    def remove_active_action(self):
        self.actions.remove(self.active_action_index)
        self.active_action_index = min(self.active_action_index, len(self.actions) - 1)
    
    @property
    def uses_coord_type(self) -> bool:
        return self.type in ['IMAGE', 'TEXTURE']
    
    def get_layer_warnings(self, context: Context) -> List[str]:
        ps_ctx = parse_context(context)
        layer_data = self.get_layer_data()
        active_channel = ps_ctx.active_channel
        flattened = active_channel.flatten_hierarchy()
        current_flat_index = next(
            (i for i, (it, _) in enumerate(flattened) if it.id == self.id), -1)
        below_layer, next_index = active_channel.get_next_sibling_item(flattened, current_flat_index)
        warnings = []
        blend_mode = get_layer_blend_type(layer_data)
        # If no layer below
        if not below_layer or active_channel.get_parent_layer_id(below_layer) != active_channel.get_parent_layer_id(self):
            if blend_mode != 'MIX':
                warnings.append("Blend mode is not MIX and there is no layer below")
            if layer_data.type == "ADJUSTMENT":
                warnings.append("Adjustment do not work without a layer below")
            
        return warnings
    
    def ensure_empty_object(self):
        context = bpy.context
        ps_ctx = parse_context(context)
        empty_name = f"{self.name} ({self.uid[:8]}) Empty"
        if empty_name in bpy.data.objects:
            empty_object = bpy.data.objects[empty_name]
            empty_object.parent = ps_ctx.ps_object
            add_empty_to_collection(context, empty_object)
        else:
            with bpy.context.temp_override():
                empty_object = bpy.data.objects.new(empty_name, None)
                empty_object.parent = ps_ctx.ps_object
                add_empty_to_collection(context, empty_object)
        self.empty_object = empty_object
        return empty_object
    
    def duplicate_layer_data(self, layer: "Layer"):
        self.uid = str(uuid.uuid4())
        if layer.node_tree:
            self.node_tree = layer.node_tree.copy()
        if layer.image:
            # if image is not saved, save it
            image: Image = layer.image
            save_image(image)
            self.image = image.copy()
        if layer.empty_object:
            self.empty_object = layer.empty_object.copy()
            self.empty_object.name = f"{self.name} ({self.uid[:8]}) Empty"
            self.ensure_empty_object()
    
    def link_layer_data(self, layer: "Layer"):
        self.apply_properties(layer, self, ignore_props=["name", "uid", "id", "order", "parent_id", "layer_name"])
    
    def unlink_layer_data(self):
        layer = self.get_layer_data()
        if is_layer_linked(self) and not self.is_linked:
            # self owns the data
            self.transfer_linked_data()
            self.duplicate_layer_data(self)
        else:
            self.linked_layer_uid = ""
            self.linked_material = None
            self.copy_layer_data(layer)
    
    def copy_layer_data(self, layer: "Layer"):
        self.duplicate_layer_data(layer)
        self.apply_properties(layer, self, ignore_props=["name", "uid", "node_tree", "image", "empty_object", "type", "id", "order", "parent_id", "layer_name"])
    
    def get_layer_data(self) -> "Layer":
        if self.is_linked:
            if not self.linked_material or not self.linked_material.ps_mat_data:
                print(f"Linked material {self.linked_material.name if self.linked_material else 'None'} not found")
                return None
            
            # Use cached UID lookup dictionary for O(1) access instead of nested loops
            uid_to_layer = _get_material_layer_uid_map(self.linked_material)
            layer = uid_to_layer.get(self.linked_layer_uid)
            if not layer:
                layer = _get_material_layer_uid_map(self.linked_material, force_refresh=True).get(self.linked_layer_uid)
            return uid_to_layer.get(self.linked_layer_uid)
        return self
    
    def transfer_linked_data(self):
        linked_layer_uid_map = {}
        for material in bpy.data.materials:
            if hasattr(material, 'ps_mat_data'):
                for group in material.ps_mat_data.groups:
                    for channel in group.channels:
                        for layer in channel.layers:
                            if layer.is_linked and layer.linked_layer_uid == self.uid:
                                linked_layer_uid_map[layer.uid] = [layer, material]
        # Migrate layer data to one of the linked layers
        linked_layers = [layer for layer, _ in linked_layer_uid_map.values() if layer.is_linked and layer.linked_layer_uid == self.uid]
        new_main_layer, new_material = list(linked_layer_uid_map.values())[0]
        new_main_layer.link_layer_data(self)
        
        for linked_layer in linked_layers[1:]:
            linked_layer.linked_layer_uid = new_main_layer.uid
            linked_layer.linked_material = new_material
        
        return new_main_layer, new_material
    
    def delete_layer_data(self):
        """
        Delete the layer data. Transfer to a linked layer if it is linked.
        """
        layer = self.get_layer_data()
        if is_layer_linked(layer) and not self.is_linked:
            print(f"Transferring layer data for {layer.name} to linked layers")
            self.transfer_linked_data()
        else:
            print(f"Deleting layer data for {self.name}")
            if self.empty_object:
                bpy.data.objects.remove(self.empty_object, do_unlink=True)
            # TODO: The following causes some issue when undoing
            if self.node_tree:
                bpy.data.node_groups.remove(self.node_tree)
    
    def apply_properties(self, from_layer: "Layer", to_layer: "Layer", ignore_props: list[str] = []):
        retry_props = []
        for prop in from_layer.bl_rna.properties:
            pid = getattr(prop, 'identifier', '')
            if not pid or getattr(prop, 'is_readonly', False):
                continue
            if pid in ignore_props:
                continue
            value = getattr(from_layer, pid)
            try:
                setattr(to_layer, pid, value)
            except Exception as e:
                retry_props.append(pid)
        # If some properties failed, force update_node_tree first and then apply the properties again
        failed_props = []
        if retry_props:
            print(f"Warning: Could not apply properties {retry_props} for {to_layer.name}, retrying...")
            original_auto_update_node_tree = bool(to_layer.auto_update_node_tree)
            to_layer.auto_update_node_tree = False
            to_layer.update_node_tree(bpy.context)
            for pid in retry_props:
                value = getattr(from_layer, pid)
                try:
                    setattr(to_layer, pid, value)
                except Exception as e:
                    failed_props.append(pid)
            to_layer.auto_update_node_tree = original_auto_update_node_tree
        if failed_props:
            print(f"Warning: Could not apply properties {failed_props} for {to_layer.name}")
    
    @property
    def modifies_color_data(self) -> bool:
        return self.type == "ATTRIBUTE" or (self.type == "GRADIENT" and self.gradient_type == "GRADIENT_MAP") or self.blend_mode != "MIX"

def get_layer_by_uid(material: Material, uid: str) -> Layer | None:
    uid_to_layer = _get_material_layer_uid_map(material)
    layer = uid_to_layer.get(uid)
    if not layer:
        layer = _get_material_layer_uid_map(material, force_refresh=True).get(uid)
    return layer

# Module-level cache for material layer UID maps
_material_uid_cache: Dict[Material, Dict[str, 'Layer']] = {}

def _get_material_layer_uid_map(material: Material, force_refresh: bool = False) -> Dict[str, 'Layer']:
    """Get a UID to Layer mapping for a material. Uses caching for performance."""
    if not material or not material.ps_mat_data:
        return {}
    
    # Check if cache is valid (simple version check using material name as key)
    cache_key = material
    if cache_key in _material_uid_cache and not force_refresh:
        return _material_uid_cache[cache_key]
    
    # Build the UID map
    uid_map = {}
    for group in material.ps_mat_data.groups:
        for channel in group.channels:
            for layer in channel.layers:
                if layer.uid:
                    uid_map[layer.uid] = layer
    
    # Cache it
    _material_uid_cache[cache_key] = uid_map
    return uid_map

def _invalidate_material_layer_cache(material: Material = None):
    """Invalidate the layer UID cache for a material or all materials."""
    global _material_uid_cache
    if material:
        _material_uid_cache.pop(material, None)
    else:
        _material_uid_cache.clear()

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

def ps_bake(context, objects: list[Object], mat: Material, uv_layer, bake_image, use_gpu=True, use_clear=True, margin=8, margin_type='ADJACENT_FACES'):
    bake_objects = []
    
    ensure_udim_tiles(bake_image, objects, uv_layer)
    
    for obj in objects:
        if mat.name in obj.data.materials:
            bake_objects.append(obj)
    
    cycles_settings = save_cycles_settings()
    # Switch to Cycles if needed
    
    node_tree = mat.node_tree
    
    image_node = node_tree.nodes.new(type='ShaderNodeTexImage')
    image_node.image = bake_image
    with context.temp_override(active_object=bake_objects[0], selected_objects=bake_objects):
        bake_params = {
            "type": 'EMIT',
            "margin": margin,
            "margin_type": margin_type,
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
            bpy.ops.object.bake(**bake_params, uv_layer=uv_layer, use_clear=use_clear)
        except Exception as e:
            # Try baking with CPU if GPU fails
            print(f"GPU baking failed, trying CPU")
            cycles.device = 'CPU'
            bpy.ops.object.bake(**bake_params, uv_layer=uv_layer, use_clear=use_clear)

    # Delete bake nodes
    node_tree.nodes.remove(image_node)
    
    restore_cycles_settings(cycles_settings)

    return bake_image

class Channel(BaseNestedListManager):
    """Custom data for material layers in the Paint System"""
    
    def get_parent_layer_id(self, layer: "Layer") -> int:
        if layer.parent_id == -1:
            return -1
        parent_layer = self.get_item_by_id(layer.parent_id)
        parent_layer_linked = parent_layer.get_layer_data()
        if parent_layer_linked.blend_mode == "PASSTHROUGH":
            return self.get_parent_layer_id(parent_layer)
        return parent_layer.id
    
    def update_node_tree(self, context:Context):
        if not self.node_tree:
            return
        _invalidate_material_layer_cache(parse_context(context).active_material)
        
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
            node_builder.add_node("uv_map", "ShaderNodeUVMap", {"uv_map": self.bake_uv_map}, force_properties=True)
            node_builder.add_node("bake_image", "ShaderNodeTexImage", {"image": self.bake_image})
            node_builder.link("uv_map", "bake_image", "UV", "Vector")
            if self.use_bake_image:
                node_builder.link("bake_image", "group_output", "Color", "Color")
                node_builder.link("bake_image", "group_output", "Alpha", "Alpha")
                node_builder.compile()
                return
        
        flattened_unlinked_layers = self.flattened_unlinked_layers
        @dataclass
        class PreviousLayer:
            color_name: str
            color_socket: str
            alpha_name: str
            alpha_socket: str
            clip_mode = False
            add_command: Optional[Add_Node] = None
            clip_color_name: Optional[str] = None
            clip_alpha_name: Optional[str] = None
            clip_color_socket: Optional[str] = None
            clip_alpha_socket: Optional[str] = None
            
        previous_dict: Dict[int, PreviousLayer] = {}
        if self.type == "VECTOR" and self.normalize_input:
            node_builder.add_node("normalize", "ShaderNodeVectorMath", {"operation": "MULTIPLY_ADD", "hide": True}, {1: (0.5, 0.5, 0.5), 2: (0.5, 0.5, 0.5)})
        if self.type == "VECTOR" and self.vector_space != "NONE" and self.vector_space != "TANGENT":
            node_builder.add_node("vector_transform", "ShaderNodeVectorTransform", {"convert_to": self.vector_space}, force_properties=True)
        
        node_builder.add_node("alpha_clamp_end", "ShaderNodeClamp", {"hide": True})
        node_builder.link("alpha_clamp_end", "group_output", "Result", "Alpha")
        previous_dict[-1] = PreviousLayer(color_name="group_output", color_socket="Color", alpha_name="alpha_clamp_end", alpha_socket="Value")
            
        if len(flattened_unlinked_layers) > 0:
            for unlinked_layer in flattened_unlinked_layers:
                layer = unlinked_layer.get_layer_data()
                if layer is None or not layer.node_tree:
                    continue
                if layer.blend_mode == "PASSTHROUGH":
                    continue
                sample_id = unlinked_layer.parent_id
                if unlinked_layer.parent_id != -1:
                    sample_id = self.get_parent_layer_id(unlinked_layer)
                previous_data = previous_dict.get(sample_id, None)
                if previous_data and previous_data.add_command and previous_data.add_command.properties.get("mute", False):
                    previous_data.add_command.properties["mute"] = False
                layer_identifier = unlinked_layer.uid
                add_command = node_builder.add_node(
                    layer_identifier, "ShaderNodeGroup",
                    {"node_tree": layer.node_tree, "mute": layer.type == "ADJUSTMENT"},
                    {"Clip": layer.is_clip or layer.type == "ADJUSTMENT"},
                    force_properties=True,
                    force_default_values=True
                )
                previous_data.add_command = add_command
                if layer.is_clip and not previous_data.clip_mode:
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
                if layer.type == "FOLDER":
                    previous_dict[unlinked_layer.id] = PreviousLayer(
                        color_name=layer_identifier,
                        color_socket="Over Color",
                        alpha_name=layer_identifier,
                        alpha_socket="Over Alpha"
                    )
                if previous_data.clip_mode and not layer.is_clip:
                    previous_data.clip_mode = False
        prev_layer = previous_dict[-1]
        if self.type == "VECTOR" and self.normalize_input:
            node_builder.link("normalize", prev_layer.color_name, "Vector", prev_layer.color_socket)
            prev_layer.color_name = "normalize"
            prev_layer.color_socket = "Vector"
        if self.type == "VECTOR" and self.vector_space != "NONE" and self.vector_space != "TANGENT":
            node_builder.link("vector_transform", prev_layer.color_name, "Vector", prev_layer.color_socket)
            prev_layer.color_name = "vector_transform"
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
    
    def create_layer(
        self, 
        context,
        layer_name: str = "Layer Name",
        layer_type: str = "BLANK", # "BLANK" is a special type that creates a blank layer with no node tree
        update_active_index: bool = True, 
        insert_at: Literal["TOP", "BOTTOM", "CURSOR", "BEFORE", "AFTER"] = "CURSOR", 
        handle_folder: bool = True,
        **kwargs
    ) -> 'Layer':
        parent_id, insert_order = self.get_insertion_data(handle_folder=handle_folder, insert_at=insert_at)
        # Adjust existing items' order
        self.adjust_sibling_orders(parent_id, insert_order)
        layer = self.add_item(
                layer_name,
                "BLANK",
                parent_id=parent_id,
                order=insert_order
            )
        layer.auto_update_node_tree = False
        layer.type = layer_type
        layer.uid = str(uuid.uuid4())
        for key, value in kwargs.items():
            setattr(layer, key, value)
        
        # Layer type specific setup
        match layer.type:
            case "IMAGE":
                if not layer.image:
                    if layer.coord_type == 'UV':
                        ps_ctx = parse_context(context)
                        use_udim_tiles = get_udim_tiles(ps_ctx.ps_object, layer.uv_map_name) != {1001}
                        layer.image = create_ps_image(layer.name, use_udim_tiles=use_udim_tiles, objects=[ps_ctx.ps_object], uv_layer_name=layer.uv_map_name)
                    else:
                        layer.image = create_ps_image(layer.name)
        
        # Update active index
        if update_active_index:
            new_id = layer.id
            if new_id != -1:
                for i, item in enumerate(self.layers):
                    if item.id == new_id:
                        self.active_index = i
                        break
        layer.auto_update_node_tree = True
        layer.update_node_tree(context)
        self.update_node_tree(context)
        return layer
    
    def set_active_index_to_layer(self, context, layer: "Layer"):
        self.normalize_orders()
        order = int(layer.order)
        parent_id = int(layer.parent_id)
        for i, item in enumerate(self.layers):
            self.active_index = i
            if item.order == order and item.parent_id == parent_id:
                break
        self.active_index = min(
            self.active_index, len(self.layers) - 1)
        self.update_node_tree(context)
    
    def delete_layer(self, context, layer: "Layer"):
        item_id = layer.id
        order = int(layer.order)
        parent_id = int(layer.parent_id)
        print(f"Deleting layer {layer.name} with id {item_id} and order {order} and parent_id {parent_id}")
        def on_delete(item: "Layer"):
            item.delete_layer_data()
        if item_id != -1 and self.remove_item_and_children(item_id, on_delete):
            # Update active_index
            self.normalize_orders()
            for i, item in enumerate(self.layers):
                self.active_index = i
                if item.order == order and item.parent_id == parent_id:
                    break
        self.active_index = min(
            self.active_index, len(self.layers) - 1)
        self.update_node_tree(context)
    
    def delete_layers(self, context, layers: list["Layer"]):
        # Sort layer by index in descending order
        layers.sort(key=lambda x: self.get_collection_index_from_id(x.id), reverse=True)
        for layer in layers:
            self.delete_layer(context, layer)
    
    def bake(
            self,
            context: Context,
            mat: Material,
            bake_image: Image,
            uv_layer: str,
            use_gpu: bool = True,
            use_group_tree: bool = True,
            force_alpha: bool = True, # Force to use alpha
            as_tangent_normal: bool = False, # Bake as tangent normal
            margin: int = 8, # Margin
            margin_type: Literal['ADJACENT_FACES', 'EXTEND'] = "ADJACENT_FACES" # Margin type
            ):
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
        
        if context.active_object and ps_context.active_object.type != "MESH" and ps_context.ps_object.type == "MESH":
            # Change the active object to the ps_object
            ps_context.active_object.select_set(False)
            ps_context.ps_object.select_set(True)
            context.view_layer.objects.active = ps_context.ps_object
        
        ps_context = parse_context(context)
        if force_alpha:
            orig_use_alpha = bool(self.use_alpha)
            self.use_alpha = True
        
        ps_objects = ps_context.ps_objects
        
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
        
        if as_tangent_normal:
            tangent_node = node_tree.nodes.new(type='ShaderNodeTangent')
            tangent_node.direction_type = "UV_MAP"
            tangent_node.uv_map = self.bake_uv_map
            to_be_deleted_nodes.append(tangent_node)
            tangent_norm_nt = get_library_nodetree(".PS Tangent Normal")
            tangent_group = node_tree.nodes.new(type='ShaderNodeGroup')
            tangent_group.node_tree = tangent_norm_nt
            to_be_deleted_nodes.append(tangent_group)
            connect_sockets(tangent_group.inputs['Custom Normal'], color_output)
            connect_sockets(tangent_group.inputs['Tangent'], tangent_node.outputs['Tangent'])
            color_output = tangent_group.outputs['Tangent Normal']
        
        # Bake image
        connect_sockets(surface_socket, color_output)
        temp_alpha_image = bake_image.copy()
        bake_image = ps_bake(context, ps_objects, mat, uv_layer, bake_image, use_gpu, margin=margin, margin_type=margin_type)
        
        temp_alpha_image.colorspace_settings.name = 'Non-Color'
        connect_sockets(surface_socket, alpha_output)
        temp_alpha_image = ps_bake(context, ps_objects, mat, uv_layer, temp_alpha_image, use_gpu, margin=margin, margin_type=margin_type)

        if bake_image and temp_alpha_image:
            # pixels_bake = np.empty(len(bake_image.pixels), dtype=np.float32)
            # pixels_temp_alpha = np.empty(len(temp_alpha_image.pixels), dtype=np.float32)
            pixels_bake = blender_image_to_numpy(bake_image)
            pixels_temp_alpha = blender_image_to_numpy(temp_alpha_image)
            
            if pixels_bake is None or pixels_temp_alpha is None:
                return
            
            # Process tiles - handle both UDIM and non-UDIM cases
            temp_alpha_single = pixels_temp_alpha.get_single_tile()
            
            # Update alpha channel for each tile in bake_image
            for tile_num in pixels_bake.tiles.keys():
                bake_tile = pixels_bake.tiles[tile_num]
                # Use corresponding tile if available, otherwise use single tile
                if tile_num in pixels_temp_alpha.tiles:
                    temp_tile = pixels_temp_alpha.tiles[tile_num]
                    bake_tile[:, :, 3] = temp_tile[:, :, 0]
                else:
                    bake_tile[:, :, 3] = temp_alpha_single[:, :, 0]
            
            set_image_pixels(bake_image, pixels_bake)
            save_image(bake_image)
        bpy.data.images.remove(temp_alpha_image)

        for node in to_be_deleted_nodes:
            node_tree.nodes.remove(node)
        
        # Restore surface socket
        if from_socket:
            connect_sockets(surface_socket, from_socket)
        
        if force_alpha:
            self.use_alpha = orig_use_alpha
        
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
    
    @property
    def flattened_layers(self):
        return [layer.get_layer_data() for layer, _ in self.flatten_hierarchy()]

    @property
    def flattened_unlinked_layers(self):
        return [layer for layer, _ in self.flatten_hierarchy()]
    
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
    normalize_input: BoolProperty(
        name="Normalize",
        description="Normalize the channel",
        default=False,
        update=update_node_tree
    )
    # world_to_object_normal: BoolProperty(
    #     name="World to Object Normal",
    #     description="World to object normal",
    #     default=False,
    #     update=update_node_tree
    # )
    def update_vector_space(self, context):
        ps_ctx = parse_context(context)
        if self.vector_space != "NONE":
            mat = ps_ctx.active_material
            if mat and mat.node_tree:
                group_node = find_node(mat.node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': ps_ctx.active_group.node_tree})
                if group_node and group_node.outputs[self.name]:
                    for link in group_node.outputs[self.name].links:
                        to_node = link.to_node
                        if to_node.bl_idname == 'ShaderNodeNormalMap':
                            to_node.space = self.bake_vector_space if self.use_bake_image else self.vector_space
                            to_node.uv_map = self.bake_uv_map if self.use_bake_image else ""
        self.update_node_tree(context)
    vector_space: EnumProperty(
        items=[
            ('WORLD', "World Space", "World Space"),
            ('OBJECT', "Object Space", "Object Space"),
            ('TANGENT', "Tangent Space", "Tangent Space"),
            ('NONE', "None", "None")
        ],
        name="Vector Space",
        description="Space of the vector",
        default='OBJECT',
        update=update_vector_space
    )
    
    def update_bake_image(self, context):
        if self.use_bake_image:
            # Force to object mode
            bpy.ops.object.mode_set(mode="OBJECT")
        self.update_vector_space(context)
        self.update_node_tree(context)
    # Bake settings
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
    bake_vector_space: EnumProperty(
        items=[
            ('WORLD', "World Space", "World Space"),
            ('OBJECT', "Object Space", "Object Space"),
            ('TANGENT', "Tangent Space", "Tangent Space")
        ],
        name="Bake Vector Space",
        description="Space of the vector",
        default='OBJECT',
        update=update_bake_image
    )
    
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
    
    def isolate_channel(self, context):
        ps_ctx = parse_context(context)
        active_group = ps_ctx.active_group
        active_channel = ps_ctx.active_channel
        ps_mat_data = ps_ctx.ps_mat_data
        mat = ps_ctx.active_material
        mat_output = get_material_output(mat.node_tree)
        if not ps_mat_data.preview_channel:
            ps_mat_data.preview_channel = True
            # Store the node connected to material output
            connected_link = mat_output.inputs[0].links[0]
            ps_ctx.ps_mat_data.original_node_name = connected_link.from_node.name
            ps_ctx.ps_mat_data.original_socket_name = connected_link.from_socket.name
            ps_ctx.ps_mat_data.original_view_transform = str(context.scene.view_settings.view_transform) # bpy.data.scenes["Scene"].view_settings.view_transform
            
            # Find channel node tree
            node = find_node(mat.node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree})
            if node:
                # Connect node tree to material output
                connect_sockets(mat_output.inputs[0], node.outputs[active_channel.name])
            
            context.scene.view_settings.view_transform = "Standard"
        else:
            ps_mat_data.preview_channel = False
            # Find node by name
            node = mat.node_tree.nodes.get(ps_mat_data.original_node_name)
            if node:
                connect_sockets(node.outputs[ps_mat_data.original_socket_name], mat_output.inputs[0])
            
            context.scene.view_settings.view_transform = ps_ctx.ps_mat_data.original_view_transform


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
        
        expected_sockets: List[ExpectedSocket] = []
        for channel in self.channels:
            # Map channel type to valid socket type
            type_map = {"COLOR": "NodeSocketColor", "VECTOR": "NodeSocketVector", "FLOAT": "NodeSocketFloat"}
            socket_type = type_map.get(channel.type, "NodeSocketColor")
            expected_sockets.append(ExpectedSocket(channel.name, socket_type, channel.use_max_min, channel.factor_min, channel.factor_max))
            if channel.use_alpha:
                expected_sockets.append(ExpectedSocket(f"{channel.name} Alpha", "NodeSocketFloat", True, 0, 1))
        
        ensure_sockets(node_tree, expected_sockets, "OUTPUT")
        ensure_sockets(node_tree, expected_sockets, "INPUT")
        
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
        default='NONE'
    )
    coord_type: EnumProperty(
        items=COORDINATE_TYPE_ENUM,
        name="Coordinate Type",
        description="Coordinate type",
        default='UV'
    )
    uv_map_name: StringProperty(
        name="UV Map",
        description="UV map"
    )
    
    def update_channel(self, context):
        ps_ctx = parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        if ps_mat_data.preview_channel:
            # Call paint_system.isolate_active_channel twice to ensure it's updated
            ps_ctx.active_channel.isolate_channel(context)
            ps_ctx.active_channel.isolate_channel(context)
        if ps_ctx.active_channel.use_bake_image:
            # Force to object mode
            bpy.ops.object.mode_set(mode="OBJECT")
        update_active_image(self, context)
    
    active_index: IntProperty(name="Active Channel Index", update=update_channel)
    node_tree: PointerProperty(
        name="Node Tree",
        type=NodeTree
    )
    
    def create_channel(
        self, 
        context, 
        channel_name: str = "New Channel",
        channel_type: str = "COLOR",
        color_space: str = "COLOR",
        use_alpha: bool = False,
        normalize_input: bool = False,
        # world_to_object_normal: bool = False,
        use_max_min: bool = False,
        factor_min: float = 0,
        factor_max: float = 1,
        vector_space: str = "OBJECT"
    ):
        channels = self.channels
        node_tree = bpy.data.node_groups.new(name=f"Temp Channel Name", type='ShaderNodeTree')
        new_channel = channels.add()
        self.active_index = len(channels) - 1
        unique_name = get_next_unique_name(channel_name, [channel.name for channel in channels])
        new_channel.name = unique_name
        new_channel.type = channel_type
        new_channel.use_alpha = use_alpha
        new_channel.normalize_input = normalize_input
        new_channel.color_space = color_space
        new_channel.use_max_min = use_max_min
        # new_channel.world_to_object_normal = world_to_object_normal
        new_channel.vector_space = vector_space
        if channel_type == "FLOAT" and new_channel.use_max_min:
            new_channel.factor_min = factor_min
            new_channel.factor_max = factor_max
        new_channel.node_tree = node_tree
        new_channel.update_node_tree(context)
        self.update_node_tree(context)
        return new_channel
    
    def delete_channel(self, context, channel: "Channel"):
        active_index = self.channels.find(channel.name)
        if active_index < 0 or active_index >= len(self.channels):
            self.report({'ERROR'}, "No valid channel selected")
            return {'CANCELLED'}
        
        self.channels.remove(active_index)
        self.active_index = max(0, active_index - 1)
        self.update_node_tree(context)


class ClipboardLayer(PropertyGroup):
    """Clipboard layer"""
    uid: StringProperty(
        name="UID",
        description="UID of the layer",
        default=""
    )
    material: PointerProperty(
        name="Material",
        type=Material
    )


class TempMaterial(PropertyGroup):
    material: PointerProperty(
        name="Material",
        type=Material
    )
    enabled: BoolProperty(
        name="Enabled",
        description="Enabled",
        default=False
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
    
    def update_hsv_color(self, context):
        if context.mode != 'PAINT_TEXTURE':
            return
        settings = context.tool_settings.image_paint
        brush = settings.brush
        if hasattr(context.tool_settings, "unified_paint_settings"):
            ups = context.tool_settings.unified_paint_settings
        else:
            ups = settings.unified_paint_settings
        ubs = ups if ups.use_unified_color else brush
        # Store color to context.ps_scene_data.hsv_color
        hsv = ubs.color.hsv
        if hsv != (context.scene.ps_scene_data.hue, context.scene.ps_scene_data.saturation, context.scene.ps_scene_data.value):
            context.scene.ps_scene_data.hue = hsv[0]
            context.scene.ps_scene_data.saturation = hsv[1]
            context.scene.ps_scene_data.value = hsv[2]
            color = ubs.color
            r = int(color[0] * 255)
            g = int(color[1] * 255)
            b = int(color[2] * 255)
            hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b).upper()
            context.scene.ps_scene_data.hex_color = hex_color
    
    clipboard_layers: CollectionProperty(
        type=ClipboardLayer,
        name="Clipboard Layers",
        description="Collection of layers in the clipboard",
        options={'SKIP_SAVE'}
    )
    active_clipboard_index: IntProperty(name="Active Clipboard Layer Index")
    layers: CollectionProperty(
        type=GlobalLayer,
        name="Paint System Layers",
        description="Collection of layers in the Paint System"
    )
    active_index: IntProperty(name="Active Layer Index")
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
    color_history_palette: PointerProperty(
        name="Color History Palette",
        type=bpy.types.Palette,
        description="Palette to store color history"
    )
    temp_materials: CollectionProperty(
        type=TempMaterial,
        name="Temp Materials",
        description="Collection of materials in the temporary collection",
        options={'SKIP_SAVE'}
    )
    
    def add_layer_to_clipboard(self, layer: "Layer"):
        ps_ctx = parse_context(bpy.context)
        clipboard_layer = self.clipboard_layers.add()
        if layer.is_linked:
            clipboard_layer.uid = layer.linked_layer_uid
            clipboard_layer.material = layer.linked_material
        else:
            clipboard_layer.uid = layer.uid
            clipboard_layer.material = ps_ctx.active_material
    
    def clear_clipboard(self):
        self.clipboard_layers.clear()
        self.active_clipboard_index = 0

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
    original_view_transform: StringProperty(
        name="Original View Transform",
        description="Original view transform of the channel"
    )
    
    def create_new_group(self, context, group_name: str, node_tree: bpy.types.NodeTree = None):
        if not node_tree:
            node_tree = bpy.data.node_groups.new(name=f"Temp Group Name", type='ShaderNodeTree')
        else:
            # Delete all nodes in the node tree
            for node in node_tree.nodes:
                node_tree.nodes.remove(node)
        lm = ListManager(self, 'groups', self, 'active_index')
        new_group = lm.add_item()
        new_group.name = group_name
        new_group.node_tree = node_tree
        new_group.update_node_tree(context)
        return new_group


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

def get_all_layers() -> list[Layer]:
    layers = []
    for material in bpy.data.materials:
        if hasattr(material, 'ps_mat_data'):
            for group in material.ps_mat_data.groups:
                for channel in group.channels:
                    for layer in channel.layers:
                        layers.append(layer)
    return layers

def is_layer_linked(check_layer: Layer) -> bool:
    """Check if the layer is linked"""
    # Check all material in the scene and count the number of times the global layer is used
    counter = Counter()
    for material in bpy.data.materials:
        if hasattr(material, 'ps_mat_data'):
            for group in material.ps_mat_data.groups:
                for channel in group.channels:
                    for layer in channel.layers:
                        counter[layer.uid if not layer.is_linked else layer.linked_layer_uid] += 1
    return counter[check_layer.uid if not check_layer.is_linked else check_layer.linked_layer_uid] > 1

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
    ClipboardLayer,
    TempMaterial,
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