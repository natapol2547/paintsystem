import bpy
from bpy.types import Panel

from .common import PSContextMixin


class IMAGE_PT_PaintSystemUV(PSContextMixin, Panel):
    """Paint System UV Tools"""
    bl_label = "Paint System"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'Paint System'
    
    @classmethod
    def poll(cls, context):
        # Guard against None context
        if not context or not getattr(context, 'area', None):
            return False
        ps_ctx = cls.parse_context(context)
        # Show panel when there's an active channel and active layer
        return ps_ctx.active_channel and ps_ctx.active_layer
    
    def draw_header(self, context):
        layout = self.layout
        if layout:
            layout.label(text="", icon='UV')
    
    def draw(self, context):
        layout = self.layout
        ps_ctx = self.parse_context(context)
        
        # Check if active layer is an image layer
        if ps_ctx.active_layer and ps_ctx.active_layer.type == 'IMAGE' and ps_ctx.active_layer.image:
            # Transfer UV section with settings exposed
            col = layout.column(align=True)
            
            # Main box with header
            box = col.box()
            header_col = box.column(align=True)
            header_row = header_col.row(align=True)
            header_row.scale_y = 1.3
            header_row.label(text="Fix UVs", icon='TOOL_SETTINGS')
            
            # Active UV (source) - with picker and button to set from layer
            if ps_ctx.ps_object and hasattr(ps_ctx.ps_object.data, 'uv_layers'):
                # Active UV section with chunky box
                active_box = box.box()
                active_col = active_box.column(align=True)
                split = active_col.split(factor=0.25, align=True)
                label_col = split.column(align=True)
                label_col.scale_y = 1.3
                label_col.label(text="Active UV", icon='UV')
                row = split.row(align=True)
                row.scale_y = 1.3
                row.prop_search(context.scene, 'ps_active_uv_map', ps_ctx.ps_object.data, "uv_layers", text="")
                row.operator("paint_system.set_active_uv_from_layer", text="", icon='EYEDROPPER')
                row.operator("paint_system.sync_uv_maps", text="", icon='UV_SYNC_SELECT')
                row.popover("PAINTSYSTEM_PT_uv_tools_popover", text="", icon='DOWNARROW_HLT')
                
                # UV Mode selector with chunky box
                mode_box = box.box()
                mode_col = mode_box.column(align=True)
                mode_row = mode_col.row(align=True)
                mode_row.scale_y = 1.3
                mode_row.label(text="Bake to Target", icon='PREFERENCES')
                mode_prop_row = mode_col.row(align=True)
                mode_prop_row.scale_y = 1.3
                mode_prop_row.prop(context.scene, 'ps_uv_transfer_mode', text="")
                
                # New UV (target) selector - shown for Create New and Use Existing modes
                uv_mode = context.scene.ps_uv_transfer_mode
                if uv_mode in {'CREATE_NEW', 'USE_EXISTING'}:
                    # Target settings in same box with separator
                    mode_col.separator(factor=0.5)
                    split = mode_col.split(factor=0.08, align=True)
                    icon_col = split.column(align=True)
                    icon_col.scale_y = 1.5
                    icon_col.label(text="", icon='UV_DATA')
                    prop_row = split.row(align=True)
                    prop_row.scale_y = 1.3
                    if uv_mode == 'USE_EXISTING':
                        prop_row.prop_search(context.scene, 'ps_transfer_uv_map', ps_ctx.ps_object.data, "uv_layers", text="")
                    else:  # CREATE_NEW
                        prop_row.prop(context.scene, 'ps_transfer_uv_map', text="")
                elif uv_mode == 'AUTO_UV':
                    # Auto-unwrap info in same box with separator
                    mode_col.separator(factor=0.5)
                    info_row = mode_col.row(align=True)
                    info_row.scale_y = 1.3
                    info_row.label(text="Auto-unwrap mesh", icon='UV')
                
                # Image Output Settings section
                output_box = box.box()
                output_col = output_box.column(align=True)
                output_row = output_col.row(align=True)
                output_row.scale_y = 1.3
                output_row.label(text="Image Output", icon='IMAGE_DATA')
                
                # Resolution buttons
                res_row = output_col.row(align=True)
                res_row.scale_y = 1.2
                res_row.prop(context.scene, 'ps_transfer_image_resolution', expand=True)
                
                # Custom resolution fields
                if context.scene.ps_transfer_image_resolution == 'CUSTOM':
                    custom_col = output_col.column(align=True)
                    custom_col.scale_y = 1.2
                    custom_col.prop(context.scene, 'ps_transfer_image_width', text="Width")
                    custom_col.prop(context.scene, 'ps_transfer_image_height', text="Height")
                
                # Advanced toggle
                output_col.separator(factor=0.5)
                adv_row = output_col.row(align=True)
                adv_row.scale_y = 1.2
                adv_row.prop(context.scene, 'ps_transfer_show_advanced', text="Advanced", icon='TRIA_DOWN' if context.scene.ps_transfer_show_advanced else 'TRIA_RIGHT', emboss=False, toggle=True)
                
                # Advanced settings - UDIM toggle only if UDIMs detected in the UV layer
                if context.scene.ps_transfer_show_advanced and ps_ctx.active_layer.coord_type == 'UV':
                    from ..paintsystem.data import get_udim_tiles
                    uv_layer = ps_ctx.ps_object.data.uv_layers.get(ps_ctx.active_layer.uv_map_name)
                    if uv_layer:
                        udim_tiles = get_udim_tiles(uv_layer)
                        if udim_tiles and udim_tiles != {1001}:
                            udim_row = output_col.row(align=True)
                            udim_row.scale_y = 1.2
                            udim_row.prop(context.scene, 'ps_transfer_use_udim', toggle=True)
            
            # Transfer button - chunky and prominent
            transfer_box = box.box()
            transfer_col = transfer_box.column(align=True)
            transfer_col.scale_y = 1.8
            transfer_col.operator("paint_system.transfer_uv_direct", text="Transfer UV", icon='EXPORT')
        else:
            layout.label(text="Select an image layer", icon='INFO')


classes = [
    IMAGE_PT_PaintSystemUV,
]


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)


def unregister():
    from bpy.utils import register_class
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
