import math
import uuid
import addon_utils
import bpy
import gpu
from bpy.props import EnumProperty, IntProperty, BoolProperty, StringProperty
from bpy.types import Operator
from bpy.utils import register_classes_factory
from bpy_extras.node_utils import connect_sockets

from ..paintsystem.data import update_active_image

# ---
from ..preferences import addon_package
from ..utils.nodes import find_node, get_material_output
from ..utils.version import is_newer_than
from ..utils.unified_brushes import get_unified_settings
from .brushes import get_brushes_from_library
from .common import MultiMaterialOperator, PSContextMixin, DEFAULT_PS_UV_MAP_NAME
from .operators_utils import redraw_panel

from bl_ui.properties_paint_common import (
    UnifiedPaintPanel,
)


class PAINTSYSTEM_OT_PickPaletteColor(Operator):
    """Pick this palette color as the active brush color"""
    bl_idname = "paint_system.pick_palette_color"
    bl_label = "Pick Palette Color"
    bl_options = {'REGISTER', 'UNDO'}
    
    palette_index: IntProperty()
    color: bpy.props.FloatVectorProperty(
        size=3,
        subtype='COLOR',
        min=0.0,
        max=1.0
    )
    
    def execute(self, context):
        tool_settings = context.tool_settings
        image_paint = getattr(tool_settings, 'image_paint', None)
        if not image_paint:
            return {'CANCELLED'}
        
        palette = getattr(image_paint, 'palette', None)
        if not palette or self.palette_index >= len(palette.colors):
            return {'CANCELLED'}
        
        # Get the color from the palette
        palette_color = palette.colors[self.palette_index].color
        
        # Set it as the active brush color (respecting unified settings)
        ups = context.tool_settings.unified_paint_settings
        use_unified = getattr(ups, 'use_unified_color', False)
        
        if use_unified:
            ups.color = palette_color
        else:
            brush = getattr(image_paint, 'brush', None)
            if brush:
                brush.color = palette_color
        
        return {'FINISHED'}
    
    def invoke(self, context, event):
        # Just execute immediately - we already have the color from properties
        return self.execute(context)

class PAINTSYSTEM_OT_TogglePaintMode(PSContextMixin, Operator):
    bl_idname = "paint_system.toggle_paint_mode"
    bl_label = "Toggle Paint Mode"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Toggle between texture paint and object mode"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object.type == 'MESH' or ps_ctx.ps_object.type == 'GREASEPENCIL'

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.ps_object
        # Set selected and active object
        context.view_layer.objects.active = obj
        obj.select_set(True)
        if obj.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
            return {'FINISHED'}
        desired_mode = 'TEXTURE_PAINT' if obj.type == 'MESH' else 'PAINT_GREASE_PENCIL'
        bpy.ops.object.mode_set(mode=desired_mode)
        is_cycles = bpy.context.scene.render.engine == 'CYCLES'
        if obj.mode == desired_mode:
            # Change shading mode
            if bpy.context.space_data.shading.type != ('RENDERED' if not is_cycles else 'MATERIAL'):
                bpy.context.space_data.shading.type = ('RENDERED' if not is_cycles else 'MATERIAL')
        
        update_active_image(self, context)

        return {'FINISHED'}


class PAINTSYSTEM_OT_SetMode(PSContextMixin, Operator):
    bl_idname = "paint_system.set_mode"
    bl_label = "Set Mode"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Switch to a specific object mode"
    
    mode: EnumProperty(
        name="Mode",
        items=[
            ('OBJECT', "Object Mode", "Switch to Object Mode"),
            ('TEXTURE_PAINT', "Texture Paint", "Switch to Texture Paint Mode"),
            ('EDIT', "Edit Mode", "Switch to Edit Mode"),
            ('SCULPT', "Sculpt Mode", "Switch to Sculpt Mode"),
            # The following are still supported by the operator, but not exposed in the UI here
            ('VERTEX_PAINT', "Vertex Paint", "Switch to Vertex Paint Mode"),
            ('WEIGHT_PAINT', "Weight Paint", "Switch to Weight Paint Mode"),
            ('PAINT_GREASE_PENCIL', "Draw", "Switch to Grease Pencil Draw Mode"),
        ]
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object.type in {'MESH', 'GREASEPENCIL'}

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        obj = ps_ctx.ps_object
        
        # Set selected and active object
        context.view_layer.objects.active = obj
        obj.select_set(True)
        
        # Toggle behavior: if already in the requested mode, switch to Object mode
        current_mode = obj.mode
        
        # Check if we're already in the requested mode
        target_blender_mode = 'EDIT' if self.mode == 'EDIT' else self.mode
        is_already_in_mode = (current_mode == target_blender_mode)
        
        if is_already_in_mode:
            # Toggle off: return to Object mode
            if current_mode != 'OBJECT':
                bpy.ops.object.mode_set(mode='OBJECT')
        else:
            # Switch to the requested mode
            if self.mode == 'OBJECT':
                if obj.mode != 'OBJECT':
                    bpy.ops.object.mode_set(mode='OBJECT')
            else:
                # Check if mode is valid for object type
                if obj.type == 'MESH':
                    valid_modes = {'TEXTURE_PAINT', 'SCULPT', 'VERTEX_PAINT', 'WEIGHT_PAINT', 'EDIT'}
                    if self.mode in valid_modes:
                        bpy.ops.object.mode_set(mode=target_blender_mode)
                        
                        # Change shading mode for texture paint
                        if self.mode == 'TEXTURE_PAINT':
                            is_cycles = context.scene.render.engine == 'CYCLES'
                            if context.space_data.shading.type != ('RENDERED' if not is_cycles else 'MATERIAL'):
                                context.space_data.shading.type = ('RENDERED' if not is_cycles else 'MATERIAL')
                            update_active_image(self, context)
                            
                elif obj.type == 'GREASEPENCIL' and self.mode == 'PAINT_GREASE_PENCIL':
                    bpy.ops.object.mode_set(mode='PAINT_GREASE_PENCIL')
                    is_cycles = context.scene.render.engine == 'CYCLES'
                    if context.space_data.shading.type != ('RENDERED' if not is_cycles else 'MATERIAL'):
                        context.space_data.shading.type = ('RENDERED' if not is_cycles else 'MATERIAL')

        return {'FINISHED'}


class PAINTSYSTEM_OT_AddPresetBrushes(Operator):
    bl_idname = "paint_system.add_preset_brushes"
    bl_label = "Import Paint System Brushes"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Add preset brushes to the active group"

    def execute(self, context):
        get_brushes_from_library()
        return {'FINISHED'}


class PAINTSYSTEM_OT_SelectMaterialIndex(PSContextMixin, Operator):
    """Select the item in the UI list"""
    bl_idname = "paint_system.select_material_index"
    bl_label = "Select Material Index"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Select the material index in the UI list"

    index: IntProperty()

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ob = ps_ctx.ps_object
        if not ob:
            return {'CANCELLED'}
        if ob.type != 'MESH':
            return {'CANCELLED'}
        ob.active_material_index = self.index
        return {'FINISHED'}





class PAINTSYSTEM_OT_NewMaterial(PSContextMixin, MultiMaterialOperator):
    bl_idname = "paint_system.new_material"
    bl_label = "New Material"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Create a new material"
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        bpy.ops.object.material_slot_add()
        bpy.data.materials.new(name="New Material")
        ps_ctx.ps_object.active_material = bpy.data.materials[-1]
        return {'FINISHED'}


class PAINTSYSTEM_OT_IsolateChannel(PSContextMixin, Operator):
    bl_idname = "paint_system.isolate_active_channel"
    bl_label = "Isolate Channel"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Isolate the active channel"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_material is not None and ps_ctx.active_channel is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.active_channel.isolate_channel(context)
                
        # Change render mode
        if bpy.context.space_data.shading.type not in {'RENDERED', 'MATERIAL'}:
            bpy.context.space_data.shading.type = 'RENDERED'
        return {'FINISHED'}


class PAINTSYSTEM_OT_ToggleBrushEraseAlpha(Operator):
    bl_idname = "paint_system.toggle_brush_erase_alpha"
    bl_label = "Toggle Brush Erase Alpha"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Toggle between brush and erase alpha"
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE'

    def execute(self, context):
        tool_settings = UnifiedPaintPanel.paint_settings(context)

        if tool_settings is not None:
            brush = tool_settings.brush
            if brush is not None:
                if brush.blend == 'ERASE_ALPHA':
                    brush.blend = 'MIX'  # Switch back to normal blending
                else:
                    brush.blend = 'ERASE_ALPHA'  # Switch to Erase Alpha mode
        return {'FINISHED'}


class PAINTSYSTEM_OT_ColorSampler(PSContextMixin, Operator):
    """Sample the color under the mouse cursor"""
    bl_idname = "paint_system.color_sampler"
    bl_label = "Color Sampler"

    x: IntProperty()
    y: IntProperty()
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE'

    def execute(self, context):
        # Hint the cursor to use the eyedropper for immediate visual feedback.
        win = getattr(context, 'window', None)
        if win:
            try:
                win.cursor_modal_set('EYEDROPPER')
            except Exception:
                pass

        if is_newer_than(4,4):
            # Delegate to Blender's modal color sampler (canvas-local).
            try:
                bpy.ops.paint.sample_color('INVOKE_DEFAULT', merged=True)
            finally:
                # Schedule a safe cursor restore shortly after invoke.
                def _restore_cursor():
                    try:
                        w = bpy.context.window
                        if w:
                            w.cursor_modal_restore()
                    except Exception:
                        pass
                    return None
                try:
                    bpy.app.timers.register(_restore_cursor, first_interval=0.6)
                except Exception:
                    # Fallback: best-effort immediate restore
                    if win:
                        try:
                            win.cursor_modal_restore()
                        except Exception:
                            pass
            return {'FINISHED'}
        # Get the screen dimensions
        x, y = self.x, self.y

        buffer = gpu.state.active_framebuffer_get()
        pixel = buffer.read_color(x, y, 1, 1, 3, 0, 'FLOAT')
        pixel.dimensions = 1 * 1 * 3
        pix_value = [float(item) for item in pixel]

        tool_settings = UnifiedPaintPanel.paint_settings(context)
        unified_settings = get_unified_settings(context, "use_unified_color")
        brush_settings = tool_settings.brush
        unified_settings.color = pix_value
        brush_settings.color = pix_value

        # Restore cursor right away for the non-modal sampling path
        if win:
            try:
                win.cursor_modal_restore()
            except Exception:
                pass
        return {'FINISHED'}

    @classmethod
    def poll(cls, context):
        try:
            area_ok = getattr(context, 'area', None) and context.area.type == 'VIEW_3D'
            mode_ok = getattr(context, 'mode', '') in {
                'PAINT_TEXTURE',
                'PAINT_GREASE_PENCIL',
                'VERTEX_GREASE_PENCIL',
            }
            return bool(area_ok and mode_ok)
        except Exception:
            return False

    def invoke(self, context, event):
        self.x = event.mouse_x
        self.y = event.mouse_y
        return self.execute(context)


class PAINTSYSTEM_OT_OpenPaintSystemPreferences(Operator):
    bl_idname = "paint_system.open_paint_system_preferences"
    bl_label = "Open Paint System Preferences"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Open the Paint System preferences"
    
    
    def execute(self, context):
        bpy.ops.screen.userpref_show()
        bpy.context.preferences.active_section = 'ADDONS'
        bpy.context.window_manager.addon_search = 'Paint System'
        modules = addon_utils.modules()
        mod = None
        for mod in modules:
            if mod.bl_info.get("name") == "Paint System":
                mod = mod
                break
        if mod is None:
            print("Paint System not found")
            return {'FINISHED'}
        bl_info = addon_utils.module_bl_info(mod)
        show_expanded = bl_info["show_expanded"]
        if not show_expanded:
            bpy.ops.preferences.addon_expand(module=addon_package())
        return {'FINISHED'}


class PAINTSYSTEM_OT_FlipNormals(Operator):
    """Flip normals of the selected mesh"""
    bl_idname = "paint_system.flip_normals"
    bl_label = "Flip Normals"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Flip normals of the selected mesh"
    
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        orig_mode = str(obj.mode)
        if obj.type == 'MESH':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.flip_normals()
            bpy.ops.object.mode_set(mode=orig_mode)
        return {'FINISHED'}

class PAINTSYSTEM_OT_RecalculateNormals(Operator):
    """Recalculate normals of the selected mesh"""
    bl_idname = "paint_system.recalculate_normals"
    bl_label = "Recalculate Normals"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Recalculate normals of the selected mesh"
    
    @classmethod
    def poll(cls, context):
        return context.object and context.object.type == 'MESH'

    def execute(self, context):
        obj = context.object
        orig_mode = str(obj.mode)
        if obj.type == 'MESH':
            bpy.ops.object.mode_set(mode='EDIT')
            bpy.ops.mesh.select_all(action='SELECT')
            bpy.ops.mesh.normals_make_consistent(inside=False)
            bpy.ops.object.mode_set(mode=orig_mode)
        return {'FINISHED'}

class PAINTSYSTEM_OT_AddCameraPlane(Operator):
    bl_idname = "paint_system.add_camera_plane"
    bl_label = "Add Camera Plane"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Add a plane with a camera texture"

    align_up: EnumProperty(
        name="Align Up",
        items=[
            ('NONE', "None", "No alignment"),
            ('X', "X", "Align up with X axis"),
            ('Y', "Y", "Align up with Y axis"),
            ('Z', "Z", "Align up with Z axis"),
        ],
        default='NONE'
    )

    def execute(self, context):
        bpy.ops.mesh.primitive_plane_add('INVOKE_DEFAULT', align='VIEW')
        return {'FINISHED'}


class PAINTSYSTEM_OT_HidePaintingTips(PSContextMixin, MultiMaterialOperator):
    """Hide the normal painting tips"""
    bl_idname = "paint_system.hide_painting_tips"
    bl_label = "Hide Normal Painting Tips"
    bl_options = {'INTERNAL'}
    
    attribute_name: bpy.props.StringProperty(
        name="Tip Attribute Name",
        description="The attribute name of the tip",
        default=""
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_settings is not None
    
    def process_material(self, context):
        ps_ctx = self.parse_context(context)
        if hasattr(ps_ctx.ps_settings, self.attribute_name):
            setattr(ps_ctx.ps_settings, self.attribute_name, True)
        else:
            return {'CANCELLED'}
        redraw_panel(context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_DuplicatePaintSystemData(PSContextMixin, MultiMaterialOperator):
    """Duplicate the selected group in the Paint System"""
    bl_idname = "paint_system.duplicate_paint_system_data"
    bl_label = "Duplicate Paint System Data"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        mat = ps_ctx.active_material
        
        for group in ps_mat_data.groups:
            original_node_tree = group.node_tree
            node_tree = bpy.data.node_groups.new(name=f"Paint System ({mat.name})", type='ShaderNodeTree')
            group.node_tree = node_tree
            for channel in group.channels:
                node_tree = bpy.data.node_groups.new(name=f"PS_Channel ({channel.name})", type='ShaderNodeTree')
                channel.node_tree = node_tree
                for layer in channel.layers:
                    if layer.is_linked:
                        continue
                    layer.duplicate_layer_data(layer)
                    layer.update_node_tree(context)
                channel.update_node_tree(context)
            group.update_node_tree(context)
            
            # Find node group that uses the original node tree
            for node in mat.node_tree.nodes:
                if node.type == 'GROUP' and node.node_tree == original_node_tree:
                    node.node_tree = group.node_tree
        redraw_panel(context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ToggleTransformGizmos(Operator):
    """Toggle transform gizmos on/off while remembering which types were enabled"""
    bl_idname = "paint_system.toggle_transform_gizmos"
    bl_label = "Toggle Transform Gizmos"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Toggle transform gizmos (remembers which types were active)"
    
    def execute(self, context):
        space = context.space_data
        if not space or space.type != 'VIEW_3D':
            return {'CANCELLED'}
        
        obj = context.object
        wm = context.window_manager
        
        # Check if in paint/sculpt mode
        in_paint_mode = obj and obj.mode in {'PAINT_TEXTURE', 'SCULPT', 'PAINT_VERTEX', 'PAINT_WEIGHT'}
        
        # Check if gizmos are currently enabled
        gizmos_enabled = (space.show_gizmo_object_translate or 
                         space.show_gizmo_object_rotate or 
                         space.show_gizmo_object_scale)
        
        if in_paint_mode:
            # In paint mode, toggle the stored preference (for when we exit paint mode)
            stored_enabled = wm.get("ps_gizmo_translate", True) or wm.get("ps_gizmo_rotate", True) or wm.get("ps_gizmo_scale", False)
            if stored_enabled:
                # Disable preference - gizmos will stay off when exiting paint mode
                wm["ps_gizmo_translate"] = False
                wm["ps_gizmo_rotate"] = False
                wm["ps_gizmo_scale"] = False
            else:
                # Enable preference - gizmos will turn on when exiting paint mode
                wm["ps_gizmo_translate"] = True
                wm["ps_gizmo_rotate"] = True
                wm["ps_gizmo_scale"] = False
        else:
            # Not in paint mode - toggle normally
            if gizmos_enabled:
                # Store current state
                wm["ps_gizmo_translate"] = space.show_gizmo_object_translate
                wm["ps_gizmo_rotate"] = space.show_gizmo_object_rotate
                wm["ps_gizmo_scale"] = space.show_gizmo_object_scale
                
                # Disable all gizmos
                space.show_gizmo_object_translate = False
                space.show_gizmo_object_rotate = False
                space.show_gizmo_object_scale = False
            else:
                # Restore previous state
                space.show_gizmo_object_translate = wm.get("ps_gizmo_translate", True)
                space.show_gizmo_object_rotate = wm.get("ps_gizmo_rotate", True)
                space.show_gizmo_object_scale = wm.get("ps_gizmo_scale", False)
        
        # Redraw to update button state
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_AssignActiveMaterialToSelected(Operator):
    """Assign the active object's material to all other selected mesh objects.
    Optionally synchronize a shared UV map name across them for Paint System operations."""
    bl_idname = "paint_system.assign_active_material_to_selected"
    bl_label = "Assign Active Material to Selected"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Apply the active object's material to all selected meshes and optionally sync UV map names"

    sync_uv: BoolProperty(
        name="Sync UV Map Name",
        description="Ensure all target meshes have/keep the same UV map name (created if missing)",
        default=True
    )
    uv_map_name: StringProperty(
        name="Target UV Map",
        description="UV map name to enforce; empty uses the active object's active UV map",
        default=""
    )

    @classmethod
    def poll(cls, context):
        obj = context.view_layer.objects.active
        return obj and obj.type == 'MESH' and obj.active_material is not None

    def execute(self, context):
        active = context.view_layer.objects.active
        if not active or active.type != 'MESH':
            return {'CANCELLED'}
        mat = active.active_material
        if mat is None:
            return {'CANCELLED'}

        # Determine target UV map name if syncing
        target_uv = None
        if self.sync_uv:
            if self.uv_map_name.strip():
                target_uv = self.uv_map_name.strip()
            else:
                try:
                    uv_layers = getattr(active.data, 'uv_layers', None)
                    if uv_layers and uv_layers.active:
                        target_uv = uv_layers.active.name
                except Exception:
                    target_uv = None

        selected_meshes = [o for o in context.selected_objects if o.type == 'MESH' and o != active]
        if not selected_meshes:
            return {'CANCELLED'}

        # Lazy import of internal helper; tolerate absence gracefully.
        sync_fn = None
        if target_uv:
            try:
                from ..paintsystem.data import _sync_uv_map_to_name as _fn
                sync_fn = _fn
            except Exception:
                sync_fn = None

        assigned_count = 0
        uv_synced = 0
        for obj in selected_meshes:
            mats = getattr(obj.data, 'materials', None)
            if mats is None:
                continue
            if mat not in mats:
                try:
                    mats.append(mat)
                except Exception:
                    # Fallback: replace first slot if append fails
                    if len(mats):
                        mats[0] = mat
                assigned_count += 1
            else:
                # Ensure the object's active material pointer references mat (optional)
                try:
                    obj.active_material = mat
                except Exception:
                    pass
            if sync_fn and target_uv:
                try:
                    sync_fn(obj, target_uv)
                    uv_synced += 1
                except Exception:
                    pass

        self.report({'INFO'}, f"Material applied to {assigned_count} objects; UV synced on {uv_synced}.")
        return {'FINISHED'}


class PAINTSYSTEM_OT_SyncLayerUVNameToUsers(PSContextMixin, Operator):
    bl_idname = "paint_system.sync_layer_uv_name_to_users"
    bl_label = "Sync Layer UV Name to Users"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Ensure all mesh objects using the active material have a UV layer with the active layer's UV name"

    @classmethod
    def poll(cls, context):
        try:
            ps_ctx = cls.parse_context(context)
            return (
                ps_ctx.ps_object is not None and
                ps_ctx.active_material is not None and
                ps_ctx.active_layer is not None and
                ps_ctx.active_layer.coord_type == 'UV' and
                bool(ps_ctx.active_layer.uv_map_name)
            )
        except Exception:
            return False

    def execute(self, context):
        ps = self.parse_context(context)
        mat = ps.active_material
        layer = ps.active_layer
        target_name = layer.uv_map_name
        synced = 0
        try:
            from ..paintsystem.data import _sync_uv_map_to_name as _sync_fn
        except Exception:
            _sync_fn = None
        if not _sync_fn:
            self.report({'WARNING'}, "Sync helper unavailable")
            return {'CANCELLED'}
        for obj in context.scene.objects:
            try:
                if obj.type == 'MESH' and any(ms.material == mat for ms in obj.material_slots if ms.material):
                    _sync_fn(obj, target_name)
                    synced += 1
            except Exception:
                continue
        self.report({'INFO'}, f"Synced UV '{target_name}' on {synced} object(s)")
        return {'FINISHED'}


class PAINTSYSTEM_OT_SetActiveUVForSelected(PSContextMixin, Operator):
    bl_idname = "paint_system.set_active_uv_for_selected"
    bl_label = "Set Active UV for Selected"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Ensure selected meshes have the active layer's UV and set it active so UV edits affect the same map"

    @classmethod
    def poll(cls, context):
        try:
            ps_ctx = cls.parse_context(context)
            any_selected_mesh = any(o for o in context.selected_objects or [] if getattr(o, 'type', '') == 'MESH')
            return (
                bool(any_selected_mesh) and
                ps_ctx.active_layer is not None and
                ps_ctx.active_layer.coord_type == 'UV' and
                bool(ps_ctx.active_layer.uv_map_name)
            )
        except Exception:
            return False

    def execute(self, context):
        ps = self.parse_context(context)
        layer = ps.active_layer
        target_name = layer.uv_map_name
        if not target_name:
            self.report({'WARNING'}, "Active layer UV Map name is empty")
            return {'CANCELLED'}
        # Lazy import to avoid cycles
        try:
            from ..paintsystem.data import _sync_uv_map_to_name as _ensure
        except Exception:
            _ensure = None
        changed = 0
        for obj in context.selected_objects:
            try:
                if getattr(obj, 'type', '') != 'MESH' or not getattr(obj, 'data', None):
                    continue
                # Ensure/rename/create the target UV
                if _ensure:
                    _ensure(obj, target_name)
                # Make it active
                uv_layers = getattr(obj.data, 'uv_layers', None)
                if uv_layers and target_name in uv_layers.keys():
                    uv_layers.active = uv_layers[target_name]
                    changed += 1
            except Exception:
                continue
        self.report({'INFO'}, f"Set active UV '{target_name}' on {changed} object(s)")
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_PickPaletteColor,
    PAINTSYSTEM_OT_TogglePaintMode,
    PAINTSYSTEM_OT_SetMode,
    PAINTSYSTEM_OT_AddPresetBrushes,
    PAINTSYSTEM_OT_SelectMaterialIndex,
    PAINTSYSTEM_OT_NewMaterial,
    PAINTSYSTEM_OT_IsolateChannel,
    PAINTSYSTEM_OT_ToggleBrushEraseAlpha,
    PAINTSYSTEM_OT_ColorSampler,
    PAINTSYSTEM_OT_OpenPaintSystemPreferences,
    PAINTSYSTEM_OT_FlipNormals,
    PAINTSYSTEM_OT_RecalculateNormals,
    PAINTSYSTEM_OT_AddCameraPlane,
    PAINTSYSTEM_OT_HidePaintingTips,
    PAINTSYSTEM_OT_DuplicatePaintSystemData,
    PAINTSYSTEM_OT_ToggleTransformGizmos,
    PAINTSYSTEM_OT_AssignActiveMaterialToSelected,
    PAINTSYSTEM_OT_SyncLayerUVNameToUsers,
    PAINTSYSTEM_OT_SetActiveUVForSelected,
)

addon_keymaps = []

_register, _unregister = register_classes_factory(classes)

def register():
    _register()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
        kmi = km.keymap_items.new(
            PAINTSYSTEM_OT_ColorSampler.bl_idname, 'I', 'PRESS', repeat=True)
        kmi = km.keymap_items.new(
            PAINTSYSTEM_OT_ToggleBrushEraseAlpha.bl_idname, type='E', value='PRESS')
        addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    _unregister()