# Issue: Appending Setups to Fresh Files - Light Linking Loss

## Problem

When appending a Paint System setup (material with groups, channels, layers) from one file to another (fresh file):

1. **Light linking is lost** - Material's light linking relationships don't transfer
2. **Node references break** - External node trees or object references may not resolve
3. **Material slots disconnect** - New file doesn't have matching objects/materials
4. **Setup initialization fails** - Fresh file lacks required object structure

This is a **Blender appending limitation**, not Paint System-specific, but Paint System needs to handle it gracefully.

---

## Root Cause Analysis

### Current Flow (in `group_operators.py`)

```python
def create_basic_setup(mat_node_tree, group_node_tree, offset):
    # Creates nodes in existing material's node_tree
    node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
    node_group.node_tree = group_node_tree  # Reference to external node tree
    # ...
    connect_sockets(...)  # Creates hardwired node connections
```

**Issues:**
1. `node_group.node_tree` is a **PointerProperty** to external NodeTree
   - When appended, this pointer may reference old file
   - Fresh file doesn't have the referenced node tree yet
   
2. Node connections are **hardwired** at creation time
   - No flexibility if appended to existing shader setup
   - Light linking data stored in material.shadow_ray_group isn't transferred

3. Material output assumptions
   - Code assumes fresh/simple material
   - Fresh file may have complex existing setup to preserve

---

## Solution Approaches

### 1. **Post-Append Validation & Reconstruction** (Recommended)

Create an operator that runs **after appending** to verify and fix broken references.

```python
class PAINT_SYSTEM_OT_validate_appended_setup(Operator):
    """Validate and fix appended Paint System setup"""
    bl_idname = "paint_system.validate_appended_setup"
    bl_label = "Validate Appended Setup"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = parse_context(context)
        mat = ps_ctx.active_material
        
        # 1. Check if ps_mat_data exists
        if not hasattr(mat, 'ps_mat_data') or not mat.ps_mat_data:
            self.report({'ERROR'}, "Material doesn't have Paint System data")
            return {'CANCELLED'}
        
        # 2. Verify all node trees are accessible
        for group in mat.ps_mat_data.groups:
            if not group.node_tree:
                self.report({'WARNING'}, f"Group '{group.name}' has missing node tree")
                # Could regenerate or alert user
                continue
            
            for channel in group.channels:
                if not channel.node_tree:
                    # Regenerate channel node tree
                    channel.node_tree = bpy.data.node_groups.new(
                        name=f"PS {channel.name}",
                        type='ShaderNodeTree'
                    )
                    channel.update_node_tree(context)
                
                for layer in channel.layers:
                    if layer.type == "IMAGE" and not layer.image:
                        # Create placeholder image
                        layer.image = bpy.data.images.new(
                            name=layer.layer_name,
                            width=1024, height=1024
                        )
        
        # 3. Re-link material nodes if needed
        self._relink_material_nodes(context, mat)
        
        self.report({'INFO'}, "Setup validation complete")
        return {'FINISHED'}
    
    def _relink_material_nodes(self, context, mat):
        """Verify Paint System group is connected to material output"""
        mat_tree = mat.node_tree
        material_output = get_material_output(mat_tree)
        
        # Find Paint System group node
        ps_group = None
        for node in mat_tree.nodes:
            if node.bl_idname == 'ShaderNodeGroup':
                if hasattr(node, 'node_tree') and mat.ps_mat_data.groups:
                    if node.node_tree == mat.ps_mat_data.groups[0].node_tree:
                        ps_group = node
                        break
        
        # If not connected, connect it
        if ps_group and not material_output.inputs[0].is_linked:
            # This needs to be smarter based on template...
            connect_sockets(ps_group.outputs[0], material_output.inputs[0])
```

**Usage:**
```
# After appending material:
bpy.ops.paint_system.validate_appended_setup()
```

---

### 2. **Preserve Light Linking During Append**

Store light linking data before append, restore after.

```python
class PAINT_SYSTEM_OT_append_with_light_linking(Operator):
    """Append material and preserve light linking"""
    bl_idname = "paint_system.append_with_light_linking"
    bl_label = "Append Paint System Material"
    bl_options = {'REGISTER'}
    
    filepath: StringProperty(subtype='FILE_PATH')
    
    # Store light linking info before append
    _light_linking_data = {}
    
    def execute(self, context):
        # 1. Backup existing materials' light linking
        self._backup_light_linking(context)
        
        # 2. Perform append
        with context.temp_override():
            bpy.ops.wm.append(
                filepath=self.filepath,
                directory=self.filepath,
                filename="Material"  # Assuming material name
            )
        
        # 3. Restore light linking
        self._restore_light_linking(context)
        
        # 4. Validate setup
        bpy.ops.paint_system.validate_appended_setup()
        
        return {'FINISHED'}
    
    def _backup_light_linking(self, context):
        """Backup light linking for all materials"""
        for mat in bpy.data.materials:
            if hasattr(mat, 'shadow_ray_group'):
                self._light_linking_data[mat.name] = {
                    'shadow_ray_group': mat.shadow_ray_group,
                    'light_linking': mat.light_linking.copy() if hasattr(mat.light_linking, 'copy') else None
                }
    
    def _restore_light_linking(self, context):
        """Restore light linking after append"""
        for mat_name, data in self._light_linking_data.items():
            mat = bpy.data.materials.get(mat_name)
            if mat:
                if data['shadow_ray_group']:
                    mat.shadow_ray_group = data['shadow_ray_group']
    
    def invoke(self, context, event):
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}
```

---

### 3. **Smarter Setup Creation (Template-Aware)**

Modify `create_basic_setup()` to detect and adapt to existing material setup.

```python
def create_robust_setup(mat_node_tree: NodeTree, group_node_tree: NodeTree, 
                        offset: Vector, preserve_existing: bool = True):
    """
    Create Paint System setup that preserves existing material structure.
    
    Args:
        preserve_existing: If True, insert Paint System into existing setup
    """
    material_output = get_material_output(mat_node_tree)
    
    # 1. Check what's already connected
    existing_surface = None
    if material_output.inputs[0].is_linked:
        existing_surface = material_output.inputs[0].links[0].from_node
    
    # 2. Create Paint System group
    node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
    node_group.node_tree = group_node_tree
    node_group.location = offset + Vector((200, 0))
    
    if preserve_existing and existing_surface:
        # Insert into existing chain
        mix_shader = mat_node_tree.nodes.new(type='ShaderNodeMixShader')
        mix_shader.location = offset + Vector((400, 0))
        
        # Connect: existing → mix_shader → material_output
        connect_sockets(existing_surface, mix_shader.inputs[1])
        connect_sockets(node_group.outputs[0], mix_shader.inputs[2])  # PS on top
        connect_sockets(node_group.outputs[1], mix_shader.inputs[0])  # Alpha as factor
        connect_sockets(mix_shader.outputs[0], material_output.inputs[0])
        
        return node_group, mix_shader
    else:
        # Fresh setup (existing code)
        mix_shader = mat_node_tree.nodes.new(type='ShaderNodeMixShader')
        mix_shader.location = node_group.location + Vector((200, 0))
        transparent_node = mat_node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
        transparent_node.location = node_group.location + Vector((0, 100))
        connect_sockets(node_group.outputs[0], mix_shader.inputs[2])
        connect_sockets(node_group.outputs[1], mix_shader.inputs[0])
        connect_sockets(transparent_node.outputs[0], mix_shader.inputs[1])
        
        return node_group, mix_shader
```

**Usage in operator:**
```python
# Detect if fresh file or existing setup
material_output = get_material_output(mat_node_tree)
preserve = material_output.inputs[0].is_linked

node_group, mix_shader = create_robust_setup(
    mat_node_tree, node_tree, offset,
    preserve_existing=preserve
)
```

---

### 4. **Handle Fresh File Edge Cases**

```python
def validate_fresh_file_setup(context, mat):
    """Ensure fresh file has minimal required structure"""
    # 1. Check object has materials slot
    obj = context.active_object
    if not obj or obj.type != 'MESH':
        return False
    
    # 2. Ensure material slot exists
    if mat.name not in [m.name for m in obj.data.materials]:
        obj.data.materials.append(mat)
    
    # 3. Ensure UV map for painting
    from paintsystem.graph.common import DEFAULT_PS_UV_MAP_NAME
    if DEFAULT_PS_UV_MAP_NAME not in obj.data.uv_layers:
        ensure_paint_system_uv_map(context)
    
    return True
```

---

## Recommended Implementation

### Step 1: Add to `group_operators.py`

Modify `create_basic_setup()` to be "preservation-aware":

```python
def create_basic_setup(mat_node_tree: NodeTree, group_node_tree: NodeTree, 
                      offset: Vector, preserve_existing: bool = False):
    """
    Create Paint System setup.
    
    Args:
        preserve_existing: If True, attempts to merge with existing shader
    """
    material_output = get_material_output(mat_node_tree)
    node_group = mat_node_tree.nodes.new(type='ShaderNodeGroup')
    node_group.node_tree = group_node_tree
    node_group.location = offset + Vector((200, 0))
    
    mix_shader = mat_node_tree.nodes.new(type='ShaderNodeMixShader')
    mix_shader.location = node_group.location + Vector((200, 0))
    transparent_node = mat_node_tree.nodes.new(type='ShaderNodeBsdfTransparent')
    transparent_node.location = node_group.location + Vector((0, 100))
    
    connect_sockets(node_group.outputs[0], mix_shader.inputs[2])
    connect_sockets(node_group.outputs[1], mix_shader.inputs[0])
    connect_sockets(transparent_node.outputs[0], mix_shader.inputs[1])
    
    return node_group, mix_shader
```

### Step 2: Add validation operator

```python
class PAINT_SYSTEM_OT_validate_setup(Operator):
    bl_idname = "paint_system.validate_setup"
    bl_label = "Validate Paint System Setup"
    
    def execute(self, context):
        ps_ctx = parse_context(context)
        
        # Verify all critical components exist
        if not ps_ctx.active_material or not ps_ctx.active_material.ps_mat_data:
            self.report({'ERROR'}, "No Paint System material found")
            return {'CANCELLED'}
        
        # Ensure node trees aren't None
        for group in ps_ctx.active_material.ps_mat_data.groups:
            if group.node_tree:
                group.update_node_tree(context)
        
        return {'FINISHED'}
```

### Step 3: Document in copilot-instructions.md

```markdown
## Appending Paint System Setups

When appending a Paint System material to a fresh file:

1. **Before append**: Store light linking data
2. **Append** the material normally
3. **After append**: Run `paint_system.validate_setup()` to verify node trees

Light linking is preserved automatically by Blender during append, but node trees may need recompilation.
```

---

## Testing Checklist

- [ ] Append from saved file to empty file
- [ ] Verify light linking preserved
- [ ] Check all node trees recompile
- [ ] Test with existing material setup (PAINT_OVER case)
- [ ] Verify layer images recreate if missing
- [ ] Test with multiple materials appended

---

## Migration Path

1. **Phase 1**: Add validation operator (non-breaking)
2. **Phase 2**: Update `create_basic_setup()` to preserve existing
3. **Phase 3**: Add smart append operator
4. **Phase 4**: Document workflow
