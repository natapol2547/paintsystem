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

# Tool mappings for Paint System
PAINT_SYSTEM_TOOL_MAPPING = [
    # Layer Creation Tools
    {"name": "New Image Layer", "operator": "paint_system.new_image_layer", "icon": 'IMAGE_DATA', "tooltip": "Create a new image layer"},
    {"name": "New Folder", "operator": "paint_system.new_folder_layer", "icon": 'FILE_FOLDER', "tooltip": "Create a new folder layer"},
    {"name": "New Solid Color", "operator": "paint_system.new_solid_color_layer", "icon": 'MATERIAL', "tooltip": "Create a new solid color layer"},
    {"name": "New Gradient", "operator": "paint_system.new_gradient_layer", "icon": 'NODE_TEXTURE', "tooltip": "Create a new gradient layer"},
    {"separator": True},
    # Baking Tools
    {"name": "Bake Channel", "operator": "paint_system.bake_channel", "icon": 'RENDER_RESULT', "tooltip": "Bake the current channel"},
    {"name": "Bake All", "operator": "paint_system.bake_all_channels", "icon": 'RENDER_ANIMATION', "tooltip": "Bake all channels"},
    {"name": "Rebake", "operator": "paint_system.rebake_channel", "icon": 'FILE_REFRESH', "tooltip": "Rebake the current channel"},
    {"separator": True},
    # Export Tools
    {"name": "Export Image", "operator": "paint_system.export_image", "icon": 'EXPORT', "tooltip": "Export current image"},
    {"name": "Export All", "operator": "paint_system.export_all_images", "icon": 'PACKAGE', "tooltip": "Export all images"},
    {"separator": True},
    # Quick Actions
    {"name": "Merge Down", "operator": "paint_system.shortcut_merge_down", "icon": 'TRIA_DOWN_BAR', "tooltip": "Merge layer down"},
    {"name": "Merge Up", "operator": "paint_system.shortcut_merge_up", "icon": 'TRIA_UP_BAR', "tooltip": "Merge layer up"},
    {"name": "Duplicate Layer", "operator": "paint_system.shortcut_duplicate_layer", "icon": 'DUPLICATE', "tooltip": "Duplicate current layer"},
    {"name": "Delete Layer", "operator": "paint_system.shortcut_delete_layer", "icon": 'TRASH', "tooltip": "Delete current layer"},
]

# UI Properties for Paint System Toolbar
class PaintSystemToolbarProps(PropertyGroup):
    """Properties to store toolbar UI state"""
    toolbar_expanded: BoolProperty(
        name="Toolbar Expanded",
        description="Whether the toolbar section is expanded",
        default=True
    )
    
    quick_tools_expanded: BoolProperty(
        name="Quick Tools Expanded", 
        description="Whether the quick tools section is expanded",
        default=True
    )
    
    layers_expanded: BoolProperty(
        name="Layers Expanded",
        description="Whether the layers section is expanded", 
        default=True
    )
    
    baking_expanded: BoolProperty(
        name="Baking Expanded",
        description="Whether the baking section is expanded",
        default=True
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
class PAINTSYSTEM_PT_Toolbar(PSContextMixin, Panel):
    """Paint System Toolbar Panel"""
    bl_label = "Paint System Tools"
    bl_idname = "PAINTSYSTEM_PT_Toolbar"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Paint System'
    bl_parent_id = 'MAT_PT_PaintSystemMainPanel'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
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
        
        # Create a row to hold our two columns
        main_row = layout.row()
        
        # Left column (tools) - Fixed width
        tool_col = main_row.column()
        tool_col.scale_x = 2
        tool_col.scale_y = 1.5
        
        # Right column (content) - Expandable
        content_col = main_row.column()
        content_col.ui_units_x = 100
        
        # Draw tools in left column
        self.draw_tools_column(context, tool_col, toolbar_props)
        
        # Draw content in right column (could be settings, info, etc.)
        self.draw_content_column(context, content_col, toolbar_props)
    
    def draw_collapsible_header(self, layout, toolbar_props, prop_name, text, icon):
        """Draw a collapsible header and return if expanded"""
        row = layout.row()
        expanded = getattr(toolbar_props, prop_name)
        
        # Draw the expand/collapse icon
        row.prop(toolbar_props, prop_name, icon='DOWNARROW_HLT' if expanded else 'RIGHTARROW',
                 icon_only=True, emboss=False)
                 
        # Draw the header text
        row.label(text=text, icon=icon)
        
        return expanded
    
    def draw_tools_column(self, context, layout, toolbar_props):
        """Draw the tools in the left column"""
        box = layout.box()
        grid = box.grid_flow(row_major=True, columns=1, even_columns=True, even_rows=True, align=True)
        button_height = 1.2
        
        for btn_data in PAINT_SYSTEM_TOOL_MAPPING:
            # Check if this is a separator
            if btn_data.get("separator", False):
                grid.separator(factor=1.5)
                continue
                
            # Create button container with fixed size
            row = grid.row()
            row.scale_y = button_height
            row.alignment = 'CENTER'
            
            # Create operator button
            if btn_data["operator"] in ["paint_system.shortcut_merge_down", "paint_system.shortcut_merge_up", 
                                       "paint_system.shortcut_duplicate_layer", "paint_system.shortcut_delete_layer"]:
                # Use our toolbar action operator for shortcut functions
                op = row.operator("paint_system.toolbar_action", text="", icon=btn_data["icon"])
                op.action = btn_data["operator"]
            else:
                # Use direct operator for existing Paint System operators
                op = row.operator(btn_data["operator"], text="", icon=btn_data["icon"])
            
            # Set the tooltip property if available
            if "tooltip" in btn_data:
                if hasattr(op, "tool_tooltip"):
                    op.tool_tooltip = btn_data["tooltip"]
    
    def draw_content_column(self, context, layout, toolbar_props):
        """Draw the content sections in the right column"""
        ps_ctx = self.parse_context(context)
        
        # Quick Info Section
        box = layout.box()
        if self.draw_collapsible_header(box, toolbar_props, "quick_tools_expanded", "Quick Info", 'INFO'):
            # Show current layer info
            if ps_ctx.active_layer:
                box.label(text=f"Layer: {ps_ctx.active_layer.name}", icon='RENDERLAYERS')
            if ps_ctx.active_channel:
                box.label(text=f"Channel: {ps_ctx.active_channel.name}", icon='TEXTURE')
            
            # Show layer count
            if ps_ctx.active_group:
                layer_count = len([layer for layer in ps_ctx.active_group.node_tree.nodes if hasattr(layer, 'ps_type')])
                box.label(text=f"Layers: {layer_count}", icon='OUTLINER')
        
        # Quick Actions Section
        box = layout.box()
        if self.draw_collapsible_header(box, toolbar_props, "layers_expanded", "Quick Actions", 'MODIFIER'):
            row = box.row(align=True)
            row.scale_y = 1.5
            
            # Layer visibility toggle
            if ps_ctx.active_layer:
                global_layer = get_global_layer(ps_ctx.active_layer)
                vis_icon = 'HIDE_OFF' if global_layer and global_layer.enabled else 'HIDE_ON'
                row.operator("paint_system.shortcut_toggle_layer_visibility", text="", icon=vis_icon)
            
            # Layer blend mode quick access (if available)
            row.operator("paint_system.new_image_layer", text="", icon='ADD')
            row.operator("paint_system.copy_layer", text="", icon='DUPLICATE')


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