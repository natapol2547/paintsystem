import bpy
from bpy.props import IntProperty
from ..paintsystem.data import COORDINATE_TYPE_ENUM, create_ps_image, get_udim_tiles
from ..paintsystem.context import PSContextMixin
from ..custom_icons import get_icon, get_icon_from_socket_type
from ..preferences import get_preferences
from ..utils.unified_brushes import get_unified_settings
from bpy.types import Operator, Context
from bpy.props import BoolProperty, EnumProperty, StringProperty

from ..paintsystem.graph.common import DEFAULT_PS_UV_MAP_NAME
from ..paintsystem.image import *

icons = bpy.types.UILayout.bl_rna.functions["prop"].parameters["icon"].enum_items.keys()

def icon_parser(icon: str, default="NONE") -> str:
    if icon in icons:
        return icon
    return default

def scale_content(context, layout, scale_x=1.2, scale_y=1.2):
    """Scale the content of the panel."""
    prefs = get_preferences(context)
    if not prefs.use_compact_design:
        layout.scale_x = scale_x
        layout.scale_y = scale_y
    return layout

class MultiMaterialOperator(Operator):
    multiple_objects: BoolProperty(
        name="Multiple Objects",
        description="Run the operator on multiple objects",
        default=True,
    )
    multiple_materials: BoolProperty(
        name="Multiple Materials",
        description="Run the operator on multiple materials",
        default=False,
    )
    def execute(self, context: Context):
        error_count = 0
        ps_ctx = PSContextMixin.parse_context(context)
        objects = set()
        objects.add(ps_ctx.ps_object)
        if self.multiple_objects:
            for obj in context.selected_objects:
                if obj.type == 'MESH' and obj.name != "PS Camera Plane":
                    objects.add(obj)
        
        seen_materials = set()
        for obj in objects:
            object_mats = obj.data.materials
            if object_mats:
                if self.multiple_materials:
                    for mat in object_mats:
                        if mat in seen_materials:
                            continue
                        with context.temp_override(object=obj, active_object=obj, selected_objects=[obj], active_material=mat):
                            error_count += not bool(self.process_material(bpy.context))
                        seen_materials.add(mat)
                else:
                    if obj.active_material in seen_materials:
                        continue
                    with context.temp_override(object=obj, active_object=obj, selected_objects=[obj], active_material=obj.active_material):
                        error_count += not bool(self.process_material(bpy.context))
                    seen_materials.add(obj.active_material)
            else:
                with context.temp_override(object=obj, active_object=obj, selected_objects=[obj]):
                    error_count += not bool(self.process_material(bpy.context))
        
        if error_count > 0:
            self.report({'WARNING'}, f"Completed with {error_count} error{'s' if error_count > 1 else ''}")
        
        return {'FINISHED'}
    
    def process_material(self, context: Context):
        """Override this method in subclasses to process the material."""
        raise NotImplementedError("Subclasses must implement this method.")
        
    def multiple_objects_ui(self, layout, context: Context):
        if len(context.selected_objects) > 1:
            box = layout.box()
            box.label(text="Applying to all selected objects", icon='INFO')


class PSUVOptionsMixin():
    
    def update_use_paint_system_uv(self, context):
        if self.use_paint_system_uv and self.coord_type != 'AUTO':
            self.coord_type = 'AUTO'
        elif not self.use_paint_system_uv and self.coord_type == 'AUTO':
            self.coord_type = 'UV'
    
    use_paint_system_uv: BoolProperty(
        name="Use Paint System UV",
        description="Use the Paint System UV",
        default=True,
        update=update_use_paint_system_uv,
        options={'SKIP_SAVE'}
    )
    def update_coord_type(self, context):
        if self.coord_type == 'AUTO' and not self.use_paint_system_uv:
            self.use_paint_system_uv = True
    
    coord_type: EnumProperty(
        name="Coordinate Type",
        items=COORDINATE_TYPE_ENUM,
        default='UV',
        update=update_coord_type,
        options={'SKIP_SAVE'}
    )
    uv_map_name: StringProperty(
        name="UV Map",
        description="Name of the UV map to use",
        options={'SKIP_SAVE'}
    )
    checked_coord_type: BoolProperty(
        name="Checked Coordinate Type",
        description="Checked coordinate type",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    def get_default_uv_map_name(self, context):
        ps_ctx = PSContextMixin.parse_context(context)
        ob = ps_ctx.ps_object
        if ob and ob.type == 'MESH' and ob.data.uv_layers:
            return ob.data.uv_layers[0].name
        return ""
    
    def store_coord_type(self, context):
        """Store the coord_type from the operator to the active channel"""
        ps_ctx = PSContextMixin.parse_context(context)
        if not self.checked_coord_type:
            self.get_coord_type(context)
        if self.use_paint_system_uv:
            self.coord_type = 'AUTO'
            self.uv_map_name = DEFAULT_PS_UV_MAP_NAME
            # User decided to use auto coord type
            ps_ctx.ps_settings.preferred_coord_type = "AUTO"
        elif self.coord_type == 'UV':
            # User decided to use UV coord type
            ps_ctx.ps_settings.preferred_coord_type = "UV"
        if ps_ctx.active_group:
            ps_ctx.active_group.coord_type = self.coord_type
            ps_ctx.active_group.uv_map_name = self.uv_map_name
    
    def get_coord_type(self, context):
        """Get the coord_type from the active channel and set it on the operator"""
        ps_ctx = PSContextMixin.parse_context(context)
        self.checked_coord_type = True
        self.uv_map_name = self.get_default_uv_map_name(context)
        if ps_ctx.ps_settings.preferred_coord_type != 'UNDETECTED':
            if ps_ctx.ps_settings.preferred_coord_type == 'AUTO':
                self.use_paint_system_uv = True
            else:
                self.use_paint_system_uv = False
            self.coord_type = ps_ctx.ps_settings.preferred_coord_type
            return
        if ps_ctx.active_channel:
            past_coord_type = ps_ctx.active_group.coord_type
            if past_coord_type == 'AUTO':
                self.use_paint_system_uv = True
            else:
                self.use_paint_system_uv = False
                self.coord_type = past_coord_type
            past_uv_map_name = ps_ctx.active_group.uv_map_name
            if past_uv_map_name:
                self.uv_map_name = past_uv_map_name
            
    def select_coord_type_ui(self, layout, context, show_warning=True):
        ps_ctx = PSContextMixin.parse_context(context)
        row = layout.row(align=True)
        row.label(text="Coordinate System", icon_value=get_icon('transform'))
        row.prop(self, "use_paint_system_uv", text="Use AUTO UV?", toggle =1)
        if self.use_paint_system_uv:
            info_box = layout.box()
            if not ps_ctx.ps_object.data.uv_layers.get(DEFAULT_PS_UV_MAP_NAME):
                info_box.alert = True
                info_box.label(text="Will create a new UV Map: " + DEFAULT_PS_UV_MAP_NAME, icon='ERROR')
            else:
                info_box.label(text="Using UV Map: " + DEFAULT_PS_UV_MAP_NAME, icon='INFO')
            return
        layout.prop(self, "coord_type", text="")
        if self.coord_type != 'UV':
            if show_warning:
            # Warning that painting may not work as expected
                box = layout.box()
                box.alert = True
                box.label(text="Painting may not work in this mode", icon='ERROR')
        else:
            row = layout.row(align=True)
            row.prop_search(self, "uv_map_name", ps_ctx.ps_object.data, "uv_layers", text="")
            if not self.uv_map_name:
                row.alert = True


class PSImageCreateMixin(PSUVOptionsMixin):
    image_name: StringProperty(
        name="Image Name",
        description="Name of the new image",
        default="New Image",
        options={'SKIP_SAVE'}
    )
    image_resolution: EnumProperty(
        items=[
            ('1024', "1024", "1024x1024"),
            ('2048', "2048", "2048x2048"),
            ('4096', "4096", "4096x4096"),
            ('8192', "8192", "8192x8192"),
            ('CUSTOM', "Custom", "Custom Resolution"),
        ],
        default='2048'
    )
    image_width: IntProperty(
        name="Width",
        default=1024,
        min=1,
        description="Width of the image in pixels",
        subtype='PIXEL'
    )
    image_height: IntProperty(
        name="Height",
        default=1024,
        min=1,
        description="Height of the image in pixels",
        subtype='PIXEL'
    )
    use_udim_tiles: BoolProperty(
        name="Use UDIM Tiles",
        description="Use UDIM tiles for the image layer",
        default=False
    )
    use_float: BoolProperty(
        name="Use Float",
        description="Use float to bake the image",
        default=False,
        options={'SKIP_SAVE'}
    )
    
    def image_create_ui(self, layout, context, show_name=True, show_float=True):
        if show_name:
            row = layout.row(align=True)
            scale_content(context, row)
            row.prop(self, "image_name")
        box = layout.box()
        box.label(text="Image Resolution", icon='IMAGE_DATA')
        row = box.row(align=True)
        row.prop(self, "image_resolution", expand=True)
        if self.image_resolution == 'CUSTOM':
            col = box.column(align=True)
            col.prop(self, "image_width", text="Width")
            col.prop(self, "image_height", text="Height")
        if self.coord_type == 'UV':
            ps_ctx = PSContextMixin.parse_context(context)
            udim_tiles = get_udim_tiles(ps_ctx.ps_object, self.uv_map_name)
            use_udim_tiles = udim_tiles != {1001}
            if udim_tiles and use_udim_tiles:
                box.prop(self, "use_udim_tiles")
        if show_float:
            box.prop(self, "use_float", text="Use Float")
            
    def create_image(self, context):
        if self.image_resolution != 'CUSTOM':
            self.image_width = int(self.image_resolution)
            self.image_height = int(self.image_resolution)
        if self.coord_type == 'UV':
            ps_ctx = PSContextMixin.parse_context(context)
            use_udim_tiles = get_udim_tiles(ps_ctx.ps_object, self.uv_map_name) != {1001} and self.use_udim_tiles
            img = create_ps_image(self.image_name, self.image_width, self.image_height, use_udim_tiles=use_udim_tiles, objects=[ps_ctx.ps_object], uv_layer_name=self.uv_map_name, use_float=self.use_float)
        else:
            img = create_ps_image(self.image_name, self.image_width, self.image_height, use_float=self.use_float)
        return img
    
    def get_coord_type(self, context):
        """Get the coord_type from the active channel and set it on the operator"""
        super().get_coord_type(context)
        ps_ctx = PSContextMixin.parse_context(context)
        if ps_ctx.ps_object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode="OBJECT")
        self.use_udim_tiles = get_udim_tiles(ps_ctx.ps_object, self.uv_map_name) != {1001}


class PSImageFilterMixin():

    image_name: StringProperty()
    
    def invoke_get_image(self, context):
        ps_ctx = PSContextMixin.parse_context(context)
        if ps_ctx.active_channel.use_bake_image:
            image = ps_ctx.active_channel.bake_image
        elif ps_ctx.active_layer:
            image = ps_ctx.active_layer.image
        if image:
            self.image_name = image.name

    def get_image(self, context) -> bpy.types.Image:
        if self.image_name:
            image = bpy.data.images.get(self.image_name)
            if not image:
                self.report({'ERROR'}, "Image not found")
                return None
        else:
            ps_ctx = PSContextMixin.parse_context(context)
            if ps_ctx.active_channel.use_bake_image:
                image = ps_ctx.active_channel.bake_image
            elif ps_ctx.active_layer:
                image = ps_ctx.active_layer.image
            if not image:
                self.report({'ERROR'}, "Layer Does not have an image")
                return None
        return image