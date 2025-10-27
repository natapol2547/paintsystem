import bpy
from .data import sort_actions, parse_context
from .graph.basic_layers import get_layer_version_for_type
import time
from .graph.nodetree_builder import get_nodetree_version

@bpy.app.handlers.persistent
def frame_change_pre(scene):
    if not hasattr(scene, 'ps_scene_data'):
        return
    update_task = {}
    for global_layer in scene.ps_scene_data.layers:
        sorted_actions = sort_actions(bpy.context, global_layer)
        for action in sorted_actions:
            match action.action_bind:
                case 'FRAME':
                    if action.frame <= scene.frame_current:
                        # print(f"Frame {action.frame} found at frame {scene.frame_current}")
                        if action.action_type == 'ENABLE' and update_task.get(global_layer, global_layer.enabled) == False:
                            update_task[global_layer] = True
                        elif action.action_type == 'DISABLE' and update_task.get(global_layer, global_layer.enabled) == True:
                            update_task[global_layer] = False
                case 'MARKER':
                    marker = scene.timeline_markers.get(action.marker_name)
                    if marker and marker.frame <= scene.frame_current:
                        # print(f"Marker {marker.frame} found at frame {scene.frame_current}")
                        if action.action_type == 'ENABLE' and update_task.get(global_layer, global_layer.enabled) == False:
                            update_task[global_layer] = True
                        elif action.action_type == 'DISABLE' and update_task.get(global_layer, global_layer.enabled) == True:
                            update_task[global_layer] = False
                case _:
                    pass
    for global_layer, enabled in update_task.items():
        if global_layer.enabled != enabled:
            # print(f"Updating layer {global_layer.name} to {enabled}")
            global_layer.enabled = enabled


@bpy.app.handlers.persistent
def load_post(scene):
    start_time = time.time()
    ps_ctx = parse_context(bpy.context)
    if not ps_ctx.ps_scene_data:
        return
    layers = {}
    # Layer Versioning
    for global_layer in ps_ctx.ps_scene_data.layers:
        target_version = get_layer_version_for_type(global_layer.type)
        if get_nodetree_version(global_layer.node_tree) != target_version:
            print(f"Updating layer {global_layer.name} to version {target_version}")
            global_layer.update_node_tree(bpy.context)
        if global_layer.name and not global_layer.layer_name:
            if not layers:
                for mat in bpy.data.materials:
                    if hasattr(mat, 'ps_mat_data'):
                        for group in mat.ps_mat_data.groups:
                            for channel in group.channels:
                                for layer in channel.layers:
                                    layers[layer.ref_layer_id] = layer
            name = global_layer.name
            # Transfer layer name to global_layer layer_name
            global_layer.layer_name = layers[name].name
            print(f"Copying layer name '{layers[name].name}' to '{global_layer.name}'")
            
    print(f"Paint System: Checked {len(ps_ctx.ps_scene_data.layers)} layers in {round((time.time() - start_time) * 1000, 2)} ms")

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
    active_layer = ps_ctx.active_global_layer
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
    
    if not hasattr(ps_scene_data, 'last_selected_object'):
        ps_scene_data.last_selected_object = None
    if not hasattr(ps_scene_data, 'last_selected_material'):
        ps_scene_data.last_selected_material = None
        
    current_obj = obj
    current_mat = mat
    
    if (ps_scene_data.last_selected_object != current_obj or 
        ps_scene_data.last_selected_material != current_mat):
        
        # Update tracking variables
        ps_scene_data.last_selected_object = current_obj
        ps_scene_data.last_selected_material = current_mat
        
        if obj and obj.type == 'MESH' and mat and hasattr(mat, 'ps_mat_data'):
            from .data import update_active_image
            try:
                update_active_image(None, bpy.context) 
            except Exception as e:
                pass


# --- On Addon Enable ---
def on_addon_enable():
    load_post(bpy.context.scene)


owner = object()

def brush_color_callback(*args):
    context = bpy.context
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
    bpy.app.handlers.depsgraph_update_post.append(material_name_change_handler)


@bpy.app.handlers.persistent
def material_name_change_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph = None):
    """Update Paint System group names when material name changes"""
    # Store material names to detect changes
    if not hasattr(bpy.app, '_ps_material_names'):
        bpy.app._ps_material_names = {}
    
    current_names = {}
    for material in bpy.data.materials:
        if hasattr(material, 'ps_mat_data') and material.ps_mat_data.groups:
            current_names[material.name_full] = material.name
    
    # Check for changes
    prev_names = bpy.app._ps_material_names
    
    # Find renamed materials
    for old_full_name, old_name in list(prev_names.items()):
        # Find if this material still exists but was renamed
        for mat in bpy.data.materials:
            if hasattr(mat, 'ps_mat_data') and mat.ps_mat_data.groups:
                if mat.name_full not in prev_names and old_name in [g.name for g in mat.ps_mat_data.groups]:
                    # Material was renamed, update groups
                    for group in mat.ps_mat_data.groups:
                        if group.name == old_name:
                            group.name = mat.name
                    break
    
    # Update stored names
    bpy.app._ps_material_names = current_names


def unregister():
    bpy.msgbus.clear_by_owner(owner)
    bpy.app.handlers.frame_change_pre.remove(frame_change_pre)
    bpy.app.handlers.load_post.remove(load_post)
    bpy.app.handlers.save_pre.remove(save_handler)
    bpy.app.handlers.load_post.remove(refresh_image)
    bpy.app.handlers.depsgraph_update_post.remove(material_name_change_handler)
    if hasattr(bpy.app.handlers, 'scene_update_pre'):
        bpy.app.handlers.scene_update_pre.remove(paint_system_object_update)
    else:
        bpy.app.handlers.depsgraph_update_post.remove(paint_system_object_update)