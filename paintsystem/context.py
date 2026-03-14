from __future__ import annotations

from dataclasses import dataclass
import bpy
from typing import TYPE_CHECKING

from bpy.types import Material

from ..preferences import get_preferences, PaintSystemPreferences
from ..utils.version import is_newer_than

if TYPE_CHECKING:
    from .data import MaterialData, Group, Channel, Layer, LayerRef, GlobalLayer, PaintSystemGlobalData

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
    active_layer_ref: "LayerRef | Layer | None" = None
    unlinked_layer: "Layer" | None = None
    active_global_layer: "GlobalLayer" | None = None

def get_legacy_global_layer(layer: "Layer") -> "GlobalLayer" | None:
    """Get the global layer data from the context."""
    if not layer or not bpy.context.scene or not bpy.context.scene.ps_scene_data:
        return None
    return bpy.context.scene.ps_scene_data.layers.get(layer.ref_layer_id, None)

def get_ps_object(obj) -> bpy.types.Object | None:
    """Return the Paint System-relevant object for *obj*, or ``None``."""
    if not obj:
        return None
    match obj.type:
        case 'EMPTY':
            if obj.parent and obj.parent.type == 'MESH' and hasattr(obj.parent.active_material, 'ps_mat_data'):
                return obj.parent
        case 'MESH':
            return obj
        case 'GREASEPENCIL':
            if is_newer_than(4, 3, 0):
                return obj
    return None

def parse_material(mat: Material) -> tuple["MaterialData", "Group", "Channel", "Layer", "LayerRef | Layer | None"]:
    """Extract active mat_data, group, channel, layer and layer_ref from a material.

    V3 materials (ps_data_version >= 3) resolve the active group via the
    ``group_nodes`` NodeTree-backed slots.  V2 materials (ps_data_version < 3)
    that still have data in the legacy ``groups`` collection return
    ``(mat_data, None, None, None, None)`` — the panels will show the migration
    banner in that case.

    Returns ``(mat_data, group, channel, unlinked_layer, active_layer_ref)``.
    *active_layer_ref* is the ``LayerRef`` (V3) or ``Layer`` (V2) that owns
    the hierarchy position.
    """
    mat_data = None
    active_group = None
    active_channel = None
    unlinked_layer = None
    active_layer_ref = None

    if not (mat and hasattr(mat, 'ps_mat_data') and mat.ps_mat_data):
        return mat_data, active_group, active_channel, unlinked_layer, active_layer_ref

    mat_data = mat.ps_mat_data

    if mat_data.ps_data_version < 3:
        if mat_data.groups:
            return mat_data, None, None, None, None

    group_nodes = mat_data.group_nodes
    if group_nodes and mat_data.active_index >= 0:
        ref = group_nodes[min(mat_data.active_index, len(group_nodes) - 1)]
        if ref.node_tree:
            active_group = ref.node_tree.ps_group_data

    if active_group:
        channel_nodes = active_group.channel_nodes
        if channel_nodes and active_group.active_index >= 0:
            ref = channel_nodes[min(active_group.active_index, len(channel_nodes) - 1)]
            if ref.node_tree:
                active_channel = ref.node_tree.ps_channel_data
        elif not channel_nodes:
            channels = active_group.channels
            if channels and active_group.active_index >= 0:
                active_channel = channels[min(active_group.active_index, len(channels) - 1)]

    if active_channel:
        layer_nodes = active_channel.layer_nodes
        if layer_nodes and active_channel.active_index >= 0:
            layer_ref = layer_nodes[min(active_channel.active_index, len(layer_nodes) - 1)]
            active_layer_ref = layer_ref
            if layer_ref.node_tree:
                unlinked_layer = layer_ref.node_tree.ps_layer_data
        elif not layer_nodes:
            layers = active_channel.layers
            if layers and active_channel.active_index >= 0:
                unlinked_layer = layers[min(active_channel.active_index, len(layers) - 1)]
                active_layer_ref = unlinked_layer

    return mat_data, active_group, active_channel, unlinked_layer, active_layer_ref

def parse_context(context: bpy.types.Context) -> PSContext:
    """Parse the context and return a PSContext object."""
    if not context:
        raise ValueError("Context cannot be None")
    if not isinstance(context, bpy.types.Context):
        raise TypeError("context must be of type bpy.types.Context")
    
    ps_settings = get_preferences(context)
    ps_scene_data = context.scene.ps_scene_data
    obj = context.active_object if hasattr(context, 'active_object') else None
    ps_object = get_ps_object(obj)
    
    ps_objects = []
    if hasattr(context, 'selected_objects'):
        for obj in [*context.selected_objects, context.active_object]:
            ps_obj = get_ps_object(obj)
            if ps_obj and ps_obj not in ps_objects:
                ps_objects.append(ps_obj)
    mat = ps_object.active_material if ps_object else None
    mat_data, active_group, active_channel, unlinked_layer, active_layer_ref = parse_material(mat)
    
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
        active_layer_ref=active_layer_ref,
        unlinked_layer=unlinked_layer,
        active_global_layer=get_legacy_global_layer(unlinked_layer) if unlinked_layer else None
    )

class PSContextMixin:
    """A mixin for classes that need access to the paint system context."""

    @staticmethod
    def parse_context(context: bpy.types.Context) -> PSContext:
        """Return a PSContext parsed from Blender context. Safe to call from class or instance methods."""
        return parse_context(context)