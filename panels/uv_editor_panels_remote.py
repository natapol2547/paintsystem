"""UV Editor panels for Paint System"""
import bpy
from bpy.types import Panel
from bpy.utils import register_classes_factory

from .common import scale_content
from ..paintsystem.data import PSContextMixin


class IMAGE_PT_PaintSystemUVTools(PSContextMixin, Panel):
    """Paint System UV Tools panel in UV Editor"""
    bl_idname = 'IMAGE_PT_PaintSystemUVTools'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Paint System'
    bl_label = "UV Tools"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material and context.area.ui_type == 'UV')

    def draw_header(self, context):
        layout = self.layout
        layout.label(icon='UV')

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        mat = ps_ctx.active_material
        obj = context.active_object
        
        if not obj or obj.type != 'MESH':
            layout.label(text="Select a mesh object", icon='INFO')
            return
        
        ps_scene_data = ps_ctx.ps_scene_data
        active_layer = ps_ctx.active_layer
        mesh = obj.data
        
        if not mesh.uv_layers:
            layout.label(text="Object has no UV maps", icon='ERROR')
            return
        
        # Check if we're in UV editing mode
        uv_editing_active = getattr(ps_scene_data, 'uv_tools_editing_mode', False) if ps_scene_data else False
        
        if not uv_editing_active:
            # ============ SETUP STAGE ============
            # UV Mapping Setup
            box = layout.box()
            box.label(text="UV Mapping Setup:", icon='UV')
            
            # Original UV (selectable - what gets baked FROM)
            row = box.row(align=True)
            row.label(text="Original UV:", icon='TEXTURE')
            
            if ps_scene_data and hasattr(ps_scene_data, 'active_editing_uv'):
                # Selectable UV from mesh
                row.prop_search(ps_scene_data, "active_editing_uv", mesh, "uv_layers", text="")
                
                # Set from active PS layer button
                if active_layer and active_layer.type == 'IMAGE':
                    layer_uv = active_layer.uv_map_name if active_layer.coord_type == 'UV' else ""
                    if layer_uv and layer_uv != ps_scene_data.active_editing_uv:
                        set_op = row.operator("paintsystem.set_original_uv_from_layer", text="", icon='LAYER_ACTIVE')
                        set_op.uv_name = layer_uv
                
                # Lock toggle button
                if hasattr(ps_scene_data, 'lock_editing_uv') and ps_scene_data.active_editing_uv:
                    lock_icon = 'LOCKED' if ps_scene_data.lock_editing_uv else 'UNLOCKED'
                    lock_op = row.operator("paint_system.toggle_uv_lock", text="", 
                                         icon=lock_icon, emboss=False)
                    lock_op.uv_name = ps_scene_data.active_editing_uv
            
            box.separator(factor=0.5)
            
            # Target UV mode selection (what you EDIT)
            if ps_scene_data and hasattr(ps_scene_data, 'uv_tools_target_mode'):
                box.prop(ps_scene_data, "uv_tools_target_mode", text="")
                
                # Show appropriate selector/info based on mode
                target_row = box.row(align=True)
                target_row.label(text="Target UV:", icon='EDITMODE_HLT')
                
                if ps_scene_data.uv_tools_target_mode == 'USE_EXISTING':
                    if hasattr(ps_scene_data, 'uv_tools_target_uv_name'):
                        target_row.prop_search(ps_scene_data, "uv_tools_target_uv_name", mesh, "uv_layers", text="")
                        
                        # Show if target already exists
                        if ps_scene_data.uv_tools_target_uv_name:
                            if ps_scene_data.uv_tools_target_uv_name not in mesh.uv_layers:
                                info_row = box.row()
                                info_row.scale_y = 0.7
                                info_row.alert = True
                                info_row.label(text="⚠ Not found - will create", icon='ERROR')
                                
                elif ps_scene_data.uv_tools_target_mode == 'CREATE_NEW':
                    if hasattr(ps_scene_data, 'uv_tools_new_uv_name'):
                        target_row.prop(ps_scene_data, "uv_tools_new_uv_name", text="")
                        
                        # Show if name already exists
                        if ps_scene_data.uv_tools_new_uv_name:
                            if ps_scene_data.uv_tools_new_uv_name in mesh.uv_layers:
                                info_row = box.row()
                                info_row.scale_y = 0.7
                                info_row.alert = True
                                info_row.label(text="⚠ Name exists - will overwrite", icon='ERROR')
                            else:
                                info_row = box.row()
                                info_row.scale_y = 0.7
                                info_row.label(text="✓ Will create & edit this", icon='CHECKMARK')
                                
                else:  # CREATE_AUTOMATIC
                    target_row.label(text="Auto-generated")
                    info_row = box.row()
                    info_row.scale_y = 0.7
                    info_row.label(text="Will auto-unwrap & edit", icon='MOD_UVPROJECT')
        else:
            # ============ EDITING STAGE ============
            # Show UV info and bake settings
            info_box = layout.box()
            info_box.alert = True
            info_col = info_box.column(align=True)
            info_col.label(text="UV Editing Mode Active", icon='EDITMODE_HLT')
            info_col.label(text="Adjust UVs, then bake below", icon='BLANK1')
            
            layout.separator()
            
            # Show Original and Target UV
            uv_box = layout.box()
            uv_box.label(text="UV Mapping:", icon='UV')
            
            uv_col = uv_box.column(align=True)
            uv_col.scale_y = 0.8
            
            if ps_scene_data and hasattr(ps_scene_data, 'active_editing_uv'):
                row = uv_col.row()
                row.label(text="Original UV:", icon='TEXTURE')
                row.label(text=ps_scene_data.active_editing_uv)
            
            # Show target UV info
            target_mode = getattr(ps_scene_data, 'uv_tools_target_mode', 'USE_EXISTING')
            target_uv = ""
            if target_mode == 'USE_EXISTING':
                target_uv = getattr(ps_scene_data, 'uv_tools_target_uv_name', '')
            elif target_mode == 'CREATE_NEW':
                target_uv = getattr(ps_scene_data, 'uv_tools_new_uv_name', '')
            else:
                target_uv = "Auto-generated"
            
            row = uv_col.row()
            row.label(text="Target UV:", icon='EDITMODE_HLT')
            row.label(text=target_uv)
            
            # Show current active UV in editor (what's actually being edited)
            if mesh.uv_layers.active:
                uv_col.separator()
                edit_row = uv_col.row()
                edit_row.scale_y = 1.2
                
                # Highlight if editing UV doesn't match target
                actual_editing = mesh.uv_layers.active.name
                if target_mode != 'CREATE_AUTOMATIC' and actual_editing != target_uv:
                    edit_row.alert = True
                    edit_row.label(text=f"⚠ Editing: {actual_editing}", icon='ERROR')
                else:
                    edit_row.label(text=f"✓ Editing: {actual_editing}", icon='CHECKMARK')
        
            
            layout.separator()
            
            # Bake Settings
            bake_box = layout.box()
            bake_box.label(text="Bake Settings:", icon='RENDER_RESULT')
            
            # Bake Scope
            if ps_scene_data and hasattr(ps_scene_data, 'fix_uv_bake_scope'):
                bake_box.prop(ps_scene_data, "fix_uv_bake_scope", text="Bake Scope")
                
                # Show active layer info only if ACTIVE_LAYER is selected
                if ps_scene_data.fix_uv_bake_scope == 'ACTIVE' and active_layer:
                    if active_layer.type == 'IMAGE':
                        info_col = bake_box.column(align=True)
                        info_col.scale_y = 0.7
                        info_col.label(text=f"Layer: {active_layer.layer_name}", icon='LAYER_ACTIVE')
                        
                        # Show image info
                        if active_layer.image:
                            info_col.label(text=f"Image: {active_layer.image.name}", icon='IMAGE_DATA')
            
            # Object Scope - respects fix_uv_selected_only
            obj_row = bake_box.row()
            obj_row.label(text="Objects:", icon='OBJECT_DATA')
            if mat:
                selected_only = getattr(ps_scene_data, 'fix_uv_selected_only', False)
                if selected_only:
                    target_objs = [o for o in context.selected_objects 
                                  if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                    obj_row.label(text=f"Selected ({len(target_objs)} objects)")
                else:
                    target_objs = [o for o in context.scene.objects 
                                  if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                    obj_row.label(text=f"All ({len(target_objs)} objects)")
            
            # Detect UDIM from active layer
            is_udim = False
            if active_layer and active_layer.type == 'IMAGE' and active_layer.image:
                try:
                    from ..utils.udim import is_udim_image
                    is_udim = is_udim_image(active_layer.image)
                except Exception:
                    is_udim = getattr(active_layer, 'is_udim', False)
            
            # Texture Settings
            layout.separator()
            img_box = layout.box()
            img_box.label(text="Texture Settings:", icon='RENDER_RESULT')
            img_col = img_box.column(align=True)

            # Consolidated sizes box
            size_box = img_col.box()
            size_box.label(text="Square Size:", icon='PREFERENCES')
            if ps_scene_data:
                size_row = size_box.row(align=True)
                # Show unified square size if exists, else fallback to bake width
                if hasattr(ps_scene_data, 'uv_tools_square_size'):
                    size_row.prop(ps_scene_data, 'uv_tools_square_size', text="Size")
                elif hasattr(ps_scene_data, 'uv_tools_bake_width'):
                    size_row.prop(ps_scene_data, 'uv_tools_bake_width', text="Size")
                # Presets
                preset_row = size_box.row(align=True)
                preset_row.scale_y = 0.8
                for sz in (512, 1024, 2048, 4096):
                    if hasattr(bpy.types, 'PAINTSYSTEM_OT_UVToolsSetSizePreset'):
                        op = preset_row.operator("paintsystem.uvtools_set_size_preset", text=str(sz))
                        op.size = sz
                bw = getattr(ps_scene_data, 'uv_tools_square_size', getattr(ps_scene_data, 'uv_tools_bake_width', None))
                if bw:
                    dyn_row = size_box.row(align=True); dyn_row.scale_y = 0.8
                    half = max(1, int(bw/2)); double = bw * 2
                    if hasattr(bpy.types, 'PAINTSYSTEM_OT_UVToolsSetSizePreset'):
                        op_h = dyn_row.operator("paintsystem.uvtools_set_size_preset", text=f"Half {half}"); op_h.size = half
                        op_d = dyn_row.operator("paintsystem.uvtools_set_size_preset", text=f"Double {double}"); op_d.size = double

            # Margin settings
            margin_box = img_col.box()
            margin_row = margin_box.row(align=True)
            if ps_scene_data:
                margin_row.prop(ps_scene_data, "uv_tools_bake_margin", text="Margin")
                margin_row.prop(ps_scene_data, "uv_tools_margin_type", text="Type")

            # Core toggles
            toggles_box = img_col.box()
            toggles_box.label(text="Options:")
            if ps_scene_data:
                rowA = toggles_box.row(align=True); rowA.prop(ps_scene_data, "uv_tools_use_float32", text="32-bit Float", toggle=True)
                rowB = toggles_box.row(align=True); rowB.prop(ps_scene_data, "uv_tools_transparent_background", text="Transparent BG", toggle=True)
                rowC = toggles_box.row(align=True); rowC.prop(ps_scene_data, "uv_tools_overwrite_original", text="Overwrite Image", toggle=True)
                rowD = toggles_box.row(align=True); rowD.prop(ps_scene_data, "uv_tools_clean_all_old_uvs", text="Clean Old UVs", toggle=True)
                rowE = toggles_box.row(align=True); rowE.prop(ps_scene_data, "uv_tools_copy_objects_after_bake", text="Copy Objects", toggle=True)
                rowF = toggles_box.row(align=True); rowF.prop(ps_scene_data, "uv_tools_clear_image", text="Clear Before Bake", toggle=True)
                rowG = toggles_box.row(align=True); rowG.prop(ps_scene_data, "uv_tools_anti_aliasing", text="Anti-aliasing", toggle=True)
                # Keep original UV toggle (only relevant in editing mode)
                if getattr(ps_scene_data, 'uv_tools_editing_mode', False):
                    rowH = toggles_box.row(align=True); rowH.prop(ps_scene_data, "uv_tools_keep_original_uv", text="Keep Original UV", toggle=True)

            # If UV layout spans UDIM tiles, offer tile usage toggle
            if ps_scene_data and hasattr(ps_scene_data, 'uv_tools_use_udim_tiles'):
                ps_obj = ps_ctx.ps_object if ps_ctx else None
                if ps_obj and ps_obj.type == 'MESH' and ps_obj.data.uv_layers:
                    uv_layers = ps_obj.data.uv_layers
                    active_uv_name = getattr(ps_scene_data, 'active_editing_uv', '') or (uv_layers.active.name if uv_layers.active else '')
                    uv_layer = uv_layers.get(active_uv_name) if active_uv_name else uv_layers.active
                    if uv_layer:
                        try:
                            from ..paintsystem.data import get_udim_tiles
                            udim_tiles = get_udim_tiles(uv_layer)
                            if udim_tiles and udim_tiles != {1001}:
                                img_col.prop(ps_scene_data, "uv_tools_use_udim_tiles", text="Use existing UDIM tiles")
                        except Exception:
                            pass

            
            # UDIM Tile Options (if UDIM detected)
            if is_udim:
                is_udim = True
                layout.separator()
                udim_box = layout.box()
                udim_box.label(text="UDIM Tile Settings:", icon='MESH_GRID')
                
                # Rebake options
                
                # Per-tile controls
                try:
                    from ..utils.udim import get_udim_tiles_from_image
                    if active_layer.image:
                        tiles = get_udim_tiles_from_image(active_layer.image)
                        if tiles:
                            tile_col = udim_box.column(align=True)
                            tile_col.scale_y = 0.7
                            tile_col.label(text="Tiles:")
                            
                            # Show first 12 tiles as buttons for quick selection
                            for i in range(0, min(len(tiles), 12), 6):
                                trow = tile_col.row(align=True)
                                for t in tiles[i:i+6]:
                                    op = trow.operator("paintsystem.select_by_udim_tile", text=str(t))
                                    op.tile_number = t
                            
                            # Toggle: Bake selected tiles only
                            if ps_scene_data and hasattr(ps_scene_data, 'bake_selected_tiles_only'):
                                tile_col.separator()
                                tile_col.prop(ps_scene_data, "bake_selected_tiles_only", text="Bake Selected Tiles Only")
                except Exception:
                    pass
                
                # Tile-based selection in edit mode
                if context.mode == 'EDIT_MESH':
                    udim_box.separator()
                    row = udim_box.row(align=True)
                    row.operator("paintsystem.select_by_udim_tile", text="Select by Tile", icon='UV_SYNC_SELECT')
            
            # Advanced options
            layout.separator()
            adv_box = layout.box()
            row = adv_box.row()
            show_adv = getattr(ps_scene_data, 'uv_tools_show_advanced', False) if ps_scene_data else False
            row.prop(ps_scene_data, "uv_tools_show_advanced", text="Advanced", 
                    icon='TRIA_DOWN' if show_adv else 'TRIA_RIGHT', emboss=False)
            
            if show_adv and ps_scene_data and hasattr(ps_scene_data, 'fix_uv_selected_only'):
                col = adv_box.column(align=True)
                col.prop(ps_scene_data, "fix_uv_selected_only", text="Selected Objects Only", toggle=True)
                
                # Show count
                if mat:
                    if ps_scene_data.fix_uv_selected_only:
                        sel_objs = [o for o in context.selected_objects 
                                   if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
                        info_row = col.row()
                        info_row.scale_y = 0.7
                        info_row.label(text=f"{len(sel_objs)} selected", icon='RESTRICT_SELECT_ON')
            
            # Cleanup section hidden entirely during UV Editing stage
            if False:
                layout.separator()
                cleanup_box = layout.box()
                row = cleanup_box.row()
                show_cleanup = getattr(ps_scene_data, 'uv_tools_show_cleanup', False)
                row.prop(ps_scene_data, "uv_tools_show_cleanup", text="Cleanup", 
                        icon='TRIA_DOWN' if show_cleanup else 'TRIA_RIGHT', emboss=False)
                
                if show_cleanup:
                    col = cleanup_box.column(align=True)
                    col.label(text="Ensure all objects use same UV:", icon='UV')
                    
                    # Cleanup mode selector
                    if hasattr(ps_scene_data, 'uv_tools_cleanup_mode'):
                        col.prop(ps_scene_data, "uv_tools_cleanup_mode", text="")
                    
                    # Show which UV will be kept: ACTIVE LAYER's UV used for image textures
                    keep_uv = ''
                    if active_layer and active_layer.type == 'IMAGE' and getattr(active_layer, 'coord_type', 'UV') == 'UV':
                        keep_uv = getattr(active_layer, 'uv_map_name', '')
                    
                    if keep_uv:
                        info_row = col.row()
                        info_row.scale_y = 0.8
                        info_row.label(text=f"Keep: {keep_uv}", icon='CHECKMARK')
                        
                        cleanup_mode = getattr(ps_scene_data, 'uv_tools_cleanup_mode', 'NONE')
                        if cleanup_mode == 'PS_ONLY':
                            info_row.label(text="Remove: PS_* UVs")
                        elif cleanup_mode == 'ALL':
                            info_row.label(text="Remove: All other UVs")
                    
                    # Apply cleanup button
                    col.separator()
                    col.operator("paintsystem.cleanup_uv_maps", 
                                text="Apply UV Cleanup", 
                                icon='BRUSH_DATA')

                    # Last cleanup summary banner
                    if hasattr(ps_scene_data, 'uv_cleanup_last_processed') and ps_scene_data.uv_cleanup_last_processed:
                        info_box = cleanup_box.box()
                        info_box.scale_y = 0.9
                        info_box.label(text=f"Unified: {ps_scene_data.uv_cleanup_last_processed} object(s)", icon='CHECKMARK')
                        info_box.label(text=f"Kept UV: {getattr(ps_scene_data, 'uv_cleanup_last_keep_name', '')}")
                        removed = getattr(ps_scene_data, 'uv_cleanup_last_removed', 0)
                        if removed:
                            info_box.label(text=f"Removed: {removed} UV map(s)")
            
            # Action buttons
            layout.separator()
            action_box = layout.box()
            col = action_box.column(align=True)
            scale_content(context, col, 1.4, 1.4)
            
            # Bake button
            col.operator("paint_system.sync_uv_maps", 
                        text="Bake & Transfer", 
                        icon='PLAY')
            
            # Cancel/Exit button
            col.operator("paintsystem.exit_uv_editing_mode", 
                        text="Cancel UV Editing", 
                        icon='CANCEL')
        
        if not uv_editing_active:
            # Setup stage action button
            layout.separator()
            
            if active_layer and active_layer.type == 'IMAGE':
                action_box = layout.box()
                col = action_box.column(align=True)
                scale_content(context, col, 1.4, 1.4)
                
                # Show validation warnings
                can_start = True
                if ps_scene_data:
                    if not ps_scene_data.active_editing_uv:
                        warn_row = col.row()
                        warn_row.alert = True
                        warn_row.label(text="Select Original UV", icon='ERROR')
                        can_start = False
                    
                    target_mode = getattr(ps_scene_data, 'uv_tools_target_mode', 'USE_EXISTING')
                    if target_mode == 'USE_EXISTING' and not ps_scene_data.uv_tools_target_uv_name:
                        warn_row = col.row()
                        warn_row.alert = True
                        warn_row.label(text="Select Target UV", icon='ERROR')
                        can_start = False
                    elif target_mode == 'CREATE_NEW' and not ps_scene_data.uv_tools_new_uv_name:
                        warn_row = col.row()
                        warn_row.alert = True
                        warn_row.label(text="Enter Target UV name", icon='ERROR')
                        can_start = False
                
                op_row = col.row()
                op_row.enabled = can_start
                op_row.operator("paintsystem.start_uv_editing_mode", 
                               text="Adjust UV", 
                               icon='EDITMODE_HLT')
            
            # Cleanup section (available in setup too; hidden during Fix Session mode)
            if ps_scene_data and not getattr(ps_ctx.ps_scene_data, 'fix_uv_session_active', False):
                layout.separator()
                cleanup_box = layout.box()
                row = cleanup_box.row()
                show_cleanup = getattr(ps_scene_data, 'uv_tools_show_cleanup', False)
                row.prop(ps_scene_data, "uv_tools_show_cleanup", text="Cleanup", 
                        icon='TRIA_DOWN' if show_cleanup else 'TRIA_RIGHT', emboss=False)
                
                if show_cleanup:
                    col = cleanup_box.column(align=True)
                    col.label(text="Ensure all objects use same UV:", icon='UV')
                    
                    # Cleanup mode selector
                    if hasattr(ps_scene_data, 'uv_tools_cleanup_mode'):
                        col.prop(ps_scene_data, "uv_tools_cleanup_mode", text="")
                    
                    # Show which UV will be kept: ACTIVE LAYER's UV used for image textures
                    keep_uv = ''
                    if active_layer and active_layer.type == 'IMAGE' and getattr(active_layer, 'coord_type', 'UV') == 'UV':
                        keep_uv = getattr(active_layer, 'uv_map_name', '')
                    
                    if keep_uv:
                        info_row = col.row()
                        info_row.scale_y = 0.8
                        info_row.label(text=f"Keep: {keep_uv}", icon='CHECKMARK')
                        
                        cleanup_mode = getattr(ps_scene_data, 'uv_tools_cleanup_mode', 'NONE')
                        if cleanup_mode == 'PS_ONLY':
                            info_row.label(text="Remove: PS_* UVs")
                        elif cleanup_mode == 'ALL':
                            info_row.label(text="Remove: All other UVs")
                    
                    # Options
                    col.separator()
                    if hasattr(ps_scene_data, 'uv_tools_overwrite_original'):
                        col.prop(ps_scene_data, "uv_tools_overwrite_original", text="Overwrite Original Image", toggle=True)
                    if hasattr(ps_scene_data, 'uv_tools_keep_original_uv'):
                        col.prop(ps_scene_data, "uv_tools_keep_original_uv", text="Keep Original UV", toggle=True)
                    
                    # Apply cleanup button
                    col.separator()
                    col.operator("paintsystem.cleanup_uv_maps", 
                                text="Apply UV Cleanup", 
                                icon='BRUSH_DATA')

                    # Last cleanup summary banner
                    if hasattr(ps_scene_data, 'uv_cleanup_last_processed') and ps_scene_data.uv_cleanup_last_processed:
                        info_box = cleanup_box.box()
                        info_box.scale_y = 0.9
                        info_box.label(text=f"Unified: {ps_scene_data.uv_cleanup_last_processed} object(s)", icon='CHECKMARK')
                        info_box.label(text=f"Kept UV: {getattr(ps_scene_data, 'uv_cleanup_last_keep_name', '')}")
                        removed = getattr(ps_scene_data, 'uv_cleanup_last_removed', 0)
                        if removed:
                            info_box.label(text=f"Removed: {removed} UV map(s)")


class IMAGE_PT_PaintSystemObjectSelection(PSContextMixin, Panel):
    """Object selection tools in UV Editor"""
    bl_idname = 'IMAGE_PT_PaintSystemObjectSelection'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Paint System'
    bl_label = "Object Selection"
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        return bool(ps_ctx and ps_ctx.active_material and context.area.ui_type == 'UV')

    def draw_header(self, context):
        layout = self.layout
        layout.label(icon='RESTRICT_SELECT_OFF')

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        mat = ps_ctx.active_material
        active_layer = ps_ctx.active_layer
        
        # Quick selection tools
        box = layout.box()
        col = box.column(align=True)
        col.label(text="Select by Material:", icon='MATERIAL')
        
        scale_content(context, col, 1.2, 1.2)
        
        # Select all with material
        sel_all_op = col.operator("paint_system.select_objects_by_material", 
                                   text="All Objects", icon='RESTRICT_SELECT_OFF')
        sel_all_op.extend = False
        sel_all_op.switch_to_edit = False
        
        # UDIM tile selection
        if active_layer and getattr(active_layer, 'is_udim', False):
            col.separator()
            col.label(text="Select by UDIM Tile:", icon='UV')
            
            # Get tiles from active layer
            try:
                from ..utils.udim import get_udim_tiles_from_image
                if active_layer.image:
                    tiles = get_udim_tiles_from_image(active_layer.image)
                    if tiles:
                        # Create grid of tile buttons
                        tile_col = col.column(align=True)
                        tile_col.scale_y = 0.9
                        
                        # Group tiles in rows of 3
                        for i in range(0, len(tiles), 3):
                            tile_row = tile_col.row(align=True)
                            for tile_num in tiles[i:i+3]:
                                sel_tile_op = tile_row.operator("paint_system.select_objects_by_uv_tiles",
                                                               text=str(tile_num))
                                sel_tile_op.extend = False
                                sel_tile_op.clear_others = True
                                sel_tile_op.switch_to_edit = False
                    else:
                        sel_tile_op = col.operator("paint_system.select_objects_by_uv_tiles",
                                                  text="By Current Tile", icon='UV')
                        sel_tile_op.extend = False
                        sel_tile_op.clear_others = True
                        sel_tile_op.switch_to_edit = False
            except Exception:
                sel_tile_op = col.operator("paint_system.select_objects_by_uv_tiles",
                                          text="By Current Tile", icon='UV')
                sel_tile_op.extend = False
                sel_tile_op.clear_others = True
                sel_tile_op.switch_to_edit = False
        
        # Show selected object count
        if mat:
            selected_meshes = [o for o in context.selected_objects 
                              if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
            if selected_meshes:
                layout.separator()
                info_box = layout.box()
                info_box.label(text=f"{len(selected_meshes)} selected", icon='CHECKMARK')


class IMAGE_PT_PaintSystemUVSession(PSContextMixin, Panel):
    """UV Fix session panel in UV Editor"""
    bl_idname = 'IMAGE_PT_PaintSystemUVSession'
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Paint System'
    bl_label = "UV Fix Session"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.safe_parse_context(context)
        if not ps_ctx or not ps_ctx.ps_scene_data:
            return False
        return getattr(ps_ctx.ps_scene_data, 'fix_uv_session_active', False) and context.area.ui_type == 'UV'

    def draw_header(self, context):
        layout = self.layout
        layout.label(icon='CHECKMARK')

    def draw(self, context):
        ps_ctx = self.parse_context(context)
        layout = self.layout
        ps_scene_data = ps_ctx.ps_scene_data
        mat = ps_ctx.active_material
        obj = context.active_object
        
        # Session info
        box = layout.box()
        box.alert = True
        col = box.column(align=True)
        col.label(text="UV Fix Session Active", icon='TIME')
        
        if hasattr(ps_scene_data, 'fix_uv_target_uv_name'):
            col.label(text=f"Target: {ps_scene_data.fix_uv_target_uv_name}", icon='UV')
        
        # Instructions
        layout.separator()
        info_box = layout.box()
        info_col = info_box.column(align=True)
        info_col.scale_y = 0.8
        info_col.label(text="Edit UVs as needed", icon='INFO')
        info_col.label(text="Then click Apply", icon='BLANK1')
        
        # Bake scope info
        bake_scope = getattr(ps_scene_data, 'fix_uv_bake_scope', 'ALL')
        if bake_scope == 'ALL':
            info_col.label(text="Will bake: All layers", icon='TEXTURE')
        else:
            info_col.label(text="Will bake: Active layer", icon='LAYER_ACTIVE')
        
        # Object scope info
        selected_only = getattr(ps_scene_data, 'fix_uv_selected_only', True)
        if selected_only and mat:
            selected_meshes = [o for o in context.selected_objects 
                              if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
            info_col.label(text=f"Objects: {len(selected_meshes)} selected", icon='RESTRICT_SELECT_ON')
        elif mat:
            mat_users = [o for o in context.scene.objects 
                        if o.type == 'MESH' and any(ms.material == mat for ms in o.material_slots if ms.material)]
            info_col.label(text=f"Objects: {len(mat_users)} (all)", icon='OBJECT_DATA')
        
        # Action buttons
        layout.separator()
        row = layout.row(align=True)
        row.scale_y = 1.5
        row.operator("paint_system.fix_uv_maps_apply", 
                    text="Apply", 
                    icon='CHECKMARK',
                    depress=True)
        row.operator("paint_system.fix_uv_maps_cancel", 
                    text="Cancel", 
                    icon='CANCEL')


classes = (
    IMAGE_PT_PaintSystemUVTools,
    IMAGE_PT_PaintSystemObjectSelection,
    IMAGE_PT_PaintSystemUVSession,
)

register, unregister = register_classes_factory(classes)
