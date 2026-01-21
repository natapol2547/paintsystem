import bpy
from bpy.types import Node, NodeTree, NodeSocket, Context
from bpy_extras.node_utils import find_base_socket_type
from ..custom_icons import get_icon_from_socket_type

def traverse_connected_nodes(node: Node, input: bool = True, output: bool = False) -> set[Node]:
    visited = set()
    nodes = set()
    stack = [node]
    
    while stack:
        curr_node = stack.pop()
        if curr_node in visited:
            continue
        visited.add(curr_node)
        
        if curr_node != node:
            nodes.add(curr_node)
            
        if input:
            for input_socket in curr_node.inputs:
                for link in input_socket.links:
                    if link.from_node not in visited:
                        stack.append(link.from_node)
        if output:
            for output_socket in curr_node.outputs:
                for link in output_socket.links:
                    if link.to_node not in visited:
                        stack.append(link.to_node)
    
    return nodes

def get_material_output(mat_node_tree: NodeTree) -> Node:
    node = None
    for node in mat_node_tree.nodes:
        if node.bl_idname == 'ShaderNodeOutputMaterial' and node.is_active_output:
            return node
    # Try to find Group Output node instead
    for node in mat_node_tree.nodes:
        if node.bl_idname == 'NodeGroupOutput':
            return node
    if node is None:
        node = mat_node_tree.nodes.new(type='ShaderNodeOutputMaterial')
        node.is_active_output = True
    return node

def transfer_connection(node_tree: NodeTree, source_socket: NodeSocket, target_socket: NodeSocket):
    """Transfer the connection from the source socket to the target socket

    Args:
        node_tree (NodeTree): The node tree to transfer the connection to
        source_socket (NodeSocket): The source socket to transfer the connection from
        target_socket (NodeSocket): The target socket to transfer the connection to

    Returns:
        bool: True if the connection was transferred, False otherwise
    """
    # If the source socket is linked, transfer the connection to the target socket
    if source_socket.is_linked:
        original_socket = source_socket.links[0].from_socket
        node_tree.links.new(original_socket, target_socket)
        return True
    else:
        # Copy the value from source socket to target socket
        try:
            target_socket.default_value = source_socket.default_value
        except Exception as e:
            print(f"Failed to transfer connection from {source_socket.name} ({source_socket.type}) to {target_socket.name} ({target_socket.type}): {e}")
        return False

def find_nodes(node_tree: NodeTree, properties: dict) -> list[Node]:
    node = get_material_output(node_tree)
    nodes = traverse_connected_nodes(node)
    return [node for node in nodes if all(hasattr(node, prop) and getattr(node, prop) == value for prop, value in properties.items())]

def find_node(node_tree: NodeTree, properties: dict, connected_to_output: bool = True) -> Node | None:
    visited = set()
    
    if connected_to_output:
        start_node = get_material_output(node_tree)
        if not start_node:
            return None

        stack = [start_node]
    else:
        start_node = None
        stack = list(node_tree.nodes)
    
    while stack:
        curr_node = stack.pop()
        if curr_node in visited:
            continue
        visited.add(curr_node)
        
        # Check properties immediately when we encounter a node (skip the start node)
        if curr_node != start_node:
            if all(hasattr(curr_node, prop) and getattr(curr_node, prop) == value for prop, value in properties.items()):
                return curr_node
        
        # Only continue traversing if we haven't found a match yet
        for input_socket in curr_node.inputs:
            for link in input_socket.links:
                if link.from_node not in visited:
                    stack.append(link.from_node)
        
        for output_socket in curr_node.outputs:
            for link in output_socket.links:
                if link.to_node not in visited:
                    stack.append(link.to_node)

    return None

def get_nodetree_socket_enum(node_tree: NodeTree, in_out: str = 'INPUT', favor_socket_name: str = None, include_none: bool = False, none_at_start: bool = True):
    socket_items = []
    count = 0
    if include_none and none_at_start:
        socket_items.append(('_NONE_', 'None', '', 'BLANK1', count))
        count += 1
    sockets = [socket for socket in node_tree.interface.items_tree if socket.item_type == 'SOCKET' and socket.in_out == in_out and socket.socket_type != 'NodeSocketShader']
    if favor_socket_name:
        sockets.sort(key=lambda x: x.name == favor_socket_name, reverse=True)
    for socket in sockets:
        socket_items.append((socket.name, socket.name, "", get_icon_from_socket_type(socket.socket_type.replace("NodeSocket", "").upper()), count))
        count += 1
    if include_none and not none_at_start:
        socket_items.append(('_NONE_', 'None', '', 'BLANK1', count))
        count += 1
    return socket_items

def get_node_socket_enum(node: Node, in_out: str = 'INPUT', favor_socket_name: str = None, include_none: bool = False, none_at_start: bool = True):
    socket_items = []
    count = 0
    sockets = [socket for socket in (node.inputs if in_out == 'INPUT' else node.outputs) if socket.enabled]
    if favor_socket_name not in [socket.name for socket in sockets]:
        favor_socket_name = None
        none_at_start = True
    if include_none and none_at_start:
        socket_items.append(('_NONE_', 'None', '', 'BLANK1', count))
        count += 1
    if favor_socket_name:
        sockets.sort(key=lambda x: x.name == favor_socket_name, reverse=True)
    for socket in sockets:
        base_socket_name = find_base_socket_type(socket).replace("NodeSocket", "").upper()
        socket_items.append((socket.name, socket.name, "", get_icon_from_socket_type(base_socket_name), count))
        count += 1
    if include_none and not none_at_start:
        socket_items.append(('_NONE_', 'None', '', 'BLANK1', count))
        count += 1
    return socket_items

def dissolve_nodes(node_tree: NodeTree, nodes: list[Node]):
    start_node = None
    end_node = None
    start_node_input = None
    end_node_output = None
    print(f"Dissolving nodes: {nodes}")
    for node in nodes:
        print(f"Checking node: {node.name}")
        for input_socket in node.inputs:
            for link in input_socket.links:
                print(f"Checking link: {link.from_node.name}")
                if link.from_node not in nodes:
                    print(f"Found start node: {link.from_node.name}")
                    start_node = link.from_node
                    start_node_input = input_socket
                    break
        for output_socket in node.outputs:
            for link in output_socket.links:
                print(f"Checking link: {link.to_node.name} in {nodes}")
                if link.to_node not in nodes:
                    print(f"Found end node: {link.to_node.name}")
                    end_node = link.to_node
                    end_node_output = output_socket
                    break
        if start_node and end_node:
            break
    if start_node and end_node and start_node_input and end_node_output:
        node_tree.links.new(start_node_input, end_node_output)
    for node in nodes:
        node_tree.nodes.remove(node)

def find_node_on_socket(socket: NodeSocket, properties: dict) -> Node | None:
    for link in socket.links:
        node = link.to_node if socket.is_output else link.from_node
        if all(hasattr(node, prop) and getattr(node, prop) == value for prop, value in properties.items()):
            return node
    return None

def find_connected_node(node: Node, properties: dict) -> Node | None:
    for input_socket in node.inputs:
        input_node = find_node_on_socket(input_socket, properties)
        if input_node:
            return input_node
    for output_socket in node.outputs:
        output_node = find_node_on_socket(output_socket, properties)
        if output_node:
            return output_node
    return None

def find_socket_on_node(node: Node, name: str, in_out: str = 'INPUT', properties: dict = {}) -> NodeSocket | None:
    properties['name'] = name
    sockets = [socket for socket in (node.inputs if in_out == 'INPUT' else node.outputs) if socket.enabled]
    for socket in sockets:
        if all(hasattr(socket, prop) and getattr(socket, prop) == value for prop, value in properties.items()):
            return socket
    return None

def is_in_nodetree(context: Context) -> bool:
    return context.space_data.type == 'NODE_EDITOR' and len(context.space_data.path) > 1