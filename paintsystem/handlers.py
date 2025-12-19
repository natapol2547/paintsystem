import bpy

from .version_check import get_latest_version
from .data import get_global_layer, sort_actions, parse_context, get_all_layers, is_valid_uuidv4
from .image import save_image
from .graph.basic_layers import get_layer_version_for_type
import time
from .graph.nodetree_builder import get_nodetree_version
import uuid
from .donations import get_donation_info

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


def load_paint_system_data(scene: bpy.types.Scene):
    print(f"Loading Paint System data...")
    start_time = time.time()
    if not hasattr(scene, 'ps_scene_data'):
        return
    
    # Global Layer Versioning. Will be removed in the future.
    for global_layer in scene.ps_scene_data.layers:
        target_version = get_layer_version_for_type(global_layer.type)
        if get_nodetree_version(global_layer.node_tree) != target_version:
            print(f"Updating layer {global_layer.name} to version {target_version}")
            try:
                global_layer.update_node_tree(bpy.context)
            except Exception as e:
                print(f"Error updating layer {global_layer.name}: {e}")
    
    seen_global_layers_map = {}
    checked_layers = set()
    # Layer Versioning
    for mat in bpy.data.materials:
        if hasattr(mat, 'ps_mat_data'):
            for group in mat.ps_mat_data.groups:
                for channel in group.channels:
                    has_migrated_global_layer = False
                    for layer in channel.layers:
                        checked_layers.add(layer.name)
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
                        layer = layer.get_layer_data()
                        mix_node = layer.mix_node
                        blend_mode = "MIX"
                        if mix_node:
                            blend_mode = str(mix_node.blend_type)
                        if blend_mode != layer.blend_mode and layer.blend_mode != "PASSTHROUGH":
                            print(f"Layer {layer.name} has blend mode {blend_mode} but {layer.blend_mode} is set")
                            layer.blend_mode = blend_mode
                        # Update every source node to have label 'source'
                        source_node = layer.source_node
                        if source_node and source_node.name != "source":
                            source_node.name = "source"
                            source_node.label = "source"
                        # If type == NODE_GROUP, update the color and alpha input and output sockets
                        if layer.type == "NODE_GROUP" and layer.custom_node_tree:
                            # Get the color and alpha input and output sockets names from the custom node tree
                            custom_node_tree: bpy.types.NodeTree = layer.custom_node_tree
                            items = custom_node_tree.interface.items_tree
                            inputs = [item for item in items if item.item_type == 'SOCKET' and item.in_out == 'INPUT']
                            outputs = [item for item in items if item.item_type == 'SOCKET' and item.in_out == 'OUTPUT']
                            layer.auto_update_node_tree = False
                            if layer.custom_color_input != -1:
                                layer.color_input_name = inputs[layer.custom_color_input].name
                                layer.custom_color_input = -1
                            if layer.custom_alpha_input != -1:
                                layer.alpha_input_name = inputs[layer.custom_alpha_input].name
                                layer.custom_alpha_input = -1
                            if layer.custom_color_output != -1:
                                layer.color_output_name = outputs[layer.custom_color_output].name
                                layer.custom_color_output = -1
                            if layer.custom_alpha_output != -1:
                                layer.alpha_output_name = outputs[layer.custom_alpha_output].name
                                layer.custom_alpha_output = -1
                            layer.auto_update_node_tree = True
                            layer.update_node_tree(bpy.context)
                        # Updating layer to the target version
                        target_version = get_layer_version_for_type(layer.type)
                        if get_nodetree_version(layer.node_tree) != target_version:
                            print(f"Updating layer {layer.name} to version {target_version}")
                            try:
                                layer.update_node_tree(bpy.context)
                            except Exception as e:
                                print(f"Error updating layer {layer.name}: {e}")
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
            
    print(f"Paint System: Checked {len(checked_layers)} layers in {round((time.time() - start_time) * 1000, 2)} ms")


@bpy.app.handlers.persistent
def load_post(scene):
    
    # Ensure color history palette is created
    if not hasattr(scene, 'ps_scene_data'):
        return
    ps_scene_data = scene.ps_scene_data
    if not ps_scene_data.color_history_palette:
        palette_name = "Paint System History"
        palette = bpy.data.palettes.get(palette_name)
        if not palette:
            palette = bpy.data.palettes.new(palette_name)
    
    load_paint_system_data(scene)
    # Check for donation info
    # get_donation_info()
    # if donation_info:
    #     print(f"Donation info: {donation_info}")
    # Check for version check
    get_latest_version()

@bpy.app.handlers.persistent
def save_handler(scene: bpy.types.Scene):
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
        save_image(image)


@bpy.app.handlers.persistent
def refresh_image(scene: bpy.types.Scene):
    ps_ctx = parse_context(bpy.context)
    active_layer = ps_ctx.active_layer
    if active_layer and active_layer.image:
        active_layer.image.reload()


@bpy.app.handlers.persistent
def color_history_handler(scene: bpy.types.Scene, depsgraph: bpy.types.Depsgraph = None):
    if not hasattr(scene, 'ps_scene_data'):
        return
    ps_scene_data = scene.ps_scene_data
    if depsgraph and not depsgraph.id_type_updated('IMAGE'):
        return
    # Color History
    try:
        ps_ctx = parse_context(bpy.context)
        active_layer = ps_ctx.active_layer
        if not active_layer:
            return
        image: bpy.types.Image = active_layer.image
        if active_layer and active_layer.type == "IMAGE" and image and image.is_dirty:
            if not ps_scene_data.color_history_palette:
                palette_name = "Paint System History"
                palette = bpy.data.palettes.get(palette_name)
                if not palette:
                    palette = bpy.data.palettes.new(palette_name)
                ps_scene_data.color_history_palette = palette
            
            palette = ps_scene_data.color_history_palette
            current_color = ps_scene_data.get_brush_color(bpy.context)
            
            should_add = True
            if len(palette.colors) > 0:
                last_color = palette.colors[0].color
                if (abs(last_color[0] - current_color[0]) < 0.001 and 
                    abs(last_color[1] - current_color[1]) < 0.001 and 
                    abs(last_color[2] - current_color[2]) < 0.001):
                    should_add = False
            
            if should_add:
                colors_to_save = [c.color[:] for c in palette.colors]
                palette.colors.clear()

                item = palette.colors.new()
                item.color = (current_color[0], current_color[1], current_color[2])
                # print(f"Color added: {item.color[:]}")
                
                for col in colors_to_save:
                    if len(palette.colors) >= 20:
                        break
                    item = palette.colors.new()
                    item.color = col
    except Exception as e:
        print(f"Color History Error: {e}")
        pass

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
    if depsgraph and not depsgraph.id_type_updated('OBJECT'):
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
    if context.scene and hasattr(context.scene, 'ps_scene_data'):
        context.scene.ps_scene_data.update_hsv_color(context)


def register():
    bpy.app.handlers.frame_change_pre.append(frame_change_pre)
    bpy.app.handlers.load_post.append(load_post)
    bpy.app.handlers.save_pre.append(save_handler)
    bpy.app.handlers.load_post.append(refresh_image)
    if hasattr(bpy.app.handlers, 'scene_update_pre'):
        bpy.app.handlers.scene_update_pre.append(paint_system_object_update)
        bpy.app.handlers.scene_update_pre.append(color_history_handler)
    else:
        bpy.app.handlers.depsgraph_update_post.append(paint_system_object_update)
        bpy.app.handlers.depsgraph_update_post.append(color_history_handler)
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
        bpy.app.handlers.scene_update_pre.remove(color_history_handler)
    else:
        bpy.app.handlers.depsgraph_update_post.remove(paint_system_object_update)
        bpy.app.handlers.depsgraph_update_post.remove(color_history_handler)