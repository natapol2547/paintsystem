import bpy
from bpy.types import Context, Material, Image, NodeTree, Node, PropertyGroup
from typing import Optional, Tuple, LiteralString
from dataclasses import dataclass
from mathutils import Vector
import os


LIBRARY_FILE_NAME = "library.blend"
NODE_GROUP_PREFIX = "_PS"
BRUSH_PREFIX = "PS_"
ADJUSTMENT_ENUM = [
    ('ShaderNodeBrightContrast', "Brightness and Contrast", ""),
    ('ShaderNodeGamma', "Gamma", ""),
    ('ShaderNodeHueSaturation', "Hue Saturation Value", ""),
    ('ShaderNodeInvert', "Invert", ""),
    ('ShaderNodeRGBCurve', "RGB Curves", ""),
    # ('ShaderNodeAmbientOcclusion', "Ambient Occlusion", ""),
]
LAYER_ENUM = [
    ('FOLDER', "Folder", "Folder layer"),
    ('IMAGE', "Image", "Image layer"),
    ('SOLID_COLOR', "Solid Color", "Solid Color layer"),
    ('ATTRIBUTE', "Attribute", "Attribute layer"),
    ('ADJUSTMENT', "Adjustment", "Adjustment layer"),
    ('SHADER', "Shader", "Shader layer"),
    ('NODE_GROUP', "Node Group", "Node Group layer"),
]
SHADER_ENUM = [
    ('_PS_Toon_Shader', "Toon Shader (EEVEE)", "Toon Shader"),
    # ('_PS_Light', "Light (EEVEE)", "Light"),
    ('_PS_Ambient_Occlusion', "Ambient Occlusion", "Ambient Occlusion"),
]
TEMPLATE_ENUM = [
    ('STANDARD', "Standard", "Replace the existing material and start off with a basic setup", "IMAGE", 0),
    ('EXISTING', "Convert Existing Material", "Add to existing material setup", "FILE_REFRESH", 1),
    ('NORMAL', "Normals Painting", "Start off with a normal painting setup", "NORMALS_VERTEX_FACE", 2),
    ('TRANSPARENT', "None", "Start off with a blank setup" , "FILE", 3),
    # ('NONE', "Manual", "Just add node group to material", "NONE", 3),
]


def get_addon_filepath():
    return os.path.dirname(bpy.path.abspath(__file__)) + os.sep


def cleanup_duplicate_nodegroups(node_tree: NodeTree):
    """
    Cleanup duplicate node groups by using Blender's remap_users feature.
    This automatically handles all node links and nested node groups.

    Args:
        node_group_name (str): Name of the main node group to clean up
    """
    def find_original_nodegroup(name):
        # Get the base name by removing the .001, .002 etc. if present
        # This gets the part before the first dot
        base_name = name.split('.')[0]

        # Find all matching node groups
        matching_groups = [ng for ng in bpy.data.node_groups
                           if ng.name == base_name or ng.name.split('.')[0] == base_name]

        if not matching_groups:
            return None

        # The original is likely the one without a number suffix
        # or the one with the lowest number if all have suffixes
        for ng in matching_groups:
            if ng.name == base_name:  # Exact match without any suffix
                return ng

        # If we didn't find an exact match, return the one with lowest suffix number
        return sorted(matching_groups, key=lambda x: x.name)[0]

    # Process each node group
    for node in node_tree.nodes:
        if node.type == 'GROUP' and node.node_tree:
            ng = node.node_tree

            # Find the original node group
            original_group = find_original_nodegroup(ng.name)

            # If this is a duplicate (not the original) and we found the original
            if original_group and ng != original_group:
                # Remap all users of this node group to the original
                ng.user_remap(original_group)
                # Remove the now-unused node group
                bpy.data.node_groups.remove(ng)


def get_nodetree_from_library(tree_name, force_reload=False):
    # Check if the node group already exists
    nt = bpy.data.node_groups.get(tree_name)
    if nt:
        if force_reload:
            bpy.data.node_groups.remove(nt)
        else:
            return nt

    # Load the library file
    filepath = get_addon_filepath() + LIBRARY_FILE_NAME
    with bpy.data.libraries.load(filepath) as (lib_file, current_file):
        lib_node_group_names = lib_file.node_groups
        current_node_groups_names = current_file.node_groups
        for node_group_name in lib_node_group_names:
            if node_group_name == tree_name:
                current_node_groups_names.append(node_group_name)

    # Getting the node group
    nt = bpy.data.node_groups.get(tree_name)
    if not nt:
        return None
    cleanup_duplicate_nodegroups(nt)
    return nt


def get_brushes_from_library():
    # Load the library file
    filepath = get_addon_filepath() + LIBRARY_FILE_NAME
    with bpy.data.libraries.load(filepath) as (lib_file, current_file):
        lib_brushes = lib_file.brushes
        current_brushes = current_file.brushes
        for brush in lib_brushes:
            if brush.startswith(BRUSH_PREFIX) and brush not in bpy.data.brushes:
                current_brushes.append(brush)

    # For blender 4.3
    if bpy.app.version >= (4, 3, 0):
        for brush in bpy.data.brushes:
            if brush.name.startswith(BRUSH_PREFIX):
                brush.asset_mark()


def get_paint_system_groups():
    groups = []
    for mat in bpy.data.materials:
        if hasattr(mat, "paint_system"):
            ps = mat.paint_system
            for group in ps.groups:
                groups.append(group)
    return groups


def get_paint_system_images(is_dirty_only=True):
    images = []
    groups = get_paint_system_groups()
    for group in groups:
        bake_image = group.bake_image
        if bake_image and (bake_image.is_dirty or not is_dirty_only):
            images.append(image)
        for item in group.items:
            image = item.image
            if image and (image.is_dirty or not is_dirty_only):
                images.append(image)
            mask_image = item.mask_image
            if mask_image and (mask_image.is_dirty or not is_dirty_only):
                images.append(mask_image)
    return images


# def update_paintsystem_data(self, context):
#     ps = PaintSystem(context)
#     active_group = ps.get_active_group()
#     mat = ps.get_active_material()
#     for layer in active_group.items:
#         if layer.node_tree:
#             layer.node_tree.name = f"PS_{layer.type} {layer.name} (MAT: {mat.name})"
#         if layer.image:
#             layer.image.name = f"PS {mat.name} {active_group.name} {layer.name}"


@dataclass
class PaintSystemPreferences:
    show_tooltips: bool
    use_compact_design: bool
    name_layers_group: bool


class PaintSystem:
    def __init__(self, context: Context):
        self.preferences: PaintSystemPreferences = bpy.context.preferences.addons[
            __package__].preferences
        self.settings = context.scene.paint_system_settings if hasattr(
            context, "scene") else None
        self.context = context
        self.active_object = context.active_object
        # self.settings = self.get_settings()
        # mat = self.get_active_material()
        # self.groups = self.get_groups()
        # active_group = self.get_active_group()
        # active_layer = self.get_active_layer()
        # layer_node_tree = self.get_active_layer().node_tree
        # self.layer_node_group = self.get_active_layer_node_group()
        # self.color_mix_node = self.find_color_mix_node()
        # self.uv_map_node = self.find_uv_map_node()
        # self.opacity_mix_node = self.find_opacity_mix_node()
        # self.clip_mix_node = self.find_clip_mix_node()
        # self.rgb_node = self.find_rgb_node()

    def add_group(self, name: str) -> PropertyGroup:
        """Creates a new group in the active material's paint system.

        Args:
            name (str): The name of the new group.

        Returns:
            PropertyGroup: The newly created group.
        """
        mat = self.get_active_material()
        new_group = mat.paint_system.groups.add()
        new_group.name = name
        node_tree = bpy.data.node_groups.new(
            name=f"PS_GROUP {name} (MAT: {mat.name})", type='ShaderNodeTree')
        new_group.node_tree = node_tree
        new_group.update_node_tree()
        # Set the active group to the newly created one
        mat.paint_system.active_group = str(
            len(mat.paint_system.groups) - 1)

        return new_group

    def delete_active_group(self):
        """
        Deletes the currently active group along with all its items and children.
        Returns:
            bool: True if the active group and its items were successfully deleted, False otherwise.
        """
        use_node_tree = False
        mat = self.get_active_material()
        active_group = self.get_active_group()
        for node in mat.node_tree.nodes:
            if node.type == 'GROUP' and node.node_tree == active_group.node_tree:
                use_node_tree = True
                break

        # 2 users: 1 for the material node tree, 1 for the datablock
        if active_group.node_tree and active_group.node_tree.users <= 1 + use_node_tree:
            bpy.data.node_groups.remove(active_group.node_tree)

        for item, _ in active_group.flatten_hierarchy():
            self._on_item_delete(item)

        active_group_idx = int(mat.paint_system.active_group)
        mat.paint_system.groups.remove(active_group_idx)

        if mat.paint_system.active_group:
            mat.paint_system.active_group = str(
                min(active_group_idx, len(mat.paint_system.groups) - 1))

        return True

    def delete_active_item(self):
        """
        Deletes the currently active item in the active group along with its children.
        Returns:
            bool: True if the active item and its children were successfully deleted, False otherwise.
        """
        active_group = self.get_active_group()
        item_id = active_group.get_id_from_flattened_index(
            active_group.active_index)

        self.delete_item_id(item_id)
    
    def delete_item_id(self, item_id):
        active_group = self.get_active_group()
        if item_id != -1 and active_group.remove_item_and_children(item_id, self._on_item_delete):
            # Update active_index
            flattened = active_group.flatten_hierarchy()
            active_group.active_index = min(
                active_group.active_index, len(flattened) - 1)

            active_group.update_node_tree()

            return True
        return False

    def create_image_layer(self, name: str, image: Image, uv_map_name: str = None) -> PropertyGroup:
        """Creates a new image layer in the active group.

        Args:
            image (Image): The image to be used in the layer.
            uv_map_name (str, optional): The name of the UV map to be used. Defaults to None.

        Returns:
            PropertyGroup: The newly created image layer.
        """
        # image.pack()

        active_group = self.get_active_group()

        # Get insertion position
        # parent_id, insert_order = active_group.get_insertion_data()
        # # Adjust existing items' order
        # active_group.adjust_sibling_orders(parent_id, insert_order)

        # mat = self.get_active_material()
        # layer_template = get_nodetree_from_library(
        #     '_PS_Layer_Template', False)
        # layer_nt = layer_template.copy()
        # layer_nt.name = f"PS {name} (MAT: {mat.name})"

        new_layer = self._add_layer(
            name, f'_PS_Layer_Template', 'IMAGE', image=image, force_reload=False, make_copy=True)
        layer_nt = new_layer.node_tree

        # Find the image texture node
        image_texture_node = None
        for node in layer_nt.nodes:
            if node.type == 'TEX_IMAGE':
                image_texture_node = node
                break
        uv_map_node = None
        # Find UV Map node
        for node in layer_nt.nodes:
            if node.type == 'UVMAP':
                uv_map_node = node
                break
        # use uv_map_name or default to first uv map
        if uv_map_name:
            uv_map_node.uv_map = uv_map_name
        else:
            uv_map_node.uv_map = bpy.context.object.data.uv_layers[0].name
        image_texture_node.image = image
        # node_tree = self._create_layer_node_tree(name, image, uv_map_name)

        # Create the new item
        # new_id = active_group.add_item(
        #     name=name,
        #     item_type='IMAGE',
        #     parent_id=parent_id,
        #     order=insert_order,
        #     image=image,
        #     node_tree=node_tree,
        # )

        # Update active index
        # if new_id != -1:
        #     flattened = active_group.flatten_hierarchy()
        #     for i, (item, _) in enumerate(flattened):
        #         if item.id == new_id:
        #             active_group.active_index = i
        #             break

        active_group.update_node_tree()

        return new_layer
    
    def create_attribute_layer(self, name: str, attribute_name: str, attribute_type: str = "") -> PropertyGroup:
        """Creates a new attribute layer in the active group.

        Args:
            name (str): The name of the new attribute layer.
            attribute_name (str): The name of the attribute to be used.

        Returns:
            PropertyGroup: The newly created attribute layer.
        """
        active_group = self.get_active_group()
        new_layer = self._add_layer(
            name, '_PS_Attribute_Template', 'ATTRIBUTE', make_copy=True)
        attr_node = new_layer.node_tree.nodes['Attribute']
        attr_node.attribute_name = attribute_name
        active_group.update_node_tree()
        return new_layer

    def create_solid_color_layer(self, name: str, color: Tuple[float, float, float, float]) -> PropertyGroup:
        """Creates a new solid color layer in the active group.

        Args:
            color (Tuple[float, float, float, float]): The color to be used in the layer.

        Returns:
            PropertyGroup: The newly created solid color layer.
        """
        # mat = self.get_active_material()
        active_group = self.get_active_group()
        # # Get insertion position
        # parent_id, insert_order = active_group.get_insertion_data()
        # # Adjust existing items' order
        # active_group.adjust_sibling_orders(parent_id, insert_order)

        # solid_color_template = get_nodetree_from_library(
        #     '_PS_Solid_Color_Template', False)
        # solid_color_nt = solid_color_template.copy()
        # solid_color_nt.name = f"PS_IMG {name} (MAT: {mat.name})"
        new_layer = self._add_layer(
            name, f'_PS_Solid_Color_Template', 'SOLID_COLOR', make_copy=True)
        solid_color_nt = new_layer.node_tree
        solid_color_nt.nodes['RGB'].outputs[0].default_value = color

        # Create the new item
        # new_id = active_group.add_item(
        #     name=name,
        #     item_type='SOLID_COLOR',
        #     parent_id=parent_id,
        #     order=insert_order,
        #     node_tree=solid_color_nt,
        # )

        # Update active index
        # if new_id != -1:
        #     flattened = active_group.flatten_hierarchy()
        #     for i, (item, _) in enumerate(flattened):
        #         if item.id == new_id:
        #             active_group.active_index = i
        #             break

        active_group.update_node_tree()

        return new_layer

    def create_folder(self, name: str) -> PropertyGroup:
        """Creates a new folder in the active group.

        Args:
            name (str): The name of the new folder.

        Returns:
            PropertyGroup: The newly created folder.
        """
        # mat = self.get_active_material()
        active_group = self.get_active_group()
        # # Get insertion position
        # parent_id, insert_order = active_group.get_insertion_data()

        # # Adjust existing items' order
        # active_group.adjust_sibling_orders(parent_id, insert_order)

        # folder_template = get_nodetree_from_library(
        #     '_PS_Folder_Template', False)
        # folder_nt = folder_template.copy()
        # folder_nt.name = f"PS_FLD {name} (MAT: {mat.name})"

        new_layer = self._add_layer(
            name, f'_PS_Folder_Template', 'FOLDER', make_copy=True)

        # Create the new item
        # new_id = active_group.add_item(
        #     name=name,
        #     item_type='FOLDER',
        #     parent_id=parent_id,
        #     order=insert_order,
        #     node_tree=folder_nt
        # )

        # Update active index
        # if new_id != -1:
        #     flattened = active_group.flatten_hierarchy()
        #     for i, (item, _) in enumerate(flattened):
        #         if item.id == new_id:
        #             active_group.active_index = i
        #             break

        active_group.update_node_tree()

        return new_layer

    def create_adjustment_layer(self, name: str, adjustment_type: str) -> PropertyGroup:
        """Creates a new adjustment layer in the active group.

        Args:
            name (str): The name of the new adjustment layer.
            adjustment_type (str): The type of adjustment to be applied.

        Returns:
            PropertyGroup: The newly created adjustment layer.
        """
        mat = self.get_active_material()
        active_group = self.get_active_group()
        # # Get insertion position
        # parent_id, insert_order = active_group.get_insertion_data()

        # # Adjust existing items' order
        # active_group.adjust_sibling_orders(parent_id, insert_order)

        # adjustment_template = get_nodetree_from_library(
        #     f'_PS_Adjustment_Template', False)
        # adjustment_nt: NodeTree = adjustment_template.copy()
        # adjustment_nt.name = f"PS_ADJ {name} (MAT: {mat.name})"
        new_layer = self._add_layer(
            name, f'_PS_Adjustment_Template', 'ADJUSTMENT', make_copy=True)
        adjustment_nt = new_layer.node_tree
        nodes = adjustment_nt.nodes
        links = adjustment_nt.links
        # Find Vector Math node
        group_input_node = None
        for node in nodes:
            if node.type == 'GROUP_INPUT':
                group_input_node = node
                break

        # Find Mix node
        mix_node = None
        for node in nodes:
            if node.type == 'MIX' and node.data_type == 'RGBA':
                mix_node = node
                break

        adjustment_node = nodes.new(adjustment_type)
        adjustment_node.label = 'Adjustment'
        adjustment_node.location = mix_node.location + Vector([0, -200])

        # Checks if the adjustment node has a factor input
        if 'Fac' in adjustment_node.inputs:
            # Create a value node
            value_node = nodes.new('ShaderNodeValue')
            value_node.label = 'Factor'
            value_node.outputs[0].default_value = 1.0
            value_node.location = adjustment_node.location + Vector([-200, 0])
            links.new(value_node.outputs['Value'],
                      adjustment_node.inputs['Fac'])

        links.new(adjustment_node.inputs['Color'],
                  group_input_node.outputs['Color'])
        links.new(mix_node.inputs['B'], adjustment_node.outputs['Color'])

        # Create the new item
        # new_id = active_group.add_item(
        #     name=name,
        #     item_type='ADJUSTMENT',
        #     parent_id=parent_id,
        #     order=insert_order,
        #     node_tree=adjustment_nt
        # )

        # Update active index
        # if new_id != -1:
        #     flattened = active_group.flatten_hierarchy()
        #     for i, (item, _) in enumerate(flattened):
        #         if item.id == new_id:
        #             active_group.active_index = i
        #             break

        active_group.update_node_tree()

        return new_layer

    def create_shader_layer(self, name: str, shader_type: str) -> PropertyGroup:
        active_group = self.get_active_group()
        new_layer = self._add_layer(
            name, shader_type, 'SHADER', sub_type=shader_type, make_copy=True)
        active_group.update_node_tree()
        return new_layer
    
    def create_node_group_layer(self, name: str, node_tree_name: str) -> PropertyGroup:
        active_group = self.get_active_group()
        new_layer = self._add_layer(
            name, node_tree_name, 'NODE_GROUP')
        active_group.update_node_tree()
        return new_layer

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
        active_group_idx = int(paint_system.active_group)
        if active_group_idx >= len(paint_system.groups):
            return None  # handle cases where active index is invalid
        return paint_system.groups[active_group_idx]

    def get_active_layer(self) -> Optional[PropertyGroup]:
        active_group = self.get_active_group()
        if not active_group:
            return None
        flattened = active_group.flatten_hierarchy()
        if not flattened:
            return None

        if active_group.active_index >= len(flattened):
            return None  # handle cases where active index is invalid

        return flattened[active_group.active_index][0]

    def get_layer_node_tree(self) -> Optional[NodeTree]:
        active_layer = self.get_active_layer()
        if not active_layer:
            return None
        return active_layer.node_tree

    def get_active_layer_node_group(self) -> Optional[Node]:
        active_group = self.get_active_group()
        layer_node_tree = self.get_active_layer().node_tree
        if not layer_node_tree:
            return None
        node_details = {'type': 'GROUP', 'node_tree': layer_node_tree}
        node = self.find_node(active_group.node_tree, node_details)
        return node

    def find_color_mix_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'type': 'MIX', 'data_type': 'RGBA'}
        return self.find_node(layer_node_tree, node_details)

    def find_uv_map_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'type': 'UVMAP'}
        return self.find_node(layer_node_tree, node_details)

    def find_opacity_mix_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'type': 'MIX', 'name': 'Opacity'}
        return self.find_node(layer_node_tree, node_details) or self.find_color_mix_node()

    def find_clip_mix_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'type': 'MIX', 'name': 'Clip'}
        return self.find_node(layer_node_tree, node_details)

    def find_image_texture_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'type': 'TEX_IMAGE'}
        return self.find_node(layer_node_tree, node_details)

    def find_rgb_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
        node_details = {'name': 'RGB'}
        return self.find_node(layer_node_tree, node_details)

    def find_adjustment_node(self) -> Optional[Node]:
        layer_node_tree = self.get_active_layer().node_tree
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
    
    def is_valid_ps_nodetree(self, node_tree: NodeTree):
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
            

    def _update_paintsystem_data(self):
        active_group = self.get_active_group()
        mat = self.get_active_material()
        # active_group.update_node_tree()
        if active_group.node_tree:
            active_group.node_tree.name = f"PS_GROUP {active_group.name} (MAT: {mat.name})"
        for layer in active_group.items:
            if not layer.type == 'NODE_GROUP':
                if layer.node_tree:
                    layer.node_tree.name = f"PS_{layer.type} {active_group.name} {layer.name} (MAT: {mat.name})"
                if layer.image:
                    layer.image.name = f"PS {active_group.name} {layer.name} (MAT: {mat.name})"

    def _add_layer(self, layer_name, tree_name: str, item_type: str, sub_type="", image=None, force_reload=False, make_copy=False) -> NodeTree:
        print(f"Creating {item_type} layer: {layer_name}")
        active_group = self.get_active_group()
        # Get insertion position
        parent_id, insert_order = active_group.get_insertion_data()
        # Adjust existing items' order
        active_group.adjust_sibling_orders(parent_id, insert_order)
        nt = get_nodetree_from_library(
            tree_name, force_reload)
        if make_copy:
            nt = nt.copy()
        # Create the new item
        new_id = active_group.add_item(
            name=layer_name,
            item_type=item_type,
            sub_type=sub_type,
            parent_id=parent_id,
            order=insert_order,
            node_tree=nt,
            image=image,
        )

        # Update active index
        if new_id != -1:
            flattened = active_group.flatten_hierarchy()
            for i, (item, _) in enumerate(flattened):
                if item.id == new_id:
                    active_group.active_index = i
                    break
        self._update_paintsystem_data()
        return active_group.get_item_by_id(new_id)

    def _value_set(self, obj, path, value):
        if '.' in path:
            path_prop, path_attr = path.rsplit('.', 1)
            prop = obj.path_resolve(path_prop)
        else:
            prop = obj
            path_attr = path
        setattr(prop, path_attr, value)

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

    def _create_folder_node_tree(self, folder_name: str, force_reload=False) -> NodeTree:
        mat = self.get_active_material()
        folder_template = get_nodetree_from_library(
            '_PS_Folder_Template', force_reload)
        folder_nt = folder_template.copy()
        folder_nt.name = f"PS {folder_name} (MAT: {mat.name})"
        return folder_nt

    def _create_layer_node_tree(self, layer_name: str, image: Image, uv_map_name: str = None, force_reload=True) -> NodeTree:
        mat = self.get_active_material()
        layer_template = get_nodetree_from_library(
            '_PS_Layer_Template', force_reload)
        layer_nt = layer_template.copy()
        layer_nt.name = f"PS {layer_name} (MAT: {mat.name})"
        # Find the image texture node
        image_texture_node = None
        for node in layer_nt.nodes:
            if node.type == 'TEX_IMAGE':
                image_texture_node = node
                break
        uv_map_node = None
        # Find UV Map node
        for node in layer_nt.nodes:
            if node.type == 'UVMAP':
                uv_map_node = node
                break
        # use uv_map_name or default to first uv map
        if uv_map_name:
            uv_map_node.uv_map = uv_map_name
        else:
            uv_map_node.uv_map = bpy.context.object.data.uv_layers[0].name
        image_texture_node.image = image
        return layer_nt

    def _on_item_delete(self, item):
        if item.node_tree:
            # 2 users: 1 for the node tree, 1 for the datablock
            if item.node_tree.users <= 2:
                # print("Removing node tree")
                bpy.data.node_groups.remove(item.node_tree)

        if item.image:
            # 2 users: 1 for the image datablock, 1 for the panel
            if item.image and item.image.users <= 2:
                # print("Removing image")
                bpy.data.images.remove(item.image)
