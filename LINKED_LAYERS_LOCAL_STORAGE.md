# Local Linked Layers: Design Approaches

## Current Implementation
The Paint System already has **material-local linked layers** (not global). Here's how it works:

```python
# Layer reference stored on each layer instance
linked_layer_uid: StringProperty()      # UID of the source layer
linked_material: PointerProperty(Material)  # Reference to source material

# When accessed, it proxies to the actual layer
def get_layer_data(self) -> Layer:
    if self.is_linked:
        uid_to_layer = _get_material_layer_uid_map(self.linked_material)
        return uid_to_layer.get(self.linked_layer_uid)  # Returns actual layer
    return self
```

This design is already **local** (scoped to materials), not global.

## Alternative Approaches to Enhance Local Linking

### 1. **Direct Node Tree Reference** (Simplest)
Instead of storing `linked_layer_uid + linked_material`, directly reference the source layer's node tree.

**Pros:**
- Simpler (no UID lookup needed)
- Direct access to node tree without traversal
- Single property instead of two

**Cons:**
- Can't track layer rename/identity changes
- If source layer deleted, link breaks silently
- Doesn't capture layer-level properties

```python
class Layer(BaseNestedListItem):
    # Replace: linked_layer_uid + linked_material
    linked_node_tree: PointerProperty(
        name="Linked Node Tree",
        type=NodeTree,
        update=update_node_tree
    )
    
    def get_layer_data(self) -> Layer:
        """Returns actual layer if linked, self otherwise"""
        if self.linked_node_tree:
            # Can't get back to layer object from node tree
            # So this approach loses layer-level metadata
            return self
        return self
```

**Usage:**
```python
# Simple copy of node tree reference
new_layer.linked_node_tree = source_layer.node_tree
```

---

### 2. **Cross-Channel Linking** (Current + Enhanced)
Keep current UID/material approach but extend to allow linking **within same material** (same or different channel).

```python
class Layer(BaseNestedListItem):
    # Existing UID + material approach
    linked_layer_uid: StringProperty()
    linked_material: PointerProperty(type=Material)
    
    @property
    def is_linked(self) -> bool:
        return bool(self.linked_layer_uid and self.linked_material)
    
    def get_layer_data(self) -> Layer:
        if self.is_linked:
            if self.linked_material == parse_context(bpy.context).active_material:
                # Within same material - fast lookup
                return get_layer_by_uid(self.linked_material, self.linked_layer_uid)
            else:
                # Cross-material (already supported)
                return get_layer_by_uid(self.linked_material, self.linked_layer_uid)
        return self
```

**Operator to create local-only link:**
```python
class PAINT_SYSTEM_OT_create_local_linked_layer(Operator):
    bl_idname = "paint_system.create_local_linked_layer"
    bl_label = "Link Layer (Same Material)"
    
    layer_uid: StringProperty()
    
    def execute(self, context):
        ps_ctx = parse_context(context)
        source_layer = get_layer_by_uid(ps_ctx.active_material, self.layer_uid)
        
        new_layer = ps_ctx.active_channel.create_layer()
        new_layer.linked_layer_uid = source_layer.uid
        new_layer.linked_material = ps_ctx.active_material  # Same material
        new_layer.layer_name = f"{source_layer.layer_name} (linked)"
        
        return {'FINISHED'}
```

**Benefit:** Supports linking within same channel (prevents circular deps) and cross-channel within same material.

---

### 3. **Metadata-Only Linking** (Copy + Track)
Create local copies that track a "source_layer_uid" but store their own data. On update, optionally sync selected properties.

```python
class Layer(BaseNestedListItem):
    # Track the original source
    source_layer_uid: StringProperty(
        name="Source Layer UID",
        description="UID of layer this was copied from"
    )
    source_material: PointerProperty(
        name="Source Material",
        type=Material
    )
    
    # Local copies that can diverge
    @property
    def is_copy_of(self) -> bool:
        return bool(self.source_layer_uid and self.source_material)
    
    def sync_from_source(self, sync_node_tree=True, sync_properties=False):
        """Sync selected properties from source layer"""
        source = get_layer_by_uid(self.source_material, self.source_layer_uid)
        if not source:
            return
        
        if sync_node_tree:
            # Copy or link node tree
            self.node_tree = source.node_tree
        
        if sync_properties:
            # Copy layer properties
            for prop in ['layer_name', 'type', 'blend_mode']:
                setattr(self, prop, getattr(source, prop))
```

**Operator:**
```python
class PAINT_SYSTEM_OT_sync_copied_layer(Operator):
    bl_idname = "paint_system.sync_copied_layer"
    bl_label = "Sync with Source"
    
    def execute(self, context):
        ps_ctx = parse_context(context)
        ps_ctx.active_layer.sync_from_source(sync_node_tree=True)
        return {'FINISHED'}
```

---

### 4. **Shared Node Tree Pool** (Advanced)
Store node trees in a centralized location within material, then reference by index.

```python
class MaterialData(PropertyGroup):
    # New: shared node tree library
    shared_node_trees: CollectionProperty(
        type=SharedNodeTree,  # Custom PropertyGroup
        name="Shared Node Trees"
    )
    
    groups: CollectionProperty(type=Group)
    active_index: IntProperty()

class SharedNodeTree(PropertyGroup):
    name: StringProperty()
    node_tree: PointerProperty(type=NodeTree)
    uid: StringProperty()

class Layer(BaseNestedListItem):
    # Reference by UID into material's shared pool
    shared_node_tree_uid: StringProperty()
    
    @property
    def node_tree(self) -> NodeTree:
        ps_ctx = parse_context(bpy.context)
        mat = ps_ctx.active_material
        for shared_nt in mat.ps_mat_data.shared_node_trees:
            if shared_nt.uid == self.shared_node_tree_uid:
                return shared_nt.node_tree
        return None
```

**Benefits:**
- True deduplication (single node tree, many references)
- Explicit management
- No external material dependencies
- Scales well for many linked layers

---

### 5. **Layer Template System** (Highest-Level)
Instead of "linked", think of it as "layer templates" with instantiation.

```python
class TemplateLayer(PropertyGroup):
    """Template stored in material"""
    uid: StringProperty()
    name: StringProperty()
    type: EnumProperty(items=LAYER_TYPE_ENUM)
    # Store serialized template data
    template_data: StringProperty()  # JSON

class Layer(BaseNestedListItem):
    # Option A: Link to template
    template_uid: StringProperty()
    
    def instantiate_from_template(self, material: Material, template_uid: str):
        """Create layer from template, allow local customization"""
        template = [t for t in material.ps_mat_data.templates 
                   if t.uid == template_uid][0]
        # Restore layer from serialized data
        self.type = template.type
        self.layer_name = template.name
        # Can now diverge locally
```

---

## Recommendation

### **Use Approach #2 (Cross-Channel Linking) because:**

1. **Already implemented** - Just clarify constraints in docs
2. **No breaking changes** - Current code works
3. **Lightweight** - Two properties, efficient UID lookup
4. **Flexible** - Supports within-channel and cross-channel
5. **Trackable** - Layer identity preserved even if renamed
6. **Circular reference prevention** - Check parent_id chain

### **Example: Add constraint to prevent circular linking**

```python
def create_linked_layer(self, layer_uid: str, material: Material) -> 'Layer':
    """Create local linked layer (same or different material)"""
    source_layer = get_layer_by_uid(material, layer_uid)
    
    # Prevent linking to self
    if material == parse_context(bpy.context).active_material:
        if layer_uid == source_layer.uid:
            raise ValueError("Cannot link layer to itself")
    
    new_layer = self.create_layer()
    new_layer.linked_layer_uid = layer_uid
    new_layer.linked_material = material
    new_layer.layer_name = f"{source_layer.layer_name} (linked)"
    
    return new_layer
```

---

## Implementation Checklist for Enhanced Local Linking

```python
# 1. Add validation in Layer class
def validate_link(self, target_material: Material, target_uid: str) -> bool:
    """Check if link is valid and prevents circular deps"""
    # Check: target layer exists
    # Check: not linking to self
    # Check: not circular (A→B→A)
    pass

# 2. Add UI helper in panels/layers_panels.py
def draw_link_ui(layout, layer, context):
    if layer.is_linked:
        layout.label(text=f"Linked to: {layer.linked_material.name}")
        layout.operator("paint_system.break_link")
    else:
        layout.operator("paint_system.link_to_layer")

# 3. Add copy operator for quick linking
class PAINT_SYSTEM_OT_duplicate_as_link(Operator):
    """Duplicate layer as linked instance"""
    
# 4. Update copilot-instructions.md with linked layer patterns
```

---

## FAQ

**Q: How do linked layers differ from instances in Blender?**  
A: Linked layers aren't "instances" (all properties linked). Instead, they proxy to another layer's **node tree only**. Layer-level properties (name, blend mode, etc.) can differ.

**Q: Can I link across materials?**  
A: Yes - `linked_material` can be any material. But within-material links are common for templates.

**Q: What happens if source layer is deleted?**  
A: The link breaks. `get_layer_data()` returns None. Should warn user.

**Q: How do I break a link?**  
A: Set `linked_layer_uid = ""` and `linked_material = None`.
