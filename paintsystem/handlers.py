import bpy
from .data import get_global_layer, sort_actions, parse_context, get_all_layers, is_valid_uuidv4
from .graph.basic_layers import get_layer_version_for_type
import time
from .graph.nodetree_builder import get_nodetree_version
import uuid

@bpy.app.handlers.persistent
def frame_change_pre(scene):
    if not hasattr(scene, 'ps_scene_data'):
        return
    update_task = {}
    for layer in get_all_layers():
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


@bpy.app.handlers.persistent
def load_post(scene):
    start_time = time.time()
    ps_ctx = parse_context(bpy.context)
    if not ps_ctx.ps_scene_data:
        return
    
    # Global Layer Versioning. Will be removed in the future.
    for global_layer in ps_ctx.ps_scene_data.layers:
        target_version = get_layer_version_for_type(global_layer.type)
        if get_nodetree_version(global_layer.node_tree) != target_version:
            print(f"Updating layer {global_layer.name} to version {target_version}")
            global_layer.update_node_tree(bpy.context)
    
    seen_global_layers_map = {}
    # Layer Versioning
    for mat in bpy.data.materials:
        if hasattr(mat, 'ps_mat_data'):
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
def save_handler(scene: bpy.types.Scene):
    print("Saving Paint System data...")
    images = set()
    ps_ctx = parse_context(bpy.context)
    for layer in ps_ctx.ps_scene_data.layers:
        image = layer.image
        if image and image.is_dirty:
            images.add(image)
    
    for mat in bpy.data.materials:
        if hasattr(mat, 'ps_mat_data'):
            for group in mat.ps_mat_data.groups:
                for channel in group.channels:
                    image = channel.bake_image
                    if image and image.is_dirty:
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
                    except Exception:
                        pass
            except Exception:
                pass
            return None  # Run once
        
        # Schedule with minimal delay
        bpy.app.timers.register(update_tracking, first_interval=0.0)


# --- On Addon Enable ---
def on_addon_enable():
    load_post(bpy.context.scene)


owner = object()

def brush_color_callback(*args):
    context = bpy.context
    if context.mode != 'PAINT_TEXTURE':
        return
    settings = context.tool_settings.image_paint
    brush = settings.brush
    if hasattr(context.tool_settings, "unified_paint_settings"):
        ups = context.tool_settings.unified_paint_settings
    else:
        ups = settings.unified_paint_settings
    prop_owner = ups if ups.use_unified_color else brush
    # Store color to context.ps_scene_data.hsv_color
    hsv = prop_owner.color.hsv
    if hsv != (context.scene.ps_scene_data.hue, context.scene.ps_scene_data.saturation, context.scene.ps_scene_data.value):
        context.scene.ps_scene_data.hue = hsv[0]
        context.scene.ps_scene_data.saturation = hsv[1]
        context.scene.ps_scene_data.value = hsv[2]
        color = prop_owner.color
        r = int(color[0] * 255)
        g = int(color[1] * 255)
        b = int(color[2] * 255)
        hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b).upper()
        context.scene.ps_scene_data.hex_color = hex_color


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
        args=(None,),
        notify=brush_color_callback,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Brush, "color"),
        owner=owner,
        args=(None,),
        notify=brush_color_callback,
    )
    bpy.msgbus.subscribe_rna(
        key=(bpy.types.Object, "mode"),
        owner=owner,
        args=(None,),
        notify=brush_color_callback,
    )

def unregister():
    bpy.msgbus.clear_by_owner(owner)
    bpy.app.handlers.frame_change_pre.remove(frame_change_pre)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.app.handlers.save_pre.remove(save_handler)
    bpy.app.handlers.load_post.remove(refresh_image)
    if hasattr(bpy.app.handlers, 'scene_update_pre'):
        bpy.app.handlers.scene_update_pre.remove(paint_system_object_update)
    else:
        bpy.app.handlers.depsgraph_update_post.remove(paint_system_object_update)