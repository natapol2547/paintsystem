import math
import uuid
import addon_utils
import bpy
import gpu
from bpy.props import EnumProperty, IntProperty
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
from .common import MultiMaterialOperator, PSContextMixin, DEFAULT_PS_UV_MAP_NAME, execute_operator_in_area, wait_for_redraw
from ..panels.common import is_editor_open
from .operators_utils import redraw_panel

from bl_ui.properties_paint_common import (
    UnifiedPaintPanel,
)

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


class PAINTSYSTEM_OT_ColorSample(PSContextMixin, Operator):
    """Sample the color under the mouse cursor"""
    bl_idname = "paint_system.color_sample"
    bl_label = "Color Sample"

    x: IntProperty()
    y: IntProperty()
    
    @classmethod
    def poll(cls, context):
        return context.mode == 'PAINT_TEXTURE'

    def execute(self, context):
        if is_newer_than(4,4):
            bpy.ops.paint.sample_color('INVOKE_DEFAULT', merged=True, palette=False)
            return {'FINISHED'}

        x, y = self.x, self.y
        buffer = gpu.state.active_framebuffer_get()
        pixel = buffer.read_color(x, y, 1, 1, 3, 0, 'FLOAT')
        pixel.dimensions = 1 * 1 * 3
        pix_value = [float(item) for item in pixel]

        tool_settings = UnifiedPaintPanel.paint_settings(context)
        brush_settings = tool_settings.brush
        unified_settings = get_unified_settings(context, "use_unified_color")

        brush_settings = tool_settings.brush
        unified_settings.color = pix_value
        brush_settings.color = pix_value
        context.scene.ps_scene_data.update_hsv_color(context)
        return {'FINISHED'}

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
            
            # Store links connected to the original node group before replacing
            group_nodes = [n for n in mat.node_tree.nodes if n.type == 'GROUP' and n.node_tree == original_node_tree]
            relink_map = {}
            for node_group in group_nodes:
                input_links = []
                output_links = []
                for input_socket in node_group.inputs[:]:
                    for link in input_socket.links:
                        input_links.append({
                            'from_socket': link.from_socket,
                            'dest_name': getattr(input_socket, "name", None),
                        })
                for output_socket in node_group.outputs[:]:
                    for link in output_socket.links:
                        output_links.append({
                            'to_socket': link.to_socket,
                            'src_name': getattr(link.from_socket, "name", None),
                        })
                relink_map[node_group] = {
                    'input_links': input_links,
                    'output_links': output_links,
                }
            
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
            
            # Reconnect the sockets using stored endpoints
            from bpy_extras.node_utils import connect_sockets
            for node_group, links in relink_map.items():
                node_group.node_tree = group.node_tree
                for link in links['input_links']:
                    dest_name = link.get('dest_name')
                    from_socket = link.get('from_socket')
                    if dest_name and dest_name in node_group.inputs and from_socket:
                        connect_sockets(from_socket, node_group.inputs[dest_name])
                for link in links['output_links']:
                    src_name = link.get('src_name')
                    to_socket = link.get('to_socket')
                    if src_name and src_name in node_group.outputs and to_socket:
                        connect_sockets(node_group.outputs[src_name], to_socket)
        redraw_panel(context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_ToggleTransformGizmos(Operator):
    bl_idname = "paint_system.toggle_transform_gizmos"
    bl_label = "Toggle Transform Gizmos"
    bl_options = {'REGISTER'}
    bl_description = "Toggle transform gizmos on/off with state memory for paint mode"

    def execute(self, context):
        space = context.area.spaces[0] if context.area and context.area.spaces else None
        if not space or space.type != 'VIEW_3D':
            return {'CANCELLED'}
        
        wm = context.window_manager
        obj = context.active_object
        
        # Determine current gizmo state
        gizmos_enabled = (space.show_gizmo_object_translate or
                         space.show_gizmo_object_rotate or
                         space.show_gizmo_object_scale)
        
        # Treat paint, sculpt, vertex/weight paint, and GP draw modes the same for gizmos
        paint_like_modes = {
            'PAINT_TEXTURE',
            'SCULPT',
            'PAINT_VERTEX',
            'PAINT_WEIGHT',
            'PAINT_GPENCIL',
            'PAINT_GPENCIL_LEGACY',
            'PAINT_GREASE_PENCIL',
        }
        in_paint_mode = obj and obj.mode in paint_like_modes
        
        if in_paint_mode:
            # Store current gizmo state before entering paint mode
            wm["ps_gizmo_translate"] = space.show_gizmo_object_translate
            wm["ps_gizmo_rotate"] = space.show_gizmo_object_rotate
            wm["ps_gizmo_scale"] = space.show_gizmo_object_scale
            # Keep gizmos disabled during paint mode
            space.show_gizmo_object_translate = False
            space.show_gizmo_object_rotate = False
            space.show_gizmo_object_scale = False
        else:
            # Not in paint mode - toggle gizmos normally
            new_state = not gizmos_enabled
            space.show_gizmo_object_translate = new_state
            space.show_gizmo_object_rotate = new_state
            space.show_gizmo_object_scale = new_state
        
        # Redraw the viewport
        for area in context.screen.areas:
            if area.type == 'VIEW_3D':
                area.tag_redraw()
        
        return {'FINISHED'}

def split_area(context: bpy.types.Context, direction: str = 'VERTICAL', factor: float = 0.55) -> bpy.types.Area | None:
    screen = context.screen
    old_areas = set(screen.areas)
    
    with context.temp_override(area=context.area):
        bpy.ops.screen.area_split(direction=direction, factor=factor)

    new_areas = set(screen.areas) - old_areas
    if not new_areas:
        return None
    new_area = new_areas.pop()
    return new_area

class PAINTSYSTEM_OT_ToggleImageEditor(PSContextMixin, Operator):
    bl_idname = "paint_system.toggle_image_editor"
    bl_label = "Toggle Image Editor"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Toggle the image editor on/off"

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_layer = ps_ctx.active_layer
        image = active_layer.image if active_layer else None
        
        if is_editor_open(context, 'IMAGE_EDITOR'):
            # Find the image editor area
            image_editor_area = next((a for a in context.screen.areas if a.type == 'IMAGE_EDITOR'), None)
            # Close the image editor area
            if image_editor_area:
                execute_operator_in_area(image_editor_area, 'screen.area_close')
                return {'FINISHED'}
        
        new_area = split_area(context)
        if not new_area:
            self.report({'WARNING'}, "Could not split the area.")
            return {'CANCELLED'}

        # Change the new area to Image Editor
        new_area.type = 'IMAGE_EDITOR'
        
        if new_area.x < context.area.x:
            new_area.type = context.area.type
            context.area.type = 'IMAGE_EDITOR'
        
        if image:
            space = new_area.spaces[0]
            space.show_region_ui = False
            space.image = image
            space.ui_mode = 'PAINT'
            space.overlay.show_overlays = active_layer.coord_type in {'AUTO', 'UV'}
            
            execute_operator_in_area(new_area, 'image.view_all', fit_view=True)

        return {'FINISHED'}

class PAINTSYSTEM_OT_FocusPSNode(PSContextMixin, Operator):
    bl_idname = "paint_system.focus_ps_node"
    bl_label = "Focus PS Node"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Focus the active node in the Paint System"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        active_group = ps_ctx.active_group
        node_tree = ps_ctx.active_material.node_tree
        
        new_area = split_area(context)
        if not new_area:
            self.report({'WARNING'}, "Could not split the area.")
            return {'CANCELLED'}

        # Change the new area to Shader Node Editor
        new_area.type = 'NODE_EDITOR'
        # Set to Shader Editor
        space = new_area.spaces[0]
        space.tree_type = 'ShaderNodeTree'
        space.show_region_ui = True
        
        # Find the node group
        node_to_focus = find_node(node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree}, connected_to_output=False)
        if not node_to_focus:
            # Find material output instead
            node_to_focus = get_material_output(node_tree)
        
        if node_to_focus:
            # Deselect all nodes
            for node in node_tree.nodes:
                if node != node_to_focus:
                    node.select = False
                else:
                    node.select = True
            node_tree.nodes.active = node_to_focus
            wait_for_redraw()
            execute_operator_in_area(new_area, 'node.view_selected')
        
        
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_TogglePaintMode,
    PAINTSYSTEM_OT_AddPresetBrushes,
    PAINTSYSTEM_OT_SelectMaterialIndex,
    PAINTSYSTEM_OT_NewMaterial,
    PAINTSYSTEM_OT_IsolateChannel,
    PAINTSYSTEM_OT_ToggleBrushEraseAlpha,
    PAINTSYSTEM_OT_ColorSample,
    PAINTSYSTEM_OT_OpenPaintSystemPreferences,
    PAINTSYSTEM_OT_FlipNormals,
    PAINTSYSTEM_OT_RecalculateNormals,
    PAINTSYSTEM_OT_AddCameraPlane,
    PAINTSYSTEM_OT_HidePaintingTips,
    PAINTSYSTEM_OT_DuplicatePaintSystemData,
    PAINTSYSTEM_OT_ToggleTransformGizmos,
    PAINTSYSTEM_OT_ToggleImageEditor,
    PAINTSYSTEM_OT_FocusPSNode,
)

register, unregister = register_classes_factory(classes)