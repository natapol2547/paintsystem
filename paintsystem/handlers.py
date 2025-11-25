import bpy
import logging
from .data import get_global_layer, sort_actions, parse_context, get_all_layers, is_valid_uuidv4
from .graph.basic_layers import get_layer_version_for_type
import time
from .graph.nodetree_builder import get_nodetree_version
import uuid
from .donations import get_donation_info

logger = logging.getLogger("PaintSystem")

# Gizmo state tracking
_gizmo_owner = object()
_last_mode = None
_gizmos_were_enabled = False

@bpy.app.handlers.persistent
def frame_change_pre(scene):
    if not hasattr(scene, 'ps_scene_data'):
        return
    update_task = {}
    for layer in get_all_layers():
        # Skip layers with no actions for performance
        if not layer.actions or len(layer.actions) == 0:
            continue
        sorted_actions = sort_actions(bpy.context, layer)
        for action in sorted_actions:
            match action.action_bind:
                case 'FRAME':
                    if action.frame <= scene.frame_current:
                        # print(f"Frame {action.frame} found at frame {scene.frame_current}")
                        if action.action_type == 'ENABLE' and update_task.get(layer, layer.enabled) == False:
                            update_task[layer] = True
                        elif action.action_type == 'DISABLE' and update_task.get(layer, layer.enabled) == True:
                            update_task[layer] = False
                case 'MARKER':
                    marker = scene.timeline_markers.get(action.marker_name)
                    if marker and marker.frame <= scene.frame_current:
                        # print(f"Marker {marker.frame} found at frame {scene.frame_current}")
                        if action.action_type == 'ENABLE' and update_task.get(layer, layer.enabled) == False:
                            update_task[layer] = True
                        elif action.action_type == 'DISABLE' and update_task.get(layer, layer.enabled) == True:
                            update_task[layer] = False
                case _:
                    pass
    for layer, enabled in update_task.items():
        if layer.enabled != enabled:
            layer.enabled = enabled


def load_paint_system_data():
    print(f"Loading Paint System data...")
    start_time = time.time()
    ps_ctx = parse_context(bpy.context)
    if not ps_ctx.ps_scene_data:
        return
    
    # Global Layer Versioning. Will be removed in the future.
    for global_layer in ps_ctx.ps_scene_data.layers:
        target_version = get_layer_version_for_type(global_layer.type)
        if get_nodetree_version(global_layer.node_tree) != target_version:
            print(f"Updating layer {global_layer.name} to version {target_version}")
            try:
                global_layer.update_node_tree(bpy.context)
            except Exception as e:
                logger.error(f"Error updating layer {global_layer.name}: {e}")
    
    seen_global_layers_map = {}
    # Layer Versioning - index PS materials first for performance
    ps_materials = [mat for mat in bpy.data.materials if hasattr(mat, 'ps_mat_data')]
    for mat in ps_materials:
            for group in mat.ps_mat_data.groups:
                for channel in group.channels:
                    has_migrated_global_layer = False
                    for layer in channel.layers:
                        # Check if layer has valid uuid
                        if not is_valid_uuidv4(layer.uid):
                            layer.uid = str(uuid.uuid4())
                        if layer.name and not layer.layer_name: # data from global layer is not copied to layer
                            global_layer = get_global_layer(layer)
                            if global_layer:
                                layer.auto_update_node_tree = False
                                print(f"Migrating global layer data ({global_layer.name}) to layer data ({layer.name}) ({layer.layer_name})")
                                has_migrated_global_layer = True
                                layer.layer_name = layer.name
                                layer.uid = global_layer.name
                                if global_layer.name not in seen_global_layers_map:
                                    seen_global_layers_map[global_layer.name] = [mat, global_layer]
                                    for prop in global_layer.bl_rna.properties:
                                        pid = getattr(prop, 'identifier', '')
                                        if not pid or getattr(prop, 'is_readonly', False):
                                            continue
                                        if pid in {"layer_name"}:
                                            continue
                                        if pid in {"name", "uid"}:
                                            continue
                                        setattr(layer, pid, getattr(global_layer, pid))
                                else:
                                    # as linked layer, properties will not be copied
                                    print(f"Layer {layer.name} is linked to {global_layer.name}")
                                    mat, global_layer = seen_global_layers_map[global_layer.name]
                                    layer.linked_layer_uid = global_layer.name
                                    layer.linked_material = mat
                                layer.auto_update_node_tree = True
                                layer.update_node_tree(bpy.context)
                        
                        # Current version of the layer
                        mix_node = layer.mix_node
                        blend_mode = "MIX"
                        if mix_node:
                            blend_mode = str(mix_node.blend_type)
                        if blend_mode != layer.blend_mode and layer.blend_mode != "PASSTHROUGH":
                            print(f"Layer {layer.name} has blend mode {blend_mode} but {layer.blend_mode} is set")
                            layer.blend_mode = blend_mode
                    if has_migrated_global_layer:
                        channel.update_node_tree(bpy.context)
    # ps_scene_data Versioning
    # As layers in ps_scene_data is not used anymore, we can remove it in the future
    ps_scene_data = getattr(bpy.context.scene, 'ps_scene_data', None)
    if ps_scene_data and hasattr(ps_scene_data, 'layers') and len(ps_scene_data.layers) > 0:
        # print(f"Removing ps_scene_data")
        ps_scene_data.layers.clear()
        ps_scene_data.last_selected_ps_object = None
        ps_scene_data.last_selected_material = None
            
    print(f"Paint System: Checked {len(ps_ctx.ps_scene_data.layers) if ps_ctx.ps_scene_data else 0} layers in {round((time.time() - start_time) * 1000, 2)} ms")


@bpy.app.handlers.persistent
def load_post(scene):
    
    load_paint_system_data()
    # Check for donation info
    get_donation_info()
    # if donation_info:
    #     print(f"Donation info: {donation_info}")

@bpy.app.handlers.persistent
def save_handler(scene: bpy.types.Scene):
    print("Saving Paint System data...")
    images = set()
    
    for mat in bpy.data.materials:
        if hasattr(mat, 'ps_mat_data'):
            for group in mat.ps_mat_data.groups:
                for channel in group.channels:
                    image = channel.bake_image
                    if image and image.is_dirty:
                        images.add(image)
                    for layer in channel.layers:
                        image = layer.image
                        if image:
                            images.add(image)
            
    for image in images:
        if not image.is_dirty:
            continue
        if image.packed_file or image.filepath == '':
            print(f"Packing image {image.name}")
            image.pack()
        else:
            print(f"Saving image {image.name}")
            image.save()


@bpy.app.handlers.persistent
def refresh_image(scene: bpy.types.Scene):
    ps_ctx = parse_context(bpy.context)
    active_layer = ps_ctx.active_layer
    if active_layer and active_layer.image:
        active_layer.image.reload()


@bpy.app.handlers.persistent
def paint_system_object_update(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph = None):
    """Handle object changes and update paint canvas - based on UcuPaint's ypaint_last_object_update"""
    
    try: 
        obj = bpy.context.object
        mat = obj.active_material if obj else None
    except: 
        return
    
    if not obj or not hasattr(scene, 'ps_scene_data'):
        return
    
    ps_scene_data = scene.ps_scene_data
    
    # Read-only comparison - don't write in depsgraph_update_post
    current_obj = obj
    current_mat = mat
    
    # Check if changed without writing (getattr handles missing attributes safely)
    last_obj = getattr(ps_scene_data, 'last_selected_object', None)
    last_mat = getattr(ps_scene_data, 'last_selected_material', None)
    
    if last_obj != current_obj or last_mat != current_mat:
        # Schedule update via timer instead of writing directly
        def update_tracking():
            try:
                scene.ps_scene_data.last_selected_object = current_obj
                scene.ps_scene_data.last_selected_material = current_mat
                
                if obj and obj.type == 'MESH' and mat and hasattr(mat, 'ps_mat_data'):
                    from .data import update_active_image
                    try:
                        update_active_image(None, bpy.context) 
                    except Exception as e:
                        logger.error(f"Failed to update active image: {e}")
            except Exception as e:
                logger.error(f"Error in material tracking timer: {e}")
            return None  # Run once
        
        # Schedule with minimal delay
        bpy.app.timers.register(update_tracking, first_interval=0.0)


# --- On Addon Enable ---
def on_addon_enable():
    load_post(bpy.context.scene)


def mode_change_handler(*args):
    """Handle mode changes to auto-disable gizmos in paint/sculpt modes"""
    global _last_mode, _gizmos_were_enabled
    
    try:
        context = bpy.context
        obj = context.object
        if not obj:
            return
        
        current_mode = obj.mode
        
        # Modes where gizmos should be disabled
        paint_modes = {'PAINT_TEXTURE', 'SCULPT', 'PAINT_VERTEX', 'PAINT_WEIGHT'}
        
        # Determine mode transitions
        entering_paint = current_mode in paint_modes and (_last_mode is None or _last_mode not in paint_modes)
        leaving_paint = _last_mode is not None and _last_mode in paint_modes and current_mode not in paint_modes
        
        # Skip if mode didn't actually change (but allow first run when _last_mode is None)
        if _last_mode is not None and current_mode == _last_mode:
            return
        
        # Early exit if no relevant transition
        if not entering_paint and not leaving_paint:
            _last_mode = current_mode
            return
        
        # Only process the active space for performance
        space = context.space_data
        if space and space.type == 'VIEW_3D':
            wm = context.window_manager
            
            if entering_paint:
                # Check if gizmos are currently enabled
                gizmos_enabled = (space.show_gizmo_object_translate or 
                                 space.show_gizmo_object_rotate or 
                                 space.show_gizmo_object_scale)
                
                if gizmos_enabled:
                    # Store that gizmos were enabled
                    _gizmos_were_enabled = True
                    wm["ps_gizmo_translate"] = space.show_gizmo_object_translate
                    wm["ps_gizmo_rotate"] = space.show_gizmo_object_rotate
                    wm["ps_gizmo_scale"] = space.show_gizmo_object_scale
                    
                    # Disable all gizmos
                    space.show_gizmo_object_translate = False
                    space.show_gizmo_object_rotate = False
                    space.show_gizmo_object_scale = False
            
            elif leaving_paint:
                # Restore gizmos if they were enabled before entering paint mode
                if _gizmos_were_enabled:
                    space.show_gizmo_object_translate = wm.get("ps_gizmo_translate", True)
                    space.show_gizmo_object_rotate = wm.get("ps_gizmo_rotate", True)
                    space.show_gizmo_object_scale = wm.get("ps_gizmo_scale", False)
                    _gizmos_were_enabled = False
        
        _last_mode = current_mode
        
    except Exception as e:
        # Log error for debugging instead of silently passing
        print(f"Paint System mode_change_handler error: {e}")


owner = object()
_color_sync_timer_running = False
_last_color_update_time = 0.0
import time

def brush_color_callback(source: str | None = None):
    context = bpy.context
    ps_scene_data = getattr(context.scene, 'ps_scene_data', None)
    if ps_scene_data is None:
        return
    settings = getattr(context.tool_settings, 'image_paint', None)
    if not settings:
        return
    brush = getattr(settings, 'brush', None)
    if brush is None:
        return
    if hasattr(context.tool_settings, "unified_paint_settings"):
        ups = context.tool_settings.unified_paint_settings
    else:
        ups = settings.unified_paint_settings
    # If unified color is enabled but a change came via Brush (e.g. sampling tools writing to brush),
    # mirror Brush color into Unified so the active paint color stays consistent across UIs/builds.
    try:
        if source == 'brush' and getattr(ups, 'use_unified_color', False):
            if tuple(ups.color) != tuple(brush.color):
                ups.color = brush.color
    except Exception:
        pass

    prop_owner = ups if getattr(ups, 'use_unified_color', False) else brush
    # Store color to context.ps_scene_data.hsv_color and sync with actual brush color
    hsv = prop_owner.color.hsv
    color = prop_owner.color
    
    # Check if update is needed (use tolerance for floating point comparison)
    hue_changed = abs(hsv[0] - ps_scene_data.hue) > 0.0001
    sat_changed = abs(hsv[1] - ps_scene_data.saturation) > 0.0001
    val_changed = abs(hsv[2] - ps_scene_data.value) > 0.0001
    
    if hue_changed or sat_changed or val_changed:
        # Set a sentinel flag to prevent the update callback from writing back to brush
        ps_scene_data['_updating_from_brush'] = True
        # Also set timestamp to block HSV updates for a short window
        global _last_color_update_time
        _last_color_update_time = time.time()
        
        try:
            # Directly set values bypassing the normal property system to avoid any update callback issues
            # Use property_unset first to ensure Blender sees the change
            if hue_changed:
                ps_scene_data.property_unset("hue")
                ps_scene_data.hue = hsv[0]
            if sat_changed:
                ps_scene_data.property_unset("saturation")
                ps_scene_data.saturation = hsv[1]
            if val_changed:
                ps_scene_data.property_unset("value")
                ps_scene_data.value = hsv[2]
            
            # Update hex color
            r = int(color[0] * 255)
            g = int(color[1] * 255)
            b = int(color[2] * 255)
            hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b).upper()
            if ps_scene_data.hex_color != hex_color:
                ps_scene_data.property_unset("hex_color")
                ps_scene_data.hex_color = hex_color
            
        finally:
            # Clear sentinel flag
            if '_updating_from_brush' in ps_scene_data:
                del ps_scene_data['_updating_from_brush']
        
        # Force property update notifications - this is critical for UI refresh
        try:
            # Tag the scene for update to ensure property changes propagate
            context.scene.update_tag()
        except Exception:
            pass
        
        # Force redraw of current area only (not all windows)
        try:
            if context.area and context.area.type == 'VIEW_3D':
                context.area.tag_redraw()
        except Exception as e:
            logger.error(f"Paint System color sync redraw error: {e}")


def _color_sync_timer():
    # Poll periodically so HSV stays synced even if host UI bypasses msgbus events
    if not _color_sync_timer_running:
        return None
    # Skip sync if we just updated color (palette click, etc) to avoid fighting with user input
    import time
    if time.time() - _last_color_update_time < 0.3:
        return 0.2  # Keep polling but don't sync yet
    try:
        brush_color_callback("timer")
    except Exception as e:
        logger.debug(f"Color sync timer error: {e}")  # Debug level since this runs frequently
    return 0.2


# UDIM Tile Auto-Management (Phase 2)
_last_image_states = {}  # Cache of {image_id: (tile_count, painted_tiles_count)}

@bpy.app.handlers.persistent
def update_udim_tile_state(context=None):
    """Track UDIM tile paint state and auto-detect UDIM images"""
    try:
        if not context:
            context = bpy.context
        ps_ctx = parse_context(context)
        if not ps_ctx or not ps_ctx.active_material:
            return
        
        from ..utils.udim import is_udim_image, get_udim_tiles_from_image
        
        # Check all IMAGE layers in all channels of the active material
        for group in ps_ctx.active_material.paint_system_groups:
            for channel in group.channels:
                for layer in channel.layers:
                    if layer.type != 'IMAGE' or not layer.image:
                        continue
                    
                    image = layer.image
                    is_image_udim = is_udim_image(image)
                    
                    # Auto-detect: if image is UDIM but layer isn't marked, mark it now
                    if is_image_udim and not layer.is_udim:
                        layer.is_udim = True
                        logger.info(f"Auto-detected UDIM image for layer '{layer.layer_name}'")
                    
                    # If layer is marked UDIM but image isn't, clear the flag
                    elif layer.is_udim and not is_image_udim:
                        layer.is_udim = False
                        layer.udim_tiles.clear()
                        continue
                    
                    # Skip non-UDIM layers
                    if not layer.is_udim:
                        continue
                    
                    # Get current tile list from image
                    current_tiles = get_udim_tiles_from_image(image)
                    image_id = id(image)
                    
                    # Compare with last known state to detect changes
                    last_state = _last_image_states.get(image_id)
                    if not last_state:
                        # First time seeing this image - initialize
                        _last_image_states[image_id] = (len(current_tiles), 0)
                        # Populate layer tile list if empty
                        if len(layer.udim_tiles) == 0:
                            for tile_num in current_tiles:
                                tile = layer.udim_tiles.add()
                                tile.number = tile_num
                                tile.is_painted = False
                                tile.is_dirty = False
                        continue
                    
                    last_tile_count, _ = last_state
                    
                    # If new tiles were added to the image, update layer
                    if len(current_tiles) > last_tile_count:
                        new_tiles = set(current_tiles) - set([t.number for t in layer.udim_tiles])
                        for tile_num in sorted(new_tiles):
                            tile = layer.udim_tiles.add()
                            tile.number = tile_num
                            tile.is_painted = False
                            tile.is_dirty = False
                        logger.info(f"Auto-created UDIM tiles {new_tiles} for layer {layer.layer_name}")
                    
                    # Update state
                    _last_image_states[image_id] = (len(current_tiles), len(current_tiles))
        
    except Exception as e:
        logger.debug(f"UDIM tile state update error: {e}")


def _timer_update_udim_tiles():
    """Timer callback for UDIM tile updates (runs periodically)"""
    try:
        update_udim_tile_state(bpy.context)
    except Exception as e:
        logger.debug(f"UDIM tile timer error: {e}")
    return 0.5  # Poll every 500ms


def register():
    bpy.app.handlers.frame_change_pre.append(frame_change_pre)
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.save_pre.append(save_handler)
    bpy.app.handlers.load_post.append(refresh_image)
    if hasattr(bpy.app.handlers, 'scene_update_pre'):
        bpy.app.handlers.scene_update_pre.append(paint_system_object_update)
    else:
        bpy.app.handlers.depsgraph_update_post.append(paint_system_object_update)
    bpy.app.timers.register(on_addon_enable, first_interval=0.1)
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.UnifiedPaintSettings, "color"),
        owner=owner,
        args=("ups",),
        notify=brush_color_callback,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Brush, "color"),
        owner=owner,
        args=("brush",),
        notify=brush_color_callback,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=owner,
        args=(None,),
        notify=brush_color_callback,
    )
    # Subscribe to mode changes for gizmo management
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=_gizmo_owner,
        args=(),
        notify=mode_change_handler,
    )
    global _color_sync_timer_running
    if not _color_sync_timer_running:
        _color_sync_timer_running = True
        bpy.app.timers.register(_color_sync_timer, first_interval=0.2, persistent=True)
    
    # Register UDIM tile tracking timer (with error handling)
    try:
        if not bpy.app.timers.is_registered(_timer_update_udim_tiles):
            bpy.app.timers.register(_timer_update_udim_tiles, first_interval=0.5, persistent=True)
    except Exception as e:
        logger.warning(f"Could not register UDIM tile timer: {e}")

def unregister():
    bpy.msgbus.clear_by_owner(owner)
    bpy.msgbus.clear_by_owner(_gizmo_owner)
    bpy.app.handlers.frame_change_pre.remove(frame_change_pre)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.app.handlers.save_pre.remove(save_handler)
    bpy.app.handlers.load_post.remove(refresh_image)
    if hasattr(bpy.app.handlers, 'scene_update_pre'):
        bpy.app.handlers.scene_update_pre.remove(paint_system_object_update)
    else:
        bpy.app.handlers.depsgraph_update_post.remove(paint_system_object_update)
    global _color_sync_timer_running
    _color_sync_timer_running = False
    if hasattr(bpy.app.timers, "unregister"):
        try:
            bpy.app.timers.unregister(_color_sync_timer)
        except Exception:
            pass
        try:
            bpy.app.timers.unregister(_timer_update_udim_tiles)
        except Exception:
            pass