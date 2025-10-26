import math

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
from .common import MultiMaterialOperator, PSContextMixin
from .operators_utils import redraw_panel

from bl_ui.properties_paint_common import (
    UnifiedPaintPanel,
)

class PAINTSYSTEM_OT_NextActiveChannel(PSContextMixin, Operator):
    bl_idname = "paint_system.next_active_channel"
    bl_label = "Next Painting Target"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Switch to the next Paint System channel"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None and len(ps_ctx.active_group.channels) > 0

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        group = ps_ctx.active_group
        if group is None or len(group.channels) == 0:
            return {'CANCELLED'}
        # Compute next index with wrap-around
        try:
            current = int(group.active_index)
        except Exception:
            current = 0
        new_index = (current + 1) % len(group.channels)
        group.active_index = new_index
        redraw_panel(context)
        return {'FINISHED'}


class PAINTSYSTEM_OT_PrevActiveChannel(PSContextMixin, Operator):
    bl_idname = "paint_system.prev_active_channel"
    bl_label = "Previous Painting Target"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Switch to the previous Paint System channel"

    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.active_group is not None and len(ps_ctx.active_group.channels) > 0

    def execute(self, context):
        ps_ctx = self.parse_context(context)
        group = ps_ctx.active_group
        if group is None or len(group.channels) == 0:
            return {'CANCELLED'}
        try:
            current = int(group.active_index)
        except Exception:
            current = 0
        new_index = (current - 1) % len(group.channels)
        group.active_index = new_index
        redraw_panel(context)
        return {'FINISHED'}

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

            # if ps.preferences.unified_brush_color:
            #     bpy.context.scene.tool_settings.unified_paint_settings.use_unified_color = True
            # if ps.preferences.unified_brush_size:
            #     bpy.context.scene.tool_settings.unified_paint_settings.use_unified_size = True

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
        active_group = ps_ctx.active_group
        active_channel = ps_ctx.active_channel
        ps_mat_data = ps_ctx.ps_mat_data
        mat = ps_ctx.active_material
        mat_output = get_material_output(mat.node_tree)
        if not ps_mat_data.preview_channel:
            ps_mat_data.preview_channel = True
            # Store the node connected to material output
            connected_link = mat_output.inputs[0].links[0]
            ps_ctx.ps_mat_data.original_node_name = connected_link.from_node.name
            ps_ctx.ps_mat_data.original_socket_name = connected_link.from_socket.name
            
            # Find channel node tree
            node = find_node(mat.node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': active_group.node_tree})
            if node:
                # Connect node tree to material output
                connect_sockets(mat_output.inputs[0], node.outputs[active_channel.name])
        else:
            ps_mat_data.preview_channel = False
            # Find node by name
            node = mat.node_tree.nodes.get(ps_mat_data.original_node_name)
            if node:
                connect_sockets(node.outputs[ps_mat_data.original_socket_name], mat_output.inputs[0])
                
        # Change render mode
        if bpy.context.space_data.shading.type not in {'RENDERED', 'MATERIAL'}:
            bpy.context.space_data.shading.type = 'RENDERED'
        return {'FINISHED'}


class PAINTSYSTEM_OT_CreatePaintSystemUVMap(PSContextMixin, Operator):
    bl_idname = "paint_system.create_paint_system_uv_map"
    bl_label = "Create Paint System UV Map"
    bl_options = {'REGISTER', 'UNDO'}
    bl_description = "Create a new UV Map"

    def execute(self, context):
        # Get all objects in selection
        selection = context.selected_objects

        # Get the active object
        ps_object = self.parse_context(context).ps_object
        
        if ps_object.data.uv_layers.get("PS_UVMap"):
            return {'FINISHED'}

        # Deselect all objects
        for obj in selection:
            if obj != ps_object:
                obj.select_set(False)
        # Make it active
        context.view_layer.objects.active = ps_object
        original_mode = str(ps_object.mode)
        bpy.ops.object.mode_set(mode='EDIT')
        obj.update_from_editmode()
        bpy.ops.mesh.select_all(action='SELECT')
        # Apply to only the active object
        uv_layers = ps_object.data.uv_layers
        uvmap = uv_layers.new(name="PS_UVMap")
        ps_object.data.uv_layers.active = uvmap
        bpy.ops.uv.smart_project(angle_limit=30/180*math.pi, island_margin=0.005)
        bpy.ops.object.mode_set(mode=original_mode)
        # Deselect the object
        ps_object.select_set(False)
        # Restore the selection
        for obj in selection:
            obj.select_set(True)
        context.view_layer.objects.active = ps_object
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
        if is_newer_than(4,4):
            bpy.ops.paint.sample_color('INVOKE_DEFAULT', merged=True)
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

        return {'FINISHED'}

    @classmethod
    def poll(cls, context):
        return context.area.type == 'VIEW_3D' and context.mode == 'PAINT_TEXTURE'

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
                channel.update_node_tree(context)
            group.update_node_tree(context)
            
            # Find node group that uses the original node tree
            for node in mat.node_tree.nodes:
                if node.type == 'GROUP' and node.node_tree == original_node_tree:
                    node.node_tree = group.node_tree
        redraw_panel(context)
        return {'FINISHED'}


classes = (
    PAINTSYSTEM_OT_NextActiveChannel,
    PAINTSYSTEM_OT_PrevActiveChannel,
    PAINTSYSTEM_OT_TogglePaintMode,
    PAINTSYSTEM_OT_AddPresetBrushes,
    PAINTSYSTEM_OT_SelectMaterialIndex,
    PAINTSYSTEM_OT_NewMaterial,
    PAINTSYSTEM_OT_IsolateChannel,
    PAINTSYSTEM_OT_CreatePaintSystemUVMap,
    PAINTSYSTEM_OT_ToggleBrushEraseAlpha,
    PAINTSYSTEM_OT_ColorSampler,
    PAINTSYSTEM_OT_OpenPaintSystemPreferences,
    PAINTSYSTEM_OT_FlipNormals,
    PAINTSYSTEM_OT_RecalculateNormals,
    PAINTSYSTEM_OT_AddCameraPlane,
    PAINTSYSTEM_OT_HidePaintingTips,
    PAINTSYSTEM_OT_DuplicatePaintSystemData,
)

addon_keymaps = []

_register, _unregister = register_classes_factory(classes)

def register():
    _register()
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        # 3D View: sampler and erase toggle
        km = kc.keymaps.new(name="3D View", space_type='VIEW_3D')
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_ColorSampler.bl_idname, 'I', 'PRESS', repeat=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_ToggleBrushEraseAlpha.bl_idname, type='E', value='PRESS')
        addon_keymaps.append((km, kmi))

        # 3D View: Ctrl+Q / Ctrl+Shift+Q for channel cycling
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_NextActiveChannel.bl_idname, type='Q', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_PrevActiveChannel.bl_idname, type='Q', value='PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))

        # Node Editor: Ctrl+Q / Ctrl+Shift+Q
        km = kc.keymaps.new(name="Node Editor", space_type='NODE_EDITOR')
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_NextActiveChannel.bl_idname, type='Q', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_PrevActiveChannel.bl_idname, type='Q', value='PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))

        # Image Editor: Ctrl+Q / Ctrl+Shift+Q
        km = kc.keymaps.new(name="Image", space_type='IMAGE_EDITOR')
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_NextActiveChannel.bl_idname, type='Q', value='PRESS', ctrl=True)
        addon_keymaps.append((km, kmi))
        kmi = km.keymap_items.new(PAINTSYSTEM_OT_PrevActiveChannel.bl_idname, type='Q', value='PRESS', ctrl=True, shift=True)
        addon_keymaps.append((km, kmi))

def unregister():
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    _unregister()