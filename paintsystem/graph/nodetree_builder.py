import bpy
from bpy.utils import register_classes_factory
from mathutils import Vector, Color
from typing import Dict, List, Union, Sequence, Set, Optional, Tuple
from dataclasses import dataclass, field
from uuid import uuid4
import re
import time
from bpy_extras.node_utils import connect_sockets

pattern_increment = re.compile(r"^(.+?_)(\d+)\.(\d+)$")
pattern_normalize = re.compile(r"^(.+?)[._](\d+)$")

# --- Special Identifiers for Graph Start and End ---
# START doesn't map to a real node, it's a conceptual entry point.
# In our context, we'll often connect from nodes that don't need inputs,
# like Texture Coordinate or Geometry.
START = "START_"

# END maps to the final output node of the tree, which is usually 'Material Output'.
END = "END_"

SOCKET_TYPES = ('NodeSocketFloat', 'NodeSocketInt', 'NodeSocketBool',
                'NodeSocketVector', 'NodeSocketColor', 'NodeSocketShader', 'NodeSocketImage')


def get_main_socket_type(socket_type: str) -> str:
    """
    Returns the canonical socket type prefix given a full socket type string.

    Args:
        socket_type (str): The Blender socket type name to normalize
                           (e.g., 'NodeSocketFloatFactor' -> 'NodeSocketFloat').

    Returns:
        str: The canonical socket type prefix if recognized, otherwise None.
    """
    for socket in SOCKET_TYPES:
        if socket_type.startswith(socket):
            return socket
    return None


def capture_node_properties(node: bpy.types.Node) -> dict:
    node_props: Dict[str, object] = {}
    try:
        for prop in getattr(node, 'bl_rna', None).properties:
            # Ignore internal/meta properties
            pid = getattr(prop, 'identifier', '')
            if not pid or getattr(prop, 'is_readonly', False):
                if node.bl_idname == "ShaderNodeValToRGB" and hasattr(node, "color_ramp"):
                    node_props["color_ramp"] = [(element.color, element.alpha, element.position) for element in node.color_ramp.elements]
                continue
            if pid in {
                'rna_type', 'type', 'location_absolute', 'location', 'internal_links',
                'inputs', 'outputs', 'parent', 'name', 'label', 'node_width', 'mute', 'hide', 'bl_idname'
            }:
                continue
            ptype = getattr(prop, 'type', None)
            if ptype in {'BOOLEAN', 'INT', 'FLOAT', 'STRING', 'ENUM'}:
                try:
                    node_props[pid] = getattr(node, pid)
                except Exception as e:
                    # print(f"Warning: Could not capture property '{pid}' for '{node.name}'. Error: {e}")
                    pass
    except Exception as e:
        # print(f"Warning: Could not capture node state for '{node.name}'. Error: {e}")
        # If introspection fails on this node type, skip silently
        pass
    return node_props


def capture_node_defaults(node: bpy.types.Node) -> dict:
    def capture_defaults(node: bpy.types.Node, property_name: str= 'inputs'):
        defaults: Dict[str, object] = {}
        try:
            for sock in getattr(node, property_name, []):
                if sock.enabled and hasattr(sock, 'default_value'):
                    try:
                        val = sock.default_value
                        # Convert vector/color/array types to tuple for safe storage
                        try:
                            # Avoid treating scalars as iterables
                            if isinstance(val, (str, bytes)):
                                defaults[sock.name] = val
                            else:
                                iter(val)
                                defaults[sock.name] = tuple(val)
                        except TypeError:
                            defaults[sock.name] = val
                    except Exception as e:
                        # print(f"Warning: Could not set default value for input '{sock.name}' to '{val}'. Error: {e}")
                        pass
        except Exception as e:
            # print(f"Warning: Could not capture node defaults for '{node.name}'. Error: {e}")
            pass
        return defaults
        
    input_defaults = capture_defaults(node, 'inputs')
    output_defaults = capture_defaults(node, 'outputs')
    return input_defaults, output_defaults


def capture_node_state(node: bpy.types.Node) -> dict:
    node_props = capture_node_properties(node)
    input_defaults, output_defaults = capture_node_defaults(node)
    return {
            'properties': node_props,
            'inputs': input_defaults,
            'outputs': output_defaults,
        }


def apply_node_properties(node: bpy.types.Node, properties: dict) -> None:
    for pid, value in properties.items():
        # try:
            if pid == "color_ramp":
                elements = node.color_ramp.elements
                desired_count = len(value)
                # Ensure we never go below 1 element in the ramp
                target_count = max(1, desired_count)

                # Add missing elements (only if necessary)
                while len(elements) < target_count:
                    if desired_count > 0 and len(elements) < desired_count:
                        # Create at the desired position for the new element
                        _, _, new_pos = value[len(elements)]
                        elements.new(new_pos)
                    else:
                        # Fallback: create at end
                        elements.new(1.0)

                # Remove extra elements (only if necessary), keep at least one
                while len(elements) > target_count:
                    try:
                        elements.remove(elements[-1])
                    except Exception as e:
                        print(f"Warning: Could not remove extra color ramp element for '{node.name}'. Error: {e}")
                        break

                # Apply desired values if provided
                if desired_count > 0:
                    # Work on stable references to avoid index changes while adjusting positions
                    element_refs = list(elements)
                    apply_count = min(len(element_refs), desired_count)
                    for i in range(apply_count):
                        color, alpha, position = value[i]
                        element_refs[i].color = color
                        element_refs[i].alpha = alpha
                        element_refs[i].position = position
            else:
                if hasattr(node, pid):
                    setattr(node, pid, value)
        # except Exception as e:
        #     # pass
        #     print(f"Warning: Could not apply property '{pid}' for '{node.name}'. Error: {e}")


def apply_node_defaults(node: bpy.types.Node, defaults: dict, outputs: dict) -> None:
    for input_name, value in defaults.items():
        try:
            if input_name in node.inputs and hasattr(node.inputs[input_name], 'default_value') and value != node.inputs[input_name].default_value:
                node.inputs[input_name].default_value = value
                # print(f"Applied input '{input_name}' for '{node.name}'")
        except Exception as e:
            pass
            # print(f"Warning: Could not apply input '{input_name}' for '{node.name}'. Error: {e}")
    for output_name, value in outputs.items():
        try:
            if output_name in node.outputs and hasattr(node.outputs[output_name], 'default_value') and value != node.outputs[output_name].default_value:
                node.outputs[output_name].default_value = value
                # print(f"Applied output '{output_name}' for '{node.name}'")
        except Exception as e:
            pass
            # print(f"Warning: Could not apply output '{output_name}' for '{node.name}'. Error: {e}")


def apply_node_state(node: bpy.types.Node, state: dict) -> None:
    apply_node_properties(node, state['properties'])
    apply_node_defaults(node, state['inputs'], state['outputs'])


def get_nodetree_version(node_tree: bpy.types.NodeTree) -> int:
    if not node_tree:
        return 0
    version_frame = node_tree.nodes.get("versioning")
    if version_frame:
        return int(version_frame.label)
    return 0

@dataclass
class Edge:
    """
    Represents a connection (edge) between two nodes in the node graph.

    Attributes:
        source (str): The name of the source node.
        target (str): The name of the target node.
        source_socket (str or int): The output socket on the source node.
        target_socket (str or int): The input socket on the target node.
    """
    source: str
    target: str
    source_socket: Union[str, int] = "Default"
    target_socket: Union[str, int] = "Default"


@dataclass
class Add_Node:
    """
    Represents a node to be added to the node graph.
    Attributes:
        identifier (str): A unique name for the node, used to refer to it in connections.
        node_type (str): The Blender identifier for the node type (e.g., 'ShaderNodeTexNoise').
        properties (dict, optional): A dictionary of properties to set on the node after creation.
    """
    identifier: str
    node_type: str
    properties: dict = None
    default_values: dict = None  # Default values for input sockets, if any
    default_outputs: dict = None  # Default values for output sockets, if any
    force_properties: bool = False
    force_default_values: bool = False
    forced_properties: set = field(default_factory=set)  # Set of property names that should be forced (from .force suffix)

@dataclass
class LayerInfo:
    """
    Represents a layer of nodes in the node graph.
    Attributes:
        name (str): The name of the layer.
        nodes (List[str]): A list of node names in this layer.
    """
    width: float = 0
    height: float = 0
    nodes: List[str] = field(default_factory=list)


class NodeTreeBuilder:
    """
    A class to construct Blender node trees in a declarative, graph-based manner.

    This class allows you to define a node graph by adding named nodes and
    specifying the edges (links) between them, similar to libraries like LangGraph.
    Once the graph is defined, the `compile` method builds the actual node tree.
    """

    def __init__(self, node_tree: bpy.types.NodeTree, frame_name, frame_color: Sequence[float] = None, adjustable: bool = False, clear: bool = False, node_width: int = 140, verbose: bool = False, version: int = 1):
        """
        Initializes the NodeTreeBuilder.

        Args:
            node_tree (bpy.types.NodeTree): The node tree to build upon (e.g., material.node_tree).
            frame_name (str, optional): The name of the frame. Defaults to None.
            clear (bool): If True, clears the existing nodes in the tree except for the output node.
            node_width (int): The width of the nodes when arranged in the graph.
        """
        if not node_tree:
            raise ValueError("A valid node_tree must be provided.")

        self._id = str(uuid4())  # Unique identifier for this graph instance
        self.version: int = version
        self.tree = node_tree
        self.node_width: float = node_width
        self.adjustable: bool = adjustable
        self.verbose: bool = verbose
        # Stores nodes added by the user, mapping name -> bpy.types.Node
        self.nodes: Dict[str, bpy.types.Node] = {}
        # Stores commands to add nodes
        self.__add_nodes_commands: Dict[str, Add_Node] = {}
        self.edges: List[Edge] = []  # Stores the connections to be made
        # Find or create a unique frame by label if provided; otherwise create a fresh frame
        self.frame, created = self._find_or_create_frame(frame_name, frame_color)
        self.compiled = not created  # Flag to indicate if the graph has been compiled
        self.sub_graphs: Set['NodeTreeBuilder'] = set()  # List of subgraphs if any
        self.width = 0 # Width of the graph
        self.node_links = []
        self.node_offset = Vector((0, 0))
        
        self.__min_x_pos = 0
        self.__max_x_pos = 0
        
        # Hydrate existing nodes under this frame into the builder map for reuse
        self._hydrate_existing_nodes_from_frame()

        if clear:
            self.clear_tree()

        # --- Identify the final output node ---
        # This node will be our 'END' point.
        
    def __str__(self):
        return self.frame.name

    def _find_frames_by_label(self, label: str) -> List[bpy.types.Node]:
        if not label:
            return []
        return [n for n in self.tree.nodes if getattr(n, 'type', '') == 'FRAME' and getattr(n, 'label', '') == label]

    def _log(self, message: str) -> None:
        if self.verbose:
            print(self.frame.label, message)

    def _find_or_create_frame(self, frame_name: str, frame_color: Optional[Sequence[float]]) -> bpy.types.Node:
        """Find an existing frame by label or create a new one.

        Ensures that the frame has a persistent graph id stored as a custom property 'ps_graph_id'.
        """
        existing_frame = None
        created = False
        if frame_name:
            matches = self._find_frames_by_label(frame_name)
            if matches:
                existing_frame = matches[0]
        if existing_frame is None:
            existing_frame = self.tree.nodes.new(type='NodeFrame')
            created = True
            if frame_name:
                existing_frame.label = frame_name
        # Ensure persistent id on the frame
        try:
            frame_graph_id = existing_frame.get('ps_graph_id')
            if frame_graph_id:
                # Reuse graph id for stability across sessions
                self._id = frame_graph_id
            else:
                existing_frame['ps_graph_id'] = self._id
        except Exception:
            pass

        # Name: keep Blender's internal name unless this is freshly created without label
        if created and not frame_name:
            existing_frame.name = self._id

        # Color behavior: apply if provided
        if frame_color:
            try:
                existing_frame.use_custom_color = True
                existing_frame.color = Color(frame_color)
            except Exception:
                pass

        return existing_frame, created

    def _hydrate_existing_nodes_from_frame(self) -> None:
        """Populate self.nodes with all nodes currently parented to this frame for reuse."""
        start_time_hydrate = time.time()
        if not self.compiled:
            self._log("Graph is not compiled. Skipping hydrating existing nodes from frame")
            return
        
        self._log("Hydrating existing nodes from frame")
        for node in self.tree.nodes:
            if getattr(node, 'parent', None) == self.frame and node.type != 'FRAME':
                self._log(f"Hydrating node: {node.name}")
                identifier = self.get_node_identifier(node)
                self.nodes[identifier] = node
                identifier = self.get_node_identifier(node)
                # If the graph is adjustable, add all nodes in the frame to add commands which can be overridden with add_node commands
                if self.adjustable:
                    self.add_node(identifier, node.bl_idname)
                    
                    for input in node.inputs:
                        if input.is_linked:
                            for link in input.links:
                                if link.from_node.parent == self.frame:
                                    self.link(self.get_node_identifier(link.from_node), identifier, link.from_socket, input, force=True)
                    for output in node.outputs:
                        if output.is_linked:
                            for link in output.links:
                                if link.to_node.parent == self.frame:
                                    self.link(identifier, self.get_node_identifier(link.to_node), output, link.to_socket, force=True)
        # self.tree.links.new
        self._log(f"Time taken to hydrate existing nodes from frame: {time.time() - start_time_hydrate} seconds")
        # self._arrange_nodes()
        

    def clear_tree(self, clean: bool = False):
        """Clears the node tree, removing nodes and links created by this builder.
        Args:
            clean (bool): If True, removes all nodes including the START and END node.
                          If False, keeps the START and END node intact.
        """
        
        try:
            for link in self.node_links:
                # if link in self.tree.links:   
                    self.tree.links.remove(link)
        except Exception as e:
            self._log(f"Error removing links: {e}")
        finally:
            # Always reset local link tracking so we don't try to remove stale links later
            self.node_links = []
            
        for node_name in list(self.nodes.keys()):
            node = self.nodes[node_name]
            if isinstance(node, NodeTreeBuilder):
                node.compile()
                continue
            if node.type == 'REROUTE' and (node.name.startswith(START) or node.name.startswith(END)):
                # Keep START and END nodes if clean is False
                if not clean:
                    continue
            self.tree.nodes.remove(node)
            del self.nodes[node_name]

        if clean:
            for idx, edge in enumerate(self.edges):
                if edge.source.startswith(START):
                    self.edges[idx].source = START
                if edge.target.startswith(END):
                    self.edges[idx].target = END
            self.tree.nodes.remove(self.frame)
            self.frame = None
        
        self.compiled = False  # Reset compiled state

    def add_node(self, identifier: str, node_type: str, properties: dict = None, default_values: dict = None, default_outputs: dict = None, force_properties: bool = False, force_default_values: bool = False) -> Add_Node:
        # Store the command to add a node
        """
        Adds a node to the graph definition.

        Args:
            identifier (str): A unique name for the node, used to refer to it in connections.
            node_type (str): The Blender identifier for the node (e.g., 'ShaderNodeTexNoise').
            properties (dict, optional): A dictionary of properties to set on the node after creation.
                                         For example: {'noise_dimensions': '4D'}. Defaults to None.
            default_values (dict, optional): A dictionary of default values to set on the node after creation.
                                            For example: {'noise_dimensions': '4D'}. Defaults to None.
            default_outputs (dict, optional): A dictionary of default outputs to set on the node after creation.
                                            For example: {'noise_dimensions': '4D'}. Defaults to None.
            force_properties (bool, optional): If True, the properties will be overridden after recompiling.
                                            Defaults to False.
            force_default_values (bool, optional): If True, the default values will be overridden after recompiling.
                                            Defaults to False.

        Returns:
            The created Blender node object.
        """
        if identifier in self.nodes and not self.compiled:
            raise ValueError(
                f"Node with identifier '{identifier}' already exists. Use a unique identifier.")
        
        if "." in identifier:
            raise ValueError(f"Identifier '{identifier}' cannot contain a dot (.).")

        if self.adjustable and self.compiled:
            self._log(f"Graph is adjustable but already compiled. Skipping node '{identifier}'")
            return
        
        # Process properties with .force suffix
        forced_properties = set()
        processed_properties = {}
        if properties:
            for key, value in properties.items():
                if key.endswith('.force'):
                    # Remove .force suffix and add to forced_properties set
                    prop_name = key[:-6]  # Remove '.force' suffix
                    forced_properties.add(prop_name)
                    processed_properties[prop_name] = value
                else:
                    processed_properties[key] = value
        else:
            processed_properties = properties
        
        self._log(f"Adding node '{identifier}' of type '{node_type}' with properties '{processed_properties}' and default values '{default_values}'")
        add_command = Add_Node(
            identifier=identifier, node_type=node_type, properties=processed_properties, default_values=default_values, default_outputs=default_outputs, force_properties=force_properties, force_default_values=force_default_values, forced_properties=forced_properties)
        
        self.__add_nodes_commands[identifier] = add_command
        return add_command
    
    def find_node(self, identifier: str) -> bpy.types.Node:
        # Check the add_nodes_commands for the node
        if identifier in self.__add_nodes_commands:
            return self.__add_nodes_commands[identifier]
        return None
    
    def get_unique_identifier(self, identifier: str, counter = 0) -> str:
        # Check the add_nodes_commands for the node
        check_identifier = identifier if counter == 0 else f"{identifier}_{counter}"
        node = self.find_node(check_identifier)
        if node is not None:
            return self.get_unique_identifier(identifier, counter + 1)
        return check_identifier

    def _create_node(self, identifier: str, node_type: str, properties: dict = None, default_values: dict = None, default_outputs: dict = None, force_properties: bool = False, force_default_values: bool = False) -> None:
        """
        Creates a node in the graph.

        Args:
            node_type (str): The Blender identifier for the node (e.g., 'ShaderNodeTexNoise').
            properties (dict, optional): A dictionary of properties to set on the node after creation.
                                         For example: {'noise_dimensions': '4D'}. Defaults to None.
            default_outputs (dict, optional): A dictionary of default outputs to set on the node after creation.
                                            For example: {'noise_dimensions': '4D'}. Defaults to None.
            force_properties (bool, optional): If True, the properties will be overridden after recompiling.
                                            Defaults to False.
            force_default_values (bool, optional): If True, the default values will be overridden after recompiling.
                                            Defaults to False.

        Returns:
            The created Blender node object.
        """
        existing = next((node for node in self.nodes.values() if self.get_node_identifier(node) == identifier), None)
        node = None
        if existing is not None and getattr(existing, 'bl_idname', None) == node_type:
            node = existing
            # Ensure correct parenting and width
            try:
                node.parent = self.frame
                node.width = self.node_width
            except Exception:
                pass
            # Ensure identifier custom property is set/updated
            try:
                node.label = identifier
            except Exception:
                pass
        else:
            # If an existing node with same name but different type exists, replace it
            if existing is not None:
                try:
                    self.tree.nodes.remove(existing)
                except Exception:
                    pass
            node = self.tree.nodes.new(type=node_type)
            node.parent = self.frame  # Set the parent frame for organization
            node.width = self.node_width
            # Persist identifier on the node as a custom property
            try:
                node.label = identifier
            except Exception:
                pass
            self.nodes[identifier] = node

        # Set custom properties if provided
        if properties:
            for key, value in properties.items():
                if hasattr(node, key):
                    setattr(node, key, value)
                else:
                    self._log(
                        f"Warning: Property '{key}' not found on node type '{node_type}'")
        
        # --- Set Input Default Values ---
        # If a default_values dictionary is provided, iterate through it
        if default_values:
            for input_name, value in default_values.items():
                # Check if the input socket exists on the node
                # if input_name in node.inputs:
                try:
                    node.inputs[input_name].default_value = value
                except Exception as e:
                    self._log(f"Warning: Could not set default value for input '{input_name}' to '{value}'. Error: {e}")
                # else:
                #     self._log(f"Warning: Input socket '{input_name}' not found on node type '{node_type}'.")
                
        if default_outputs:
            for output_name, value in default_outputs.items():
                try:
                    node.outputs[output_name].default_value = value
                except Exception as e:
                    self._log(f"Warning: Could not set default value for output '{output_name}' to '{value}'. Error: {e}")

    def link(
        self,
        source: Union[str, 'NodeTreeBuilder'],
        target: Union[str, 'NodeTreeBuilder'],
        source_socket: Optional[Union[bpy.types.NodeSocket, str, int]] = None,
        target_socket: Optional[Union[bpy.types.NodeSocket, str, int]] = None,
        force: bool = False
    ) -> None:
        """
        Defines an edge (link) between two nodes or subgraphs.

        The connection is stored and will be created when `compile()` is called.

        Args:
            source (str | NodeTreeBuilder): Source node identifier. Can be START or a subgraph.
            target (str | NodeTreeBuilder): Target node identifier. Can be END or a subgraph.
            source_socket (Socket | str | int | None): Output socket name or index on the source. If None or "Default",
                                              the first output socket will be used.
            target_socket (Socket | str | int | None): Input socket name or index on the target. If None or "Default",
                                              the first input socket will be used.
            force (bool): If True, the link will be added even if the graph is adjustable and already compiled.
        """
        
        if self.adjustable and self.compiled and not force:
            self._log(f"Graph is adjustable but already compiled. Skipping link '{source}' to '{target}'")
            if isinstance(source, NodeTreeBuilder):
                self.nodes[str(source)] = source
                self.sub_graphs.add(source)
            if isinstance(target, NodeTreeBuilder):
                self.nodes[str(target)] = target
                self.sub_graphs.add(target)
            return
        
        # Check if the source and target are valid
        if isinstance(source, NodeTreeBuilder):
            self.nodes[str(source)] = source
            self.sub_graphs.add(source)
        elif isinstance(source, str):
            if source == END:
                raise ValueError(
                    "Cannot connect from END. END is a conceptual exit point, not a node.")
            if source == START:
                # Find the START node
                node, socket = self._get_socket_by_prefix(True, source_socket)
                source = self.get_node_identifier(node)
        else:
            raise ValueError(
                "Source must be a NodeTreeBuilder instance or a string representing a node name.")

        if isinstance(target, NodeTreeBuilder):
            self.nodes[str(target)] = target
            self.sub_graphs.add(target)
        elif isinstance(target, str):
            if target == START:
                raise ValueError(
                    "Cannot connect to START. START is a conceptual entry point, not a node.")
            if target == END:
                # Find the END node
                node, socket = self._get_socket_by_prefix(False, target_socket)
                target = self.get_node_identifier(node)
        else:
            raise ValueError(
                "Target must be a NodeTreeBuilder instance or a string representing a node name.")

        self.edges.append(Edge(source, target, source_socket, target_socket))
        self._log(f"Added link: {source} -> {target}")
        
    def unlink(self, source: str, target: str) -> None:
        """
        Removes a link between two nodes.

        Args:
            source (str): The name of the source node.
            target (str): The name of the target node.
        """
        if self.adjustable and self.compiled:
            self._log(f"Graph is adjustable but already compiled. Skipping unlink '{source}' to '{target}'")
            return
        
        # Find the edge to remove
        edge_to_remove = None
        for edge in self.edges:
            if edge.source == source and edge.target == target:
                edge_to_remove = edge
                break
        
        if edge_to_remove:
            self.edges.remove(edge_to_remove)
        else:
            self._log(f"No link found between '{source}' and '{target}'.")
        
    def _get_socket_by_prefix(
        self,
        is_input_socket: bool,
        socket_name: str
    ) -> Union[tuple[bpy.types.Node, bpy.types.NodeSocket], tuple[None, None]]:
        """
        Helper function to find a node and socket based on a name prefix.

        Args:
            is_input (bool): If True, searches in outputs (START nodes), otherwise in inputs (END nodes).
            socket_name (str): The name of the socket to find.

        Returns:
            bpy.types.Node, bpy.types.NodeSocket: The node and socket if found, otherwise None.
        """
        prefix = START if is_input_socket else END
        for node in self.nodes.values():
            if node.type != 'REROUTE':
                continue
            socket = node.inputs[0] if is_input_socket else node.outputs[0]
            identifier = node.get("identifier", None)
            if identifier is not None and identifier.startswith(f"{prefix}{socket_name}"):
                return node, socket
        return None, None

    def get_output(self, output_name: str) -> Tuple[bpy.types.Node, bpy.types.NodeSocket]:
        """
        Retrieves an output node and socket based on the output name.

        Args:
            nodetree_builder (NodeTreeBuilder): The NodeTreeBuilder instance to search in.
            output_name (str): The name of the output to find.

        Returns:
            Tuple[bpy.types.Node, bpy.types.NodeSocket]: The output node and socket.

        Raises:
            ValueError: If no output node or socket is found for the given name.
        """
        node, sock = self._get_socket_by_prefix(False, output_name)
        if node is None:
            raise ValueError(f"{self.frame.name} No output node found for '{output_name}'. Ensure it is connected to END.")
        if sock is None:
            raise ValueError(f"{self.frame.name} No output socket found for '{output_name}' on node '{node.name}'.")
        return node, sock
    
    def get_input(self, input_name: str) -> Tuple[bpy.types.Node, bpy.types.NodeSocket]:
        """
        Retrieves an input node and socket based on the input name.

        Args:
            nodetree_builder (NodeTreeBuilder): The NodeTreeBuilder instance to search in.
            input_name (str): The name of the input to find.

        Returns:
            Tuple[bpy.types.Node, bpy.types.NodeSocket]: The input node and socket.

        Raises:
            ValueError: If no input node or socket is found for the given name.
        """
        node, sock = self._get_socket_by_prefix(True, input_name)
        if node is None:
            raise ValueError(f"No input node found for '{input_name}'. Ensure it is connected to START.")
        if sock is None:
            raise ValueError(f"No input socket found for '{input_name}' on node '{node.name}'.")
        return node, sock

    def _create_reroute_node(self, socket_name: str, is_input_socket: bool) -> tuple:
        """
        Creates a NodeReroute node, sets its name, label, and parent.
        It also configures the relevant input/output socket and updates the edge
        to point to this newly created reroute node.
        
        Args:
            prefix (str): "START" or "END" to form the node name.
            socket_name (str): The name to assign to the reroute node's socket.
            is_input_socket (bool): True if creating an input reroute (for END),
                                     False if creating an output reroute (for START).
            
        Returns:
            tuple: A tuple containing the created reroute node and its configured socket.
        """
        prefix = END if is_input_socket else START
        reroute_node = self.tree.nodes.new(type='NodeReroute')
        identifier = f"{prefix}{socket_name}"
        reroute_node.name = identifier
        reroute_node.label = identifier
        reroute_node.parent = self.frame
        # Persist identifier on the reroute node as well for consistency
        # try:
        #     reroute_node["identifier"] = identifier
        # except Exception:
        #     pass

        if is_input_socket:
            sock = reroute_node.inputs[0]
        else:
            sock = reroute_node.outputs[0]
            
        sock.name = socket_name # Name the reroute socket
        return reroute_node, sock

    def _resolve_node_and_socket(
        self,
        identifier: Union[str, 'NodeTreeBuilder'],
        socket: Optional[Union[bpy.types.NodeSocket, str, int]],
        is_source: bool,
        edge_idx: int
    ) -> tuple:
        """
        Resolves a node and its specific socket based on the identifier provided in an edge.
        This function handles:
        1. Nested NodeTreeBuilder instances (compiles them if necessary).
        2. Special 'START'/'END' keywords by creating Reroute nodes.
        3. Existing nodes identified by their name string.
        
        Args:
            identifier: The value from `edge.source` or `edge.target` (can be a string or NodeTreeBuilder instance).
            socket (Socket | str | int | None): The socket spec to find (name, index, or None/"Default").
            is_source (bool): True if resolving a source node (looking for an output socket),
                              False if resolving a target node (looking for an input socket).
            edge_idx (int): The index of the current edge in `self.edges`, used to update `edge.source`/`edge.target`
                            if a new reroute node is created.

        Returns:
            tuple: A tuple containing the resolved node object and its corresponding socket object.
        
        Raises:
            ValueError: If a node is not found or a specified socket does not exist on the node.
        """
        node = None
        sock = None
        
        if isinstance(identifier, NodeTreeBuilder):
            # Handle nested NodeTreeBuilder instances
            if not identifier.compiled:
                identifier.compile()
            identifier.frame.parent = self.frame # Ensure nested graph's frame is parented correctly
            
            # If explicit socket name provided, use it. Otherwise, pick the first available reroute.
            if socket not in (None, "Default"):
                if is_source:
                    node, sock = identifier.get_output(str(socket))
                else:
                    node, sock = identifier.get_input(str(socket))
            else:
                if is_source:
                    # Outputs of a subgraph are its END_* reroutes; pick the first
                    for maybe_node in identifier.nodes.values():
                        if getattr(maybe_node, 'type', None) == 'REROUTE' and maybe_node.name.startswith(END):
                            node = maybe_node
                            sock = maybe_node.outputs[0]
                            break
                else:
                    # Inputs of a subgraph are its START_* reroutes; pick the first
                    for maybe_node in identifier.nodes.values():
                        if getattr(maybe_node, 'type', None) == 'REROUTE' and maybe_node.name.startswith(START):
                            node = maybe_node
                            sock = maybe_node.inputs[0]
                            break
        
        elif isinstance(identifier, str):
            # Handle special START/END keywords
            if is_source and identifier == START:
                # Try to find node by prefix and create a reroute node if not found
                # node, sock = self._get_socket_by_prefix(False, socket_name)
                node = next((node for node in self.nodes.values() if node.get("identifier", None).startswith(f"{START}{socket}")), None)
                if not node:
                    node, sock = self._create_reroute_node(socket, False)
                else:
                    sock = node.outputs[0]
                self.nodes[node.name] = node # Store the new node
                self.edges[edge_idx].source = node.name # Update edge source
            elif not is_source and identifier == END:
                # Try to find node by prefix and create a reroute node if not found
                node = next((node for node in self.nodes.values() if node.get("identifier", None).startswith(f"{END}{socket}")), None)
                if not node:
                    node, sock = self._create_reroute_node(socket, True)
                else:
                    sock = node.inputs[0]
                self.nodes[node.name] = node # Store the new node
                self.edges[edge_idx].target = node.name # Update edge target
            else:
                # Assume it's the name of an existing node
                node = self.nodes.get(identifier)
                if node is None:
                    self._log(str(self.nodes))
                    raise ValueError(f"{self.frame.label} Node '{identifier}' not found in the current tree's nodes.")

                # Retrieve the socket based on node type
                if node.type != 'REROUTE':
                    # For most nodes, select socket by name/index or default to first
                    sockets = node.outputs if is_source else node.inputs
                    if isinstance(socket, bpy.types.NodeSocket):
                        sock = socket
                    else:
                        sock = self._select_socket_from_spec(sockets, socket)
                else:
                    # Reroute nodes typically have only one input and one output socket
                    if is_source:
                        sock = node.outputs[0]
                    else:
                        sock = node.inputs[0]

        # Final check if a socket was successfully found
        if sock is None:
            node_name = getattr(node, 'name', 'Unknown Node') # Safe access to node name
            socket_type_str = "output" if is_source else "input"
            raise ValueError(
                f"Required {socket_type_str} socket '{socket}' not found on node '{node_name}' (type: {getattr(node, 'type', 'Unknown')})."
            )
        
        return node, sock

    def _select_socket_from_spec(
        self,
        sockets,
        spec: Optional[Union[str, int]],
    ) -> Optional[bpy.types.NodeSocket]:
        """Select a socket from a node's inputs/outputs collection.

        - If spec is None or "Default": return the first socket if available
        - If spec is int: return by index (supports negative indices)
        - If spec is str: return by case-sensitive name, then try case-insensitive match
        """
        try:
            length = len(sockets)
        except Exception:
            length = 0

        if spec in (None, "Default"):
            return sockets[0] if length > 0 else None   

        if isinstance(spec, int):
            # Support negative indices just like standard Python sequences
            if -length <= spec < length:
                return sockets[spec]
            return None

        if isinstance(spec, str):
            # Direct lookup if available on Blender collections
            direct = getattr(sockets, 'get', lambda _name: None)(spec)
            if direct is not None:
                return direct
            # Fallback: case-insensitive name match
            for candidate in sockets:
                if getattr(candidate, 'name', '').lower() == spec.lower():
                    return candidate
        return None

    def get_node_identifier(self, node: bpy.types.Node) -> str:
        """
        Get the identifier of a node.
        """
        try:
            # Prefer custom identifier property when available
            getter = getattr(node, 'get', None)
            if callable(getter):
                ident = node.label
                if ident is not None:
                    return ident
        except Exception as e:
            self._log(f"Exception getting node identifier: {node}, {e}")
            pass
        # Fallback to Blender internal name
        return getattr(node, 'name', '')
    
    def _remove_unused_nodes(self) -> None:
        """Remove nodes that are not connected to any other nodes."""
        used_node_identifiers = self.__add_nodes_commands.keys()
        to_remove = set()
        for node in self.nodes.values():
            node_identifier = self.get_node_identifier(node)
            bl_idname = node.bl_idname
            desired_bl_idname = self.__add_nodes_commands[node_identifier].node_type if node_identifier in self.__add_nodes_commands else None # Ensure deletion of nodes that are not in add commands
            if self.adjustable:
                # Check only nodes in add commands
                if node_identifier not in used_node_identifiers:
                    continue
                if node not in to_remove and node.type != 'REROUTE' and bl_idname != desired_bl_idname:
                    to_remove.add(node)
            else:
                if node not in to_remove and node.type != 'REROUTE' and (node_identifier not in used_node_identifiers or bl_idname != desired_bl_idname):
                    to_remove.add(node)
        for node in to_remove:
            del self.nodes[self.get_node_identifier(node)]
            self.tree.nodes.remove(node)

    # @timing_decorator("Node Tree Compilation")
    def compile(self, arrange_nodes: bool = True) -> 'NodeTreeBuilder':
        """
        Builds the node tree by creating all the defined links and arranging the nodes.
        """
            
        self._log(f"Compiling graph {self.frame.label}")
        # Remove unused nodes
        self._remove_unused_nodes()
        # Capture current node state so we can restore user-changed values on recompilation
        saved_state: Dict[str, dict] = {}
        if self.compiled:
            saved_state = self._capture_node_states()
            self._log("Graph already compiled. Recompiling...")
            # for subgraph in self.sub_graphs:
            #     subgraph.compile()
            # if not self.adjustable:
            #     self.clear_tree()  # Clear existing nodes and links
            self.compiled = False
        
        # Reset link tracking for a fresh build
        self.node_links = []

        # Add all pre-defined nodes to the tree
        self._log("Adding nodes to the tree")
        start_time_add_nodes = time.time()
        for identifier, command in self.__add_nodes_commands.items():
            self._create_node(identifier, command.node_type, command.properties, command.default_values, command.default_outputs)
        self._log(f"Time taken to add nodes: {time.time() - start_time_add_nodes} seconds")

        # Re-apply previously captured state (node-level props and input defaults)
        if saved_state:
            self._apply_node_states(saved_state)

        # --- Create the links between nodes ---
        # Remove existing links touching any node in this frame to avoid duplicates
        self._remove_existing_links_in_frame()
        # self._log("Linking edges")
        start_time_link_edges = time.time()
        for idx, edge in enumerate(self.edges):
            self._log(f"Linking edge {idx + 1}: {edge.source} -> {edge.target}")
            # Resolve the source node and its specific output socket
            source_node, source_sock = self._resolve_node_and_socket(
                edge.source, edge.source_socket, is_source=True, edge_idx=idx
            )
            
            # Resolve the target node and its specific input socket
            target_node, target_sock = self._resolve_node_and_socket(
                edge.target, edge.target_socket, is_source=False, edge_idx=idx
            )
            # Create the link between the resolved source and target sockets
            self.node_links.append(connect_sockets(source_sock, target_sock))
            # self._log(f"Linked edge {idx + 1}/{len(self.edges)}")
        self._log(f"Time taken to link edges: {time.time() - start_time_link_edges} seconds")
        # --- Arrange nodes for clarity (simple horizontal layout) ---
        self._log("Arranging nodes")
        start_time_arrange_nodes = time.time()
        if arrange_nodes:
            self._arrange_nodes()
            
        # Create version frame
        if "versioning" not in self.tree.nodes:
            version_frame = self.tree.nodes.new(type='NodeFrame')
            version_frame.name = "versioning"
            version_frame.label = str(self.version)
            version_frame.location = Vector((200, 0))
        else:
            self.tree.nodes["versioning"].label = str(self.version)
        self._log(f"Time taken to arrange nodes: {time.time() - start_time_arrange_nodes} seconds")
        self._log("Updating node tree")
        self.compiled = True
        self.frame.width = self.width
        self._log(f"Compiled graph {self.frame.label}")
        self._log("-----------------------------------")
        return self

    def _remove_existing_links_in_frame(self) -> None:
        """Remove links where either end belongs to a node parented to this frame."""
        self._log(f"Removing existing links in frame {self.frame.label}")
        nodes_in_frame = {node for node in self.tree.nodes if getattr(node, 'parent', None) == self.frame}
        if not nodes_in_frame:
            return
        try:
            # Copy list to avoid mutating during iteration
            for link in list(self.tree.links):
                from_node = getattr(getattr(link, 'from_socket', None), 'node', None)
                to_node = getattr(getattr(link, 'to_socket', None), 'node', None)
                if from_node in nodes_in_frame or to_node in nodes_in_frame:
                    self.tree.links.remove(link)
        except Exception:
            pass

    def _capture_node_states(self) -> Dict[str, dict]:
        """Capture non-readonly node properties and input socket default values.

        Returns a mapping: identifier -> { 'properties': {...}, 'inputs': {...} }
        """
        self._log("Capturing node state")
        captured: Dict[str, dict] = {}
        for identifier, node in list(self.nodes.items()):
            # Skip subgraphs and special reroutes
            if isinstance(node, NodeTreeBuilder):
                continue
            if getattr(node, 'type', None) == 'REROUTE' and (
                str(getattr(node, 'name', '')).startswith(START) or str(getattr(node, 'name', '')).startswith(END)
            ):
                continue

            captured[identifier] = capture_node_state(node)
        self._log("Captured node state")
        self._log(captured)
        return captured

    def _apply_node_states(self, saved_state: Dict[str, dict]) -> None:
        """Apply captured properties and input defaults to current nodes by identifier."""
        self._log("Applying node state")
        for identifier, state in saved_state.items():
            node = next((n for n in self.nodes.values() if self.get_node_identifier(n) == identifier.split('.')[0]), None)
            if node is None or isinstance(node, NodeTreeBuilder):
                self._log(f"Skipping node {identifier}")
                continue
            
            # Get the add command for this node
            add_command = self.__add_nodes_commands.get(identifier)
            if add_command is None:
                continue
            
            # Filter out forced properties (either from force_properties flag or forced_properties set)
            properties_to_apply = {}
            if not add_command.force_properties:
                # If force_properties is False, apply all properties except those in forced_properties set
                properties_to_apply = {
                    key: value for key, value in state['properties'].items()
                    if key not in add_command.forced_properties
                }
            # If force_properties is True, don't apply any properties (existing behavior)
            
            if properties_to_apply:
                apply_node_properties(node, properties_to_apply)

            # Ignore if the node is force_default_values
            # Find node in __add_nodes_commands
            if not add_command.force_default_values:
                apply_node_defaults(node, state['inputs'], state['outputs'])
        self._log("Applied node state")

    def _arrange_nodes(self):
        """A simple node arrangement algorithm."""

        # Reset layout bounds before computing positions
        self.__min_x_pos = 0
        self.__max_x_pos = 0

        # --- 1. Determine End Nodes by Analyzing Connections ---
        # An "end node" is any node within the graph that does not serve as a
        # source for any defined edge. These are the leaves of the graph.
        source_node_names = {str(edge.source) for edge in self.edges}
        self._log(f"Source nodes: {source_node_names}")
        
        end_node_names = [name for name in self.nodes if name not in source_node_names]
        
        self._log(f"End nodes: {end_node_names}")
        
        # --- 2. Calculate Node Levels with a Backwards Traversal ---
        # We traverse from the end nodes (level 0) backwards. A node's level is
        # its longest path distance from an end node.
        level_map: dict[str, int] = {}  # Stores {node_name: level}
        nodes_to_process = []
        
        for name in end_node_names:
            if name not in level_map:
                level_map[name] = 0
                nodes_to_process.append(name)
                
        layer_infos: Dict[int, LayerInfo] = {}
        
        while nodes_to_process:
            self._log(f"Processing nodes: {nodes_to_process}")
            current_node_name = nodes_to_process.pop(0)
            current_level = level_map[current_node_name]

            # Find nodes that connect to the current node
            for edge in self.edges:
                if str(edge.target) == current_node_name:
                    source_node_name = str(edge.source)
                    level_map[source_node_name] = max(
                        current_level + 1, level_map.get(source_node_name, 1))
                    if source_node_name not in nodes_to_process and current_node_name != source_node_name:
                        nodes_to_process.append(source_node_name)
        
        NODE_MARGIN = 20  # Margin between nodes
        
        for name, level in list(level_map.items()):
            if level not in layer_infos:
                layer_infos[level] = LayerInfo()

            matching_subgraph = next((sg for sg in self.sub_graphs if name == str(sg)), None)
            if matching_subgraph is not None:
                layer_infos[level].width = max(layer_infos[level].width, matching_subgraph.width)
            else:
                base_width = 0 if name.startswith(START) or name.startswith(END) else self.node_width
                layer_infos[level].width = max(layer_infos[level].width, base_width)

            layer_infos[level].nodes.append(name)
        
        def calculate_node_position(name: str, node: bpy.types.Node):
            current_level = level_map.get(name, 1)
            current_level_info = layer_infos.get(current_level, LayerInfo())
            x_pos = -1 * (sum(layer_infos[l].width for l in range(current_level) if l in layer_infos) + current_level * NODE_MARGIN)
            y_pos = 200
            if not isinstance(node, NodeTreeBuilder):
                if node.type != "FRAME":
                    x_pos -= current_level_info.width
                if node.type == 'REROUTE':
                    y_pos = current_level_info.height
                    current_level_info.height -= NODE_MARGIN
                else:
                    y_pos = current_level_info.height
                    current_level_info.height -= 200 + NODE_MARGIN
            self.__min_x_pos = min(self.__min_x_pos, x_pos)
            self.__max_x_pos = max(self.__max_x_pos, x_pos + current_level_info.width)
            return x_pos, y_pos
        
        for name, node in self.nodes.items():
            x_pos, y_pos = calculate_node_position(name, node)
            pos = Vector((x_pos, y_pos)) + self.node_offset
            if isinstance(node, NodeTreeBuilder):
                node.set_node_offset(pos, arrange_nodes=True)
            else:
                if hasattr(node, 'location_absolute'):
                    node.location_absolute = pos
                else:
                    node.location = pos
        self.width = self.__max_x_pos - self.__min_x_pos + 35*2
    
    def set_node_offset(self, offset: Vector, arrange_nodes: bool = False):
        """
        Offsets all nodes in the graph by a given vector.

        Args:
            offset (Vector): The offset to apply to each node's location.
        """
        self.node_offset = offset
        if arrange_nodes:
            self._arrange_nodes()  # Re-arrange nodes after setting the offset


# --- Example Usage within a Blender Operator ---

class EXAMPLE_OT_BuildMyNodeTree(bpy.types.Operator):
    """Builds a sample node tree using the NodeTreeBuilder"""
    bl_idname = "object.build_my_node_tree"
    bl_label = "Build Sample Node Tree"

    def execute(self, context):
        # --- 1. Setup: Get or create a material ---
        # material_name = "NodeBuilderMaterial"
        # mat = bpy.data.materials.get(material_name)

        # if mat is None:
        #     mat = bpy.data.materials.new(name=material_name)

        # mat.use_nodes = True
        snode = context.space_data
        group = snode.edit_tree
        node_tree = group if group else context.material.node_tree
        
        # for node in node_tree.nodes:
        #     node_tree.nodes.remove(node)

        # --- 2. Instantiate the builder ---
        graph_builder = NodeTreeBuilder(
            node_tree, frame_name="Sub Graph", frame_color=(0.27083, 0.130401, 0.130401))

        # --- 3. Add Nodes ---
        # The first argument is the unique name we'll use to refer to the node.
        # The second argument is the Blender node type.
        graph_builder.add_node("tex_coord", "ShaderNodeTexCoord")
        graph_builder.add_node("noise_texture", "ShaderNodeTexNoise", properties={
                               'noise_dimensions': '4D'}, default_values={'Scale': 10})
        graph_builder.add_node("color_ramp", "ShaderNodeValToRGB")
        # graph_builder.add_node("color_ramp2", "ShaderNodeValToRGB")
        # graph_builder.add_node("color_ramp3", "ShaderNodeValToRGB")
        graph_builder.add_node("principled_shader", "ShaderNodeBsdfPrincipled")
        graph_builder.add_node("shader_to_rgb", "ShaderNodeShaderToRGB")
        graph_builder.add_node("mix_rgb", "ShaderNodeMix", properties={
                               'blend_type': 'MULTIPLY', 'data_type': 'RGBA'})

        # --- 4. Add Edges (Define the graph flow) ---
        # An edge from START indicates this is an entry point to the graph.
        # graph_builder.add_edge(START, tex_coord)

        # Connect nodes using their unique names. We can specify sockets by name or index.
        # Using "Default" will try to find the first valid connection.
        graph_builder.link("tex_coord", "noise_texture",
                              source_socket="Generated", target_socket="Vector")
        graph_builder.link("noise_texture", "color_ramp",
                              source_socket="Fac", target_socket="Fac")
        # graph_builder.link("noise_texture", "color_ramp2",
        #                       source_socket="Fac", target_socket="Fac")
        graph_builder.link("color_ramp", "principled_shader",
                              source_socket="Color", target_socket="Base Color")
        # graph_builder.link("color_ramp3", "principled_shader",
        #                       source_socket="Color", target_socket="Alpha")
        graph_builder.link("noise_texture", "principled_shader",
                              source_socket="Fac", target_socket="Roughness")
        graph_builder.link("principled_shader", "shader_to_rgb",
                              source_socket="BSDF", target_socket="Shader")
        graph_builder.link("mix_rgb", "noise_texture",
                              source_socket="Result", target_socket="W")

        # An edge to END connects to the final output node.
        graph_builder.link("shader_to_rgb", END,
                              source_socket="Color", target_socket="Color")
        graph_builder.link("shader_to_rgb", END,
                              source_socket="Alpha", target_socket="Alpha")
        graph_builder.link("shader_to_rgb", END,
                              source_socket="Alpha", target_socket="Alpha")

        graph_builder.link(
            START, "mix_rgb", source_socket="Color", target_socket="A")
        graph_builder.link(
            START, "mix_rgb", source_socket="Alpha", target_socket="Factor")
        
        # graph_builder.compile()
        
        graph_builder2 = NodeTreeBuilder(
            node_tree, frame_name="Graph 2", adjustable=True)
        graph_builder2.add_node("mix_rgb", "ShaderNodeMix",
                            properties={'data_type': 'RGBA'})
        graph_builder2.link(
            START, "mix_rgb", source_socket="Color", target_socket="A")
        graph_builder2.link(
            START, "mix_rgb", source_socket="Alpha", target_socket="Factor")
        graph_builder2.link(
            START, "mix_rgb", source_socket="Alpha", target_socket="B")
        graph_builder2.link(
            "mix_rgb", END, source_socket="Result", target_socket="Color")
        
        graph_builder3 = NodeTreeBuilder(
            node_tree, frame_name="Graph 3", adjustable=True)
        graph_builder3.add_node("mix_rgb", "ShaderNodeMix",
                            properties={'data_type': 'RGBA'})
        graph_builder3.add_node("mix_rgb2", "ShaderNodeMix",
                            properties={'data_type': 'RGBA'})
        graph_builder3.link(
            START, "mix_rgb", source_socket="Color", target_socket="A")
        graph_builder3.link(
            "mix_rgb", "mix_rgb2", source_socket="Result", target_socket="A")
        graph_builder3.link(
            "mix_rgb2", END, source_socket="Result", target_socket="Color")

        main_graph = NodeTreeBuilder(node_tree, frame_name="Main Graph")
        main_graph.link(
            graph_builder, graph_builder2, source_socket="Color", target_socket="Color")
        main_graph.link(
            graph_builder, graph_builder2, source_socket="Alpha", target_socket="Alpha")
        main_graph.link(
            graph_builder, graph_builder2, source_socket="Alpha", target_socket="Alpha")
        main_graph.link(
            graph_builder2, graph_builder3, source_socket="Color", target_socket="Color")

        graph_builder.compile()
        main_graph.compile()
        
        
        # # graph_builder.compile()
        # graph_builder.link("color_ramp2", "color_ramp3",
        #                       source_socket="Color", target_socket="Fac")
        # graph_builder2.add_node("mix_rgb2", "ShaderNodeMix",
        #                     properties={'data_type': 'RGBA'})
        # graph_builder2.link(
        #     "mix_rgb", "mix_rgb2", source_socket="Result", target_socket="A")
        # graph_builder2.link(
        #     "mix_rgb2", END, source_socket="Result", target_socket="Color")
        # graph_builder.clear_tree()
        # graph_builder2.clear_tree(True)
        # main_graph.compile()

        self.report({'INFO'}, 'Successfully built the node tree.')
        return {'FINISHED'}


class EXAMPLE_PT_NodeTreeBuilderPanel(bpy.types.Panel):
    """Creates a Panel in the Object properties window"""
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Node Builder"
    bl_label = "Node Tree Builder"
    bl_idname = "NODE_PT_node_tree_builder"

    def draw(self, context):
        layout = self.layout
        layout.operator(EXAMPLE_OT_BuildMyNodeTree.bl_idname,
                        text="Build Sample Node Tree")
        
        active_node = context.active_node
        if active_node and hasattr(active_node, 'name'):
            layout.label(text=f"Active Node: {active_node.name}")
            layout.label(text=f"Node Type: {active_node.bl_idname}"
                           f" ({active_node.type})")
            layout.label(text=f"Node Location: {active_node.location[0]:.2f}, {active_node.location[1]:.2f}")
            layout.label(text=f"Node Location: {active_node.location_absolute[0]:.2f}, {active_node.location_absolute[1]:.2f}")
            layout.prop(active_node, "name", text="Node Name")
            layout.prop(active_node, "width", text="Node Width")
            if active_node.get("identifier", None) is not None:
                layout.label(text=f"Node Identifier: {active_node.get('identifier')}")


classes = (
    EXAMPLE_OT_BuildMyNodeTree,
    EXAMPLE_PT_NodeTreeBuilderPanel,
)

register, unregister = register_classes_factory(classes)
