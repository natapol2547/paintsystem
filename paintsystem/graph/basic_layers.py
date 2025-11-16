from __future__ import annotations
from typing import TYPE_CHECKING

import bpy
from .common import create_mixing_graph, NodeTreeBuilder, create_coord_graph, get_library_nodetree

if TYPE_CHECKING:
    from ..data import Layer

IMAGE_LAYER_VERSION = 3
FOLDER_LAYER_VERSION = 1
SOLID_COLOR_LAYER_VERSION = 1
ATTRIBUTE_LAYER_VERSION = 1
ADJUSTMENT_LAYER_VERSION = 1
GRADIENT_LAYER_VERSION = 1
RANDOM_LAYER_VERSION = 2
CUSTOM_LAYER_VERSION = 1
TEXTURE_LAYER_VERSION = 1
GEOMETRY_LAYER_VERSION = 1

ALPHA_OVER_LAYER_VERSION = 1

def get_layer_blend_type(layer: Layer) -> str:
    """Get the blend mode of the global layer"""
    blend_mode = layer.blend_mode
    if blend_mode == "PASSTHROUGH":
        return "MIX"
    return blend_mode

def set_layer_blend_type(layer: Layer, blend_type: str) -> None:
    """Set the blend mode of the global layer"""
    layer.blend_mode = blend_type

def get_layer_version_for_type(type: str) -> int:
    match type:
        case "IMAGE":
            return IMAGE_LAYER_VERSION
        case "FOLDER":
            return FOLDER_LAYER_VERSION
        case "SOLID_COLOR":
            return SOLID_COLOR_LAYER_VERSION
        case "ATTRIBUTE":
            return ATTRIBUTE_LAYER_VERSION
        case "ADJUSTMENT":
            return ADJUSTMENT_LAYER_VERSION
        case "GRADIENT":
            return GRADIENT_LAYER_VERSION
        case "RANDOM":
            return RANDOM_LAYER_VERSION
        case "CUSTOM":
            return CUSTOM_LAYER_VERSION
        case "TEXTURE":
            return TEXTURE_LAYER_VERSION
        case "GEOMETRY":
            return GEOMETRY_LAYER_VERSION
        case _:
            raise ValueError(f"Invalid layer type: {type}")

def get_texture_identifier(texture_type: str) -> str:
    identifier_mapping = {
        'TEX_BRICK': 'ShaderNodeTexBrick',
        'TEX_CHECKER': 'ShaderNodeTexChecker',
        'TEX_GRADIENT': 'ShaderNodeTexGradient',
        'TEX_MAGIC': 'ShaderNodeTexMagic',
        'TEX_NOISE': 'ShaderNodeTexNoise',
        'TEX_VORONOI': 'ShaderNodeTexVoronoi',
        'TEX_WAVE': 'ShaderNodeTexWave',
        'TEX_WHITE_NOISE': 'ShaderNodeTexWhiteNoise',
    }
    return identifier_mapping.get(texture_type, "")

def get_adjustment_identifier(adjustment_type: str) -> str:
    identifier_mapping = {
        'BRIGHTCONTRAST': 'ShaderNodeBrightContrast',
        'GAMMA': 'ShaderNodeGamma',
        'HUE_SAT': 'ShaderNodeHueSaturation',
        'INVERT': 'ShaderNodeInvert',
        'CURVE_RGB': 'ShaderNodeRGBCurve',
        'RGBTOBW': 'ShaderNodeRGBToBW',
        'MAP_RANGE': 'ShaderNodeMapRange',
    }
    return identifier_mapping.get(adjustment_type, "")

def create_image_graph(layer: "Layer"):
    node_tree = layer.node_tree
    img = layer.image
    correct_image_aspect = layer.correct_image_aspect
    resolution_x = 0
    resolution_y = 0
    if img:
        resolution_x = img.size[0]
        resolution_y = img.size[1]
    coord_type = layer.coord_type
    empty_object = layer.empty_object
    uv_map_name = layer.uv_map_name
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=IMAGE_LAYER_VERSION)
    if coord_type == "DECAL":
        builder.add_node("decal_depth_separate_xyz", "ShaderNodeSeparateXYZ")
        builder.add_node("decal_depth_clip", "ShaderNodeMath", {"operation": "COMPARE"}, default_values={1: 0, 2: 0.5}, force_default_values=True)
        builder.add_node("decal_alpha_multiply", "ShaderNodeMath", {"operation": "MULTIPLY"})
        builder.link("multiply_vector", "decal_depth_separate_xyz", "Vector", 0)
        builder.link("decal_depth_separate_xyz", "decal_depth_clip", "Z", 0)
        builder.link("decal_depth_clip", "decal_alpha_multiply", "Value", 0)
        builder.link("image", "decal_alpha_multiply", "Alpha", 1)
        create_mixing_graph(builder, "image", "Color", "decal_alpha_multiply", "Value", blend_mode=blend_mode)
    else:
        create_mixing_graph(builder, "image", "Color", "image", "Alpha", blend_mode=blend_mode)
    builder.add_node("image", "ShaderNodeTexImage", {"image": img, "interpolation": "Closest"})
    if correct_image_aspect:
        aspect_correct = get_library_nodetree(".PS Correct Aspect")
        builder.add_node("multiply_vector", "ShaderNodeVectorMath", {"operation": "MULTIPLY_ADD"}, default_values={2: (0.5, 0.5, 0) if coord_type == "DECAL" else (0, 0, 0)})
        builder.add_node("aspect_correct", "ShaderNodeGroup", {"node_tree": aspect_correct}, default_values={0: resolution_x, 1: resolution_y}, force_default_values=True)
        builder.link("aspect_correct", "multiply_vector", "Vector", 1)
        builder.link("multiply_vector", "image", "Vector", "Vector")
        create_coord_graph(builder, coord_type, uv_map_name, "multiply_vector", 0, empty_object=empty_object)
    else:
        create_coord_graph(builder, coord_type, uv_map_name, "image", "Vector", empty_object=empty_object)
    return builder

def create_folder_graph(layer: "Layer"):
    node_tree = layer.node_tree
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=FOLDER_LAYER_VERSION)
    create_mixing_graph(builder, "group_input", "Over Color", "group_input", "Over Alpha", blend_mode=blend_mode)
    return builder

def create_solid_graph(layer: "Layer"):
    node_tree = layer.node_tree
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=SOLID_COLOR_LAYER_VERSION)
    create_mixing_graph(builder, "rgb", "Color", blend_mode=blend_mode)
    builder.add_node("rgb", "ShaderNodeRGB", default_outputs={0: (1, 1, 1, 1)})
    return builder

def create_attribute_graph(layer: "Layer"):
    node_tree = layer.node_tree
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=ATTRIBUTE_LAYER_VERSION)
    create_mixing_graph(builder, "attribute", "Color", blend_mode=blend_mode)
    builder.add_node("attribute", "ShaderNodeAttribute")
    return builder

def create_adjustment_graph(layer: "Layer"):
    node_tree = layer.node_tree
    adjustment_type = get_adjustment_identifier(layer.adjustment_type)
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=ADJUSTMENT_LAYER_VERSION)
    input_socket_name = "Color"
    output_socket_name = "Color"
    builder.add_node("adjustment", adjustment_type)
    match adjustment_type:
        case "ShaderNodeRGBToBW":
            output_socket_name = "Val"
        case "ShaderNodeMapRange":
            input_socket_name = "Value"
            output_socket_name = "Result"
        case _:
            if adjustment_type in {"ShaderNodeHueSaturation", "ShaderNodeInvert", "ShaderNodeRGBCurve"}:
                # Remove factor input if it exists
                builder.add_node("value", "ShaderNodeValue", default_outputs={0:1})
                builder.link("value", "adjustment", "Value", "Fac")
    create_mixing_graph(builder, "adjustment", output_socket_name, blend_mode=blend_mode)
    builder.link("group_input", "adjustment", "Color", input_socket_name)
    return builder

def create_gradient_graph(layer: "Layer"):
    node_tree = layer.node_tree
    gradient_type = layer.gradient_type
    empty_object = layer.empty_object
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=GRADIENT_LAYER_VERSION)
    create_mixing_graph(builder, "gradient", "Color", "gradient", "Alpha", blend_mode=blend_mode)
    builder.add_node("gradient", "ShaderNodeValToRGB")
    match gradient_type:
        case "LINEAR":
            builder.add_node("map_range", "ShaderNodeMapRange")
            builder.add_node("tex_coord", "ShaderNodeTexCoord", {"object": empty_object})
            builder.add_node("separate_xyz", "ShaderNodeSeparateXYZ")
            builder.link("tex_coord", "separate_xyz", "Object", "Vector")
            builder.link("separate_xyz", "map_range", "Z", "Value")
        case "RADIAL":
            builder.add_node("map_range", "ShaderNodeMapRange", default_values={1: 1, 2: 0})
            builder.add_node("tex_coord", "ShaderNodeTexCoord", {"object": empty_object})
            builder.add_node("vector_math", "ShaderNodeVectorMath", {"operation": "LENGTH"})
            builder.link("tex_coord", "vector_math", "Object", "Vector")
            builder.link("vector_math", "map_range", "Value", "Value")
        case "DISTANCE":
            builder.add_node("map_range", "ShaderNodeMapRange")
            builder.add_node("camera_data", "ShaderNodeCameraData")
            builder.link("camera_data", "map_range", "View Distance", "Value")
        case "GRADIENT_MAP":
            builder.add_node("map_range", "ShaderNodeMapRange")
            builder.link("group_input", "map_range", "Color", "Value")
        case _:
            raise ValueError(f"Invalid gradient type: {gradient_type}")
    builder.link("map_range", "gradient", "Result", "Fac")
    return builder

def create_random_graph(layer: "Layer"):
    node_tree = layer.node_tree
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=RANDOM_LAYER_VERSION)
    create_mixing_graph(builder, "hue_saturation_value", "Color", blend_mode=blend_mode)
    builder.add_node("object_info", "ShaderNodeObjectInfo")
    builder.add_node("white_noise", "ShaderNodeTexWhiteNoise", {"noise_dimensions": "1D"})
    builder.add_node("add", "ShaderNodeMath", {"operation": "ADD"})
    builder.add_node("add_2", "ShaderNodeMath", {"operation": "ADD"}, {1: 0})
    builder.add_node("vector_math", "ShaderNodeVectorMath", {"operation": "MULTIPLY_ADD"}, default_values={1: (2, 2, 2), 2: (-1, -1, -1)})
    builder.add_node("separate_xyz", "ShaderNodeSeparateXYZ")
    builder.add_node("hue_multiply_add", "ShaderNodeMath", {"operation": "MULTIPLY_ADD"}, default_values={1: 1, 2: 0.5})
    builder.add_node("saturation_multiply_add", "ShaderNodeMath", {"operation": "MULTIPLY_ADD"}, default_values={1: 1, 2: 1})
    builder.add_node("value_multiply_add", "ShaderNodeMath", {"operation": "MULTIPLY_ADD"}, default_values={1: 1, 2: 1})
    builder.add_node("hue_saturation_value", "ShaderNodeHueSaturation", default_values={"Color": (0.5, 0.25, 0.25, 1)})
    builder.link("object_info", "add", "Material Index", 0)
    builder.link("object_info", "add", "Random", 1)
    builder.link("add", "add_2", "Value", 0)
    builder.link("add_2", "white_noise", "Value", "W")
    builder.link("white_noise", "vector_math", "Color", "Vector")
    builder.link("vector_math", "separate_xyz", "Vector", "Vector")
    builder.link("separate_xyz", "hue_multiply_add", "X", "Value")
    builder.link("separate_xyz", "saturation_multiply_add", "Y", "Value")
    builder.link("separate_xyz", "value_multiply_add", "Z", "Value")
    builder.link("hue_multiply_add", "hue_saturation_value", "Value", "Hue")
    builder.link("saturation_multiply_add", "hue_saturation_value", "Value", "Saturation")
    builder.link("value_multiply_add", "hue_saturation_value", "Value", "Value")
    return builder

def create_custom_graph(layer: "Layer"):
    node_tree = layer.node_tree
    custom_node_tree = layer.custom_node_tree
    color_input = layer.custom_color_input
    alpha_input = layer.custom_alpha_input
    color_output = layer.custom_color_output
    alpha_output = layer.custom_alpha_output
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=CUSTOM_LAYER_VERSION)
    if alpha_output != -1:
        create_mixing_graph(builder, "custom_node_tree", color_output, "custom_node_tree", alpha_output, blend_mode=blend_mode)
        builder.link("group_input", "custom_node_tree", "Alpha", alpha_input)
    else:
        create_mixing_graph(builder, "custom_node_tree", color_output, blend_mode=blend_mode)
    builder.add_node("custom_node_tree", "ShaderNodeGroup", {"node_tree": custom_node_tree})
    if color_input != -1:
        builder.link("group_input", "custom_node_tree", "Color", color_input)
    if alpha_input != -1:
        builder.link("group_input", "custom_node_tree", "Alpha", alpha_input)
    return builder

def create_texture_graph(layer: "Layer"):
    node_tree = layer.node_tree
    texture_type = get_texture_identifier(layer.texture_type)
    coord_type = layer.coord_type
    uv_map_name = layer.uv_map_name
    empty_object = layer.empty_object
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=TEXTURE_LAYER_VERSION)
    create_mixing_graph(builder, "texture", "Color", blend_mode=blend_mode)
    builder.add_node("texture", texture_type)
    create_coord_graph(builder, coord_type, uv_map_name, 'texture', 'Vector', empty_object=empty_object)
    return builder

def create_geometry_graph(layer: "Layer"):
    node_map = {
        'WORLD_NORMAL': 'ShaderNodeNewGeometry',
        'WORLD_TRUE_NORMAL': 'ShaderNodeNewGeometry',
        'POSITION': 'ShaderNodeNewGeometry',
        'BACKFACING': 'ShaderNodeNewGeometry',
        'OBJECT_NORMAL': 'ShaderNodeTexCoord',
        'OBJECT_POSITION': 'ShaderNodeTexCoord',
        'VECTOR_TRANSFORM': 'ShaderNodeVectorTransform',
    }
    output_name_map = {
        'WORLD_NORMAL': 'Normal',
        'WORLD_TRUE_NORMAL': 'True Normal',
        'POSITION': 'Position',
        'BACKFACING': 'Backfacing',
        'OBJECT_NORMAL': 'Normal',
        'OBJECT_POSITION': 'Object',
        'VECTOR_TRANSFORM': 'Vector',
    }
    normalize_normals = layer.normalize_normal
    node_tree = layer.node_tree
    geometry_type = layer.geometry_type
    blend_mode = get_layer_blend_type(layer)
    builder = NodeTreeBuilder(node_tree, "Layer", version=GEOMETRY_LAYER_VERSION)
    if geometry_type == 'VECTOR_TRANSFORM':
        builder.link("group_input", "geometry", "Color", "Vector")
    if geometry_type in ['WORLD_NORMAL', 'WORLD_TRUE_NORMAL', 'OBJECT_NORMAL'] and normalize_normals:
        builder.add_node("normalize", "ShaderNodeVectorMath", {"operation": "MULTIPLY_ADD", "hide": True}, {1: (0.5, 0.5, 0.5), 2: (0.5, 0.5, 0.5)})
        builder.link("geometry", "normalize", output_name_map[geometry_type], "Vector")
        create_mixing_graph(builder, "normalize", "Vector", blend_mode=blend_mode)
    else:
        create_mixing_graph(builder, "geometry", output_name_map[geometry_type], blend_mode=blend_mode)
    builder.add_node("geometry", node_map[geometry_type])
    return builder

def get_alpha_over_nodetree():
    if ".PS Alpha Over" in bpy.data.node_groups:
        return bpy.data.node_groups[".PS Alpha Over"]
    node_tree = bpy.data.node_groups.new(name=".PS Alpha Over", type="ShaderNodeTree")
    node_tree.interface.new_socket("Clip", in_out="INPUT", socket_type="NodeSocketBool")
    node_tree.interface.new_socket("Color", in_out="INPUT", socket_type="NodeSocketColor")
    node_tree.interface.new_socket("Alpha", in_out="INPUT", socket_type="NodeSocketFloat")
    node_tree.interface.new_socket("Over Color", in_out="INPUT", socket_type="NodeSocketColor")
    node_tree.interface.new_socket("Over Alpha", in_out="INPUT", socket_type="NodeSocketFloat")
    node_tree.interface.new_socket("Color", in_out="OUTPUT", socket_type="NodeSocketColor")
    node_tree.interface.new_socket("Alpha", in_out="OUTPUT", socket_type="NodeSocketFloat")
    builder = NodeTreeBuilder(node_tree, "Layer", version=ALPHA_OVER_LAYER_VERSION)
    create_mixing_graph(builder, "group_input", "Over Color", "group_input", "Over Alpha")
    builder.compile()
    return node_tree