import bpy
from bpy.types import Operator, Object, NodeTree, Node
from bpy.utils import register_classes_factory

from ..paintsystem.version_check import get_latest_version, get_current_version, reset_version_cache
from .common import PSContextMixin

from ..paintsystem import data as _ps_data
from ..paintsystem.data import (
    LegacyPaintSystemContextParser,
    LegacyPaintSystemLayer,
    LAYER_TYPE_ENUM,
)
from ..paintsystem.graph.nodetree_builder import capture_node_state, apply_node_state
from ..utils.nodes import find_nodes
from bpy_extras.node_utils import connect_sockets
from ..utils.version import is_online
from ..preferences import addon_package
import addon_utils
from ..utils.logging import get_logger

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# V2 → V3 migration helpers
# ---------------------------------------------------------------------------

def _copy_pg(src, dst, skip_props=None):
    """Copy all non-collection, non-readonly properties from *src* to *dst*.

    Handles scalar, enum, bool, string, float, and pointer properties.
    Collections must be handled separately by the caller.
    """
    _skip = {'rna_type', 'updating_name_flag'} | (skip_props or set())
    for prop in src.bl_rna.properties:
        pid = prop.identifier
        if pid in _skip or prop.is_readonly:
            continue
        if prop.type == 'COLLECTION':
            continue
        try:
            setattr(dst, pid, getattr(src, pid))
        except (AttributeError, TypeError, RuntimeError):
            pass


def _copy_marker_actions(src_layer, dst_layer):
    """Copy the MarkerAction collection from *src_layer* to *dst_layer*."""
    for action in src_layer.actions:
        new_action = dst_layer.actions.add()
        _copy_pg(action, new_action)


def _copy_masks(src_layer, dst_layer):
    """Copy the LayerMask collection from *src_layer* to *dst_layer*."""
    for mask in src_layer.masks:
        new_mask = dst_layer.masks.add()
        _copy_pg(mask, new_mask)


def _copy_layer_to_nt(src_layer, layer_nt):
    """Copy a V2 Layer's properties into a NodeTree's ps_layer_data.

    Tags the NodeTree as LAYER and populates ``ps_layer_data``.
    ``auto_update_node_tree`` is left **False**; the caller re-enables it
    after the full migration completes.
    """
    layer_nt.ps_type = 'LAYER'
    dst = layer_nt.ps_layer_data
    dst.auto_update_node_tree = False
    _copy_pg(src_layer, dst,
             skip_props={'auto_update_node_tree', 'actions', 'masks',
                         'node_tree', 'linked_layer_uid', 'linked_material'})
    _copy_marker_actions(src_layer, dst)
    _copy_masks(src_layer, dst)
    if dst.type != src_layer.type:
        logger.warning(
            "  _copy_layer_to_nt: type mismatch! src=%s dst=%s (uid=%s)",
            src_layer.type, dst.type, src_layer.uid,
        )
    logger.info(
        "  _copy_layer_to_nt: uid=%s name='%s' type=%s -> NT='%s' (dst.type=%s)",
        src_layer.uid, src_layer.name, src_layer.type, layer_nt.name, dst.type,
    )
    return dst


def _find_v2_layer_by_uid(material, uid):
    """Search a V2 material's groups/channels/layers for a layer with the given uid."""
    if not material:
        logger.warning("    _find_v2_layer_by_uid: material is None")
        return None
    ps_data = getattr(material, 'ps_mat_data', None)
    if not ps_data:
        logger.warning("    _find_v2_layer_by_uid: material '%s' has no ps_mat_data",
                        material.name)
        return None
    logger.info("    _find_v2_layer_by_uid: searching '%s' (groups=%d, version=%d) "
                "for uid='%s'",
                material.name, len(ps_data.groups), ps_data.ps_data_version, uid)
    for group in ps_data.groups:
        for channel in group.channels:
            for layer in channel.layers:
                if layer.uid == uid:
                    logger.info("    _find_v2_layer_by_uid: FOUND layer '%s' "
                                "type=%s in group='%s' channel='%s'",
                                layer.name, layer.type, group.name, channel.name)
                    return layer
    logger.warning("    _find_v2_layer_by_uid: NOT FOUND in '%s'. "
                    "Available layer uids:", material.name)
    for group in ps_data.groups:
        for channel in group.channels:
            for layer in channel.layers:
                logger.warning("      group='%s' channel='%s' layer='%s' "
                                "uid=%s type=%s",
                                group.name, channel.name, layer.name,
                                layer.uid, layer.type)
    return None


def _copy_channel_to_nt(src_channel, channel_nt, uid_to_layer_nt):
    """Copy a V2 Channel's properties into a NodeTree's ps_channel_data.

    Tags the NodeTree as CHANNEL and populates ``ps_channel_data``.
    Layer data is written into each layer's NodeTree and a LayerRef is
    added to ``ps_channel_data.layer_nodes``.

    For linked layers (V2: ``is_linked=True``, ``type='BLANK'``), the
    original layer is resolved via ``linked_material`` + ``linked_layer_uid``.
    If the original has already been migrated its NodeTree is reused;
    otherwise it is migrated on the spot so the LayerRef can share it.

    ``auto_update_node_tree`` is left **False** on all written PropertyGroups.
    """
    channel_nt.ps_type = 'CHANNEL'
    dst = channel_nt.ps_channel_data
    dst.auto_update_node_tree = False
    _copy_pg(src_channel, dst,
             skip_props={'layers', 'layer_nodes', 'auto_update_node_tree',
                         'node_tree'})

    for src_layer in src_channel.layers:
        logger.info(
            "  Layer uid=%s name='%s' type=%s is_linked=%s "
            "linked_uid='%s' linked_mat=%s has_node_tree=%s",
            src_layer.uid, src_layer.name, src_layer.type,
            src_layer.is_linked, src_layer.linked_layer_uid,
            (src_layer.linked_material.name
             if src_layer.linked_material else 'None'),
            src_layer.node_tree is not None,
        )

        if src_layer.is_linked:
            linked_uid = src_layer.linked_layer_uid
            if linked_uid in uid_to_layer_nt:
                layer_nt = uid_to_layer_nt[linked_uid]
                logger.info(
                    "    -> LINKED (cached): reusing NT='%s'", layer_nt.name,
                )
            else:
                linked_mat = src_layer.linked_material
                logger.info(
                    "    -> LINKED (resolving): searching material '%s' for uid '%s'",
                    linked_mat.name if linked_mat else 'None', linked_uid,
                )
                original = _find_v2_layer_by_uid(linked_mat, linked_uid)
                if original and original.node_tree:
                    layer_nt = original.node_tree
                    _copy_layer_to_nt(original, layer_nt)
                    uid_to_layer_nt[linked_uid] = layer_nt
                    logger.info(
                        "    -> Resolved original: uid=%s name='%s' type=%s NT='%s'",
                        original.uid, original.name, original.type, layer_nt.name,
                    )
                else:
                    logger.warning(
                        "    -> FAILED to resolve linked layer uid='%s' "
                        "(original=%s, has_node_tree=%s) — skipping.",
                        linked_uid,
                        original.name if original else 'None',
                        (original.node_tree is not None) if original else 'N/A',
                    )
                    continue
        elif src_layer.node_tree:
            layer_nt = src_layer.node_tree
            if src_layer.uid not in uid_to_layer_nt:
                _copy_layer_to_nt(src_layer, layer_nt)
                uid_to_layer_nt[src_layer.uid] = layer_nt
                logger.info("    -> NORMAL: migrated to NT='%s'", layer_nt.name)
            else:
                layer_nt = uid_to_layer_nt[src_layer.uid]
                logger.info(
                    "    -> NORMAL (already migrated): reusing NT='%s'",
                    layer_nt.name,
                )
        else:
            logger.warning(
                "    -> SKIPPED: not linked and no node_tree",
            )
            continue

        ref = dst.layer_nodes.add()
        ref.node_tree = layer_nt

    return dst


def _reenable_auto_update(ps_data):
    """Re-enable ``auto_update_node_tree`` on every migrated V3 PropertyGroup.

    Called once after **all** data has been copied so that no update callback
    can fire during the migration window.
    """
    for group_ref in ps_data.group_nodes:
        nt = group_ref.node_tree
        if not nt:
            continue
        group = nt.ps_group_data
        group.auto_update_node_tree = True

        for ch_ref in group.channel_nodes:
            ch_nt = ch_ref.node_tree
            if not ch_nt:
                continue
            channel = ch_nt.ps_channel_data
            channel.auto_update_node_tree = True
            for layer_ref in channel.layer_nodes:
                if layer_ref.node_tree:
                    layer_ref.node_tree.ps_layer_data.auto_update_node_tree = True

def _unlink_id_pointers(pg):
    """
    Recursively walk a PropertyGroup and nullify any pointers to Blender IDs.
    This works around Blender's ID user decrement bug when clearing nested PropertyGroups.
    Collections are always readonly in Blender RNA (you can't replace the collection
    itself, only its items), so they are handled separately outside the readonly guard.
    """
    for prop in pg.bl_rna.properties:
        pid = prop.identifier

        if prop.type == 'COLLECTION':
            # Always recurse into collections regardless of readonly flag.
            for item in getattr(pg, pid):
                _unlink_id_pointers(item)

        elif prop.type == 'POINTER' and not prop.is_readonly:
            val = getattr(pg, pid, None)
            if val is None:
                continue
            if isinstance(val, bpy.types.ID):
                setattr(pg, pid, None)
            elif isinstance(val, bpy.types.PropertyGroup):
                _unlink_id_pointers(val)


def _migrate_material_v2_to_v3(ps_data, uid_to_layer_nt):
    """Migrate a single material's ps_mat_data from V2 to V3 in-place.

    V3 structure:
      MaterialData.group_nodes → GroupNodeRef → NodeTree(GROUP)
        ps_group_data.channel_nodes → ChannelRef → NodeTree(CHANNEL)
          ps_channel_data.layer_nodes → LayerRef → NodeTree(LAYER)

    *uid_to_layer_nt* is shared across all materials so that cross-material
    linked layers (V2 ``linked_material`` + ``linked_layer_uid``) can
    resolve to a NodeTree already migrated from a different material.

    All ``auto_update_node_tree`` flags are kept **False** throughout the
    entire copy phase.  Only after every group, channel, and layer has been
    migrated does ``_reenable_auto_update`` flip them back to True, ensuring
    no ``update_node_tree`` callback fires during migration.
    """
    mat_name = ps_data.id_data.name if ps_data.id_data else '<unknown>'
    logger.info("=== Migrating material '%s' ===", mat_name)

    for v2_group in ps_data.groups:
        group_nt = v2_group.node_tree
        if not group_nt:
            logger.warning("V2 group '%s' has no node_tree — skipping.", v2_group.name)
            continue

        logger.info("Group '%s' -> NT='%s'", v2_group.name, group_nt.name)
        group_nt.ps_type = 'GROUP'
        target_group = group_nt.ps_group_data
        target_group.auto_update_node_tree = False

        _copy_pg(v2_group, target_group,
                 skip_props={'channels', 'channel_nodes',
                             'auto_update_node_tree', 'node_tree'})

        for v2_channel in v2_group.channels:
            ch_nt = v2_channel.node_tree
            if not ch_nt:
                logger.warning("V2 channel '%s' has no node_tree — skipping.", v2_channel.name)
                continue
            logger.info(" Channel '%s' -> NT='%s' (%d layers)",
                        v2_channel.name, ch_nt.name, len(v2_channel.layers))
            _copy_channel_to_nt(v2_channel, ch_nt, uid_to_layer_nt)

            ch_ref = target_group.channel_nodes.add()
            ch_ref.node_tree = ch_nt

        ref = ps_data.group_nodes.add()
        ref.node_tree = group_nt

    # Keep active_index in bounds for the new group_nodes list.
    new_len = len(ps_data.group_nodes)
    if new_len > 0:
        ps_data.active_index = min(ps_data.active_index, new_len - 1)
    else:
        ps_data.active_index = 0

    # Log the final V3 state before cleanup.
    logger.info("--- V3 result for '%s' ---", mat_name)
    for gi, gref in enumerate(ps_data.group_nodes):
        gnt = gref.node_tree
        if not gnt:
            logger.info("  group_nodes[%d]: NT=None", gi)
            continue
        gd = gnt.ps_group_data
        logger.info("  group_nodes[%d]: NT='%s'  channels=%d",
                     gi, gnt.name, len(gd.channel_nodes))
        for ci, cref in enumerate(gd.channel_nodes):
            cnt = cref.node_tree
            if not cnt:
                logger.info("    channel_nodes[%d]: NT=None", ci)
                continue
            cd = cnt.ps_channel_data
            logger.info("    channel_nodes[%d]: NT='%s'  layers=%d",
                         ci, cnt.name, len(cd.layer_nodes))
            for li, lref in enumerate(cd.layer_nodes):
                lnt = lref.node_tree
                if not lnt:
                    logger.info("      layer_nodes[%d]: NT=None", li)
                    continue
                ld = lnt.ps_layer_data
                logger.info(
                    "      layer_nodes[%d]: NT='%s' type=%s name='%s' uid=%s",
                    li, lnt.name, ld.type, ld.name, ld.uid,
                )

    # Free V2 data and mark this material as V3.
    for v2_group in ps_data.groups:
        _unlink_id_pointers(v2_group)

    ps_data.groups.clear()
    ps_data.ps_data_version = 3

    _reenable_auto_update(ps_data)

pid_mapping = {
    "name": "name",
    "enabled": "enabled",
    "image": "image",
    "clip": "is_clip",
    "lock_alpha": "lock_alpha",
    "lock_layer": "lock_layer",
    "external_image": "external_image",
    "expanded": "is_expanded",
}

type_mapping = {
    "FOLDER": "FOLDER",
    "IMAGE": "IMAGE",
    "SOLID_COLOR": "SOLID_COLOR",
    "ATTRIBUTE": "ATTRIBUTE",
    "ADJUSTMENT": "ADJUSTMENT",
    "SHADER": "SHADER",
    "NODE_GROUP": "NODE_GROUP",
    "GRADIENT": "GRADIENT",
}

def get_legacy_layer_adjustment_type(legacy_layer: LegacyPaintSystemLayer) -> str:
    adjustment_type = None
    for node in legacy_layer.node_tree.nodes:
        if node.label == "Adjustment":
            adjustment_type = node.type
            break
    return adjustment_type

def get_legacy_layer_gradient_type(legacy_layer: LegacyPaintSystemLayer) -> str:
    for node in legacy_layer.node_tree.nodes:
        if node.bl_idname == "ShaderNodeSeparateXYZ":
            return "LINEAR"
    return "RADIAL"

def get_legacy_layer_empty_object(legacy_layer: LegacyPaintSystemLayer) -> Object:
    tex_coord_node = legacy_layer.node_tree.nodes["Texture Coordinate"]
    if tex_coord_node:
        return tex_coord_node.object
    return None

def find_node_by_name(node_tree: NodeTree, name: str) -> Node:
    for node in node_tree.nodes:
        if node.name == name:
            return node
    return None

class PAINTSYSTEM_OT_UpdatePaintSystemData(PSContextMixin, Operator):
    bl_idname = "paint_system.update_paint_system_data"
    bl_description = "Update Paint System Data"
    bl_label = "Update Paint System Data"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        legacy_ps_ctx = LegacyPaintSystemContextParser(context)
        legacy_groups = legacy_ps_ctx.get_material_settings().groups
        ps_ctx = self.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        warning_messages = []
        for legacy_group in legacy_groups:
            # Workaround to remap alpha socket name
            for item in legacy_group.node_tree.interface.items_tree:
                if item.item_type == 'SOCKET' and item.name == "Alpha":
                    item.name = "Color Alpha"
            legacy_group_nodes = find_nodes(ps_ctx.active_material.node_tree, {'bl_idname': 'ShaderNodeGroup', 'node_tree': legacy_group.node_tree})
            relink_map = {}
            for node_group in legacy_group_nodes:
                # Snapshot link endpoints so we don't hold onto link objects that Blender may free
                input_links = []
                output_links = []
                for input_socket in node_group.inputs[:]:
                    for link in input_socket.links:
                        input_links.append({
                            'from_socket': link.from_socket,
                            'dest_name': getattr(input_socket, "name", None),
                        })
                for output_socket in node_group.outputs[:]:
                    for link in output_socket.links:
                        output_links.append({
                            'to_socket': link.to_socket,
                            'src_name': getattr(link.from_socket, "name", None),
                        })
                relink_map[node_group] = {
                    'input_links': input_links,
                    'output_links': output_links,
                }
            new_group = ps_mat_data.create_new_group(context, legacy_group.name, legacy_group.node_tree)
            new_channel = new_group.create_channel(context, channel_name='Color', channel_type='COLOR', use_alpha=True)
            ps_ctx = self.parse_context(context)
            for legacy_layer in legacy_group.items:
                if legacy_layer.type not in [layer[0] for layer in LAYER_TYPE_ENUM]:
                    logger.warning(f"Skipping layer {legacy_layer.name} of type {legacy_layer.type} because it is not supported anymore")
                    warning_messages.append(f"Skipping layer {legacy_layer.name} of type {legacy_layer.type} because it is not supported anymore")
                    continue
                new_layer = new_channel.create_layer(context, legacy_layer.name, legacy_layer.type)
                
                # Apply legacy layer properties
                for prop in legacy_layer.bl_rna.properties:
                    pid = getattr(prop, 'identifier', '')
                    if not pid or getattr(prop, 'is_readonly', False):
                        continue
                    if pid in {"name", "node_tree", "type"} or pid not in pid_mapping:
                        continue
                    setattr(new_layer, pid_mapping[pid], getattr(legacy_layer, pid))
                if legacy_layer.type == "ADJUSTMENT":
                    new_layer.adjustment_type = get_legacy_layer_adjustment_type(legacy_layer)
                if legacy_layer.type == "GRADIENT":
                    new_layer.gradient_type = get_legacy_layer_gradient_type(legacy_layer)
                    new_layer.empty_object = get_legacy_layer_empty_object(legacy_layer)
                if legacy_layer.type == "IMAGE":
                    uv_map_node = legacy_ps_ctx.find_node(legacy_layer.node_tree, {'bl_idname': 'ShaderNodeUVMap'})
                    if uv_map_node:
                        uv_map_name = uv_map_node.uv_map
                        new_layer.coord_type = "UV"
                        new_layer.uv_map_name = uv_map_name
                new_layer.update_node_tree(context)
                if legacy_layer.type == "NODE_GROUP":
                    new_layer.custom_node_tree = legacy_layer.node_tree

                    def _pick_enum(items, target, fallback="_NONE_"):
                        for ident, name, *_ in items:
                            if ident == target or name == target:
                                return ident
                        return fallback if items else fallback

                    # Inputs (include _NONE_)
                    input_items = new_layer.get_inputs_enum(context)
                    if input_items:
                        new_layer.color_input_name = _pick_enum(input_items, "Color", fallback=input_items[0][0])
                        new_layer.alpha_input_name = _pick_enum(input_items, "Color Alpha", fallback=input_items[0][0])

                    # Outputs (may lack alpha; use first available if target missing)
                    try:
                        color_out_items = new_layer.get_color_enum(context)
                    except TypeError:
                        color_out_items = []
                    if color_out_items:
                        new_layer.color_output_name = _pick_enum(color_out_items, "Color", fallback=color_out_items[0][0])

                    try:
                        alpha_out_items = new_layer.get_alpha_enum(context)
                    except TypeError:
                        alpha_out_items = []
                    if alpha_out_items:
                        new_layer.alpha_output_name = _pick_enum(alpha_out_items, "Color Alpha", fallback=alpha_out_items[0][0])

                # Preserve blend mode if possible
                legacy_mix = next(
                    (n for n in legacy_layer.node_tree.nodes
                     if getattr(n, "bl_idname", "") == "ShaderNodeMix" and getattr(n, "data_type", "") == "RGBA"),
                    None,
                ) if legacy_layer.node_tree else None
                if legacy_mix and hasattr(new_layer, "blend_mode"):
                    new_layer.blend_mode = getattr(legacy_mix, "blend_type", new_layer.blend_mode)
                # Apply node values
                # Copy rgb node value
                if legacy_layer.type == "SOLID_COLOR":
                    rgb_node = find_node_by_name(legacy_layer.node_tree, 'RGB')
                    if rgb_node:
                        new_layer.source_node.outputs[0].default_value = rgb_node.outputs[0].default_value
                if legacy_layer.type == "ADJUSTMENT":
                    state = capture_node_state(legacy_ps_ctx.find_node(legacy_layer.node_tree, {'label': 'Adjustment'}))
                    apply_node_state(new_layer.source_node, state)
                if legacy_layer.type == "GRADIENT":
                    state = capture_node_state(legacy_ps_ctx.find_node(legacy_layer.node_tree, {'label': 'Gradient Color Ramp'}))
                    apply_node_state(new_layer.source_node, state)
                
                # Copy opacity node value
                opacity_node = find_node_by_name(legacy_layer.node_tree, 'Opacity')
                if opacity_node:
                    new_layer.pre_mix_node.inputs['Opacity'].default_value = opacity_node.inputs[0].default_value
                # refresh paintsystem context
            new_channel.update_node_tree(context)
            new_group.update_node_tree(context)
            
            # Remap the node tree
            # Find node group
            for node_group, links in relink_map.items():
                node_group.node_tree = new_group.get_node_tree()
                for link in links['input_links']:
                    dest_name = link.get('dest_name')
                    from_socket = link.get('from_socket')
                    if dest_name and dest_name in node_group.inputs and from_socket:
                        connect_sockets(from_socket, node_group.inputs[dest_name])
                for link in links['output_links']:
                    src_name = link.get('src_name')
                    to_socket = link.get('to_socket')
                    if src_name and src_name in node_group.outputs and to_socket:
                        connect_sockets(node_group.outputs[src_name], to_socket)
        legacy_groups.clear()
        if warning_messages:
            self.report({'WARNING'}, "\n".join(warning_messages))
        return {'FINISHED'}


class PAINTSYSTEM_OT_MigrateV2ToV3(Operator):
    """Migrate all Paint System materials in this file from V2 to V3 format.

    V3 stores group/channel/layer data directly in NodeTrees, enabling proper
    Blender linking. This is a one-way migration: after running it the file
    cannot be opened in earlier versions of Paint System.
    """

    bl_idname = "paint_system.migrate_v2_to_v3"
    bl_label = "Update Paint System to V3"
    bl_description = (
        "Migrate all Paint System materials to V3 (NodeTree-based storage). "
        "Required to continue working. This cannot be undone."
    )
    bl_options = {'REGISTER'}

    def execute(self, context):
        migrated = 0
        skipped = 0
        errors = []

        _ps_data.pause_all_node_tree_updates = True
        uid_to_layer_nt = {}
        try:
            for mat in bpy.data.materials:
                ps_data = getattr(mat, 'ps_mat_data', None)
                if not ps_data:
                    continue
                if ps_data.ps_data_version >= 3:
                    skipped += 1
                    continue
                if not ps_data.groups:
                    ps_data.ps_data_version = 3
                    continue
                try:
                    _migrate_material_v2_to_v3(ps_data, uid_to_layer_nt)
                    migrated += 1
                    logger.info("Migrated material '%s' to V3.", mat.name)
                except Exception as exc:  # pylint: disable=broad-except
                    errors.append(f"{mat.name}: {exc}")
                    logger.error("Failed to migrate '%s': %s", mat.name, exc,
                                 exc_info=True)
            logger.info("=== uid_to_layer_nt final (%d entries) ===",
                        len(uid_to_layer_nt))
            for uid, nt in uid_to_layer_nt.items():
                logger.info("  uid=%s -> NT='%s'", uid, nt.name)
        finally:
            _ps_data.pause_all_node_tree_updates = False
            _ps_data._invalidate_material_layer_cache()

        if errors:
            self.report(
                {'WARNING'},
                f"Migrated {migrated} material(s) to V3 with {len(errors)} error(s): "
                + "; ".join(errors),
            )
        else:
            self.report(
                {'INFO'},
                f"Successfully migrated {migrated} material(s) to V3"
                + (f" ({skipped} already at V3)." if skipped else "."),
            )
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class PAINTSYSTEM_OT_CheckForUpdates(PSContextMixin, Operator):
    bl_idname = "paint_system.check_for_updates"
    bl_label = "Check for Updates"
    bl_description = "Check for Updates"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        ps_ctx = cls.parse_context(context)
        if ps_ctx.ps_settings is None:
            return False
        return is_online() and ps_ctx.ps_settings.update_state != 'LOADING'
    
    def execute(self, context):
        # Delete version cache
        reset_version_cache()
        # Check for updates
        get_latest_version()
        return {'FINISHED'}


class PAINTSYSTEM_OT_OpenExtensionPreferences(Operator):
    bl_idname = "paint_system.open_extension_preferences"
    bl_label = "Open Extension Preferences"
    bl_description = "Open Extension Preferences"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        bpy.ops.screen.userpref_show()
        bpy.context.preferences.active_section = 'EXTENSIONS'
        bpy.context.window_manager.extension_search = 'Paint System'
        modules = addon_utils.modules()
        mod = None
        for mod in modules:
            if mod.bl_info.get("name") == "Paint System":
                mod = mod
                break
        if mod is None:
            logger.error("Paint System not found")
            return {'FINISHED'}
        bl_info = addon_utils.module_bl_info(mod)
        show_expanded = bl_info["show_expanded"]
        if not show_expanded:
            bpy.ops.preferences.addon_expand(module=addon_package())
        return {'FINISHED'}


class PAINTSYSTEM_OT_DismissUpdate(PSContextMixin, Operator):
    bl_idname = "paint_system.dismiss_update"
    bl_label = "Dismiss Update"
    bl_description = "Dismiss Update"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        ps_ctx = self.parse_context(context)
        ps_ctx.ps_settings.update_state = 'UNAVAILABLE'
        return {'FINISHED'}

classes = (
    PAINTSYSTEM_OT_UpdatePaintSystemData,
    PAINTSYSTEM_OT_MigrateV2ToV3,
    PAINTSYSTEM_OT_CheckForUpdates,
    PAINTSYSTEM_OT_OpenExtensionPreferences,
    PAINTSYSTEM_OT_DismissUpdate,
)

register, unregister = register_classes_factory(classes)