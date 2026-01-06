from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..data import Layer

from pathlib import Path
from typing import Optional
from .nodetree_builder import NodeTreeBuilder

import bpy

LIBRARY_FILENAME = "library2.blend"
DEFAULT_PS_UV_MAP_NAME = "PS_UVMap"

LIBRARY_NODE_TREE_VERSIONS = {
    ".PS Projection": 1,
}

def get_layer_blend_type(layer: Layer) -> str:
    """Get the blend mode of the global layer"""
    blend_mode = layer.blend_mode
    if blend_mode == "PASSTHROUGH":
        return "MIX"
    return blend_mode

def set_layer_blend_type(layer: Layer, blend_type: str) -> None:
    """Set the blend mode of the global layer"""
    layer.blend_mode = blend_type

def _resolve_library_path(filename: str = LIBRARY_FILENAME) -> Path:
    """
    Resolve the absolute path to the given library filename.

    `LIBRARY_FILENAME` resides with this file.
    """
    folder_root = Path(__file__).resolve().parent.parent
    return folder_root / filename


def get_library_nodetree(tree_name: str, library_filename: str = LIBRARY_FILENAME, force_append: bool = False) -> bpy.types.NodeTree:
    """
    Return a `bpy.types.NodeTree` by name, appending it from the given library if needed.

    - First checks the current .blend for an existing node tree with `tree_name` and returns it if found.
    - Otherwise, appends the node tree from `library_filename` and returns the appended datablock.

    Args:
        tree_name: Name of the node tree (node group) to retrieve.
        library_filename: Blend file to append from. Defaults to LIBRARY_FILENAME.

    Returns:
        The resolved `bpy.types.NodeTree` instance.

    Raises:
        FileNotFoundError: If the library file cannot be found.
        ValueError: If the requested node tree name does not exist in the library.
    """
    # Check if the node tree already exists in the current .blend
    existing_tree = bpy.data.node_groups.get(tree_name)
    if existing_tree is not None:
        if force_append:
            # Rename the existing tree temprorary
            existing_tree.name = f"{existing_tree.name} (TEMP)"
        else:
            return existing_tree

    # Resolve path to the library file
    library_path = _resolve_library_path(library_filename)
    if not library_path.exists():
        raise FileNotFoundError(f"Library file not found: {library_path}")

    # Inspect the library for the node tree, then append it
    library_path_str = str(library_path)
    with bpy.data.libraries.load(library_path_str, link=False) as (data_from, data_to):
        if tree_name not in data_from.node_groups:
            raise ValueError(
                f"Node tree '{tree_name}' not found in '{library_filename}'.\n"
                f"Available: {list(data_from.node_groups)}"
            )
        data_to.node_groups = [tree_name]

    # Return the newly appended node tree (now present in bpy.data.node_groups)
    appended_tree: Optional[bpy.types.NodeTree] = bpy.data.node_groups.get(tree_name)
    
    if existing_tree and force_append:
        # Remap the users to the new tree
        existing_tree.user_remap(appended_tree)
        bpy.data.node_groups.remove(existing_tree)

    return appended_tree

def get_library_object(object_name: str, library_filename: str = LIBRARY_FILENAME) -> bpy.types.Object:
    """
    Return a `bpy.types.Object` by name, appending it from the given library if needed.
    """
    library_path = _resolve_library_path(library_filename)
    if not library_path.exists():
        raise FileNotFoundError(f"Library file not found: {library_path}")
    library_path_str = str(library_path)
    with bpy.data.libraries.load(library_path_str, link=False) as (data_from, data_to):
        if object_name not in data_from.objects:
            raise ValueError(f"Object '{object_name}' not found in '{library_filename}'.\nAvailable: {list(data_from.objects)}")
        data_to.objects = [object_name]
    return bpy.data.objects.get(object_name)

def create_mixing_graph(builder: NodeTreeBuilder, layer: "Layer", color_node_name: str = None, color_socket: str = None, alpha_node_name: str = None, alpha_socket: str = None) -> NodeTreeBuilder:
    blend_mode = get_layer_blend_type(layer) if layer is not None else "MIX"
    pre_mix = get_library_nodetree(".PS Pre Mix")
    post_mix = get_library_nodetree(".PS Post Mix")
    builder.add_node("group_input", "NodeGroupInput")
    builder.add_node("group_output", "NodeGroupOutput")
    builder.add_node("pre_mix", "ShaderNodeGroup", {"node_tree": pre_mix}, {"Over Alpha": 1.0})
    builder.add_node("post_mix", "ShaderNodeGroup", {"node_tree": post_mix})
    builder.add_node("mix_rgb", "ShaderNodeMix", {"blend_type": blend_mode, "data_type": "RGBA"}, force_properties=True)
    if alpha_node_name is not None and alpha_socket is not None:
        builder.link(alpha_node_name, "pre_mix", alpha_socket, "Over Alpha")
    builder.link("group_input", "pre_mix", "Color", "Color")
    builder.link("group_input", "pre_mix", "Alpha", "Alpha")
    builder.link("pre_mix", "mix_rgb", "Color", "A")
    builder.link("pre_mix", "mix_rgb", "Over Alpha", "Factor")
    if color_node_name is not None and color_socket is not None:
        builder.link(color_node_name, "mix_rgb", color_socket, "B")
    builder.link("mix_rgb", "post_mix", "Result", "Color")
    builder.link("pre_mix", "post_mix", "Over Alpha", "Over Alpha")
    builder.link("group_input", "post_mix", "Alpha", "Alpha")
    builder.link("group_input", "post_mix", "Clip", "Clip")
    builder.link("post_mix", "group_output", "Color", "Color")
    builder.link("post_mix", "group_output", "Alpha", "Alpha")
    return builder


def create_coord_graph(builder: NodeTreeBuilder, layer: "Layer", coord_type: str, uv_map_name: str, node_name: str, socket_name: str, alpha_node_name: str = None, alpha_socket: str = None) -> NodeTreeBuilder:
    builder.add_node("mapping", "ShaderNodeMapping")
    if coord_type == "AUTO":
        builder.add_node("uvmap", "ShaderNodeUVMap", {"uv_map": DEFAULT_PS_UV_MAP_NAME}, force_properties=True)
        builder.link("uvmap", "mapping", "UV", "Vector")
        builder.link("mapping", node_name, "Vector", socket_name)
    elif coord_type == "UV":
        builder.add_node("uvmap", "ShaderNodeUVMap", {"uv_map": uv_map_name}, force_properties=True)
        builder.link("uvmap", "mapping", "UV", "Vector")
        builder.link("mapping", node_name, "Vector", socket_name)
    elif coord_type in ["OBJECT", "CAMERA", "WINDOW", "REFLECTION", "GENERATED"]:
        empty_object = layer.empty_object
        builder.add_node("tex_coord", "ShaderNodeTexCoord", {"object": empty_object})
        builder.link("tex_coord", "mapping", coord_type.title(), "Vector")
        builder.link("mapping", node_name, "Vector", socket_name)
    elif coord_type == "POSITION":
        builder.add_node("geometry", "ShaderNodeNewGeometry")
        builder.link("geometry", "mapping", "Position", "Vector")
        builder.link("mapping", node_name, "Vector", socket_name)
    elif coord_type == "DECAL":
        empty_object = layer.empty_object
        use_decal_depth_clip = layer.use_decal_depth_clip
        builder.add_node("tex_coord", "ShaderNodeTexCoord", {"object": empty_object}, force_properties=True)
        builder.link("tex_coord", "mapping", "Object", "Vector")
        builder.link("mapping", node_name, "Vector", socket_name)
        if use_decal_depth_clip:
            builder.add_node("decal_depth_separate_xyz", "ShaderNodeSeparateXYZ")
            builder.add_node("decal_depth_clip", "ShaderNodeMath", {"operation": "COMPARE"}, default_values={1: 0, 2: 0.5}, force_default_values=True)
            builder.link("mapping", "decal_depth_separate_xyz", "Vector", 0)
            builder.link("decal_depth_separate_xyz", "decal_depth_clip", "Z", 0)
            if alpha_node_name is not None and alpha_socket is not None:
                builder.add_node("decal_alpha_multiply", "ShaderNodeMath", {"operation": "MULTIPLY"}, default_values={0: 1, 1: 1} , force_default_values=True)
                builder.link("decal_depth_clip", "decal_alpha_multiply", "Value", 0)
                builder.link(alpha_node_name, "decal_alpha_multiply", alpha_socket, 1)
                alpha_node_name = "decal_alpha_multiply"
                alpha_socket = 0
            else:
                alpha_node_name = "decal_depth_clip"
                alpha_socket = 0
    elif coord_type == "PROJECT":
        proj_nt = get_library_nodetree(".PS Projection")
        builder.add_node(
            "proj_node",
            "ShaderNodeGroup",
            {"node_tree": proj_nt},
            {"Vector": layer.projection_position, "Rotation": layer.projection_rotation, "FOV": layer.projection_fov},
            force_properties=True,
            force_default_values=True
        )
        builder.link("proj_node", "mapping", "Vector", "Vector")
        builder.link("mapping", node_name, "Vector", socket_name)
    return alpha_node_name, alpha_socket