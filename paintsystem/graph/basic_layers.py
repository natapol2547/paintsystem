from __future__ import annotations
from typing import TYPE_CHECKING, Optional
import uuid

import bpy
from bpy.types import Context

from .nodetree_builder import END
from .common import create_mask_mixing_graph, create_mixing_graph, NodeTreeBuilder, create_coord_graph, get_library_nodetree, get_layer_blend_type, set_layer_blend_type, DEFAULT_PS_UV_MAP_NAME

if TYPE_CHECKING:
    from ..data import Layer, LayerMask

IMAGE_LAYER_VERSION = 4
FOLDER_LAYER_VERSION = 2
SOLID_COLOR_LAYER_VERSION = 2
ATTRIBUTE_LAYER_VERSION = 2
ADJUSTMENT_LAYER_VERSION = 2
GRADIENT_LAYER_VERSION = 2
RANDOM_LAYER_VERSION = 3
CUSTOM_LAYER_VERSION = 2
TEXTURE_LAYER_VERSION = 2
GEOMETRY_LAYER_VERSION = 2

ALPHA_OVER_LAYER_VERSION = 1

class PSNodeTreeBuilder:
    """
    A wrapper around NodeTreeBuilder that automatically creates the mixing graph.
    This makes it easier to create layer graphs by handling the common mixing graph setup.
    
    The mixing graph is created automatically during initialization, and nodes can be
    linked to it even if they don't exist yet (errors will be caught at compile time).
    
    Supports adding color and alpha modifiers that will be chained together automatically.
    """
    
    def __init__(
        self,
        layer: "Layer",
        version: int,
        color_node_name: Optional[str] = None,
        color_socket: Optional[str] = None,
        alpha_node_name: Optional[str] = None,
        alpha_socket: Optional[str] = None,
        frame_name: str = "Layer",
        as_subgraph: bool = False,
        **kwargs
    ):
        """
        Initialize PSNodeTreeBuilder with automatic mixing graph creation.
        
        Args:
            layer: The layer object (must have a node_tree attribute)
            version: Version number for the layer graph
            color_node_name: Name of the node providing color (can be added later)
            color_socket: Socket name/index on the color node
            alpha_node_name: Name of the node providing alpha (can be added later)
            alpha_socket: Socket name/index on the alpha node
            is_mask: Whether this builder is for a mask
            as_subgraph: Whether to create the graph as a subgraph
            **kwargs: Additional arguments passed to NodeTreeBuilder
        """
        self._builder = NodeTreeBuilder(layer.node_tree, frame_name, version=version, verbose=True, **kwargs)
        self._layer = layer
        
        self.mask_builders = []

        
        # Store original source nodes for modifier chaining
        self._color_source_node = color_node_name
        self._color_source_socket = color_socket
        self._alpha_source_node = alpha_node_name
        self._alpha_source_socket = alpha_socket
        
        # Track modifier chains: list of (node_name, input_socket, output_socket) tuples
        self._color_modifiers: list[tuple[str, str, str]] = []
        self._alpha_modifiers: list[tuple[str, str, str]] = []
        
        # Create the mixing graph automatically, but don't link color/alpha yet
        # We'll link them after modifiers are added (or at compile time)
        create_mixing_graph(
            self._builder,
            layer,
            None,  # Don't link color yet - will be done after modifiers
            None,
            None,  # Don't link alpha yet - will be done after modifiers
            None,
            as_subgraph=as_subgraph,
        )
        
        # Now link the sources (or final modifier outputs) to the mixing graph
        self._update_mixing_graph_links()
    
    def _create_mapping_setup(self, node_name: str, socket_name: str):
        self._builder.add_node("mapping", "ShaderNodeMapping")
        output_node_name = "mapping"
        output_socket_name = "Vector"
        if self._layer.type == "IMAGE" and hasattr(self._layer, 'correct_image_aspect') and self._layer.correct_image_aspect and self._layer.image:
            resolution_x = 0
            resolution_y = 0
            img = self._layer.image
            if img:
                resolution_x = img.size[0]
                resolution_y = img.size[1]
            aspect_correct = get_library_nodetree(".PS Correct Aspect")
            self._builder.add_node("multiply_vector", "ShaderNodeVectorMath", {"operation": "MULTIPLY"})
            self._builder.add_node("aspect_correct", "ShaderNodeGroup", {"node_tree": aspect_correct}, default_values={0: resolution_x, 1: resolution_y}, force_default_values=True)
            self._builder.link("aspect_correct", "multiply_vector", "Vector", 0)
            self._builder.link(node_name, "multiply_vector", socket_name, 1)
            self._builder.link("multiply_vector", "mapping", 0, "Vector")
        else:
            self._builder.link(node_name, "mapping", socket_name, "Vector")
        if self._layer.coord_type in {"PROJECT", "DECAL"}:
            self._builder.add_node("center_image", "ShaderNodeVectorMath", {"operation": "ADD"}, default_values={1: (0.5, 0.5, 0)}, force_default_values=True)
            self._builder.link("mapping", "center_image", "Vector", 0)
            output_node_name = "center_image"
            output_socket_name = 0
        return output_node_name, output_socket_name
    
    def __getattr__(self, name):
        """Delegate all other method calls to the underlying NodeTreeBuilder"""
        return getattr(self._builder, name)
    
    def add_node(self, *args, **kwargs):
        """Add a node to the graph"""
        return self._builder.add_node(*args, **kwargs)
    
    def link(self, *args, **kwargs):
        """Link nodes in the graph"""
        return self._builder.link(*args, **kwargs)
    
    def compile(self, *args, **kwargs):
        """Compile the graph, ensuring modifier chains are properly linked"""
        # Compile mask builders first
        for mask_builder in self.mask_builders:
            mask_builder.compile(*args, **kwargs)
            
        # Update mixing graph links before compiling to ensure modifiers are connected
        self._update_mixing_graph_links()
        return self._builder.compile(*args, **kwargs)
    
    @property
    def builder(self):
        """Access the underlying NodeTreeBuilder if needed"""
        return self._builder
    
    def create_coord_graph(self, node_name: str, socket_name: str) -> NodeTreeBuilder:
        """Create the coordinate graph for the layer.

        Args:
            node_name (str): The name of the node to link the coordinate graph to.
            socket_name (str): The socket name to link the coordinate graph to.
        """
        coord_type = self._layer.coord_type
        if coord_type == "AUTO":
            self._builder.add_node("uvmap", "ShaderNodeUVMap", {"uv_map": DEFAULT_PS_UV_MAP_NAME}, force_properties=True)
            output_node_name, output_socket_name = self._create_mapping_setup("uvmap", "UV")
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
        elif coord_type == "UV":
            # Handle both layer and mask UV map property names
            uv_map_name = getattr(self._layer, 'uv_map_name', getattr(self._layer, 'mask_uv_map', ''))
            self._builder.add_node("uvmap", "ShaderNodeUVMap", {"uv_map": uv_map_name}, force_properties=True)
            output_node_name, output_socket_name = self._create_mapping_setup("uvmap", "UV")
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
        elif coord_type in ["OBJECT", "CAMERA", "WINDOW", "REFLECTION", "GENERATED"]:
            empty_object = self._layer.empty_object
            self._builder.add_node("tex_coord", "ShaderNodeTexCoord", {"object": empty_object})
            output_node_name, output_socket_name = self._create_mapping_setup("tex_coord", coord_type.title())
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
        elif coord_type == "POSITION":
            self._builder.add_node("geometry", "ShaderNodeNewGeometry")
            output_node_name, output_socket_name = self._create_mapping_setup("geometry", "Position")
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
        elif coord_type == "DECAL":
            empty_object = self._layer.empty_object
            use_decal_depth_clip = getattr(self._layer, 'use_decal_depth_clip', False)
            self._builder.add_node("tex_coord", "ShaderNodeTexCoord", {"object": empty_object}, force_properties=True)
            output_node_name, output_socket_name = self._create_mapping_setup("tex_coord", "Object")
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
            if use_decal_depth_clip:
                self._builder.add_node("decal_depth_separate_xyz", "ShaderNodeSeparateXYZ")
                self._builder.add_node("decal_depth_clip", "ShaderNodeMath", {"operation": "COMPARE"}, default_values={1: 0, 2: 0.5}, force_default_values=True)
                self._builder.link("mapping", "decal_depth_separate_xyz", "Vector", 0)
                self._builder.link("decal_depth_separate_xyz", "decal_depth_clip", "Z", 0)
                if self._alpha_source_node is not None and self._alpha_source_socket is not None:
                    self._builder.add_node("decal_alpha_multiply", "ShaderNodeMath", {"operation": "MULTIPLY"}, default_values={0: 1, 1: 1} , force_default_values=True)
                    self._builder.link("decal_depth_clip", "decal_alpha_multiply", "Value", 0)
                    self.add_alpha_modifier("decal_alpha_multiply", 1, 0)
                else:
                    self._alpha_source_node = "decal_depth_clip"
                    self._alpha_source_socket = 0
        elif coord_type == "PROJECT":
            proj_nt = get_library_nodetree(".PS Projection")
            self._builder.add_node(
                "proj_node",
                "ShaderNodeGroup",
                {"node_tree": proj_nt, "hide": True},
                {"Vector": self._layer.projection_position, "Rotation": self._layer.projection_rotation, "FOV": self._layer.projection_fov, "Object Space": self._layer.projection_space == "OBJECT"},
                force_properties=True,
                force_default_values=True
            )
            output_node_name, output_socket_name = self._create_mapping_setup("proj_node", "Vector")
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
            if self._alpha_source_node is not None and self._alpha_source_socket is not None:
                self._builder.add_node("projcetion_alpha_multiply", "ShaderNodeMath", {"operation": "MULTIPLY"}, default_values={0: 1, 1: 1} , force_default_values=True)
                self._builder.link("proj_node", "projcetion_alpha_multiply", "Mask", 0)
                self.add_alpha_modifier("projcetion_alpha_multiply", 1, 0)
            else:
                self._alpha_source_node = "proj_node"
                self._alpha_source_socket = "Mask"
        elif coord_type == "PARALLAX":
            match self._layer.parallax_space:
                case "UV":
                    parallax_nt = get_library_nodetree(".PS UV Parallax")
                    self._builder.add_node("geometry", "ShaderNodeNewGeometry")
                    self._builder.add_node("parallax", "ShaderNodeGroup", {"node_tree": parallax_nt}, force_properties=True)
                    self._builder.add_node("uvmap", "ShaderNodeUVMap", {"uv_map": self._layer.parallax_uv_map_name}, force_properties=True)
                    self._builder.add_node("uv_tangent", "ShaderNodeTangent", {"direction_type": "UV_MAP", "uv_map": self._layer.parallax_uv_map_name}, force_properties=True)
                    self._builder.link("uvmap", "parallax", "UV", "UV")
                    self._builder.link("uv_tangent", "parallax", "Tangent", "Tangent")
                    self._builder.link("geometry", "parallax", "Normal", "Normal")
                case "Object":
                    parallax_nt = get_library_nodetree(".PS Object Parallax")
                    self._builder.add_node("parallax", "ShaderNodeGroup", {"node_tree": parallax_nt}, force_properties=True)
            output_node_name, output_socket_name = self._create_mapping_setup("parallax", "Vector")
            self._builder.link(output_node_name, node_name, output_socket_name, socket_name)
    
    def _remove_final_color_link(self):
        """Remove any existing link to mix_rgb.B input."""
        # Find and remove any edge that targets mix_rgb with target_socket "B"
        edges_to_remove = [
            edge for edge in self._builder.edges
            if edge.target == "mix_rgb" and edge.target_socket == "B"
        ]
        for edge in edges_to_remove:
            self._builder.edges.remove(edge)
    
    def _remove_final_alpha_link(self):
        """Remove any existing link to pre_mix.Over Alpha input."""
        # Find and remove any edge that targets pre_mix with target_socket "Over Alpha"
        edges_to_remove = [
            edge for edge in self._builder.edges
            if edge.target == "pre_mix" and edge.target_socket == "Over Alpha"
        ]
        for edge in edges_to_remove:
            self._builder.edges.remove(edge)
    
    def _update_mixing_graph_links(self):
        """Update the links from color/alpha sources (through modifiers) to the mixing graph."""
        # Determine final color source (last modifier or original source)
        if self._color_modifiers:
            final_color_node, _, final_color_socket = self._color_modifiers[-1]
        else:
            final_color_node = self._color_source_node
            final_color_socket = self._color_source_socket
        
        # Remove old color link and create new one
        if final_color_node is not None and final_color_socket is not None:
            self._remove_final_color_link()
            self._builder.link(final_color_node, "mix_rgb", final_color_socket, "B")
        
        # Determine final alpha source (last modifier or original source)
        if self._alpha_modifiers:
            final_alpha_node, _, final_alpha_socket = self._alpha_modifiers[-1]
        else:
            final_alpha_node = self._alpha_source_node
            final_alpha_socket = self._alpha_source_socket
        
        # Remove old alpha link and create new one
        if final_alpha_node is not None and final_alpha_socket is not None:
            self._remove_final_alpha_link()
            self._builder.link(final_alpha_node, "pre_mix", final_alpha_socket, "Over Alpha")
    
    def add_color_modifier(self, node_name: str, input_socket: str, output_socket: str):
        """
        Add a color modifier node to the color processing chain.
        
        Modifiers are chained together automatically. The first modifier receives input
        from the original color source, and each subsequent modifier receives input from
        the previous modifier's output. The final modifier's output connects to the mix node.
        
        Args:
            node_name: Name/identifier of the modifier node (must be added with add_node first)
            input_socket: Input socket name/index on the modifier node to receive color
            output_socket: Output socket name/index on the modifier node that outputs color
            
        Example:
            builder.add_node("brightness", "ShaderNodeBrightContrast")
            builder.add_color_modifier("brightness", "Color", "Color")
            builder.add_node("gamma", "ShaderNodeGamma")
            builder.add_color_modifier("gamma", "Color", "Color")
            # Results in: color_source -> brightness -> gamma -> mix_rgb
        """
        if self._color_source_node is None or self._color_source_socket is None:
            raise ValueError(
                "Cannot add color modifier: color_node_name and color_socket must be provided "
                "when initializing PSNodeTreeBuilder."
            )
        
        # Determine the input source for this modifier
        if self._color_modifiers:
            # Link from the previous modifier's output
            prev_node, _, prev_output_socket = self._color_modifiers[-1]
            self._builder.link(prev_node, node_name, prev_output_socket, input_socket)
        else:
            # Remove the direct link from source to mix_rgb (if it exists)
            self._remove_final_color_link()
            # Link from the original color source to the first modifier
            self._builder.link(self._color_source_node, node_name, self._color_source_socket, input_socket)
        
        # Add to modifier chain
        self._color_modifiers.append((node_name, input_socket, output_socket))
        
        # Update the final link to point to this modifier's output
        self._update_mixing_graph_links()
    
    def add_alpha_modifier(self, node_name: str, input_socket: str, output_socket: str):
        """
        Add an alpha modifier node to the alpha processing chain.
        
        Modifiers are chained together automatically. The first modifier receives input
        from the original alpha source, and each subsequent modifier receives input from
        the previous modifier's output. The final modifier's output connects to the pre_mix node.
        
        Args:
            node_name: Name/identifier of the modifier node (must be added with add_node first)
            input_socket: Input socket name/index on the modifier node to receive alpha
            output_socket: Output socket name/index on the modifier node that outputs alpha
            
        Example:
            builder.add_node("multiply", "ShaderNodeMath", {"operation": "MULTIPLY"})
            builder.add_alpha_modifier("multiply", "Value", "Value")
            builder.add_node("clamp", "ShaderNodeMath", {"operation": "CLAMP"})
            builder.add_alpha_modifier("clamp", "Value", "Value")
            # Results in: alpha_source -> multiply -> clamp -> pre_mix
            
        Raises:
            ValueError: If alpha_node_name and alpha_socket were not provided during initialization
        """
        if self._alpha_source_node is None or self._alpha_source_socket is None:
            raise ValueError(
                "Cannot add alpha modifier: alpha_node_name and alpha_socket must be provided "
                "when initializing PSNodeTreeBuilder."
            )
        
        # Determine the input source for this modifier
        if self._alpha_modifiers:
            # Link from the previous modifier's output
            prev_node, _, prev_output_socket = self._alpha_modifiers[-1]
            self._builder.link(prev_node, node_name, prev_output_socket, input_socket)
        else:
            # Remove the direct link from source to pre_mix (if it exists)
            self._remove_final_alpha_link()
            # Link from the original alpha source to the first modifier
            self._builder.link(self._alpha_source_node, node_name, self._alpha_source_socket, input_socket)
        
        # Add to modifier chain
        self._alpha_modifiers.append((node_name, input_socket, output_socket))
        
        # Update the final link to point to this modifier's output
        self._update_mixing_graph_links()

    @classmethod
    def create_layer_graph(cls, layer: "Layer", context: Context) -> "PSNodeTreeBuilder":
        layer_pre_processing(layer, context)
        
        match layer.type:
            case "IMAGE":
                if layer.image:
                    layer.image.name = layer.layer_name
                img = layer.image
                color_socket = parse_socket_name(layer, layer.color_output_name, "Color")
                alpha_socket = parse_socket_name(layer, layer.alpha_output_name, "Alpha")
                builder = cls(layer, IMAGE_LAYER_VERSION, "source", color_socket, "source", alpha_socket)
                builder.add_node("source", "ShaderNodeTexImage", {"image.force": img, "interpolation": "Closest", "name": "source"})
                builder.create_coord_graph("source", "Vector")
                
            case "FOLDER":
                builder = cls(layer, FOLDER_LAYER_VERSION, "group_input", "Over Color", "group_input", "Over Alpha")
            
            case "SOLID_COLOR":
                builder = cls(layer, SOLID_COLOR_LAYER_VERSION, "source", "Color")
                builder.add_node("source", "ShaderNodeRGB", {"name": "source"}, default_outputs={0: (1, 1, 1, 1)})
                
            case "ATTRIBUTE":
                color_socket = parse_socket_name(layer, layer.color_output_name, "Color")
                alpha_socket = parse_socket_name(layer, layer.alpha_output_name, "Alpha")
                if alpha_socket:
                    builder = cls(layer, ATTRIBUTE_LAYER_VERSION, "source", color_socket, "source", alpha_socket)
                else:
                    builder = cls(layer, ATTRIBUTE_LAYER_VERSION, "source", color_socket)
                builder.add_node("source", "ShaderNodeAttribute", {"name": "source"})
                
            case "ADJUSTMENT":
                adjustment_type = get_adjustment_identifier(layer.adjustment_type)
                input_socket_name = "Color"
                output_socket_name = "Color"
                match adjustment_type:
                    case "ShaderNodeRGBToBW":
                        output_socket_name = "Val"
                    case "ShaderNodeMapRange":
                        input_socket_name = "Value"
                        output_socket_name = "Result"
                builder = cls(layer, ADJUSTMENT_LAYER_VERSION, "source", output_socket_name)
                builder.add_node("source", adjustment_type, {"name": "source"})
                match adjustment_type:
                    case "ShaderNodeRGBToBW":
                        pass
                    case "ShaderNodeMapRange":
                        pass
                    case _:
                        if adjustment_type in {"ShaderNodeHueSaturation", "ShaderNodeInvert", "ShaderNodeRGBCurve"}:
                            builder.add_node("value", "ShaderNodeValue", default_outputs={0:1})
                            builder.link("value", "source", "Value", "Fac")
                builder.link("group_input", "source", "Color", input_socket_name)

            case "GRADIENT":
                gradient_type = layer.gradient_type
                empty_object = layer.empty_object
                builder = cls(layer, GRADIENT_LAYER_VERSION, "source", "Color", "source", "Alpha")
                builder.add_node("source", "ShaderNodeValToRGB", {"name": "source"})
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
                    case "FAKE_LIGHT":
                        builder.add_node("map_range", "ShaderNodeMapRange")
                        builder.add_node("combine_xyz", "ShaderNodeCombineXYZ", default_values={2: -1 if empty_object and empty_object.type == 'EMPTY' else 1}, force_default_values=True)
                        builder.add_node("object_rotation", "ShaderNodeCombineXYZ")
                        builder.add_node("vector_rotate", "ShaderNodeVectorRotate", {"rotation_type": "EULER_XYZ"})
                        builder.add_node("normal", "ShaderNodeNewGeometry")
                        builder.add_node("dot_product", "ShaderNodeVectorMath", {"operation": "DOT_PRODUCT"})
                        builder.link("combine_xyz", "vector_rotate", "Vector", "Vector")
                        builder.link("object_rotation", "vector_rotate", "Vector", "Rotation")
                        builder.link("vector_rotate", "dot_product", "Vector", 0)
                        builder.link("normal", "dot_product", "Normal", 1)
                        builder.link("dot_product", "map_range", "Value", "Value")
                    case _:
                        raise ValueError(f"Invalid gradient type: {gradient_type}")
                builder.link("map_range", "source", "Result", "Fac")

            case "RANDOM":
                builder = cls(layer, RANDOM_LAYER_VERSION, "hue_saturation_value", "Color")
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

            case "NODE_GROUP":
                custom_node_tree = layer.custom_node_tree
                color_input = parse_socket_name(layer, layer.color_input_name, None)
                alpha_input = parse_socket_name(layer, layer.alpha_input_name, None)
                color_output = parse_socket_name(layer, layer.color_output_name, None)
                alpha_output = parse_socket_name(layer, layer.alpha_output_name, None)
                if alpha_output:
                    builder = cls(layer, CUSTOM_LAYER_VERSION, "source" if color_output else None, color_output, "source" if alpha_output else None, alpha_output)
                else:
                    builder = cls(layer, CUSTOM_LAYER_VERSION, "source" if color_output else None, color_output)
                builder.add_node("source", "ShaderNodeGroup", {"node_tree": custom_node_tree, "name": "source"})
                if color_input:
                    builder.link("group_input", "source", "Color", color_input)
                if alpha_input:
                    builder.link("group_input", "source", "Alpha", alpha_input)

            case "TEXTURE":
                color_socket = parse_socket_name(layer, layer.color_output_name, "Color")
                alpha_socket = parse_socket_name(layer, layer.alpha_output_name, None)
                texture_type = get_texture_identifier(layer.texture_type)
                if alpha_socket:
                    builder = cls(layer, TEXTURE_LAYER_VERSION, "source", color_socket, "source", alpha_socket)
                else:
                    builder = cls(layer, TEXTURE_LAYER_VERSION, "source", color_socket)
                builder.add_node("source", texture_type, {"name": "source"})
                builder.create_coord_graph('source', 'Vector')

            case "GEOMETRY":
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
                geometry_type = layer.geometry_type
                # Determine which node and socket to use for mixing graph
                if geometry_type in ['WORLD_NORMAL', 'WORLD_TRUE_NORMAL', 'OBJECT_NORMAL'] and normalize_normals:
                    color_node_name = "normalize"
                    color_socket = "Vector"
                else:
                    color_node_name = "geometry"
                    color_socket = output_name_map[geometry_type]
                builder = cls(layer, GEOMETRY_LAYER_VERSION, color_node_name, color_socket)
                if geometry_type == 'VECTOR_TRANSFORM':
                    builder.link("group_input", "geometry", "Color", "Vector")
                if geometry_type in ['WORLD_NORMAL', 'WORLD_TRUE_NORMAL', 'OBJECT_NORMAL'] and normalize_normals:
                    builder.add_node("normalize", "ShaderNodeVectorMath", {"operation": "MULTIPLY_ADD", "hide": True}, {1: (0.5, 0.5, 0.5), 2: (0.5, 0.5, 0.5)})
                    builder.link("geometry", "normalize", output_name_map[geometry_type], "Vector")
                builder.add_node("geometry", node_map[geometry_type])

            case _:
                raise ValueError(f"Invalid layer type: {layer.type}")
        
        # Handle Mask Builders
        if hasattr(layer, "layer_masks"):
            for mask in layer.layer_masks:
                if not mask.uid:
                    mask.uid = str(uuid.uuid4())
                builder.mask_builders.append(cls._create_mask_graph(mask, context).builder)
        
        return builder

    @classmethod
    def _create_mask_graph(cls, layer_mask: "LayerMask", context: Context):
        layer_pre_processing(layer_mask, context)
        
        builder = cls(layer_mask, IMAGE_LAYER_VERSION, "source", "Color", as_subgraph=True, properties={"hide": True})
        
        match layer_mask.type:
            case "IMAGE":
                if layer_mask.mask_image:
                    layer_mask.mask_image.name = layer_mask.name
                img = layer_mask.mask_image
                create_mask_mixing_graph(builder, layer_mask, "source", "Color")
                builder.add_node("source", "ShaderNodeTexImage", {"image.force": img, "interpolation": "Closest", "name": "source"})
                builder.create_coord_graph("source", "Vector")
                return builder
            
            case "SOLID_COLOR":
                create_mask_mixing_graph(builder, layer_mask, "source", "Color")
                builder.add_node("source", "ShaderNodeRGB", {"name": "source"}, default_outputs={0: (1, 1, 1, 1)})
                return builder
                
            case "ATTRIBUTE":
                color_socket = parse_socket_name(layer_mask, "source", "Color")
                create_mask_mixing_graph(builder, layer_mask, "source", "Color")
                builder.add_node("source", "ShaderNodeAttribute", {"name": "source"})
                return builder

            case "GRADIENT":
                gradient_type = layer_mask.gradient_type
                empty_object = layer_mask.empty_object
                create_mask_mixing_graph(builder, layer_mask, "source", "Color")
                builder.add_node("source", "ShaderNodeValToRGB", {"name": "source"})
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
                builder.link("map_range", "source", "Result", "Fac")
                return builder

            case "RANDOM":
                create_mask_mixing_graph(builder, layer_mask, "hue_saturation_value", "Color")
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

            case "TEXTURE":
                color_socket = parse_socket_name(layer_mask, "source", "Color")
                texture_type = get_texture_identifier(layer_mask.texture_type)
                create_mask_mixing_graph(builder, layer_mask, "source", color_socket)
                builder.add_node("source", texture_type, {"name": "source"})
                builder.create_coord_graph('source', 'Vector')
                return builder

            case _:
                raise ValueError(f"Invalid layer mask type: {layer_mask.type}")

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
        case "NODE_GROUP":
            return CUSTOM_LAYER_VERSION
        case "BLANK":
            return 0
        case _:
            return 0

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

# Layers that can have custom types are IMAGE, ATTRIBUTE, CUSTOM, TEXTURE
def parse_socket_name(layer: "Layer", socket_name: str, default_socket_name: str = None) -> str:
    if layer.type == "NODE_GROUP":
        custom_node_tree = layer.custom_node_tree
        if custom_node_tree:
            return socket_name if socket_name in custom_node_tree.interface.items_tree else None
        return default_socket_name
    elif layer.source_node:
        return socket_name if socket_name != "_NONE_" else None
    return default_socket_name

def get_paint_system_collection(context: bpy.types.Context) -> bpy.types.Collection:
    view_layer = context.view_layer
    if "Paint System Collection" not in view_layer.layer_collection.collection.children:
        collection = bpy.data.collections.new("Paint System Collection")
        view_layer.layer_collection.collection.children.link(collection)
    else:
        collection = view_layer.layer_collection.collection.children["Paint System Collection"]
    return collection

def add_empty_to_collection(context: bpy.types.Context, empty_object: bpy.types.Object):
    collection = get_paint_system_collection(context)
    if empty_object.name not in collection.objects:
        collection.objects.link(empty_object)

def layer_pre_processing(layer: "Layer", context: Context):
    if layer.coord_type == "DECAL":
        if not layer.empty_object:
            layer.ensure_empty_object()
            layer.empty_object.empty_display_type = 'SINGLE_ARROW'
        elif layer.empty_object.name not in context.view_layer.objects:
            add_empty_to_collection(context, layer.empty_object)
            
    if layer.type == "GRADIENT" and layer.gradient_type in ('LINEAR', 'RADIAL', 'FAKE_LIGHT'):
        if not layer.empty_object:
            layer.ensure_empty_object()
            if layer.gradient_type == 'LINEAR':
                layer.empty_object.empty_display_type = 'SINGLE_ARROW'
            elif layer.gradient_type == 'RADIAL':
                layer.empty_object.empty_display_type = 'SPHERE'
            elif layer.gradient_type == 'FAKE_LIGHT':
                layer.empty_object.location.z += 2.0
                layer.empty_object.rotation_euler = (2.35619449, 0.78539816, 0.0)
                layer.empty_object.empty_display_type = 'SINGLE_ARROW'
        elif layer.empty_object.name not in context.view_layer.objects:
            add_empty_to_collection(context, layer.empty_object)
    
    # Clean up
    if layer.empty_object and layer.type not in ("GRADIENT", "IMAGE", "TEXTURE"):
        collection = get_paint_system_collection(context)
        if layer.empty_object.name in collection.objects:
            collection.objects.unlink(layer.empty_object)
    elif layer.type == "IMAGE" and layer.empty_object and layer.coord_type != "DECAL":
        collection = get_paint_system_collection(context)
        if layer.empty_object.name in collection.objects:
            collection.objects.unlink(layer.empty_object)

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
    create_mixing_graph(builder, None, "group_input", "Over Color", "group_input", "Over Alpha")
    builder.compile()
    return node_tree

def create_layer_graph(layer: "Layer"):
    layer_graph = None
    match layer.type:
        case "IMAGE":
            layer_graph = create_image_graph(layer)
        case "FOLDER":
            layer_graph = create_folder_graph(layer)
        case "SOLID_COLOR":
            layer_graph = create_solid_graph(layer)
        case "ATTRIBUTE":
            layer_graph = create_attribute_graph(layer)
        case "ADJUSTMENT":
            layer_graph = create_adjustment_graph(layer)
        case "GRADIENT":
            layer_graph = create_gradient_graph(layer)
        case "RANDOM":
            layer_graph = create_random_graph(layer)
        case "NODE_GROUP":
            layer_graph = create_custom_graph(layer)
        case "TEXTURE":
            layer_graph = create_texture_graph(layer)
        case "GEOMETRY":
            layer_graph = create_geometry_graph(layer)
    if not layer_graph:
        return None
    if not layer.enabled:
        layer_graph.link("group_input", "group_output", "Color", "Color")
        layer_graph.link("group_input", "group_output", "Alpha", "Alpha")
    return layer_graph
