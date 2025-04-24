import bpy
from bpy.props import (
    BoolProperty,
    StringProperty,
    FloatVectorProperty,
    EnumProperty,
    IntProperty,
)
from bpy.types import Operator, Context
from .common import get_object_uv_maps
from .paint_system import PaintSystem


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
        objects: list[bpy.types.Object] = []
        if self.multiple_objects:
            objects.extend(context.selected_objects)
        else:
            objects.append(context.active_object)
        
        materials = set()
        for object in objects:
            object_mats = object.data.materials
            if object_mats:
                if self.multiple_materials:
                    for mat in object_mats:
                        if mat in materials:
                            continue
                        with context.temp_override(active_object=object, selected_objects=[object], active_material=mat):
                            error_count += self._process_material(bpy.context)
                        materials.add(mat)
                else:
                    with context.temp_override(active_object=object, selected_objects=[object], active_material=object.active_material):
                        error_count += self._process_material(bpy.context)
                    materials.add(object.active_material)
            else:
                with context.temp_override(active_object=object, selected_objects=[object]):
                    error_count += self._process_material(bpy.context)
        
        if error_count > 0:
            self.report({'WARNING'}, f"Completed with {error_count} error{'s' if error_count > 1 else ''}")
        
        return {'FINISHED'}
    
    # @staticmethod
    # def process_object(self, context: Context, obj: bpy.types.Object):
    #     error_count = 0
    #     materials = set()
    #     if self.multiple_materials:
    #         materials = obj.data.materials
    #         if not materials:
    #             with context.temp_override(active_object=obj, selected_objects=[obj]):
    #                 error_count += self._process_material(bpy.context)
    #         else:
    #             for mat in obj.data.materials:
    #                 with context.temp_override(active_object=obj, selected_objects=[obj], active_material=mat):
    #                     error_count += self._process_material(bpy.context)
    #     else:
    #         with context.temp_override(active_object=obj, selected_objects=[obj]):
    #             error_count += self._process_material(bpy.context)
                
    #     return error_count
    
    def _process_material(self, context: Context):
        try:
            return self.process_material(context)
        except Exception as e:
            import traceback
            print(f"Error processing material: {e}")
            print(traceback.format_exc())
            return 1
        
    def multiple_objects_ui(self, layout):
        box = layout.box()
        box.label(text="Applying to all selected objects", icon='INFO')
    
    def process_material(self, context: Context):
        raise NotImplementedError('This method should be overridden in subclasses')
        return 0  # Return 0 errors by default



class UVLayerHandler(Operator):
    uv_map_mode: EnumProperty(
        name="UV Map",
        items=[
            ('PAINT_SYSTEM', "Paint System UV", "Use the Paint System UV Map"),
            ('OPEN', "Use Existing", "Open an existing UV Map"),
        ]
    )
    uv_map_name: EnumProperty(
        name="UV Map",
        items=get_object_uv_maps
    )

    def get_uv_mode(self, context: Context):
        ps = PaintSystem(context)
        mat_settings = ps.get_material_settings()
        if mat_settings:
            self.uv_map_mode = 'PAINT_SYSTEM' if mat_settings.use_paintsystem_uv else 'OPEN'
            # print(f"UV Mode: {self.uv_map_mode}")

    def set_uv_mode(self, context: Context):
        ps = PaintSystem(context)
        mat_settings = ps.get_material_settings()
        if mat_settings:
            ps.get_material_settings().use_paintsystem_uv = self.uv_map_mode == "PAINT_SYSTEM"
            
        self.ensure_uv_map(context)
        return self.uv_map_mode

    def ensure_uv_map(self, context):
        if self.uv_map_mode == 'PAINT_SYSTEM':
            if 'PaintSystemUVMap' not in [uvmap[0] for uvmap in get_object_uv_maps(self, context)]:
                bpy.ops.paint_system.create_new_uv_map(
                    'INVOKE_DEFAULT', uv_map_name="PaintSystemUVMap")
            self.uv_map_name = "PaintSystemUVMap"
        elif not self.uv_map_name:
            self.report({'ERROR'}, "No UV Map selected")
            return {'CANCELLED'}

    def select_uv_ui(self, layout):
        layout.label(text="UV Map", icon='UV')
        row = layout.row(align=True)
        row.prop(self, "uv_map_mode", expand=True)
        if self.uv_map_mode == 'OPEN':
            layout.prop(self, "uv_map_name", text="")
