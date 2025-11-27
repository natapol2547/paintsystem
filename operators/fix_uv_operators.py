"""Fix UV Maps operators - Session-based UV retargeting workflow"""
import bpy
import math
from bpy.types import Operator
from bpy.props import StringProperty, BoolProperty, FloatProperty, EnumProperty
from bpy.utils import register_classes_factory

from .common import PSContextMixin, PSImageCreateMixin, DEFAULT_PS_UV_MAP_NAME
from ..paintsystem.data import _sync_uv_map_to_name, ensure_udim_tiles_for_objects
from ..utils import get_next_unique_name

import logging
logger = logging.getLogger("PaintSystem")


class PAINTSYSTEM_OT_FixUVSetScope(Operator):
    """Set bake scope for Fix UV Maps workflow"""
    bl_idname = "paint_system.fix_uv_set_scope"
    bl_label = "Set Bake Scope"
    bl_options = {'INTERNAL'}
    
    scope: EnumProperty(
        items=[
            ('ALL', "All Layers", ""),
            ('ACTIVE', "Active Layer", ""),
        ]
    )
    
    def execute(self, context):
        ps_scene_data = context.scene.paintsystem_scene_data
        ps_scene_data.fix_uv_bake_scope = self.scope
        return {'FINISHED'}


class PAINTSYSTEM_OT_FixUVMapsStart(PSContextMixin, PSImageCreateMixin, Operator):
    """Start Fix UV Maps session - retarget layers to new UV layout"""
    bl_idname = "paint_system.fix_uv_maps_start"
    bl_label = "Fix UV Maps"
    bl_description = "Start guided session to transfer layers to a new or edited UV map"
    bl_options = {'REGISTER', 'UNDO'}
    
    show_advanced: BoolProperty(
        name="Show Advanced Options",
        description="Show advanced options that can break material setup if used incorrectly",
        default=False
    )
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if not ps_ctx.active_layer or ps_ctx.active_layer.type != 'IMAGE':
            return False
        # Must have valid UV (including AUTO/PS UV)
        return ps_ctx.active_layer.uses_coord_type
    
    def invoke(self, context, event):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        active_layer = ps_ctx.active_layer
        obj = ps_ctx.ps_object
        mat = ps_ctx.active_material
        
        # Detect UV maps and suggest target
        if obj and obj.type == 'MESH' and obj.data.uv_layers:
            current_uv = None
            if active_layer.coord_type == 'UV':
                current_uv = active_layer.uv_map_name
            elif active_layer.coord_type == 'AUTO':
                current_uv = DEFAULT_PS_UV_MAP_NAME
            
            # Check for existing PS_ UV maps
            existing_names = [uv.name for uv in obj.data.uv_layers]
            ps_uvs = [name for name in existing_names if name.startswith("PS_")]
            
            # If PS_ UVs exist, default to USE_EXISTING mode with the most recent one
            if ps_uvs:
                ps_scene_data.fix_uv_target_mode = 'USE_EXISTING'
                # Use the last PS_ UV (most recently created)
                ps_scene_data.fix_uv_target_uv_name = ps_uvs[-1]
                logger.info(f"Found existing PS_ UVs, defaulting to USE_EXISTING with {ps_uvs[-1]}")
            else:
                # No PS_ UVs, create new one
                ps_scene_data.fix_uv_target_mode = 'COPY_ORIGINAL'
                
                # Determine base name for PS_ UV
                base_name = "UVMap"
                if current_uv:
                    # Strip PS_ prefix if present to get base name
                    if current_uv.startswith("PS_"):
                        base_name = current_uv[3:]  # Remove PS_ prefix
                    else:
                        base_name = current_uv
                
                # Find next available PS_ name
                target_name = get_next_unique_name(f"PS_{base_name}", existing_names)
                ps_scene_data.fix_uv_target_uv_name = target_name
        else:
            ps_scene_data.fix_uv_target_uv_name = "PS_UVMap"
        
        # Default to selected objects mode (most common workflow)
        if hasattr(ps_scene_data, 'fix_uv_selected_only'):
            ps_scene_data.fix_uv_selected_only = True
        else:
            self._selected_only_default = True
        
        # Defaults: prefer copy/edit existing UV; bake all layers
        try:
            ps_scene_data.fix_uv_target_mode = 'COPY_ORIGINAL'
            ps_scene_data.fix_uv_bake_scope = 'ALL'
        except Exception:
            pass

        # Initialize image settings from mixin
        self.get_coord_type(context)
        
        # Auto-enable UDIM tiles if active layer is UDIM
        if active_layer and getattr(active_layer, 'is_udim', False):
            self.use_udim = True
            self.udim_auto_detect = True
            logger.info("Auto-enabled UDIM tiles for UDIM layer")
        
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        obj = ps_ctx.ps_object
        mat = ps_ctx.active_material
        active_layer = ps_ctx.active_layer
        
        # Info banner - compact
        info_row = layout.row()
        info_row.label(text="Transfer painted layers to new UV layout", icon='INFO')
        
        # Current layer info - compact inline
        if active_layer and active_layer.image:
            current_uv = active_layer.uv_map_name if active_layer.coord_type == 'UV' else DEFAULT_PS_UV_MAP_NAME
            
            info_box = layout.box()
            info_col = info_box.column(align=True)
            info_row = info_col.row(align=True)
            info_row.label(text="Current:", icon='LAYER_ACTIVE')
            info_row.label(text=f"{active_layer.image.name}")
            
            detail_row = info_col.row(align=True)
            detail_row.label(text=f"UV: {current_uv}", icon='UV')
            
            # Show UDIM badge if applicable
            try:
                from ..utils.udim import is_udim_image, get_udim_tiles_from_image
                if is_udim_image(active_layer.image):
                    tiles = get_udim_tiles_from_image(active_layer.image)
                    detail_row.label(text=f"{len(tiles)} tiles", icon='MESH_GRID')
            except Exception:
                pass
        
        # Check if we have selected objects with the material
        selected_has_material = False
        if mat:
            selected_meshes = [o for o in context.selected_objects 
                              if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
            selected_has_material = len(selected_meshes) > 0
        
        # Show selection helpers prominently if no selection
        if not selected_has_material:
            layout.separator()
            sel_box = layout.box()
            sel_box.alert = True
            sel_col = sel_box.column(align=True)
            sel_col.label(text="⚠ No objects selected with this material", icon='ERROR')
            sel_col.label(text="Select objects to fix:", icon='HAND')
            
            btn_row = sel_col.row(align=True)
            btn_row.scale_y = 1.5
            
            sel_all_op = btn_row.operator("paint_system.select_objects_by_material", 
                                          text="Select All Objects", icon='RESTRICT_SELECT_OFF')
            sel_all_op.extend = False
            sel_all_op.switch_to_edit = True
            
            # UDIM tile selection
            if active_layer and getattr(active_layer, 'is_udim', False):
                sel_tile_op = btn_row.operator("paint_system.select_objects_by_uv_tiles",
                                               text="Select by Tile", icon='UV')
                sel_tile_op.extend = False
                sel_tile_op.clear_others = True
                sel_tile_op.switch_to_edit = True
            
            sel_col.separator()
            sel_col.label(text="Or select objects manually in 3D View", icon='BLANK1')
        
        # UV Target - show selector or text input based on mode
        layout.separator()
        uv_box = layout.box()
        
        target_mode = getattr(ps_scene_data, 'fix_uv_target_mode', 'COPY_ORIGINAL')
        if target_mode == 'USE_EXISTING' and obj and obj.type == 'MESH' and obj.data.uv_layers:
            uv_box.label(text="Target UV:", icon='UV')
            uv_box.prop_search(ps_scene_data, "fix_uv_target_uv_name", obj.data, "uv_layers", text="", icon='UV_DATA')
        else:
            uv_box.prop(ps_scene_data, "fix_uv_target_uv_name", text="New UV Name", icon='UV')

        # Bake action buttons - prominent and clear
        layout.separator()
        action_col = layout.column(align=True)
        action_col.label(text="Choose Action:", icon='RENDER_RESULT')
        
        # Large buttons for each mode
        bake_scope = getattr(ps_scene_data, 'fix_uv_bake_scope', 'ALL')
        
        btn_all = action_col.row(align=True)
        btn_all.scale_y = 1.5
        op_all = btn_all.operator("paint_system.fix_uv_set_scope", 
                                  text="Bake All Layers to New UV", 
                                  icon='OUTLINER' if bake_scope == 'ALL' else 'LAYER_USED',
                                  depress=(bake_scope == 'ALL'))
        op_all.scope = 'ALL'
        
        btn_layer = action_col.row(align=True)
        btn_layer.scale_y = 1.5
        op_layer = btn_layer.operator("paint_system.fix_uv_set_scope", 
                                      text="Bake Layer to New UV", 
                                      icon='IMAGE_DATA' if bake_scope == 'ACTIVE' else 'LAYER_USED',
                                      depress=(bake_scope == 'ACTIVE'))
        op_layer.scope = 'ACTIVE'
        
        # Compact object/layer summary
        layout.separator()
        summary_box = layout.box()
        summary_col = summary_box.column(align=True)
        
        # Object count - show selected vs all
        if mat:
            selected_only_val = bool(getattr(ps_scene_data, 'fix_uv_selected_only', True))
            
            if selected_only_val:
                selected_meshes = [o for o in context.selected_objects 
                                  if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                obj_row = summary_col.row(align=True)
                obj_row.label(text="Objects:", icon='RESTRICT_SELECT_ON')
                obj_row.label(text=f"{len(selected_meshes)} selected")
            else:
                mat_users = [o for o in context.scene.objects 
                            if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                obj_row = summary_col.row(align=True)
                obj_row.label(text="Objects:", icon='OBJECT_DATA')
                obj_row.label(text=f"{len(mat_users)} (all)")
        
        # Layer count based on scope
        bake_scope = getattr(ps_scene_data, 'fix_uv_bake_scope', 'ALL')
        if bake_scope == 'ALL':
            total_img_layers = 0
            if ps_ctx.active_group:
                for channel in ps_ctx.active_group.channels:
                    total_img_layers += sum(1 for layer in channel.flattened_layers if layer.type == 'IMAGE')
            layer_row = summary_col.row(align=True)
            layer_row.label(text="Layers:", icon='TEXTURE')
            layer_row.label(text=f"{total_img_layers} (all channels)")
        else:
            layer_row = summary_col.row(align=True)
            layer_row.label(text="Layers:", icon='TEXTURE')
            layer_row.label(text="1 (active only)")
        
        # Advanced Options (collapsible, compact)
        layout.separator()
        adv_box = layout.box()
        adv_header = adv_box.row()
        adv_header.prop(self, "show_advanced", 
                       icon='TRIA_DOWN' if self.show_advanced else 'TRIA_RIGHT',
                       icon_only=True, emboss=False)
        adv_header.label(text="Advanced", icon='SETTINGS')
        
        if self.show_advanced:
            adv_box.label(text="⚠ Expert options - use with caution", icon='ERROR')
            
            # UV Creation Mode - compact toggle
            mode_box = adv_box.box()
            mode_box.label(text="UV Mode:", icon='UV')
            mode_box.prop(ps_scene_data, "fix_uv_target_mode", expand=True)
            
            # Mode-specific options
            if ps_scene_data.fix_uv_target_mode == 'USE_EXISTING':
                # Show UV selector for existing UV maps
                if obj and obj.type == 'MESH' and obj.data.uv_layers:
                    uv_select_box = mode_box.box()
                    uv_select_col = uv_select_box.column(align=True)
                    uv_select_col.label(text="Select UV Map:", icon='UV_DATA')
                    
                    # Get all PS_ prefixed UVs
                    ps_uvs = [uv.name for uv in obj.data.uv_layers if uv.name.startswith("PS_")]
                    if ps_uvs:
                        uv_select_col.prop_search(ps_scene_data, "fix_uv_target_uv_name", obj.data, "uv_layers", text="UV", icon='UV')
                        info_row = uv_select_col.row(align=True)
                        info_row.scale_y = 0.8
                        info_row.label(text=f"{len(ps_uvs)} PS_ UV(s) available", icon='INFO')
                    else:
                        warn_row = uv_select_col.row(align=True)
                        warn_row.alert = True
                        warn_row.label(text="No PS_ UVs found!", icon='ERROR')
                        uv_select_col.label(text="Switch to Copy/Generate mode", icon='BLANK1')
            
            elif ps_scene_data.fix_uv_target_mode == 'GENERATE_NEW':
                unwrap_box = mode_box.box()
                unwrap_col = unwrap_box.column(align=True)
                unwrap_col.use_property_split = True
                unwrap_col.use_property_decorate = False
                unwrap_col.prop(ps_scene_data, "fix_uv_smart_project_angle", text="Angle")
                unwrap_col.prop(ps_scene_data, "fix_uv_smart_project_margin", text="Margin")
            
            # UV Cleanup option (not applicable for USE_EXISTING)
            if ps_scene_data.fix_uv_target_mode != 'USE_EXISTING':
                mode_box.separator()
                mode_box.prop(ps_scene_data, "fix_uv_cleanup_old", text="Remove Old UV After Bake")
            
            # Object Scope
            scope_box = adv_box.box()
            scope_box.label(text="Object Scope:", icon='OBJECT_DATA')
            
            # Scope toggle
            if hasattr(ps_scene_data, 'fix_uv_selected_only'):
                scope_box.prop(ps_scene_data, "fix_uv_selected_only", text="Use Selected Only", toggle=True)
                selected_only_val = bool(getattr(ps_scene_data, 'fix_uv_selected_only', True))
                
                # Show helper buttons only if objects are already selected
                if selected_only_val and mat:
                    selected_meshes = [o for o in context.selected_objects 
                                      if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                    
                    if selected_meshes:
                        scope_box.label(text=f"{len(selected_meshes)} selected", icon='CHECKMARK')
                        
                        # Show reselection helpers
                        scope_box.separator()
                        sel_row = scope_box.row(align=True)
                        sel_all_op = sel_row.operator("paint_system.select_objects_by_material", 
                                                      text="Select All", icon='RESTRICT_SELECT_OFF')
                        sel_all_op.extend = False
                        sel_all_op.switch_to_edit = True
                        
                        if active_layer and getattr(active_layer, 'is_udim', False):
                            sel_tile_op = sel_row.operator("paint_system.select_objects_by_uv_tiles",
                                                           text="By Tile", icon='UV')
                            sel_tile_op.extend = False
                            sel_tile_op.clear_others = True
                            sel_tile_op.switch_to_edit = True
            else:
                selected_only_val = True
        
        # Image settings - compact at bottom
        layout.separator()
        img_box = layout.box()
        img_box.label(text="New Image Settings:", icon='IMAGE_DATA')
        self.image_create_ui(img_box, context, show_name=False)
        
        # UDIM-specific bake settings (shown when UDIM enabled)
        if self.use_udim and active_layer and getattr(active_layer, 'is_udim', False):
            layout.separator()
            udim_bake_box = layout.box()
            udim_bake_box.label(text="UDIM Bake Settings:", icon='MESH_GRID')
            
            bake_col = udim_bake_box.column(align=True)
            bake_col.prop(ps_scene_data, "fix_uv_preserve_tiles", 
                         text="Smart Tile Baking", 
                         icon='CHECKBOX_HLT' if ps_scene_data.fix_uv_preserve_tiles else 'CHECKBOX_DEHLT')
            
            if ps_scene_data.fix_uv_preserve_tiles:
                info_col = bake_col.column(align=True)
                info_col.scale_y = 0.8
                info_col.label(text="Only bakes tiles marked as dirty", icon='INFO')
                info_col.label(text="Preserves unchanged tiles", icon='BLANK1')
    
    def execute(self, context):
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        mat = ps_ctx.active_material
        active_layer = ps_ctx.active_layer
        obj = ps_ctx.ps_object
        
        # Validate target UV name
        if not ps_scene_data.fix_uv_target_uv_name:
            self.report({'ERROR'}, "Target UV name cannot be empty")
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        # Get session parameters
        target_mode = ps_scene_data.fix_uv_target_mode
        target_uv_name = ps_scene_data.fix_uv_target_uv_name
        selected_only = bool(getattr(ps_scene_data, 'fix_uv_selected_only', False))
        smart_angle = ps_scene_data.fix_uv_smart_project_angle
        smart_margin = ps_scene_data.fix_uv_smart_project_margin
        
        # CRITICAL: Process ALL material users (not just selected)
        # This ensures consistent UV map name across all objects from the start
        # The selected_only setting only affects which objects are BAKED later
        all_material_users = []
        if mat:
            all_material_users = [o for o in context.scene.objects 
                                 if o and o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        else:
            all_material_users = [obj] if obj and obj.type == 'MESH' else []
        
        if not all_material_users:
            self.report({'ERROR'}, "No valid mesh objects found with this material")
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        # IMPORTANT: Keep the exact target name across all targeted objects.
        # If it already exists, we overwrite/update that UV layer instead of renaming.
        # This preserves material graph expectations that reference UV by name.
        
        # Get source UV from active layer
        source_uv_name = None
        if active_layer:
            if active_layer.coord_type == 'UV':
                source_uv_name = active_layer.uv_map_name
            elif active_layer.coord_type == 'AUTO':
                source_uv_name = DEFAULT_PS_UV_MAP_NAME
        
        # Ensure target UV name has PS_ prefix (except for USE_EXISTING which uses exact name)
        if target_mode != 'USE_EXISTING' and not target_uv_name.startswith("PS_"):
            logger.warning(f"Target UV '{target_uv_name}' doesn't have PS_ prefix, adding it")
            target_uv_name = f"PS_{target_uv_name}"
            ps_scene_data.fix_uv_target_uv_name = target_uv_name
        
        # For USE_EXISTING mode, verify the UV exists on at least one object
        if target_mode == 'USE_EXISTING':
            found_on_any = any(
                obj.type == 'MESH' and 
                obj.data.uv_layers and 
                target_uv_name in obj.data.uv_layers
                for obj in all_material_users
            )
            if not found_on_any:
                self.report({'ERROR'}, f"UV '{target_uv_name}' not found on any object. Create it first or switch mode.")
                context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
            logger.info(f"USE_EXISTING mode: will re-use existing UV '{target_uv_name}'")
        
        # Create/update UV maps on ALL material users (skip for USE_EXISTING)
        created_count = 0
        old_uv_names = {}  # Track old UV names for cleanup
        
        for tgt_obj in all_material_users:
            if not tgt_obj or tgt_obj.type != 'MESH' or not tgt_obj.data:
                continue
            
            uvs = tgt_obj.data.uv_layers
            
            # For USE_EXISTING mode, just verify and activate
            if target_mode == 'USE_EXISTING':
                if target_uv_name in uvs:
                    uvs.active = uvs[target_uv_name]
                    created_count += 1
                    logger.info(f"Activated existing UV '{target_uv_name}' on {tgt_obj.name}")
                else:
                    logger.warning(f"UV '{target_uv_name}' not found on {tgt_obj.name}, skipping")
                continue
            
            # Track old active UV for potential cleanup
            if uvs.active and uvs.active.name.startswith("PS_"):
                old_uv_names[tgt_obj.name] = uvs.active.name
            
            # Ensure target layer exists and is active
            target_layer = uvs.get(target_uv_name) if hasattr(uvs, 'get') else None
            if not target_layer:
                try:
                    target_layer = uvs.new(name=target_uv_name)
                except Exception as e:
                    logger.error(f"Unable to create UV '{target_uv_name}' on {tgt_obj.name}: {e}")
                    continue
            uvs.active = target_layer

            if target_mode == 'COPY_ORIGINAL':
                # Copy from source UV into the target UV (overwrite if exists)
                if source_uv_name and (source_uv_name in uvs):
                    src = uvs[source_uv_name]
                    dst = uvs[target_uv_name]
                    try:
                        for i, loop in enumerate(src.data):
                            dst.data[i].uv = loop.uv
                        logger.info(f"Updated '{target_uv_name}' from '{source_uv_name}' on {tgt_obj.name}")
                        created_count += 1
                    except Exception as e:
                        logger.warning(f"Copy UV failed on {tgt_obj.name}: {e}")
                else:
                    self.report({'WARNING'}, f"Source UV '{source_uv_name}' not found on {tgt_obj.name}")

            elif target_mode == 'GENERATE_NEW':
                # Smart unwrap directly into the target UV (overwrite existing layout)
                try:
                    bpy.ops.object.mode_set(mode='EDIT')
                    bpy.ops.mesh.select_all(action='SELECT')
                    bpy.ops.uv.smart_project(
                        angle_limit=math.radians(smart_angle),
                        island_margin=smart_margin,
                        area_weight=0.0,
                        correct_aspect=True,
                        scale_to_bounds=False
                    )
                    bpy.ops.object.mode_set(mode='OBJECT')
                    logger.info(f"Smart unwrapped into '{target_uv_name}' on {tgt_obj.name}")
                    created_count += 1
                except Exception as e:
                    logger.error(f"Failed to smart unwrap {tgt_obj.name}: {e}")
                    try:
                        bpy.ops.object.mode_set(mode='OBJECT')
                    except:
                        pass
        
        if created_count == 0:
            self.report({'WARNING'}, "No UV maps were created. They may already exist.")
        
        # Enter EDIT mode for UV editing with new UV active
        try:
            if obj and obj.type == 'MESH':
                context.view_layer.objects.active = obj
                
                # CRITICAL: Set new UV as active so UV Editor displays it
                if target_uv_name in obj.data.uv_layers:
                    obj.data.uv_layers.active = obj.data.uv_layers[target_uv_name]
                    logger.info(f"Set '{target_uv_name}' as active UV for editing")
                
                bpy.ops.object.mode_set(mode='EDIT')
        except Exception as e:
            logger.warning(f"Failed to enter edit mode: {e}")
        
        # NOW start the session - UV maps are ready for editing
        ps_scene_data.fix_uv_session_active = True
        
        # Initialize tile tracking for UDIM layers
        if active_layer and getattr(active_layer, 'is_udim', False):
            try:
                from ..utils.udim import detect_udim_from_uv, get_udim_tiles_from_image
                
                # Mark all tiles in new UV layout as "dirty" (need checking)
                detected_tiles = set()
                for tgt_obj in all_material_users:
                    try:
                        obj_tiles = detect_udim_from_uv(tgt_obj, target_uv_name)
                        detected_tiles.update(int(t) for t in obj_tiles)
                    except Exception:
                        pass
                
                # Mark tiles that exist in new layout as potentially dirty
                for tile in active_layer.udim_tiles:
                    if tile.number in detected_tiles:
                        tile.is_dirty = True  # Will be re-evaluated during Apply
                    else:
                        tile.is_dirty = False
                
                logger.info(f"Initialized tile tracking: {len(detected_tiles)} tiles in new UV layout")
            except Exception as e:
                logger.warning(f"Failed to initialize tile tracking: {e}")
        
        # Force update to lock painting
        from ..paintsystem.data import update_active_image
        update_active_image(None, context)
        
        context.window.cursor_set('DEFAULT')
        
        self.report({'INFO'}, f"UV Fix mode active. '{target_uv_name}' created on {created_count} object(s). Edit UVs, then click Apply in N-panel.")
        
        # Trigger UI redraw
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_FixUVMapsApply(PSContextMixin, Operator):
    """Apply UV fixes - bake all affected layers to new UV layout"""
    bl_idname = "paint_system.fix_uv_maps_apply"
    bl_label = "Apply UV Fixes"
    bl_description = "Bake layers to new UV layout and exit session"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_scene_data and getattr(ps_ctx.ps_scene_data, 'fix_uv_session_active', False)
    
    def _get_material_users(self, context, mat, selected_only):
        """Get list of mesh objects using the material"""
        from ..utils.udim import detect_udim_from_uv
        ps_ctx = self.parse_context(context)
        layer = ps_ctx.active_layer
        uv_name = None
        try:
            if layer and getattr(layer, 'coord_type', None) == 'UV':
                uv_name = layer.uv_map_name
            else:
                from .common import DEFAULT_PS_UV_MAP_NAME
                uv_name = DEFAULT_PS_UV_MAP_NAME
        except Exception:
            uv_name = None

        # Candidates: all material users (mesh only)
        candidates = []
        if mat:
            candidates = [o for o in context.scene.objects
                          if getattr(o, 'type', None) == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        else:
            obj = ps_ctx.ps_object
            candidates = [obj] if obj and getattr(obj, 'type', None) == 'MESH' else []

        if not selected_only:
            return candidates

        # Selected-only: find tiles from selected seeds, then include all candidates sharing any tile
        seeds = [o for o in context.selected_objects
                 if getattr(o, 'type', None) == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        if not seeds:
            return candidates  # fallback – behave like ALL

        seed_tiles = set()
        for so in seeds:
            try:
                for t in detect_udim_from_uv(so, uv_name):
                    seed_tiles.add(int(t))
            except Exception:
                pass
        if not seed_tiles:
            seed_tiles = {1001}

        matched = []
        for co in candidates:
            try:
                co_tiles = set(detect_udim_from_uv(co, uv_name))
                if co_tiles & seed_tiles:
                    matched.append(co)
            except Exception:
                continue
        return matched
    
    def execute(self, context):
        context.window.cursor_set('WAIT')
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        mat = ps_ctx.active_material
        active_layer = ps_ctx.active_layer
        active_group = ps_ctx.active_group
        
        if not getattr(ps_scene_data, 'fix_uv_session_active', False):
            self.report({'ERROR'}, "No active UV fix session")
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        # Get session parameters
        target_uv_name = ps_scene_data.fix_uv_target_uv_name
        selected_only = bool(getattr(ps_scene_data, 'fix_uv_selected_only', False))
        
        # Get material users (for baking)
        targets = self._get_material_users(context, mat, selected_only)
        if not targets:
            self.report({'ERROR'}, "No valid mesh objects found")
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        # CRITICAL: Ensure ALL material users (not just targets) have the new PS_ UV active
        # This ensures that even if only one tile was changed, all objects use the new UV
        all_mat_users = [o for o in context.scene.objects 
                        if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
        
        missing_uv_objs = []
        no_uv_objs = []
        synced_count = 0
        
        for obj in all_mat_users:
            if not obj or obj.type != 'MESH':
                continue
            
            # Check if object has any UV layers
            try:
                uvs = obj.data.uv_layers
                if not uvs or len(uvs) == 0:
                    no_uv_objs.append(obj.name)
                    logger.warning(f"Skipping {obj.name}: no UV layers at all")
                    continue
                
                # Check if target UV exists
                if target_uv_name not in uvs:
                    missing_uv_objs.append(obj.name)
                    continue
                
                # Set as active - CRITICAL for ensuring all edits happen on this UV
                uvs.active = uvs[target_uv_name]
                synced_count += 1
            except Exception as e:
                logger.warning(f"Failed to set active UV on {obj.name}: {e}")
                missing_uv_objs.append(obj.name)
        
        if missing_uv_objs:
            self.report({'ERROR'}, f"UV '{target_uv_name}' not found on: {', '.join(missing_uv_objs[:3])}")
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        if no_uv_objs:
            logger.warning(f"{len(no_uv_objs)} object(s) have no UV layers: {', '.join(no_uv_objs[:3])}")
        
        logger.info(f"Synced active UV '{target_uv_name}' on {synced_count} object(s)")
        
        # Collect layers to process according to scope
        layers_to_process = []
        bake_scope = getattr(ps_scene_data, 'fix_uv_bake_scope', 'ALL')
        if bake_scope == 'ACTIVE':
            if active_layer and active_layer.type == 'IMAGE' and active_layer.image:
                layers_to_process.append((ps_ctx.active_channel, active_layer))
        else:
            if active_group:
                for channel in active_group.channels:
                    for layer in channel.flattened_layers:
                        if layer.type == 'IMAGE' and layer.image:
                            layers_to_process.append((channel, layer))
            elif active_layer and active_layer.type == 'IMAGE' and active_layer.image:
                layers_to_process.append((ps_ctx.active_channel, active_layer))
        
        if not layers_to_process:
            self.report({'WARNING'}, "No IMAGE layers to process")
            # Clear session anyway
            ps_scene_data.fix_uv_session_active = False
            from ..paintsystem.data import update_active_image
            update_active_image(None, context)
            context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        
        # Process each layer
        processed_count = 0
        for channel, layer in layers_to_process:
            try:
                logger.info(f"Fix UV Maps: Processing {channel.name}/{layer.layer_name}...")
                
                # Create new image
                img_name = f"{mat.name if mat else 'Material'}_{channel.name}_{layer.layer_name}_Fixed"
                img_width = layer.image.size[0]
                img_height = layer.image.size[1]
                
                # Check if UDIM
                is_udim = False
                try:
                    from ..utils.udim import is_udim_image
                    is_udim = is_udim_image(layer.image)
                except Exception:
                    pass
                
                if is_udim:
                    # Create UDIM image
                    try:
                        from ..utils.udim import detect_udim_from_uv, create_udim_image, copy_udim_tiles, get_udim_tiles_from_image
                        # Detect tiles from new UV layout
                        new_tiles = set()
                        for obj in targets:
                            try:
                                obj_tiles = detect_udim_from_uv(obj, target_uv_name)
                                new_tiles.update(obj_tiles)
                            except Exception as e:
                                logger.warning(f"Failed to detect UDIM tiles for {obj.name}: {e}")
                        
                        if not new_tiles:
                            new_tiles = {1001}
                        
                        # Get original tiles
                        original_tiles = set(get_udim_tiles_from_image(layer.image))
                        
                        # Use tile tracking to optimize baking
                        preserve_tiles = getattr(ps_scene_data, 'fix_uv_preserve_tiles', True)
                        tiles_to_bake = new_tiles
                        
                        if preserve_tiles and original_tiles:
                            # Check layer's tile tracking for dirty/painted tiles
                            dirty_tile_numbers = set()
                            if hasattr(layer, 'udim_tiles'):
                                for tile in layer.udim_tiles:
                                    if tile.is_dirty or tile.is_painted:
                                        dirty_tile_numbers.add(tile.number)
                            
                            # Only bake tiles that are marked dirty/painted AND exist in new layout
                            if dirty_tile_numbers:
                                tiles_to_bake = new_tiles & dirty_tile_numbers
                                logger.info(f"Tile-optimized baking: {len(tiles_to_bake)} tiles marked as modified")
                            else:
                                # No tracking data - bake all tiles in new layout
                                tiles_to_bake = new_tiles
                                logger.info(f"No tile tracking data, baking all {len(tiles_to_bake)} tiles")
                        
                        # Create new UDIM image with all tiles (new layout)
                        new_image = create_udim_image(img_name, sorted(new_tiles), width=img_width, height=img_height, alpha=True)
                        logger.info(f"Created UDIM image with {len(new_tiles)} tiles")
                        
                        # If preserving tiles, copy unchanged tiles from original
                        if preserve_tiles and original_tiles:
                            tiles_to_copy = (original_tiles & new_tiles) - tiles_to_bake
                            if tiles_to_copy:
                                logger.info(f"Preserving {len(tiles_to_copy)} unchanged tiles from original")
                                if copy_udim_tiles(layer.image, new_image, list(tiles_to_copy)):
                                    logger.info(f"Preserved {len(tiles_to_copy)} unchanged tiles from original")
                    except Exception as e:
                        logger.error(f"Failed to create UDIM image: {e}")
                        new_image = bpy.data.images.new(name=img_name, width=img_width, height=img_height, alpha=True)
                else:
                    # Create regular image
                    new_image = bpy.data.images.new(name=img_name, width=img_width, height=img_height, alpha=True)
                
                new_image.colorspace_settings.name = 'sRGB'
                
                # Disable all other layers in channel temporarily
                to_be_re_enabled = []
                for other_layer in channel.flattened_layers:
                    if other_layer.enabled and other_layer != layer and other_layer.type != 'FOLDER':
                        to_be_re_enabled.append(other_layer)
                        other_layer.enabled = False
                
                # Bake layer to new UV
                try:
                    import inspect
                    sig = inspect.signature(channel.bake)
                    bake_kwargs = {
                        'use_group_tree': False,
                        'force_alpha': True,
                    }
                    if 'multi_object' in sig.parameters:
                        bake_kwargs['multi_object'] = not selected_only
                    
                    # For UDIM with selective baking, only bake modified tiles
                    # The UV map is already correct, we're just updating the image
                    channel.bake(context, mat, new_image, target_uv_name, **bake_kwargs)
                    
                    # Update layer properties
                    old_uv_name = layer.uv_map_name if layer.coord_type == 'UV' else None
                    layer.coord_type = 'UV'
                    layer.uv_map_name = target_uv_name
                    layer.image = new_image
                    
                    # Store old UV name for cleanup
                    if not hasattr(self, '_old_uv_names'):
                        self._old_uv_names = set()
                    if old_uv_name and old_uv_name != target_uv_name:
                        self._old_uv_names.add(old_uv_name)
                    
                    processed_count += 1
                    logger.info(f"Successfully processed {layer.layer_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to bake {layer.layer_name}: {e}")
                    self.report({'WARNING'}, f"Failed to bake {layer.layer_name}")
                
                # Re-enable other layers
                for other_layer in to_be_re_enabled:
                    other_layer.enabled = True
                
            except Exception as e:
                logger.error(f"Error processing layer {layer.layer_name}: {e}")
                self.report({'WARNING'}, f"Error processing {layer.layer_name}")
        
        # Clean up old UV maps if requested
        cleanup_old = getattr(ps_scene_data, 'fix_uv_cleanup_old', True)
        locked_uv = getattr(ps_scene_data, 'active_editing_uv', '') if getattr(ps_scene_data, 'lock_editing_uv', False) else ''
        
        if cleanup_old and hasattr(self, '_old_uv_names') and self._old_uv_names:
            removed_count = 0
            protected_count = 0
            for obj in targets:
                if not obj or obj.type != 'MESH':
                    continue
                try:
                    uvs = obj.data.uv_layers
                    for old_uv_name in self._old_uv_names:
                        if old_uv_name in uvs and old_uv_name != target_uv_name:
                            # Protect locked editing UV
                            if locked_uv and old_uv_name == locked_uv:
                                protected_count += 1
                                logger.info(f"Protected locked UV '{old_uv_name}' on {obj.name}")
                                continue
                            # Only remove if not the active/new UV
                            old_uv = uvs.get(old_uv_name)
                            if old_uv:
                                uvs.remove(old_uv)
                                removed_count += 1
                                logger.info(f"Removed old UV '{old_uv_name}' from {obj.name}")
                except Exception as e:
                    logger.warning(f"Failed to remove old UV from {obj.name}: {e}")
            
            if removed_count > 0:
                self.report({'INFO'}, f"Cleaned up {removed_count} old UV map(s)")
            if protected_count > 0:
                self.report({'INFO'}, f"Protected {protected_count} locked UV map(s)")
        
        # Clear session
        ps_scene_data.fix_uv_session_active = False
        
        # Restore painting
        from ..paintsystem.data import update_active_image
        update_active_image(None, context)
        
        # Return to object mode
        try:
            bpy.ops.object.mode_set(mode='OBJECT')
        except:
            pass
        
        context.window.cursor_set('DEFAULT')
        
        self.report({'INFO'}, f"UV Fix applied! Baked {processed_count} layer(s) to UV '{target_uv_name}'")
        
        # Trigger UI redraw
        for area in context.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}


class PAINTSYSTEM_OT_FixUVMapsCancel(PSContextMixin, Operator):
    """Cancel UV fix session without applying changes"""
    bl_idname = "paint_system.fix_uv_maps_cancel"
    bl_label = "Cancel UV Fixes"
    bl_description = "Exit session without applying changes"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_scene_data and getattr(ps_ctx.ps_scene_data, 'fix_uv_session_active', False)
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_scene_data = ps_ctx.ps_scene_data
        
        # Clear session
        ps_scene_data.fix_uv_session_active = False
        
        # Restore painting
        from ..paintsystem.data import update_active_image
        update_active_image(None, context)
        
        self.report({'INFO'}, "Fix UV Maps session cancelled")
        
        # Trigger UI redraw
        for area in context.screen.areas:
            area.tag_redraw()
        
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_FixUVSetScope,
    PAINTSYSTEM_OT_FixUVMapsStart,
    PAINTSYSTEM_OT_FixUVMapsApply,
    PAINTSYSTEM_OT_FixUVMapsCancel,
)

register, unregister = register_classes_factory(classes)
