"""
Toolbar operators for Paint System
These operators provide quick access to Paint System functionality from the toolbar
"""

import bpy
from bpy.utils import register_classes_factory
from bpy.types import Operator
from bpy.props import StringProperty
from .common import PSContextMixin
from ..paintsystem.data import get_global_layer

class PAINTSYSTEM_OT_ShortcutMergeDown(PSContextMixin, Operator):
    """Merge current layer down - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_merge_down"
    bl_label = "Merge Down"
    bl_description = "Merge the current layer with the layer below"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_group is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.merge_down('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to merge down: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutMergeUp(PSContextMixin, Operator):
    """Merge current layer up - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_merge_up"
    bl_label = "Merge Up"
    bl_description = "Merge the current layer with the layer above"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_group is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.merge_up('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to merge up: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutDuplicateLayer(PSContextMixin, Operator):
    """Duplicate current layer - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_duplicate_layer"
    bl_label = "Duplicate Layer"
    bl_description = "Duplicate the current layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_group is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.copy_layer('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to duplicate layer: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutDeleteLayer(PSContextMixin, Operator):
    """Delete current layer - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_delete_layer"
    bl_label = "Delete Layer"
    bl_description = "Delete the current layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_group is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.delete_item('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to delete layer: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutToggleLayerVisibility(PSContextMixin, Operator):
    """Toggle layer visibility - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_toggle_layer_visibility"
    bl_label = "Toggle Layer Visibility"
    bl_description = "Toggle the visibility of the current layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_layer is not None
    
    def execute(self, context):
        try:
            ps_ctx = self.parse_context(context)
            if ps_ctx.active_layer:
                # Get the global item for this layer using Paint System's method
                global_layer = get_global_layer(ps_ctx.active_layer)
                if global_layer:
                    global_layer.enabled = not global_layer.enabled
                    return {'FINISHED'}
                else:
                    self.report({'ERROR'}, "Could not find global layer data")
                    return {'CANCELLED'}
            else:
                self.report({'ERROR'}, "No active layer found")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to toggle layer visibility: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutNewImageLayer(PSContextMixin, Operator):
    """Create new image layer - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_new_image_layer"
    bl_label = "New Image Layer"
    bl_description = "Create a new image layer"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_group is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.new_image_layer('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to create new image layer: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutBakeChannel(PSContextMixin, Operator):
    """Bake current channel - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_bake_channel"
    bl_label = "Bake Channel"
    bl_description = "Bake the current channel"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_channel is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.bake_channel('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to bake channel: {str(e)}")
            return {'CANCELLED'}

class PAINTSYSTEM_OT_ShortcutExportImage(PSContextMixin, Operator):
    """Export current image - shortcut for toolbar"""
    bl_idname = "paint_system.shortcut_export_image"
    bl_label = "Export Image"
    bl_description = "Export the current image"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_channel is not None
    
    def execute(self, context):
        try:
            bpy.ops.paint_system.export_image('INVOKE_DEFAULT')
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to export image: {str(e)}")
            return {'CANCELLED'}

# Main toolbar operator that can execute any Paint System tool
class PAINTSYSTEM_OT_ToolbarExecute(PSContextMixin, Operator):
    """Execute Paint System tool from toolbar"""
    bl_idname = "paint_system.toolbar_execute"
    bl_label = "Paint System Tool"
    bl_description = "Execute a Paint System tool"
    bl_options = {'REGISTER', 'UNDO'}
    
    tool_name: StringProperty(
        name="Tool Name",
        description="Name of the Paint System tool to execute",
        default=""
    )
    
    tool_tooltip: StringProperty(
        name="Tool Tooltip",
        description="Tooltip to show for this tool",
        default=""
    )
    
    @classmethod
    def description(cls, context, properties):
        """Dynamic description/tooltip based on property"""
        if properties.tool_tooltip:
            return properties.tool_tooltip
        return f"Execute {properties.tool_name}"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None
    
    def execute(self, context):
        try:
            # Map tool names to actual operators
            tool_mapping = {
                "New Image Layer": "paint_system.new_image_layer",
                "New Folder": "paint_system.new_folder_layer", 
                "New Solid Color": "paint_system.new_solid_color_layer",
                "New Gradient": "paint_system.new_gradient_layer",
                "New Adjustment": "paint_system.new_adjustment_layer",
                "New Shader": "paint_system.new_shader_layer",
                "Bake Channel": "paint_system.bake_channel",
                "Bake All": "paint_system.bake_all_channels",
                "Rebake": "paint_system.rebake_channel",
                "Export Image": "paint_system.export_image",
                "Export All": "paint_system.export_all_images",
                "Merge Down": "paint_system.merge_down",
                "Merge Up": "paint_system.merge_up",
                "Duplicate Layer": "paint_system.copy_layer",
                "Delete Layer": "paint_system.delete_item",
            }
            
            if self.tool_name in tool_mapping:
                operator_name = tool_mapping[self.tool_name]
                # Execute the operator with INVOKE_DEFAULT to show dialogs if needed
                eval(f"bpy.ops.{operator_name}('INVOKE_DEFAULT')")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, f"Tool '{self.tool_name}' not found")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Failed to execute {self.tool_name}: {str(e)}")
            return {'CANCELLED'}

classes = (
    PAINTSYSTEM_OT_ShortcutMergeDown,
    PAINTSYSTEM_OT_ShortcutMergeUp,
    PAINTSYSTEM_OT_ShortcutDuplicateLayer,
    PAINTSYSTEM_OT_ShortcutDeleteLayer,
    PAINTSYSTEM_OT_ShortcutToggleLayerVisibility,
    PAINTSYSTEM_OT_ShortcutNewImageLayer,
    PAINTSYSTEM_OT_ShortcutBakeChannel,
    PAINTSYSTEM_OT_ShortcutExportImage,
    PAINTSYSTEM_OT_ToolbarExecute,
)

register, unregister = register_classes_factory(classes)