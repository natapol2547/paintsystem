from __future__ import annotations

from dataclasses import dataclass
import bpy
from typing import TYPE_CHECKING

from bpy.types import Material

from ..preferences import get_preferences, PaintSystemPreferences
from ..utils.version import is_newer_than

if TYPE_CHECKING:
    from .data import MaterialData, Group, Channel, Layer, GlobalLayer, PaintSystemGlobalData

@dataclass
class PSContext:
    ps_settings: "PaintSystemPreferences" | None = None
    ps_scene_data: "PaintSystemGlobalData" | None = None
    active_object: bpy.types.Object | None = None
    ps_object: bpy.types.Object | None = None
    ps_objects: list[bpy.types.Object] | None = None
    active_material: bpy.types.Material | None = None
    ps_mat_data: "MaterialData" | None = None
    active_group: "Group" | None = None
    active_channel: "Channel" | None = None
    active_layer: "Layer" | None = None
    unlinked_layer: "Layer" | None = None
    active_global_layer: "GlobalLayer" | None = None

def get_legacy_global_layer(layer: "Layer") -> "GlobalLayer" | None:
    """Get the global layer data from the context."""
    if not layer or not bpy.context.scene or not bpy.context.scene.ps_scene_data:
        return None
    # for global_layer in bpy.context.scene.ps_scene_data.layers[layer.ref_layer_id]:
    #     if global_layer.name == layer.ref_layer_id:
    #         return global_layer
    return bpy.context.scene.ps_scene_data.layers.get(layer.ref_layer_id, None)

def get_ps_object(obj) -> bpy.types.Object:
    ps_object = None
    if obj:
        match obj.type:
            case 'EMPTY':
                if obj.parent and obj.parent.type == 'MESH' and hasattr(obj.parent.active_material, 'ps_mat_data'):
                    ps_object = obj.parent
            case 'MESH':
                ps_object = obj
            case 'GREASEPENCIL':
                if is_newer_than(4,3,0):
                    ps_object = obj
            case _:
                obj = None
                ps_object = None
    return ps_object

def parse_material(mat: Material) -> tuple["MaterialData", "Group", "Channel", "Layer"]:
    mat_data = None
    groups = None
    active_group = None
    if mat and hasattr(mat, 'ps_mat_data') and mat.ps_mat_data:
        mat_data = mat.ps_mat_data
        groups = mat_data.groups
        if groups and mat_data.active_index >= 0:
            active_group = groups[min(mat_data.active_index, len(groups) - 1)]
    
    channels = None
    active_channel = None
    if active_group:
        channels = active_group.channels
        if channels and active_group.active_index >= 0:
            active_channel = channels[min(active_group.active_index, len(channels) - 1)]

    layers = None
    unlinked_layer = None
    if active_channel:
        layers = active_channel.layers
        if layers and active_channel.active_index >= 0:
            unlinked_layer = layers[min(active_channel.active_index, len(layers) - 1)]
            if unlinked_layer:
                unlinked_layer = unlinked_layer
    
    return mat_data, active_group, active_channel, unlinked_layer

def parse_context(context: bpy.types.Context) -> PSContext:
    """Parse the context and return a PSContext object."""
    if not context:
        raise ValueError("Context cannot be None")
    if not isinstance(context, bpy.types.Context):
        raise TypeError("context must be of type bpy.types.Context")
    
    ps_settings = get_preferences(context)
    ps_scene_data = context.scene.ps_scene_data
    obj = hasattr(context, 'active_object') and context.active_object
    ps_object = get_ps_object(obj)
    
    ps_objects = []
    if hasattr(context, 'selected_objects'):
        for obj in [*context.selected_objects, context.active_object]:
            ps_obj = get_ps_object(obj)
            if ps_obj and ps_obj not in ps_objects:
                ps_objects.append(ps_obj)
    mat = ps_object.active_material if ps_object else None
    mat_data, active_group, active_channel, unlinked_layer = parse_material(mat)
    
    return PSContext(
        ps_settings=ps_settings,
        ps_scene_data=ps_scene_data,
        active_object=obj,
        ps_object=ps_object,
        ps_objects=ps_objects,
        active_material=mat,
        ps_mat_data=mat_data,
        active_group=active_group,
        active_channel=active_channel,
        active_layer=unlinked_layer.get_layer_data() if unlinked_layer else None,
        unlinked_layer=unlinked_layer,
        active_global_layer=get_legacy_global_layer(unlinked_layer) if unlinked_layer else None
    )

class PSContextMixin:
    """A mixin for classes that need access to the paint system context."""

    @staticmethod
    def parse_context(context: bpy.types.Context) -> PSContext:
        """Return a PSContext parsed from Blender context. Safe to call from class or instance methods."""
        return parse_context(context)