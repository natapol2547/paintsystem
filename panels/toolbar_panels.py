import bpy
from bpy.utils import register_classes_factory
from bpy.types import Panel, Operator, PropertyGroup
from bpy.props import StringProperty, BoolProperty, EnumProperty, FloatVectorProperty, FloatProperty
from .common import (
    PSContextMixin,
    get_icon,
    scale_content,
    check_group_multiuser
)
from ..paintsystem.data import get_global_layer
from bl_ui.properties_paint_common import UnifiedPaintPanel
from ..utils.version import is_newer_than

# Tool mappings for Paint System organized by category
LAYER_TOOLS = [
    {"name": "New Image Layer", "operator": "paint_system.new_image_layer", "icon": 'IMAGE_DATA', "tooltip": "Create a new image layer"},
    {"name": "New Folder", "operator": "paint_system.new_folder_layer", "icon": 'FILE_FOLDER', "tooltip": "Create a new folder layer"},
    {"name": "New Solid Color", "operator": "paint_system.new_solid_color_layer", "icon": 'MATERIAL', "tooltip": "Create a new solid color layer"},
    {"name": "New Gradient", "operator": "paint_system.new_gradient_layer", "icon": 'NODE_TEXTURE', "tooltip": "Create a new gradient layer"},
]

BAKE_TOOLS = [
    {"name": "Bake Channel", "operator": "paint_system.bake_channel", "icon": 'RENDER_RESULT', "tooltip": "Bake the current channel"},
    {"name": "Bake All Channels", "operator": "paint_system.bake_all_channels", "icon": 'RENDER_ANIMATION', "tooltip": "Bake all channels"},
    {"name": "Rebake Channel", "operator": "paint_system.rebake_channel", "icon": 'FILE_REFRESH', "tooltip": "Rebake the current channel"},
]

EXPORT_TOOLS = [
    {"name": "Export Image", "operator": "paint_system.export_image", "icon": 'EXPORT', "tooltip": "Export current image"},
    {"name": "Export All Images", "operator": "paint_system.export_all_images", "icon": 'PACKAGE', "tooltip": "Export all images"},
]

LAYER_ACTIONS = [
    {"name": "Merge Down", "operator": "paint_system.shortcut_merge_down", "icon": 'TRIA_DOWN_BAR', "tooltip": "Merge layer down"},
    {"name": "Merge Up", "operator": "paint_system.shortcut_merge_up", "icon": 'TRIA_UP_BAR', "tooltip": "Merge layer up"},
    {"name": "Duplicate Layer", "operator": "paint_system.shortcut_duplicate_layer", "icon": 'DUPLICATE', "tooltip": "Duplicate current layer"},
    {"name": "Delete Layer", "operator": "paint_system.shortcut_delete_layer", "icon": 'TRASH', "tooltip": "Delete current layer"},
]

# UI Properties for Paint System Toolbar
class PaintSystemToolbarProps(PropertyGroup):
    """Properties to store toolbar UI state"""
    color_picker_expanded: BoolProperty(
        name="Color Picker Expanded",
        description="Whether the color picker section is expanded",
        default=True
    )
    
    brush_settings_expanded: BoolProperty(
        name="Brush Settings Expanded",
        description="Whether the brush settings section is expanded",
        default=True
    )
    
    layer_tools_expanded: BoolProperty(
        name="Layer Tools Expanded",
        description="Whether the layer tools section is expanded", 
        default=True
    )
    
    bake_tools_expanded: BoolProperty(
        name="Bake Tools Expanded",
        description="Whether the bake tools section is expanded",
        default=True
    )
    
    export_tools_expanded: BoolProperty(
        name="Export Tools Expanded",
        description="Whether the export tools section is expanded",
        default=True
    )
    
    layer_actions_expanded: BoolProperty(
        name="Layer Actions Expanded",
        description="Whether the layer actions section is expanded",
        default=True
    )
    
    advanced_expanded: BoolProperty(
        name="Advanced Expanded",
        description="Whether the advanced settings section is expanded",
        default=False
    )

# Toolbar Operators
class PAINTSYSTEM_OT_ToolbarAction(PSContextMixin, Operator):
    """Execute a Paint System tool action from the toolbar"""
    bl_idname = "paint_system.toolbar_action"
    bl_label = "Paint System Tool"
    bl_options = {'REGISTER', 'UNDO'}
    
    action: StringProperty(
        name="Action",
        description="Action to perform",
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
        return f"Execute {properties.action}"
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None
    
    def execute(self, context):
        try:
            # Execute the specific Paint System operator
            if hasattr(bpy.ops.paint_system, self.action.replace("paint_system.", "")):
                eval(f"bpy.ops.{self.action}('INVOKE_DEFAULT')")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, f"Operator {self.action} not found")
                return {'CANCELLED'}
        except Exception as e:
            self.report({'ERROR'}, f"Failed to execute {self.action}: {str(e)}")
            return {'CANCELLED'}

# Main Toolbar Panel
class PAINTSYSTEM_PT_Toolbar(PSContextMixin, UnifiedPaintPanel, Panel):
    """Paint System Toolbar Panel"""
    bl_label = "Paint System Tools"
    bl_idname = "PAINTSYSTEM_PT_Toolbar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Paint System'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        # Only show in texture paint, vertex paint, and grease pencil modes
        valid_modes = {'PAINT_TEXTURE', 'PAINT_VERTEX', 'PAINT_GPENCIL'}
        if context.mode not in valid_modes:
            return False
        
        ps_ctx = cls.parse_context(context)
        return ps_ctx.ps_object is not None and ps_ctx.active_group is not None
    
    def draw(self, context):
        layout = self.layout
        toolbar_props = context.scene.paint_system_toolbar_props
        ps_ctx = self.parse_context(context)
        
        # Check if we have a valid Paint System context
        if not ps_ctx.active_group:
            layout.label(text="Add Paint System first", icon='INFO')
            return
        
        # ======================
        # COLOR PICKER SECTION
        # ======================
        self.draw_color_picker_section(context, layout, toolbar_props, ps_ctx)
        
        # ======================
        # BRUSH SETTINGS SECTION
        # ======================
        self.draw_brush_settings_section(context, layout, toolbar_props, ps_ctx)
        
        # ======================
        # LAYER TOOLS SECTION
        # ======================
        self.draw_layer_tools_section(context, layout, toolbar_props)
        
        # ======================
        # BAKE TOOLS SECTION
        # ======================
        self.draw_bake_tools_section(context, layout, toolbar_props)
        
        # ======================
        # EXPORT TOOLS SECTION
        # ======================
        self.draw_export_tools_section(context, layout, toolbar_props)
        
        # ======================
        # LAYER ACTIONS SECTION
        # ======================
        self.draw_layer_actions_section(context, layout, toolbar_props)
        
        # ======================
        # ADVANCED SETTINGS SECTION
        # ======================
        self.draw_advanced_section(context, layout, toolbar_props, ps_ctx)
    
    def draw_collapsible_header(self, layout, toolbar_props, prop_name, text, icon='TRIA_DOWN'):
        """Draw a collapsible header and return if expanded"""
        box = layout.box()
        row = box.row()
        expanded = getattr(toolbar_props, prop_name)
        
        # Draw the expand/collapse icon
        row.prop(toolbar_props, prop_name, 
                 icon='DOWNARROW_HLT' if expanded else 'RIGHTARROW',
                 icon_only=True, emboss=False)
        
        # Draw the header text with icon
        row.label(text=text, icon=icon)
        
        return expanded, box
    
    def draw_tool_button(self, layout, tool_data, scale_y=1.2):
        """Draw a single tool button"""
        row = layout.row()
        row.scale_y = scale_y
        
        # Use direct operator for most tools
        if tool_data["operator"].startswith("paint_system.shortcut_"):
            op = row.operator("paint_system.toolbar_action", 
                            text=tool_data["name"], 
                            icon=tool_data["icon"])
            op.action = tool_data["operator"]
            op.tool_tooltip = tool_data.get("tooltip", "")
        else:
            op = row.operator(tool_data["operator"], 
                            text=tool_data["name"], 
                            icon=tool_data["icon"])
    
    def draw_color_picker_section(self, context, layout, toolbar_props, ps_ctx):
        """Draw the color picker section"""
        settings = self.paint_settings(context)
        if not settings or not hasattr(settings, 'brush'):
            return
        
        brush = settings.brush
        
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'color_picker_expanded', 
            "Color Picker", 'COLOR'
        )
        
        if expanded:
            col = box.column(align=True)
            
            # Settings button
            row = col.row(align=True)
            row.scale_y = 1.2
            row.popover(
                panel="MAT_PT_BrushColorSettings",
                icon="SETTINGS",
                text=""
            )
            
            # Color picker
            from ..utils.unified_brushes import get_unified_settings
            prop_owner = get_unified_settings(context, "use_unified_color")
            row = col.row()
            row.scale_y = 1.5 if ps_ctx.ps_settings and hasattr(ps_ctx.ps_settings, 'color_picker_scale') else 1.5
            
            if hasattr(self, 'prop_unified_color_picker'):
                self.prop_unified_color_picker(row, context, brush, "color", value_slider=True)
            else:
                row.template_color_picker(prop_owner, "color", value_slider=True)
            
            # HSV sliders
            col.separator(factor=0.5)
            if not context.preferences.view.color_picker_type == "SQUARE_SV":
                col.prop(ps_ctx.ps_scene_data, "hue", text="Hue", slider=True)
            col.prop(ps_ctx.ps_scene_data, "saturation", text="Saturation", slider=True)
            col.prop(ps_ctx.ps_scene_data, "value", text="Value", slider=True)
            
            # Hex color
            if ps_ctx.ps_settings and hasattr(ps_ctx.ps_settings, 'show_hex_color') and ps_ctx.ps_settings.show_hex_color:
                col.separator(factor=0.5)
                col.prop(ps_ctx.ps_scene_data, "hex_color", text="Hex")
            
            # Color palette
            col.separator()
            if hasattr(context.tool_settings, 'image_paint'):
                image_paint = context.tool_settings.image_paint
                col.template_palette(image_paint, "palette", color=True)
    
    def draw_brush_settings_section(self, context, layout, toolbar_props, ps_ctx):
        """Draw the brush settings section"""
        settings = self.paint_settings(context)
        if not settings or not hasattr(settings, 'brush'):
            return
        
        brush = settings.brush
        
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'brush_settings_expanded',
            "Brush Settings", 'BRUSH_DATA'
        )
        
        if expanded:
            col = box.column(align=True)
            
            # Tooltips button
            if ps_ctx.ps_settings and hasattr(ps_ctx.ps_settings, 'show_tooltips') and ps_ctx.ps_settings.show_tooltips:
                row = col.row()
                row.popover(
                    panel="MAT_PT_BrushTooltips",
                    text='Shortcuts',
                    icon='INFO_LARGE' if is_newer_than(4, 3) else 'INFO'
                )
                col.separator(factor=0.5)
            
            # Brush settings
            from bl_ui.properties_paint_common import brush_settings
            scale_content(context, col, scale_x=1, scale_y=1.1)
            brush_settings(col, context, brush, popover=self.is_popover)
            
            # Preset brushes
            brush_imported = False
            for ps_brush in bpy.data.brushes:
                if ps_brush.name.startswith("PS_"):
                    brush_imported = True
                    break
            
            if not brush_imported:
                col.separator()
                col.operator("paint_system.add_preset_brushes",
                           text="Add Preset Brushes", icon="IMPORT")
    
    def draw_layer_tools_section(self, context, layout, toolbar_props):
        """Draw the layer creation tools section"""
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'layer_tools_expanded',
            "Layer Tools", 'RENDERLAYERS'
        )
        
        if expanded:
            col = box.column(align=True)
            for tool in LAYER_TOOLS:
                self.draw_tool_button(col, tool)
    
    def draw_bake_tools_section(self, context, layout, toolbar_props):
        """Draw the baking tools section"""
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'bake_tools_expanded',
            "Bake Tools", 'RENDER_RESULT'
        )
        
        if expanded:
            col = box.column(align=True)
            for tool in BAKE_TOOLS:
                self.draw_tool_button(col, tool)
    
    def draw_export_tools_section(self, context, layout, toolbar_props):
        """Draw the export tools section"""
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'export_tools_expanded',
            "Export Tools", 'EXPORT'
        )
        
        if expanded:
            col = box.column(align=True)
            for tool in EXPORT_TOOLS:
                self.draw_tool_button(col, tool)
    
    def draw_layer_actions_section(self, context, layout, toolbar_props):
        """Draw the layer actions section"""
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'layer_actions_expanded',
            "Layer Actions", 'MODIFIER'
        )
        
        if expanded:
            col = box.column(align=True)
            for tool in LAYER_ACTIONS:
                self.draw_tool_button(col, tool)
    
    def draw_advanced_section(self, context, layout, toolbar_props, ps_ctx):
        """Draw the advanced settings section"""
        expanded, box = self.draw_collapsible_header(
            layout, toolbar_props, 'advanced_expanded',
            "Advanced Settings", 'SETTINGS'
        )
        
        if expanded:
            col = box.column(align=True)
            
            image_paint = context.tool_settings.image_paint
            if image_paint:
                col.prop(image_paint, "use_occlude", text="Occlude Faces")
                col.prop(image_paint, "use_backface_culling", text="Backface Culling")
                col.prop(image_paint, "use_normal_falloff", text="Normal Falloff")
                
                if image_paint.use_normal_falloff:
                    col.separator(factor=0.5)
                    col.prop(image_paint, "normal_angle", text="Angle", slider=True)
            
            if ps_ctx.ps_settings and hasattr(ps_ctx.ps_settings, 'allow_image_overwrite'):
                col.separator()
                col.prop(ps_ctx.ps_settings, "allow_image_overwrite",
                        text="Auto Image Select", icon='FILE_IMAGE')


classes = (
    PaintSystemToolbarProps,
    PAINTSYSTEM_OT_ToolbarAction,
    PAINTSYSTEM_PT_Toolbar,
)

def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)
    
    # Register properties
    bpy.types.Scene.paint_system_toolbar_props = bpy.props.PointerProperty(type=PaintSystemToolbarProps)

def unregister():
    from bpy.utils import unregister_class
    
    # Unregister properties
    if hasattr(bpy.types.Scene, 'paint_system_toolbar_props'):
        del bpy.types.Scene.paint_system_toolbar_props
    
    for cls in reversed(classes):
        try:
            unregister_class(cls)
        except:
            pass