import bpy
from bpy.types import Operator, Context, Node, NodeTree
from bpy.utils import register_classes_factory
from .paint_system import PaintSystem, get_nodetree_from_library
from typing import List, Tuple
from mathutils import Vector
from .common import redraw_panel, map_range
import copy

IMPOSSIBLE_NODES = (
    "ShaderNodeShaderInfo"
)
REQUIRES_INTERMEDIATE_STEP = (
    "ShaderNodeShaderToRGB"
)


def get_connected_nodes(output_node: Node) -> List[Node]:
    """
    Gets all nodes connected to the given output_node, 
    maintaining the order in which they were found and removing duplicates.

    Args:
        node: The output node.

    Returns:
        A list of nodes, preserving the order of discovery and removing duplicates.
    """

    nodes = []
    visited = set()  # Here's where the set is used

    def traverse(node: Node):
        if node not in visited:  # Check if the node has been visited
            visited.add(node)  # Add the node to the visited set
            nodes.append(node)
            for input in node.inputs:
                for link in input.links:
                    traverse(link.from_node)

    traverse(output_node)
    return nodes


def get_active_material_output(node_tree: NodeTree) -> Node:
    """Get the active material output node

    Args:
        node_tree (bpy.types.NodeTree): The node tree to check

    Returns:
        bpy.types.Node: The active material output node
    """
    for node in node_tree.nodes:
        if node.bl_idname == "ShaderNodeOutputMaterial" and node.is_active_output:
            return node
    return None


def is_bakeable(context: Context) -> Tuple[bool, str, List[Node]]:
    """Check if the node tree is multi-user

    Args:
        context (bpy.types.Context): The context to check

    Returns:
        Tuple[bool, str, List[bpy.types.Node]]: A tuple containing a boolean indicating if the node tree is multi-user and an error message if any
    """
    ps = PaintSystem(context)
    active_group = ps.get_active_group()
    mat = ps.get_active_material()
    if not mat:
        return False, "No active material found.", []
    if not mat.use_nodes:
        return False, "Material does not use nodes.", []
    if not mat.node_tree:
        return False, "Material has no node tree.", []
    if not mat.node_tree.nodes:
        return False, "Material node tree has no nodes.", []
    output_node = get_active_material_output(mat.node_tree)
    if not output_node:
        return False, "No active material output node found.", []
    node_tree = active_group.node_tree

    connected_nodes = get_connected_nodes(output_node)

    ps_groups = []
    impossible_nodes = []

    for node in connected_nodes:
        if node.bl_idname == "ShaderNodeGroup" and node.node_tree == node_tree:
            ps_groups.append(node)
        if node.bl_idname in IMPOSSIBLE_NODES:
            impossible_nodes.append(node)

    if len(ps_groups) != 1:
        print(len(ps_groups))
        return False, "Paint System group is not found or used multiple times.", ps_groups
    if impossible_nodes:
        return False, "Unsupported nodes found.", impossible_nodes

    return True, "", []


def save_cycles_settings():
    """Saves relevant Cycles render settings to a dictionary."""
    settings = {}
    scene = bpy.context.scene

    if scene.render.engine == 'CYCLES':  # Only save if Cycles is the engine
        settings['render_engine'] = scene.render.engine
        settings['device'] = scene.cycles.device
        settings['samples'] = scene.cycles.samples
        settings['preview_samples'] = scene.cycles.preview_samples
        settings['denoiser'] = scene.cycles.denoiser
        settings['use_denoising'] = scene.cycles.use_denoising

        # Add more settings you need to save here!
    return copy.deepcopy(settings)


def rollback_cycles_settings(saved_settings):
    """Rolls back Cycles render settings using the saved dictionary, with robustness checks."""
    scene = bpy.context.scene

    # Only rollback if settings were saved and we are in Cycles
    if saved_settings and scene.render.engine == 'CYCLES':
        try:  # Use a try-except block to catch potential errors during rollback
            # Check if 'engine' attribute still exists
            if 'render_engine' in saved_settings and hasattr(scene.render, 'engine'):
                scene.render.engine = saved_settings['render_engine']

            # Check if 'cycles' and 'device' exist
            if 'device' in saved_settings and hasattr(scene.cycles, 'device'):
                scene.cycles.device = saved_settings['device']
            if 'samples' in saved_settings and hasattr(scene.cycles, 'samples'):
                scene.cycles.samples = saved_settings['samples']
            if 'preview_samples' in saved_settings and hasattr(scene.cycles, 'preview_samples'):
                scene.cycles.preview_samples = saved_settings['preview_samples']
            if 'denoiser' in saved_settings and hasattr(scene.cycles, 'denoiser'):
                scene.cycles.denoiser = saved_settings['denoiser']
            if 'use_denoising' in saved_settings and hasattr(scene.cycles, 'use_denoising'):
                scene.cycles.use_denoising = saved_settings['use_denoising']

            # Add rollbacks for any other settings you saved with similar checks!

        except Exception as e:
            # Log any errors during rollback
            print(f"Error during Cycles settings rollback: {e}")
            # You might want to handle the error more specifically, e.g., show a message to the user.


def bake_node(context: Context, target_node: Node, width=1024, height=1024) -> Node:
    """
    Bakes a specific node from the active material with optimized settings

    Args:
        node_name bpy.types.Node: The node to bake
        bake_type (str): Type of bake to perform ('DIFFUSE', 'NORMAL', etc.)

    Returns:
        Image Texture Node: The baked image texture node
    """
    obj = context.active_object
    if not obj or not obj.active_material:
        return None

    material = obj.active_material
    material.use_nodes = True
    nodes = material.node_tree.nodes
    material_output = get_active_material_output(material.node_tree)
    connected_nodes = get_connected_nodes(material_output)
    last_node_socket = material_output.inputs[0].links[0].from_socket

    # Save the original links from connected_nodes
    links = material.node_tree.links
    original_links = []
    for node in connected_nodes:
        for input in node.inputs:
            for link in input.links:
                original_links.append(link)

    try:
        # Store original settings
        original_engine = getattr(context.scene.render, "engine")
        # Switch to Cycles if needed
        if context.scene.render.engine != 'CYCLES':
            context.scene.render.engine = 'CYCLES'

        cycles_settings = save_cycles_settings()
        cycles = context.scene.cycles
        bake_nt = None
        if 'Color' in target_node.outputs:
            bake_nt = get_nodetree_from_library("_PS_Bake")
            bake_node = nodes.new('ShaderNodeGroup')
            bake_node.node_tree = bake_nt
            links.new(bake_node.inputs['Color'], target_node.outputs['Color'])
            links.new(material_output.inputs[0], bake_node.outputs['Shader'])
            # Check if target node has Alpha output
            if 'Alpha' in target_node.outputs:
                links.new(bake_node.inputs['Alpha'],
                          target_node.outputs['Alpha'])
            bake_params = {
                "type": 'COMBINED',
                "pass_filter": {'EMIT', 'DIRECT'},
                "use_clear": True,
            }
            cycles.samples = 1
            cycles.use_denoising = False
            cycles.use_adaptive_sampling = False
        elif 'Shader' in target_node.outputs:
            links.new(material_output.inputs[0], target_node.outputs[0])
            bake_params = {
                "type": 'COMBINED',
                "use_clear": True,
            }
            cycles.samples = 256
            cycles.use_denoising = True
            cycles.use_adaptive_sampling = True
        else:
            return None

        # Create a new image with appropriate settings
        image_name = f"{material.name}_{target_node.name}"
        image = bpy.data.images.new(
            name=image_name,
            width=width,
            height=height,
            alpha=True,
        )
        image.colorspace_settings.name = 'sRGB'

        # Create and set up the image texture node
        bake_tex_node = nodes.new('ShaderNodeTexImage')
        bake_tex_node.name = "temp_bake_node"
        bake_tex_node.image = image  # Link the image to the texture node
        bake_tex_node.location = target_node.location + Vector((0, 300))

        for node in nodes:
            node.select = False
        bake_tex_node.select = True

        # Perform bake
        bpy.ops.object.bake(**bake_params)

        # Pack the image
        if not image.packed_file:
            image.pack()
            image.reload()
            print(f"Image {image.name} packed.")

        # Delete temporary bake node
        nodes.remove(bake_node)
        rollback_cycles_settings(cycles_settings)

        # Restore original links
        links.new(material_output.inputs[0], last_node_socket)
        context.scene.render.engine = original_engine

        return bake_node

    except Exception as e:
        print(f"Baking failed: {str(e)}")
        return None


class PAINTSYSTEM_OT_BakeGroup(Operator):
    bl_idname = "paint_system.bake_group"
    bl_label = "Bake Group"
    bl_description = "Bake the selected group"
    bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

    bake_started = False

    # @classmethod
    # def poll(cls, context):
    #     return is_bakeable(context)[0]

    def execute(self, context):
        ps = PaintSystem(context)
        mat = ps.get_active_material()
        active_group = ps.get_active_group()
        if not mat:
            return {'CANCELLED'}

        bakable, error, nodes = is_bakeable(context)
        if not bakable:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}

        connected_node = get_connected_nodes(
            get_active_material_output(mat.node_tree))
        baking_steps: List[Tuple[Node, str]] = []
        for node in connected_node:
            if node.bl_idname in REQUIRES_INTERMEDIATE_STEP:
                if node.bl_idname == "ShaderNodeShaderToRGB":
                    node = node.inputs[0].links[0].from_node
                baking_steps.append((node, "COMBINED"))
            if node.bl_idname == "ShaderNodeGroup" and node.node_tree == active_group.node_tree:
                baking_steps.append((node, "EMIT"))

        baking_steps.reverse()
        print(baking_steps)

        for idx, (node, bake_type) in enumerate(baking_steps):
            tex_node = bake_node(context, node)

        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_BakeGroup,
)

register, unregister = register_classes_factory(classes)
