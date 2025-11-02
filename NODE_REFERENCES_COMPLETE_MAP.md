# Node References in Paint System - Complete Analysis

## Overview
Paint System uses three levels of node references that can break when appending to fresh files:

1. **Blender PointerProperties** - Direct object references (stored as data)
2. **Node tree string identifiers** - Named references used by NodeTreeBuilder
3. **Hardwired socket connections** - Physical node links created at graph compile time

---

## 1. PointerProperty References (Data Layer)

### Primary PointerProperty References

```python
# In Layer class (paintsystem/data.py)
node_tree: PointerProperty(
    name="Node Tree",
    type=NodeTree  # Direct reference to external ShaderNodeTree
)

image: PointerProperty(
    name="Image",
    type=Image,  # Reference to image data block
    update=update_node_tree
)

custom_node_tree: PointerProperty(
    name="Custom Node Tree",
    type=NodeTree,  # For NODE_GROUP layer type
    update=update_node_tree
)

empty_object: PointerProperty(
    name="Empty Object",
    type=Object,  # For GRADIENT layer positioning
    update=update_node_tree
)

external_image: PointerProperty(
    name="Edit External Image",
    type=Image,  # External image editing reference
)

# In Channel class
node_tree: PointerProperty(
    name="Node Tree",
    type=NodeTree  # Channel-level composition tree
)

bake_image: PointerProperty(
    name="Bake Image",
    type=Image,  # Pre-baked texture
    update=update_bake_image
)

# In Group class
node_tree: PointerProperty(
    name="Node Tree",
    type=NodeTree  # Group-level composition tree
)

# In Layer class (linked layers)
linked_material: PointerProperty(
    name="Linked Material",
    type=Material,  # Reference to source material for linked layers
    update=update_node_tree
)

# In Group class (material reference)
# Implicit via Group ownership in MaterialData.groups
```

### Reference Hierarchy

```
Material.ps_mat_data (MaterialData)
├── Group.node_tree → NodeTree (ShaderNodeTree)
│   └── Contains nodes referencing channels
├── Channel.node_tree → NodeTree (ShaderNodeTree)
│   └── Contains ShaderNodeGroup nodes per layer
├── Layer.node_tree → NodeTree (ShaderNodeTree)
│   └── Layer-specific composition
├── Layer.image → Image (bpy.data.images)
├── Layer.custom_node_tree → NodeTree (for NODE_GROUP types)
├── Layer.empty_object → Object (for GRADIENT/LINEAR gradient controls)
├── Channel.bake_image → Image (pre-baked result)
└── Layer.linked_material → Material (for linked layer proxying)
```

### Problem When Appending

When appending a material from File A to File B:

```
File A: Material → Group → Channel → Layer → node_tree (NodeTree A)
                                              → image (Image A)
                                              → linked_material (Material A)
                ↓ (append to fresh file)
File B: Material → Group → Channel → Layer → node_tree (NodeTree A) ❌ BROKEN
                                              → image (Image A) ❌ MISSING
                                              → linked_material (Material A) ❌ MISSING
```

**Why it breaks:**
- NodeTree A doesn't exist in File B's `bpy.data.node_groups`
- Image A might exist but with different ID
- Material A reference becomes invalid null pointer
- Blender's append copies data blocks but doesn't follow PointerProperty references

---

## 2. NodeTreeBuilder String Identifiers (Logical Layer)

### How NodeTreeBuilder Works

```python
class NodeTreeBuilder:
    def __init__(self, node_tree: NodeTree, ...):
        self.nodes: Dict[str, bpy.types.Node] = {}  # Maps identifier → actual node
        self.edges: List[Edge] = []  # Stores connection commands
        self.__add_nodes_commands: Dict[str, Add_Node] = {}  # Pending nodes
```

### Reference Resolution

```python
def add_node(self, identifier: str, node_type: str, properties: dict = None):
    """
    Add a node with a string identifier.
    The identifier is used later to connect nodes.
    """
    self.__add_nodes_commands[identifier] = Add_Node(
        identifier=identifier,
        node_type=node_type,
        properties=properties
    )

def link(self, source: str, target: str, source_socket, target_socket):
    """
    Create a logical connection using string identifiers.
    The actual socket connections happen at compile time.
    """
    self.edges.append(Edge(
        source=source,
        target=target,
        source_socket=source_socket,
        target_socket=target_socket
    ))

def compile(self):
    """
    Resolve string identifiers to actual nodes and create socket connections.
    """
    # 1. Create all nodes from pending commands
    for identifier, add_cmd in self.__add_nodes_commands.items():
        node = self.tree.nodes.new(type=add_cmd.node_type)
        self.nodes[identifier] = node  # Store by identifier
        apply_node_properties(node, add_cmd.properties)
    
    # 2. Connect all edges
    for edge in self.edges:
        source_node = self.nodes[edge.source]  # Resolve identifier
        target_node = self.nodes[edge.target]  # Resolve identifier
        source_sock = source_node.outputs[edge.source_socket]
        target_sock = target_node.inputs[edge.target_socket]
        connect_sockets(source_sock, target_sock)
```

### Identifier Usage Patterns

```python
# Pattern 1: Layer identifiers use UID
layer_identifier = layer.uid  # "550e8400-e29b-41d4-a716-446655440000"
node_builder.add_node(
    layer_identifier, "ShaderNodeGroup",
    {"node_tree": layer.node_tree}  # PointerProperty set here!
)

# Pattern 2: Fixed identifiers for special nodes
node_builder.add_node("group_input", "NodeGroupInput")
node_builder.add_node("group_output", "NodeGroupOutput")
node_builder.add_node("alpha_clamp_end", "ShaderNodeClamp")

# Pattern 3: Channel names
channel_name = channel.name  # "Color", "Normal", etc.
node_builder.add_node(channel_name, "ShaderNodeGroup", ...)

# Pattern 4: Clipping mode identifiers
clip_nt_identifier = f"clip_nt_{layer.id}"
```

### Identifier Resolution at Compile Time

```python
# In Channel.update_node_tree()
for layer in flattened_layers:
    if not layer.node_tree:
        continue  # ❌ SKIP: node_tree is None
    
    layer_identifier = layer.uid  # Use UID as identifier
    node_builder.add_node(
        layer_identifier, "ShaderNodeGroup",
        {"node_tree": layer.node_tree}  # ❌ BROKEN: node_tree reference is invalid
    )
    
    # Later, connect this identifier to other nodes
    node_builder.link(
        layer_identifier,
        previous_data.color_name,
        "Color",
        previous_data.color_socket
    )
```

### Problem: Circular Dependency

1. **Identifier resolution works fine** ✓ (UIDs are unique strings)
2. **But node_tree PointerProperty is None** ✗ (appended node tree not found)
3. **Result**: ShaderNodeGroup node created but references invalid NodeTree
4. **Visual effect**: Grey/error nodes in Blender UI, render fails

---

## 3. Hardwired Socket Connections (Execution Layer)

### Connection Pattern

```python
# In group_operators.py
def create_basic_setup(mat_node_tree, group_node_tree, offset):
    # 1. Create Paint System group node
    node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
    node_group.node_tree = group_node_tree  # PointerProperty set directly
    
    # 2. Create mix shader node
    mix_shader = mat_node_tree.nodes.new(type='ShaderNodeMixShader')
    
    # 3. Create connection at material creation time (hardwired)
    connect_sockets(node_group.outputs[0], mix_shader.inputs[2])
    connect_sockets(node_group.outputs[1], mix_shader.inputs[0])
    # ❌ Problem: If node_group.node_tree is invalid, these connections fail
```

### Connection Verification Needed

```python
def verify_socket_connections(node_tree: NodeTree):
    """Check if all socket connections have valid sources."""
    invalid_links = []
    
    for link in node_tree.links:
        source_node = link.from_node
        target_node = link.to_node
        
        # Check if ShaderNodeGroup references valid node tree
        if source_node.bl_idname == 'ShaderNodeGroup':
            if not source_node.node_tree:
                invalid_links.append(f"Invalid source: {source_node.name}")
        
        if target_node.bl_idname == 'ShaderNodeGroup':
            if not target_node.node_tree:
                invalid_links.append(f"Invalid target: {target_node.name}")
    
    return invalid_links
```

---

## 4. Breakdown Map: Where References Break When Appending

| Reference Type | Location | What Gets Broken | Why |
|---|---|---|---|
| **PointerProperty** | `Layer.node_tree` | Node tree reference | External NodeTree not copied |
| **PointerProperty** | `Channel.node_tree` | Channel composition | NodeTree orphaned |
| **PointerProperty** | `Group.node_tree` | Group composition | NodeTree orphaned |
| **PointerProperty** | `Layer.image` | Bake/paint target | Image might not exist |
| **PointerProperty** | `Layer.linked_material` | Linked layer source | Source material not in new file |
| **PointerProperty** | `Layer.empty_object` | Gradient control | Object might not exist |
| **String Identifier** | UIDs in `link()` | Layer connections | Fine (strings are stable) |
| **Socket Connection** | `connect_sockets()` | Shader node links | Targets point to invalid node trees |

---

## 5. Solution: Store References by Name/Type Instead

### Current Approach (Breaks on Append)

```python
# Store actual reference to NodeTree
layer.node_tree = bpy.data.node_groups.new(...)  # Direct PointerProperty
```

### Proposed Approach (Survives Append)

#### Option A: Store NodeTree by Name

```python
class Layer(PropertyGroup):
    # Replace PointerProperty with string reference
    node_tree_name: StringProperty(
        name="Node Tree Name",
        description="Name of the node tree to reference"
    )
    
    @property
    def node_tree(self) -> NodeTree | None:
        """Resolve node tree by name at runtime."""
        return bpy.data.node_groups.get(self.node_tree_name)
    
    @node_tree.setter
    def node_tree(self, value: NodeTree) -> None:
        """Store node tree name instead of reference."""
        if value:
            self.node_tree_name = value.name
        else:
            self.node_tree_name = ""
```

**Pros:**
- Survives append (name references are stable)
- Simple implementation
- Backward compatible (getter/setter)

**Cons:**
- Name collisions possible (two NodeTrees with same name)
- Names can be changed by user

---

#### Option B: Store NodeTree Name + Creation Rule

```python
class Layer(PropertyGroup):
    node_tree_name: StringProperty()
    node_tree_type: EnumProperty(items=[
        ('LAYER', "Layer", "Layer-specific node tree"),
        ('CHANNEL', "Channel", "Channel composition tree"),
        ('SHARED', "Shared", "Shared across materials"),
    ])
    
    def get_or_create_node_tree(self) -> NodeTree:
        """Get existing or create new node tree."""
        nt = bpy.data.node_groups.get(self.node_tree_name)
        
        if not nt:
            # Regenerate if missing
            nt = bpy.data.node_groups.new(
                name=self.node_tree_name,
                type='ShaderNodeTree'
            )
            # Rebuild from layer type
            layer_graph = create_image_graph(self)  # etc.
            layer_graph.compile()
        
        return nt
```

**Pros:**
- Self-healing (recreates if missing)
- More robust

**Cons:**
- Slower (name lookup on every access)
- Requires versioning of node tree structure

---

#### Option C: Hybrid PointerProperty + Fallback

```python
class Layer(PropertyGroup):
    # Keep PointerProperty for normal use
    node_tree: PointerProperty(type=NodeTree)
    
    # Add fallback by name for recovery
    node_tree_name: StringProperty()
    
    def get_valid_node_tree(self, context) -> NodeTree:
        """Get node tree, with fallback to name lookup."""
        if self.node_tree and self.node_tree.name in bpy.data.node_groups:
            return self.node_tree
        
        # Fallback: lookup by name
        if self.node_tree_name:
            nt = bpy.data.node_groups.get(self.node_tree_name)
            if nt:
                self.node_tree = nt  # Update broken reference
                return nt
        
        # Last resort: recreate
        return self._recreate_node_tree(context)
```

**Pros:**
- Backward compatible with existing files
- Smart recovery
- No performance cost (PointerProperty used when valid)

**Cons:**
- More complex
- Migration logic needed

---

## 6. Implementation for Fresh File Append

### Step 1: Add Post-Append Validation

```python
class PAINT_SYSTEM_OT_validate_appended_setup(Operator):
    """Validate and fix appended Paint System setup"""
    bl_idname = "paint_system.validate_appended_setup"
    bl_label = "Validate Setup"
    
    def execute(self, context):
        for mat in bpy.data.materials:
            if not hasattr(mat, 'ps_mat_data'):
                continue
            
            self._fix_material_references(context, mat)
        
        return {'FINISHED'}
    
    def _fix_material_references(self, context, mat):
        """Fix all broken PointerProperty references."""
        for group in mat.ps_mat_data.groups:
            self._fix_node_tree(context, group.node_tree, group)
            
            for channel in group.channels:
                self._fix_node_tree(context, channel.node_tree, channel)
                
                for layer in channel.layers:
                    self._fix_layer_references(context, layer, mat)
    
    def _fix_node_tree(self, context, nt, owner):
        """Validate or recreate node tree."""
        if not nt or nt.name not in bpy.data.node_groups:
            # Recreate node tree
            new_nt = bpy.data.node_groups.new(
                name=owner.name,
                type='ShaderNodeTree'
            )
            owner.node_tree = new_nt
            owner.update_node_tree(context)
    
    def _fix_layer_references(self, context, layer, material):
        """Fix layer-specific broken references."""
        # 1. Validate node_tree
        if not layer.node_tree or layer.node_tree.name not in bpy.data.node_groups:
            layer.node_tree = None
            layer.update_node_tree(context)
        
        # 2. Validate image
        if layer.image and layer.image.name not in bpy.data.images:
            layer.image = None
        
        # 3. Validate linked material (might be in different file)
        if layer.is_linked and not layer.linked_material:
            # Break the link
            layer.linked_layer_uid = ""
            layer.linked_material = None
```

### Step 2: Add Validation to Group Creation

```python
def create_basic_setup(mat_node_tree, group_node_tree, offset):
    """Create setup with validation."""
    
    # Validate group_node_tree exists
    if not group_node_tree or group_node_tree.name not in bpy.data.node_groups:
        raise ValueError(f"Invalid group_node_tree: {group_node_tree}")
    
    node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
    node_group.node_tree = group_node_tree
    
    # ... rest of setup
```

---

## 7. Quick Reference: All Node References

### By Data Layer

**PropertyGroups (data.py):**
- `Layer.node_tree` → NodeTree (critical)
- `Layer.image` → Image (critical)
- `Layer.custom_node_tree` → NodeTree (NODE_GROUP type)
- `Layer.empty_object` → Object (GRADIENT type)
- `Layer.external_image` → Image (editing)
- `Layer.linked_material` → Material (linked layers)
- `Channel.node_tree` → NodeTree (critical)
- `Channel.bake_image` → Image
- `Group.node_tree` → NodeTree (critical)

**NodeTreeBuilder (nodetree_builder.py):**
- String identifiers: `layer.uid`, `channel.name`, `clip_nt_{id}`
- Socket references: by name string (`"Color"`, `"Alpha"`, etc.)
- Node references: `self.nodes[identifier]` dict

### By Severity When Appending

**Critical (app crashes/render fails):**
- Layer.node_tree
- Channel.node_tree
- Group.node_tree

**Important (UI breaks):**
- Layer.image
- Channel.bake_image

**Nice-to-have (features disabled):**
- Layer.empty_object (gradient controls)
- Layer.linked_material (linked layers)
- Layer.external_image (image editing)

---

## 8. Testing Checklist

- [ ] Append material from File A to fresh File B
- [ ] Run `validate_appended_setup()`
- [ ] Check all node trees recompile
- [ ] Verify layer images recreate
- [ ] Test render doesn't fail
- [ ] Check linked layers break gracefully
- [ ] Test with BASIC, PBR, NORMAL templates
- [ ] Multiple material append
