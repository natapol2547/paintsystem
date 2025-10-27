import bpy
from bpy.props import IntProperty
from ..paintsystem.data import PSContextMixin, get_global_layer, COORDINATE_TYPE_ENUM
from ..custom_icons import get_icon
from ..preferences import get_preferences
from ..utils.unified_brushes import get_unified_settings
from bpy.types import Operator, Context
from bpy.props import BoolProperty, EnumProperty, StringProperty

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
    coord_type: EnumProperty(
        name="Coordinate Type",
        items=COORDINATE_TYPE_ENUM,
        default='UV'
    )
    uv_map_name: StringProperty(
        name="UV Map",
        description="Name of the UV map to use",
        default="UVMap"
    )
    
    def store_coord_type(self, context):
        """Store the coord_type from the operator to the active channel"""
        ps_ctx = PSContextMixin.parse_context(context)
        if ps_ctx.active_group:
            ps_ctx.active_group.coord_type = self.coord_type
            ps_ctx.active_group.uv_map_name = self.uv_map_name
    
    def get_coord_type(self, context):
        """Get the coord_type from the active channel and set it on the operator"""
        ps_ctx = PSContextMixin.parse_context(context)
        if ps_ctx.active_channel:
            self.coord_type = ps_ctx.active_group.coord_type
            self.uv_map_name = ps_ctx.active_group.uv_map_name
            
    def select_coord_type_ui(self, layout, context):
        layout.label(text="Coordinate Type", icon='UV')
        layout.prop(self, "coord_type", text="")
        if self.coord_type not in ['AUTO', 'UV']:
            # Warning that painting may not work as expected
            box = layout.box()
            box.alert = True
            box.label(text="Painting may not work in this mode", icon='ERROR')
        
        if self.coord_type == 'UV':
            row = layout.row(align=True)
            row.prop_search(self, "uv_map_name", context.object.data, "uv_layers", text="")
            if not self.uv_map_name:
                row.alert = True


class PSImageCreateMixin():
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
    
    def image_create_ui(self, layout, context, show_name=True):
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
            
    def create_image(self):
        print("Creating image")
        self.image_width = int(self.image_resolution)
        self.image_height = int(self.image_resolution)
        img = bpy.data.images.new(
            name=self.image_name, width=self.image_width, height=self.image_height, alpha=True)
        img.generated_color = (0, 0, 0, 0)
        img.pack()
        return img


class PSImageFilterMixin():

    image_name: StringProperty()

    def get_image(self, context) -> bpy.types.Image:
        if self.image_name:
            image = bpy.data.images.get(self.image_name)
            if not image:
                self.report({'ERROR'}, "Image not found")
                return None
        else:
            ps_ctx = PSContextMixin.parse_context(context)
            if ps_ctx.active_global_layer:
                image = ps_ctx.active_global_layer.image
            else:
                self.report({'ERROR'}, "Layer Does not have an image")
                return None
        return image
    