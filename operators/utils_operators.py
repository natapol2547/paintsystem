import math
import uuid
import addon_utils
import bpy
import gpu
from bpy.props import EnumProperty, IntProperty, BoolProperty, StringProperty, FloatProperty
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
from .common import MultiMaterialOperator, PSContextMixin, PSImageCreateMixin, DEFAULT_PS_UV_MAP_NAME
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


class PAINTSYSTEM_OT_SyncUVMaps(PSContextMixin, PSImageCreateMixin, Operator):
    """Create synced PS_ UV maps from active UV on each object"""
    bl_idname = "paint_system.sync_uv_maps"
    bl_label = "Sync UV Maps"
    bl_description = "Create PS_ prefixed UV maps from each object's active UV with unified naming"
    bl_options = {'REGISTER', 'UNDO'}
    
    target_ps_uv_name: StringProperty(
        name="PS UV Name",
        description="Name for the synced PS_ UV map (without PS_ prefix)",
        default="UVMap"
    )
    
    cleanup_old_ps: BoolProperty(
        name="Clean Old PS_ UVs",
        description="Remove other PS_ prefixed UV maps",
        default=True
    )
    
    # Multi-object support
    selected_only: BoolProperty(
        name="Selected Objects Only",
        description="Only process selected objects (unchecked = all objects with material)",
        default=True,
        options={'SKIP_SAVE'}
    )
    
    # Smart UV parameters for CREATE_AUTOMATIC mode
    smart_project_angle: FloatProperty(
        name="Angle Limit",
        description="Angle limit for smart UV project",
        default=66.0,
        min=1.0,
        max=89.0,
        subtype='ANGLE',
        options={'SKIP_SAVE'}
    )
    
    smart_project_margin: FloatProperty(
        name="Island Margin",
        description="Margin between UV islands",
        default=0.0,
        min=0.0,
        max=1.0,
        options={'SKIP_SAVE'}
    )
    
    # UDIM tile baking
    bake_selected_tiles_only: BoolProperty(
        name="Bake Selected UDIM Tiles Only",
        description="Only bake tiles marked as dirty",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    # Advanced options
    show_advanced: BoolProperty(
        name="Advanced Options",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material)
    
    def _get_target_objects(self, context, mat):
        """Get list of target objects based on selected_only setting"""
        if self.selected_only:
            return [o for o in context.selected_objects 
                   if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        return [o for o in context.scene.objects 
               if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        ps_scene_data = ps_ctx.ps_scene_data
        
        # Initialize image/UV settings from mixin
        self.get_coord_type(context)
        
        # Read selected_only from scene data
        if ps_scene_data and hasattr(ps_scene_data, 'fix_uv_selected_only'):
            self.selected_only = ps_scene_data.fix_uv_selected_only
        
        # Get target objects based on selection
        mat_users = self._get_target_objects(context, mat)
        
        # Read target mode from scene properties
        target_mode = getattr(ps_scene_data, 'uv_tools_target_mode', 'USE_EXISTING')
        
        if target_mode == 'USE_EXISTING':
            # Use existing UV - get from scene property
            target_uv = getattr(ps_scene_data, 'uv_tools_target_uv_name', '')
            if target_uv:
                self.target_ps_uv_name = target_uv
        elif target_mode == 'CREATE_NEW':
            # Create new UV - get name from scene property
            new_name = getattr(ps_scene_data, 'uv_tools_new_uv_name', 'UVMap')
            self.target_ps_uv_name = new_name
        else:  # CREATE_AUTOMATIC
            # Auto-detect most common PS_ UV base name
            ps_uv_counts = {}
            for obj in mat_users:
                for uv in obj.data.uv_layers:
                    if uv.name.startswith("PS_"):
                        base_name = uv.name[3:]  # Remove PS_ prefix
                        ps_uv_counts[base_name] = ps_uv_counts.get(base_name, 0) + 1
            
            if ps_uv_counts:
                self.target_ps_uv_name = max(ps_uv_counts, key=ps_uv_counts.get)
            else:
                # Check active UV on first object
                for obj in mat_users:
                    if obj.data.uv_layers.active:
                        active_name = obj.data.uv_layers.active.name
                        if active_name.startswith("PS_"):
                            self.target_ps_uv_name = active_name[3:]
                        else:
                            self.target_ps_uv_name = active_name
                        break
        
        # Check for UDIM
        active_layer = ps_ctx.active_layer
        if active_layer and getattr(active_layer, 'is_udim', False):
            self.use_udim = True
            self.udim_auto_detect = True
        
        # No pop-up dialog; execute directly using UV Tools panel settings
        return self.execute(context)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        mat = ps_ctx.active_material
        
        # Info banner
        box = layout.box()
        box.label(text="Transfer layers to new UV layout", icon='INFO')
        
        # Target UV name
        layout.separator()
        target_mode = getattr(ps_scene_data, 'uv_tools_target_mode', 'USE_EXISTING')
        
        uv_box = layout.box()
        uv_box.label(text="Target UV:", icon='UV')
        
        if target_mode == 'CREATE_AUTOMATIC':
            row = uv_box.row()
            row.label(text="Auto-generate: PS_")
            row.prop(self, "target_ps_uv_name", text="")
            
            # Smart UV options
            smart_col = uv_box.column(align=True)
            smart_col.prop(self, "smart_project_angle")
            smart_col.prop(self, "smart_project_margin")
        else:
            row = uv_box.row()
            if not self.target_ps_uv_name.startswith("PS_"):
                row.label(text="PS_")
            row.prop(self, "target_ps_uv_name", text="")
        
        # Object scope
        layout.separator()
        scope_box = layout.box()
        scope_box.label(text="Object Scope:", icon='OBJECT_DATA')
        scope_box.prop(self, "selected_only", toggle=True)
        
        if mat:
            target_objects = self._get_target_objects(context, mat)
            info_row = scope_box.row()
            info_row.scale_y = 0.8
            if self.selected_only:
                info_row.label(text=f"{len(target_objects)} selected object(s)", icon='RESTRICT_SELECT_ON')
            else:
                info_row.label(text=f"{len(target_objects)} object(s) with material", icon='MATERIAL')
            
            # Show first 3 objects
            if target_objects and len(target_objects) <= 5:
                obj_col = scope_box.column(align=True)
                obj_col.scale_y = 0.7
                for obj in target_objects:
                    obj_col.label(text=f"  • {obj.name}", icon='MESH_CUBE')
            elif len(target_objects) > 5:
                obj_col = scope_box.column(align=True)
                obj_col.scale_y = 0.7
                for obj in target_objects[:3]:
                    obj_col.label(text=f"  • {obj.name}", icon='MESH_CUBE')
                obj_col.label(text=f"  • ... {len(target_objects) - 3} more", icon='BLANK1')
        
        # Image settings for baking
        layout.separator()
        self.image_create_ui(layout, context, show_name=False)
        
        # Advanced options
        layout.separator()
        adv_box = layout.box()
        row = adv_box.row()
        row.prop(self, "show_advanced", icon='TRIA_DOWN' if self.show_advanced else 'TRIA_RIGHT', emboss=False)
        
        if self.show_advanced:
            col = adv_box.column(align=True)
            col.prop(self, "cleanup_old_ps")
            
            # UDIM tile options
            active_layer = ps_ctx.active_layer
            if active_layer and getattr(active_layer, 'is_udim', False):
                col.separator()
                col.prop(self, "bake_selected_tiles_only")
    
    def execute(self, context):
        # Set cursor to wait
        context.window.cursor_set('WAIT')
        
        import logging
        logger = logging.getLogger("PaintSystem")
        
        try:
            ps_ctx = self.parse_context(context)
            ps_scene_data = ps_ctx.ps_scene_data
            mat = ps_ctx.active_material
            active_channel = ps_ctx.active_channel
            
            # Read selected_only from scene data (default OFF) and save it back
            if ps_scene_data and hasattr(ps_scene_data, 'fix_uv_selected_only'):
                self.selected_only = bool(ps_scene_data.fix_uv_selected_only)
                ps_scene_data.fix_uv_selected_only = self.selected_only
            
            if not self.target_ps_uv_name:
                self.report({'ERROR'}, "UV name cannot be empty")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
            
            # Get Original UV from scene data
            original_uv_name = getattr(ps_scene_data, 'active_editing_uv', '')
            if not original_uv_name:
                self.report({'ERROR'}, "Select an Original UV first")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
            
            # Determine target mode
            target_mode = getattr(ps_scene_data, 'uv_tools_target_mode', 'USE_EXISTING')
            
            # Get target objects
            mat_users = self._get_target_objects(context, mat)
            
            if not mat_users:
                self.report({'WARNING'}, "No objects found")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
            
            # Determine full target UV name based on scene settings
            full_target_name = self.target_ps_uv_name
            if target_mode != 'USE_EXISTING' and not full_target_name.startswith("PS_"):
                full_target_name = f"PS_{self.target_ps_uv_name}"
            
            # Step 1: Create/update UV maps on all objects
            created_count = 0
            cleaned_count = 0
            
            for obj in mat_users:
                try:
                    uvs = obj.data.uv_layers
                    if not uvs:
                        logger.warning(f"No UV layers on {obj.name}")
                        continue
                    
                    # Handle CREATE_AUTOMATIC mode
                    if target_mode == 'CREATE_AUTOMATIC':
                        # Create new UV with smart unwrap
                        target_uv = uvs.get(full_target_name)
                        if not target_uv:
                            target_uv = uvs.new(name=full_target_name, do_init=True)
                            created_count += 1
                        
                        uvs.active = target_uv
                        
                        # Perform smart unwrap
                        original_mode = obj.mode
                        bpy.ops.object.mode_set(mode='EDIT')
                        bpy.ops.mesh.select_all(action='SELECT')
                        bpy.ops.uv.smart_project(
                            angle_limit=self.smart_project_angle,
                            island_margin=self.smart_project_margin
                        )
                        bpy.ops.object.mode_set(mode=original_mode)
                    else:
                        # USE_EXISTING or CREATE_NEW - copy from Original UV
                        source_uv = uvs.get(original_uv_name)
                        if not source_uv:
                            logger.warning(f"Original UV '{original_uv_name}' not found on {obj.name}")
                            continue
                        
                        # Skip if source is already the target
                        if source_uv.name == full_target_name:
                            uvs.active = source_uv
                            continue
                        
                        # Get or create target UV
                        target_uv = uvs.get(full_target_name)
                        if target_uv:
                            # Copy data to existing target
                            if source_uv != target_uv:
                                for poly in obj.data.polygons:
                                    for loop_idx in poly.loop_indices:
                                        target_uv.data[loop_idx].uv = source_uv.data[loop_idx].uv
                        else:
                            # Create new UV by copying source
                            target_uv = uvs.new(name=full_target_name, do_init=True)
                            for poly in obj.data.polygons:
                                for loop_idx in poly.loop_indices:
                                    target_uv.data[loop_idx].uv = source_uv.data[loop_idx].uv
                            created_count += 1
                        
                        uvs.active = target_uv
                    
                    # Cleanup old PS_ UVs if requested
                    if self.cleanup_old_ps:
                        ps_uvs_to_remove = [uv for uv in uvs if uv.name.startswith("PS_") and uv.name != full_target_name]
                        for uv in ps_uvs_to_remove:
                            try:
                                uvs.remove(uv)
                                cleaned_count += 1
                            except Exception as e:
                                logger.warning(f"Could not remove {uv.name} from {obj.name}: {e}")
                    
                except Exception as e:
                    logger.warning(f"Failed to process UV on {obj.name}: {e}")
                    continue
            
            # Step 2: Bake layers if channel exists
            baked_count = 0
            baked_images = []
            if active_channel:
                bake_scope = getattr(ps_scene_data, 'fix_uv_bake_scope', 'ALL')
                
                # Get layers to bake
                layers_to_bake = []
                if bake_scope == 'ACTIVE':
                    active_layer = ps_ctx.active_layer
                    if active_layer and active_layer.type == 'IMAGE':
                        layers_to_bake = [active_layer]
                else:  # ALL
                    layers_to_bake = [l for l in active_channel.layers if l.type == 'IMAGE' and l.image]
                
                # Bake each layer
                for layer in layers_to_bake:
                    try:
                        new_img = self._bake_layer_to_new_uv(context, ps_ctx, layer, full_target_name)
                        if new_img:
                            baked_images.append(new_img)
                            baked_count += 1
                    except Exception as e:
                        logger.warning(f"Failed to bake layer {layer.name}: {e}")
            
            # Return to object mode
            bpy.ops.object.mode_set(mode="OBJECT")
            
            # Report results
            context.window.cursor_set('DEFAULT')
            
            # Exit UV editing mode if active
            if ps_scene_data and getattr(ps_scene_data, 'uv_tools_editing_mode', False):
                ps_scene_data.uv_tools_editing_mode = False
            
            if baked_count > 0:
                self.report({'INFO'}, f"Created {created_count} UV(s), baked {baked_count} layer(s) to '{full_target_name}'")
            else:
                self.report({'INFO'}, f"Created/updated UV '{full_target_name}' on {len(mat_users)} object(s)")

            # Propagate baked UV to all IMAGE layers in active material (unified UV usage)
            try:
                mat = ps_ctx.active_material
                if mat and hasattr(mat, 'ps_mat_data') and mat.ps_mat_data:
                    target_uv_for_layers = full_target_name
                    # If user explicitly wants unified UV, assign to every IMAGE layer
                    for g in mat.ps_mat_data.groups:
                        for ch in g.channels:
                            for l in ch.layers:
                                if getattr(l, 'type', None) == 'IMAGE':
                                    l.coord_type = 'UV'
                                    l.uv_map_name = target_uv_for_layers
                    # If exactly one baked image, replace old images (share same baked result)
                    if len(baked_images) == 1:
                        baked_image = baked_images[0]
                        for g in mat.ps_mat_data.groups:
                            for ch in g.channels:
                                for l in ch.layers:
                                    if getattr(l, 'type', None) == 'IMAGE':
                                        # Replace only if layer previously used a different image
                                        if getattr(l, 'image', None) is not baked_image:
                                            l.image = baked_image
                        # Attempt to set image editor active image
                        try:
                            for area in context.screen.areas:
                                if area.type == 'IMAGE_EDITOR':
                                    for space in area.spaces:
                                        if space.type == 'IMAGE_EDITOR':
                                            space.image = baked_image
                        except Exception:
                            pass
                # Update Paint System scene data active UV to new one for UI feedback
                if ps_scene_data:
                    ps_scene_data.active_editing_uv = full_target_name
            except Exception as e:
                logger.warning(f"Failed to propagate baked UV/image: {e}")

            # Post-bake cleanup of old UVs (optional)
            if ps_scene_data and getattr(ps_scene_data, 'uv_tools_clean_all_old_uvs', False):
                keep_original = getattr(ps_scene_data, 'uv_tools_keep_original_uv', False)
                original_uv_name = getattr(ps_scene_data, 'active_editing_uv', '') if keep_original else ''
                removed_total = 0
                for obj in mat_users:
                    try:
                        uvs = obj.data.uv_layers
                        for uv in list(uvs):
                            if uv.name not in (full_target_name, original_uv_name):
                                try:
                                    uvs.remove(uv)
                                    removed_total += 1
                                except Exception:
                                    pass
                    except Exception:
                        pass
                if removed_total:
                    self.report({'INFO'}, f"Cleaned {removed_total} old UV map(s)")

            # Optional duplication of baked objects
            if ps_scene_data and getattr(ps_scene_data, 'uv_tools_copy_objects_after_bake', False):
                duplicated = 0
                for obj in mat_users:
                    try:
                        new_obj = obj.copy()
                        if hasattr(obj.data, 'copy'):
                            new_obj.data = obj.data.copy()
                        new_obj.name = f"{obj.name}_Baked"
                        cols = getattr(obj, 'users_collection', [])
                        if cols:
                            cols[0].objects.link(new_obj)
                        else:
                            context.scene.collection.objects.link(new_obj)
                        duplicated += 1
                    except Exception:
                        pass
                if duplicated:
                    self.report({'INFO'}, f"Duplicated {duplicated} object(s) with baked UV/image")

            return {'FINISHED'}
            
        except Exception as e:
            logger.error(f"UV sync failed: {e}")
            context.window.cursor_set('DEFAULT')
            self.report({'ERROR'}, f"Operation failed: {str(e)}")
            return {'CANCELLED'}
    
    def _bake_layer_to_new_uv(self, context, ps_ctx, layer, target_uv_name):
        """Bake a single layer to the new UV layout"""
        from ..paintsystem.data import set_layer_blend_type, get_layer_blend_type
        
        active_channel = ps_ctx.active_channel
        
        # Pull bake texture settings from scene panel
        ps_scene_data = ps_ctx.ps_scene_data
        bake_width = 1024
        bake_height = 1024
        output_width = 1024
        output_height = 1024
        bake_margin = 4
        margin_type = 'ADJACENT_FACES'
        use_float32 = False
        transparent_bg = False
        clear_image = True
        anti_aliasing = False
        
        try:
            if ps_scene_data:
                if hasattr(ps_scene_data, 'uv_tools_bake_width'):
                    bake_width = int(ps_scene_data.uv_tools_bake_width)
                if hasattr(ps_scene_data, 'uv_tools_bake_height'):
                    bake_height = int(ps_scene_data.uv_tools_bake_height)
                if hasattr(ps_scene_data, 'uv_tools_output_width'):
                    output_width = int(ps_scene_data.uv_tools_output_width)
                if hasattr(ps_scene_data, 'uv_tools_output_height'):
                    output_height = int(ps_scene_data.uv_tools_output_height)
                if hasattr(ps_scene_data, 'uv_tools_bake_margin'):
                    bake_margin = int(ps_scene_data.uv_tools_bake_margin)
                if hasattr(ps_scene_data, 'uv_tools_margin_type'):
                    margin_type = ps_scene_data.uv_tools_margin_type
                if hasattr(ps_scene_data, 'uv_tools_use_float32'):
                    use_float32 = bool(ps_scene_data.uv_tools_use_float32)
                if hasattr(ps_scene_data, 'uv_tools_transparent_background'):
                    transparent_bg = bool(ps_scene_data.uv_tools_transparent_background)
                if hasattr(ps_scene_data, 'uv_tools_clear_image'):
                    clear_image = bool(ps_scene_data.uv_tools_clear_image)
                if hasattr(ps_scene_data, 'uv_tools_anti_aliasing'):
                    anti_aliasing = bool(ps_scene_data.uv_tools_anti_aliasing)
                if hasattr(ps_scene_data, 'uv_tools_use_udim'):
                    self.use_udim = bool(ps_scene_data.uv_tools_use_udim)
                if hasattr(ps_scene_data, 'uv_tools_use_udim_tiles'):
                    self.use_udim_tiles = bool(ps_scene_data.uv_tools_use_udim_tiles)
        except Exception:
            pass

        overwrite_original = getattr(ps_scene_data, 'uv_tools_overwrite_original', False) if ps_scene_data else False
        # Prepare target image
        orig_img = getattr(layer, 'image', None)
        if overwrite_original and orig_img:
            new_image = orig_img
            self.image_name = orig_img.name
            # Resize original if dimensions differ
            try:
                if int(orig_img.size[0]) != bake_width or int(orig_img.size[1]) != bake_height:
                    orig_img.scale(bake_width, bake_height)
            except Exception:
                pass
        else:
            # Generate incremental image name from layer name (LayerName → LayerName.001)
            layer_name = getattr(layer, 'layer_name', 'Baked')
            base_name = layer_name
            counter = 1
            new_name = f"{base_name}.{counter:03d}"
            while new_name in bpy.data.images:
                counter += 1
                new_name = f"{base_name}.{counter:03d}"
            self.image_name = new_name
            self.image_width = bake_width
            self.image_height = bake_height
            new_image = self.create_image(context)
        
        # Apply float32 if requested
        if use_float32:
            new_image.use_half_precision = False
            new_image.is_float = True
        # Apply colorspace from original (if new image)
        try:
            if orig_img and new_image is not orig_img:
                cs_settings = getattr(orig_img, 'colorspace_settings', None)
                cs_name = getattr(cs_settings, 'name', None)
                if cs_name and hasattr(new_image, 'colorspace_settings') and hasattr(new_image.colorspace_settings, 'name'):
                    new_image.colorspace_settings.name = cs_name
        except Exception:
            pass
        
        # Clear image if requested
        if clear_image:
            try:
                if transparent_bg:
                    new_image.generated_color = (0, 0, 0, 0)
                else:
                    new_image.generated_color = (0, 0, 0, 1)
            except Exception:
                pass
        
        # Save layer state
        to_be_enabled_layers = []
        for other_layer in active_channel.layers:
            if other_layer.enabled and other_layer != layer:
                to_be_enabled_layers.append(other_layer)
                other_layer.enabled = False
        
        original_blend_mode = get_layer_blend_type(layer)
        set_layer_blend_type(layer, 'MIX')
        orig_is_clip = bool(layer.is_clip)
        if layer.is_clip:
            layer.is_clip = False
        
        # Bake with texture settings
        try:
            import inspect
            sig = inspect.signature(active_channel.bake)
            bake_kwargs = {'use_group_tree': False, 'force_alpha': not transparent_bg}
            if 'multi_object' in sig.parameters:
                bake_kwargs['multi_object'] = not self.selected_only
            
            # Store original render settings
            scene = context.scene
            orig_margin = scene.render.bake.margin
            orig_margin_type = scene.render.bake.margin_type
            
            try:
                scene.render.bake.margin = bake_margin
                scene.render.bake.margin_type = margin_type
                
                active_channel.bake(context, ps_ctx.active_material, new_image, target_uv_name, **bake_kwargs)
            finally:
                # Restore render settings
                scene.render.bake.margin = orig_margin
                scene.render.bake.margin_type = orig_margin_type
        except Exception as e:
            raise e
        finally:
            # Restore layer state
            if layer.is_clip != orig_is_clip:
                layer.is_clip = orig_is_clip
            set_layer_blend_type(layer, original_blend_mode)
            
            # Re-enable other layers
            for other_layer in to_be_enabled_layers:
                other_layer.enabled = True
        
        # Scale to output dimensions if different and not overwriting original (avoid double scaling)
        if (output_width != bake_width or output_height != bake_height) and (not overwrite_original):
            try:
                new_image.scale(output_width, output_height)
            except Exception:
                pass
        
        # Update layer to use new UV and image
        layer.coord_type = 'UV'
        layer.uv_map_name = target_uv_name
        layer.image = new_image
        
        return new_image  # Return baked image object for propagation


class PAINTSYSTEM_OT_CleanupAllUVs(PSContextMixin, Operator):
    """Sync or rebuild UV maps across all objects"""
    bl_idname = "paint_system.cleanup_all_uvs"
    bl_label = "Sync UV Maps"
    bl_description = "Switch every object to the selected UV map or build a new unified PS_ UV"
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(
        name="Sync Mode",
        items=[
            ('USE_EXISTING', "Use Existing", "Use the selected UV map on all objects"),
            ('CREATE_NEW', "Create New", "Create a PS_ UV map on every object from the active UV"),
        ],
        default='USE_EXISTING'
    )
    target_uv_name: StringProperty(
        name="Target UV",
        description="Existing UV map name to assign",
        default=""
    )
    new_uv_base_name: StringProperty(
        name="PS_ Base Name",
        description="Base name for the new PS_ UV (without prefix)",
        default="UVMap"
    )
    cleanup_mode: EnumProperty(
        name="Cleanup",
        items=[
            ('NONE', "Keep Others", "Keep all other UV maps"),
            ('PS_ONLY', "Remove PS_", "Remove other PS_ prefixed UV maps"),
            ('ALL', "Remove All", "Remove every other UV map"),
        ],
        default='PS_ONLY'
    )

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material)

    def _get_material_users(self, context, mat):
        return [
            o for o in context.scene.objects
            if getattr(o, 'type', None) == 'MESH'
            and any(ms.material == mat for ms in o.material_slots if ms.material)
        ]

    def _get_source_layer(self, uvs):
        source = uvs.active
        if not source and len(uvs) > 0:
            source = uvs[0]
        return source

    def _copy_uv_data(self, obj, source_layer, target_layer):
        if not source_layer or not target_layer:
            return
        # Ensure target layer has data initialized
        if len(target_layer.data) == 0:
            return
        for poly in obj.data.polygons:
            for loop_idx in poly.loop_indices:
                target_layer.data[loop_idx].uv = source_layer.data[loop_idx].uv

    def _cleanup_layers(self, logger, obj, uvs, target_name, locked_uv=''):
        if self.cleanup_mode == 'NONE':
            return 0
        removed = 0
        for uv_layer in list(uvs):
            if uv_layer.name == target_name:
                continue
            # Protect locked editing UV
            if locked_uv and uv_layer.name == locked_uv:
                logger.info(f"Protected locked UV '{locked_uv}' on {obj.name}")
                continue
            if self.cleanup_mode == 'PS_ONLY' and not uv_layer.name.startswith("PS_"):
                continue
            try:
                uvs.remove(uv_layer)
                removed += 1
            except Exception as exc:
                logger.warning(f"Could not remove {uv_layer.name} from {obj.name}: {exc}")
        return removed

    def _ensure_ps_prefix(self, name):
        name = name.strip() or "UVMap"
        return name if name.startswith("PS_") else f"PS_{name}"

    def _guess_active_uv(self, context):
        obj = context.active_object
        if obj and obj.type == 'MESH' and obj.data.uv_layers.active:
            return obj.data.uv_layers.active.name
        return ""

    def _sync_existing(self, logger, mat_users, target_name):
        processed = 0
        created = 0
        cleaned = 0
        for obj in mat_users:
            try:
                uvs = obj.data.uv_layers
            except AttributeError:
                continue
            if not uvs:
                logger.warning(f"No UV layers on {obj.name}")
                continue

            target_layer = uvs.get(target_name)
            if not target_layer:
                source_layer = self._get_source_layer(uvs)
                if not source_layer:
                    logger.warning(f"No source UV on {obj.name}")
                    continue
                # Create with do_init=True so Blender allocates .data
                target_layer = uvs.new(name=target_name, do_init=True)
                self._copy_uv_data(obj, source_layer, target_layer)
                created += 1

            uvs.active = target_layer
            cleaned += self._cleanup_layers(logger, obj, uvs, target_name)
            processed += 1
        return processed, created, cleaned

    def _create_new_ps_uv(self, logger, mat_users, target_name):
        processed = 0
        created = 0
        cleaned = 0
        for obj in mat_users:
            try:
                uvs = obj.data.uv_layers
            except AttributeError:
                continue
            if not uvs:
                logger.warning(f"No UV layers on {obj.name}")
                continue

            source_layer = self._get_source_layer(uvs)
            if not source_layer:
                logger.warning(f"No source UV on {obj.name}")
                continue

            target_layer = uvs.get(target_name)
            if not target_layer:
                # Create with do_init=True so Blender allocates .data
                target_layer = uvs.new(name=target_name, do_init=True)
                created += 1

            self._copy_uv_data(obj, source_layer, target_layer)
            uvs.active = target_layer
            cleaned += self._cleanup_layers(logger, obj, uvs, target_name, self.locked_uv)
            processed += 1
        return processed, created, cleaned

    def execute(self, context):
        import logging
        logger = logging.getLogger("PaintSystem")

        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        if not mat:
            self.report({'ERROR'}, "No active material")
            return {'CANCELLED'}
        
        # Get locked editing UV from scene data
        ps_scene_data = ps_ctx.ps_scene_data
        self.locked_uv = ''
        if ps_scene_data and getattr(ps_scene_data, 'lock_editing_uv', False):
            self.locked_uv = getattr(ps_scene_data, 'active_editing_uv', '')

        mat_users = self._get_material_users(context, mat)
        if not mat_users:
            self.report({'WARNING'}, "No mesh objects found for this material")
            return {'CANCELLED'}

        if self.mode == 'USE_EXISTING':
            target_name = self.target_uv_name.strip() or self._guess_active_uv(context)
            if not target_name:
                self.report({'ERROR'}, "Select a UV map to sync")
                return {'CANCELLED'}
            processed, created, cleaned = self._sync_existing(logger, mat_users, target_name)
        else:
            base_name = self.new_uv_base_name.strip() or "UVMap"
            target_name = self._ensure_ps_prefix(base_name)
            processed, created, cleaned = self._create_new_ps_uv(logger, mat_users, target_name)

        if processed == 0:
            self.report({'WARNING'}, "No objects were updated")
            return {'CANCELLED'}

        self.report({'INFO'}, f"Synced '{target_name}' on {processed} object(s), created {created}, removed {cleaned}")
        return {'FINISHED'}


class PAINTSYSTEM_OT_ToggleUVLock(PSContextMixin, Operator):
    """Toggle UV lock protection"""
    bl_idname = "paint_system.toggle_uv_lock"
    bl_label = "Toggle UV Lock"
    bl_description = "Protect this UV from being overwritten during bake operations"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_name: StringProperty(
        name="UV Name",
        description="UV map to toggle lock for",
        default=""
    )
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        
        if not ps_scene_data or not self.uv_name:
            return {'CANCELLED'}
        
        # Toggle lock state
        if ps_scene_data.active_editing_uv == self.uv_name and ps_scene_data.lock_editing_uv:
            # Unlock
            ps_scene_data.lock_editing_uv = False
            ps_scene_data.active_editing_uv = ""
            self.report({'INFO'}, f"Unlocked UV: {self.uv_name}")
        else:
            # Lock
            ps_scene_data.active_editing_uv = self.uv_name
            ps_scene_data.lock_editing_uv = True
            self.report({'INFO'}, f"Locked UV: {self.uv_name}")
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_SetOriginalUVFromLayer(PSContextMixin, Operator):
    """Set Original UV from active layer's UV"""
    bl_idname = "paintsystem.set_original_uv_from_layer"
    bl_label = "Set from Active Layer"
    bl_description = "Set Original UV to the UV used by the active layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_name: StringProperty(
        name="UV Name",
        description="UV name to set as original",
        default=""
    )
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        
        if not ps_scene_data or not self.uv_name:
            return {'CANCELLED'}
        
        # Set as active editing UV
        ps_scene_data.active_editing_uv = self.uv_name
        
        self.report({'INFO'}, f"Original UV set to: {self.uv_name}")
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_StartUVEditingMode(PSContextMixin, Operator):
    """Enter UV editing mode with setup target UV"""
    bl_idname = "paintsystem.start_uv_editing_mode"
    bl_label = "Adjust UV"
    bl_description = "Setup target UV and enter editing mode"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        active_layer = ps_ctx.active_layer
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            self.report({'ERROR'}, "Select a mesh object")
            return {'CANCELLED'}
        
        if not ps_scene_data:
            self.report({'ERROR'}, "Paint System scene data not found")
            return {'CANCELLED'}
        
        mesh = obj.data
        
        # Store original active UV for cancel restoration
        if obj.type == 'MESH' and mesh.uv_layers.active:
            ps_scene_data.uv_tools_original_active_uv = mesh.uv_layers.active.name
        
        # Prefill panel texture settings from active layer image if present
        if active_layer and active_layer.type == 'IMAGE' and active_layer.image:
            try:
                orig_img = active_layer.image
                ow, oh = int(orig_img.size[0]), int(orig_img.size[1])
                
                # Bake dimensions - match original
                ps_scene_data.uv_tools_bake_width = ow
                ps_scene_data.uv_tools_bake_height = oh
                
                # Output dimensions - match original
                ps_scene_data.uv_tools_output_width = ow
                ps_scene_data.uv_tools_output_height = oh
                
                # UDIM detection
                try:
                    from ..utils.udim import is_udim_image
                    if is_udim_image(orig_img):
                        ps_scene_data.uv_tools_use_udim = True
                        ps_scene_data.uv_tools_use_udim_tiles = True
                except Exception:
                    pass
            except Exception:
                pass
        
        # Validate settings
        if not ps_scene_data.active_editing_uv:
            self.report({'ERROR'}, "Select Original UV")
            return {'CANCELLED'}
        
        target_mode = ps_scene_data.uv_tools_target_mode
        target_uv = ""
        
        # Determine target UV name based on mode
        if target_mode == 'USE_EXISTING':
            target_uv = ps_scene_data.uv_tools_target_uv_name
            if not target_uv:
                self.report({'ERROR'}, "Select Target UV")
                return {'CANCELLED'}
            
            # Create if doesn't exist
            if target_uv not in mesh.uv_layers:
                mesh.uv_layers.new(name=target_uv)
                self.report({'INFO'}, f"Created UV map '{target_uv}'")
        
        elif target_mode == 'CREATE_NEW':
            target_uv = ps_scene_data.uv_tools_new_uv_name
            if not target_uv:
                self.report({'ERROR'}, "Enter Target UV name")
                return {'CANCELLED'}
            
            # Create or overwrite
            if target_uv in mesh.uv_layers:
                self.report({'INFO'}, f"Overwriting existing UV map '{target_uv}'")
            else:
                mesh.uv_layers.new(name=target_uv)
                self.report({'INFO'}, f"Created UV map '{target_uv}'")
        
        else:  # CREATE_AUTOMATIC
            target_uv = "PS_AutoUV"
            if target_uv not in mesh.uv_layers:
                uv_layer = mesh.uv_layers.new(name=target_uv)
            else:
                uv_layer = mesh.uv_layers[target_uv]
            
            # Auto unwrap with Smart UV Project
            mesh.uv_layers.active = uv_layer
            
            # Enter edit mode to unwrap
            if context.mode != 'EDIT_MESH':
                bpy.ops.object.mode_set(mode='EDIT')
            
            # Select all
            bpy.ops.mesh.select_all(action='SELECT')
            
            # Smart UV project
            angle_limit = getattr(ps_scene_data, 'fix_uv_smart_angle', 66.0)
            island_margin = getattr(ps_scene_data, 'fix_uv_smart_margin', 0.0)
            bpy.ops.uv.smart_project(angle_limit=angle_limit, island_margin=island_margin)
            
            self.report({'INFO'}, f"Auto-unwrapped to '{target_uv}'")
        
        # Copy original UV data to target
        if target_uv and target_uv in mesh.uv_layers:
            orig_uv = mesh.uv_layers.get(ps_scene_data.active_editing_uv)
            target_uv_layer = mesh.uv_layers[target_uv]
            
            if orig_uv and target_mode != 'CREATE_AUTOMATIC':
                # Copy UV data from original to target
                for orig_loop, target_loop in zip(orig_uv.data, target_uv_layer.data):
                    target_loop.uv = orig_loop.uv.copy()
            
            # Set target as active UV for editing
            mesh.uv_layers.active = target_uv_layer
        
        # Enter UV editing mode
        ps_scene_data.uv_tools_editing_mode = True
        
        self.report({'INFO'}, f"Editing '{target_uv}' - adjust UVs then bake")
        return {'FINISHED'}


class PAINTSYSTEM_OT_ExitUVEditingMode(PSContextMixin, Operator):
    """Exit UV editing mode without baking"""
    bl_idname = "paintsystem.exit_uv_editing_mode"
    bl_label = "Cancel UV Editing"
    bl_description = "Exit UV editing mode without baking"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        obj = context.active_object
        
        # Restore original active UV
        if ps_scene_data and obj and obj.type == 'MESH':
            orig_uv_name = getattr(ps_scene_data, 'uv_tools_original_active_uv', '')
            if orig_uv_name and orig_uv_name in obj.data.uv_layers:
                obj.data.uv_layers.active = obj.data.uv_layers[orig_uv_name]
        
        if ps_scene_data:
            ps_scene_data.uv_tools_editing_mode = False
        
        self.report({'INFO'}, "Exited UV editing mode")
        return {'FINISHED'}


class PAINTSYSTEM_OT_SelectByUDIMTile(PSContextMixin, Operator):
    """Select mesh faces by UDIM tile number"""
    bl_idname = "paintsystem.select_by_udim_tile"
    bl_label = "Select by UDIM Tile"
    bl_description = "Select mesh faces in Edit Mode by UDIM tile number"
    bl_options = {'REGISTER', 'UNDO'}
    
    tile_number: IntProperty(
        name="Tile Number",
        description="UDIM tile number to select (1001, 1002, etc.)",
        default=1001,
        min=1001,
        max=1999
    )
    
    @classmethod
    def poll(cls, context):
        return (context.mode == 'EDIT_MESH' and 
                context.active_object and 
                context.active_object.type == 'MESH' and
                context.active_object.data.uv_layers.active)
    
    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def execute(self, context):
        import bmesh
        
        obj = context.active_object
        mesh = obj.data
        bm = bmesh.from_edit_mesh(mesh)
        
        # Use active UV layer (which should be the target UV in editing mode)
        uv_layer = bm.loops.layers.uv.active
        if not uv_layer:
            self.report({'ERROR'}, "No active UV layer")
            return {'CANCELLED'}
        
        # Calculate UDIM tile grid position
        tile_u = (self.tile_number - 1001) % 10
        tile_v = (self.tile_number - 1001) // 10
        
        selected_count = 0
        
        # Deselect all first
        for face in bm.faces:
            face.select = False
        
        # Select faces with ALL UVs in the target tile
        for face in bm.faces:
            # Check if all UV coordinates of this face are in the target tile
            all_in_tile = True
            for loop in face.loops:
                uv = loop[uv_layer].uv
                # Check if UV is within tile bounds [tile_u, tile_u+1) x [tile_v, tile_v+1)
                if not (tile_u <= uv.x < tile_u + 1 and tile_v <= uv.y < tile_v + 1):
                    all_in_tile = False
                    break
            
            if all_in_tile:
                face.select = True
                selected_count += 1
        
        # Update mesh
        bm.select_flush_mode()
        bmesh.update_edit_mesh(mesh, loop_triangles=False, destructive=False)
        
        self.report({'INFO'}, f"Selected {selected_count} faces in tile {self.tile_number}")
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_CleanupUVMaps(PSContextMixin, Operator):
    """Cleanup UV maps on all objects with material"""
    bl_idname = "paintsystem.cleanup_uv_maps"
    bl_label = "Cleanup UV Maps"
    bl_description = "Ensure all objects use the same UV map and optionally remove other UV maps"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        mat = ps_ctx.active_material
        
        if not ps_scene_data:
            self.report({'ERROR'}, "Paint System scene data not found")
            return {'CANCELLED'}
        
        # Determine which UV to keep
        # Prefer the UV map currently used by layers, not the editing/target selector
        keep_uv_name = ''
        try:
            active_layer = ps_ctx.active_layer
            if active_layer and getattr(active_layer, 'type', None) == 'IMAGE':
                # If the active layer uses UV coordinates, take its uv_map_name
                if getattr(active_layer, 'coord_type', 'UV') == 'UV':
                    keep_uv_name = getattr(active_layer, 'uv_map_name', '') or ''
            
            # If not found, try to infer from active channel layers
            if not keep_uv_name and ps_ctx.active_channel:
                for l in ps_ctx.active_channel.layers:
                    if getattr(l, 'type', None) == 'IMAGE' and getattr(l, 'coord_type', 'UV') == 'UV':
                        uvn = getattr(l, 'uv_map_name', '')
                        if uvn:
                            keep_uv_name = uvn
                            break
        except Exception:
            pass
        
        # Fallback to UI target mode if no layer-based UV found
        if not keep_uv_name:
            target_mode = getattr(ps_scene_data, 'uv_tools_target_mode', 'USE_EXISTING')
            if target_mode == 'USE_EXISTING':
                keep_uv_name = getattr(ps_scene_data, 'uv_tools_target_uv_name', '')
            elif target_mode == 'CREATE_NEW':
                keep_uv_name = getattr(ps_scene_data, 'uv_tools_new_uv_name', '')
            else:  # CREATE_AUTOMATIC
                keep_uv_name = "PS_AutoUV"
        
        if not keep_uv_name:
            self.report({'ERROR'}, "No target UV specified")
            return {'CANCELLED'}
        
        # Decide desired unified UV name: prefer layer-used UV, else user-provided new name
        desired_uv_name = keep_uv_name or getattr(ps_scene_data, 'uv_tools_new_uv_name', '')
        if not desired_uv_name:
            self.report({'ERROR'}, "No UV name to unify to. Set Target/New UV name or ensure layers use a UV.")
            return {'CANCELLED'}

        # Get cleanup mode
        cleanup_mode = getattr(ps_scene_data, 'uv_tools_cleanup_mode', 'NONE')
        
        # Get all objects with material
        selected_only = getattr(ps_scene_data, 'fix_uv_selected_only', False)
        if selected_only:
            mat_users = [o for o in context.selected_objects 
                        if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        else:
            mat_users = [o for o in context.scene.objects 
                        if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        
        if not mat_users:
            self.report({'WARNING'}, "No objects found with this material")
            return {'CANCELLED'}
        
        processed_count = 0
        removed_count = 0
        
        for obj in mat_users:
            try:
                mesh = obj.data
                uvs = mesh.uv_layers
                
                if not uvs:
                    continue
                
                # Source UV: the one layers use (keep_uv_name), else active
                source_uv = uvs.get(keep_uv_name) if keep_uv_name else None
                if source_uv is None:
                    source_uv = uvs.active
                
                # Target unified UV: desired_uv_name
                target_uv = uvs.get(desired_uv_name)
                if target_uv is None:
                    # Create new and copy coordinates from source
                    target_uv = uvs.new(name=desired_uv_name, do_init=True)
                    try:
                        for poly in mesh.polygons:
                            for loop_idx in poly.loop_indices:
                                target_uv.data[loop_idx].uv = source_uv.data[loop_idx].uv
                    except Exception:
                        # Fallback to loop-range copy
                        for i in range(min(len(target_uv.data), len(source_uv.data))):
                            target_uv.data[i].uv = source_uv.data[i].uv
                else:
                    # If exists, ensure it has same coordinates as source
                    try:
                        for poly in mesh.polygons:
                            for loop_idx in poly.loop_indices:
                                target_uv.data[loop_idx].uv = source_uv.data[loop_idx].uv
                    except Exception:
                        for i in range(min(len(target_uv.data), len(source_uv.data))):
                            target_uv.data[i].uv = source_uv.data[i].uv
                
                # Set as active
                uvs.active = target_uv
                
                # Cleanup other UVs based on mode
                if cleanup_mode == 'PS_ONLY':
                    # Remove other PS_ prefixed UVs
                    uvs_to_remove = [uv for uv in uvs if uv.name.startswith("PS_") and uv.name != keep_uv_name]
                    for uv in uvs_to_remove:
                        try:
                            uvs.remove(uv)
                            removed_count += 1
                        except Exception:
                            pass
                
                elif cleanup_mode == 'ALL':
                    # Remove all other UVs
                    uvs_to_remove = [uv for uv in uvs if uv.name != keep_uv_name]
                    for uv in uvs_to_remove:
                        try:
                            uvs.remove(uv)
                            removed_count += 1
                        except Exception:
                            pass
                
                processed_count += 1
                
            except Exception as e:
                import logging
                logger = logging.getLogger("PaintSystem")
                logger.warning(f"Failed to cleanup UVs on {obj.name}: {e}")
                continue
        
        # Update all IMAGE layers in the active material to use the unified UV name
        try:
            mat = ps_ctx.active_material
            if mat and hasattr(mat, 'ps_mat_data') and mat.ps_mat_data:
                for g in mat.ps_mat_data.groups:
                    for ch in g.channels:
                        for l in ch.layers:
                            if getattr(l, 'type', None) == 'IMAGE' and getattr(l, 'coord_type', 'UV') == 'UV':
                                l.uv_map_name = desired_uv_name
        except Exception:
            pass

        # Store summary on scene data for panel feedback
        try:
            if ps_ctx.ps_scene_data:
                ps_ctx.ps_scene_data.uv_cleanup_last_processed = processed_count
                ps_ctx.ps_scene_data.uv_cleanup_last_removed = removed_count
                ps_ctx.ps_scene_data.uv_cleanup_last_keep_name = desired_uv_name
        except Exception:
            pass

        if cleanup_mode == 'NONE':
            self.report({'INFO'}, f"Unified to '{desired_uv_name}' on {processed_count} object(s)")
        else:
            self.report({'INFO'}, f"Unified to '{desired_uv_name}' on {processed_count} object(s), removed {removed_count} UV map(s)")
        
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


class PAINTSYSTEM_OT_UVToolsSetSizePreset(PSContextMixin, Operator):
    """Quickly set bake/output sizes to a preset (TexTools style)"""
    bl_idname = "paintsystem.uvtools_set_size_preset"
    bl_label = "Set Size Preset"
    bl_description = "Apply size preset to bake and output dimensions"
    bl_options = {'REGISTER', 'UNDO'}

    size: IntProperty(
        name="Size",
        description="Preset size for bake & output",
        default=1024,
        min=1,
    )

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = getattr(ps_ctx, 'ps_scene_data', None)
        if not ps_scene_data:
            return {'CANCELLED'}
        # Set all four dimensions if present
        for attr in ("uv_tools_bake_width", "uv_tools_bake_height", "uv_tools_output_width", "uv_tools_output_height"):
            if hasattr(ps_scene_data, attr):
                setattr(ps_scene_data, attr, self.size)
        # Also set unified square size if available (triggers update callback keeping square)
        if hasattr(ps_scene_data, 'uv_tools_square_size'):
            ps_scene_data.uv_tools_square_size = self.size
        self.report({'INFO'}, f"Set bake/output size to {self.size}")
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


class PAINTSYSTEM_OT_SetActiveUVOnAll(PSContextMixin, Operator):
    """Set a specific UV map as active on all objects using the active material"""
    bl_idname = "paint_system.set_active_uv_on_all"
    bl_label = "Set Active UV on All"
    bl_description = "Set this UV map as active on all objects with the active material"
    bl_options = {'REGISTER', 'UNDO'}
    
    uv_name: bpy.props.StringProperty(
        name="UV Name",
        description="UV map name to set as active",
        default=""
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material)
    
    def execute(self, context):
        import logging
        logger = logging.getLogger("PaintSystem")
        
        ps_ctx = self.parse_context(context)
        mat = ps_ctx.active_material
        
        if not self.uv_name:
            self.report({'ERROR'}, "UV name cannot be empty")
            return {'CANCELLED'}
        
        # Get all material users
        mat_users = [o for o in context.scene.objects 
                    if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        
        if not mat_users:
            self.report({'WARNING'}, "No objects found with this material")
            return {'CANCELLED'}
        
        synced_count = 0
        skipped_count = 0
        
        for obj in mat_users:
            try:
                uvs = obj.data.uv_layers
                if not uvs or len(uvs) == 0:
                    logger.warning(f"Skipping {obj.name}: no UV layers")
                    skipped_count += 1
                    continue
                
                # Check if UV exists
                if self.uv_name in uvs:
                    uvs.active = uvs[self.uv_name]
                    synced_count += 1
                else:
                    logger.warning(f"UV '{self.uv_name}' not found on {obj.name}, has: {[uv.name for uv in uvs]}")
                    skipped_count += 1
                
            except Exception as e:
                logger.warning(f"Failed to set active UV on {obj.name}: {e}")
                skipped_count += 1
                continue
        
        msg = f"Set '{self.uv_name}' as active on {synced_count} object(s)"
        if skipped_count > 0:
            msg += f" ({skipped_count} skipped - no UV or UV not found)"
        self.report({'INFO'}, msg)
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
    PAINTSYSTEM_OT_SyncUVMaps,
    PAINTSYSTEM_OT_CleanupAllUVs,
    PAINTSYSTEM_OT_ToggleUVLock,
    PAINTSYSTEM_OT_SetOriginalUVFromLayer,
    PAINTSYSTEM_OT_StartUVEditingMode,
    PAINTSYSTEM_OT_ExitUVEditingMode,
    PAINTSYSTEM_OT_SelectByUDIMTile,
    PAINTSYSTEM_OT_CleanupUVMaps,
    PAINTSYSTEM_OT_AddCameraPlane,
    PAINTSYSTEM_OT_HidePaintingTips,
    PAINTSYSTEM_OT_DuplicatePaintSystemData,
    PAINTSYSTEM_OT_ToggleTransformGizmos,
    PAINTSYSTEM_OT_AssignActiveMaterialToSelected,
    PAINTSYSTEM_OT_SetActiveUVForSelected,
    PAINTSYSTEM_OT_SetActiveUVOnAll,
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