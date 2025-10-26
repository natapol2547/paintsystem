# SPDX-License-Identifier: GPL-3.0-or-later
# Reference: UCUpaint v2.3.5 - common.py and BakeTarget.py

"""
Image Editor Synchronization Module

This module handles automatic updating of the image editor when painting targets 
(channels) are switched. It's based on UCUpaint's implementation pattern.

When a user switches the active channel (e.g., with Ctrl+Q), this module ensures
the image editor automatically displays the corresponding source image without
requiring manual layer triggering or refresh.
"""

import bpy


def get_edit_image_editor_space(context):
    """
    Retrieves the image editor space that was previously recorded as the 
    edit image editor (for EDIT mode painting).
    
    In EDIT mode, we want to pin the image editor to a specific image so that
    switching channels always updates the correct editor window.
    
    Args:
        context: Blender context
        
    Returns:
        The image editor space if found, None otherwise
    """
    try:
        # Try to get stored editor references from window manager properties
        wm = context.window_manager
        if wm and hasattr(wm, 'ps_props'):
            ps_props = wm.ps_props
            area_index = getattr(ps_props, 'edit_image_editor_area_index', -1)
            window_index = getattr(ps_props, 'edit_image_editor_window_index', -1)
            
            if window_index >= 0 and window_index < len(wm.windows):
                window = wm.windows[window_index]
                if area_index >= 0 and area_index < len(window.screen.areas):
                    area = window.screen.areas[area_index]
                    if area.type == 'IMAGE_EDITOR' and len(area.spaces) > 0:
                        space = area.spaces[0]
                        return space
    except:
        pass
    
    return None


def get_first_unpinned_image_editor_space(context):
    """
    Finds the first image editor space that is not pinned.
    
    When not in EDIT mode or when no specific editor is recorded, we want to find
    the first available unpinned image editor to update.
    
    Args:
        context: Blender context
        
    Returns:
        The first unpinned image editor space if found, None otherwise
    """
    try:
        wm = context.window_manager
        if not wm:
            return None
            
        for window in wm.windows:
            for area in window.screen.areas:
                if area.type == 'IMAGE_EDITOR' and len(area.spaces) > 0:
                    space = area.spaces[0]
                    # Check if this editor is unpinned (or has image_pin attribute)
                    if hasattr(space, 'use_image_pin'):
                        if not space.use_image_pin:
                            return space
                    else:
                        # If no pin attribute, assume it's available
                        return space
    except:
        pass
    
    return None


def update_image_editor_image(context, image):
    """
    Updates the image editor to display the specified image.
    
    This is the core function that handles showing the correct image in the
    image editor when channels are switched. It handles both EDIT mode and
    other modes appropriately.
    
    Reference: UCUpaint v2.3.5 common.py lines 1160-1175
    
    Args:
        context: Blender context
        image: The image to display (can be None to clear the editor)
    """
    obj = context.object
    
    # In EDIT mode: Pin the image editor to the specified image
    if obj and obj.mode == 'EDIT':
        space = get_edit_image_editor_space(context)
        if space:
            space.use_image_pin = True
            space.image = image
    else:
        # In other modes: Use first unpinned image editor
        space = get_first_unpinned_image_editor_space(context)
        if space:
            space.image = image
            # Hack for Blender compatibility: some versions auto-pin
            if hasattr(space, 'use_image_pin'):
                space.use_image_pin = False


def get_channel_source_image(channel):
    """
    Extracts the source image from a channel.
    
    This handles different channel types and retrieves the image that should
    be displayed in the image editor when this channel is active.
    
    Args:
        channel: The channel property group
        
    Returns:
        The source image, or None if not found
    """
    if not channel:
        return None
    
    # If channel has a bake_image and it's enabled, use it
    if hasattr(channel, 'bake_image') and channel.bake_image:
        if getattr(channel, 'use_bake_image', False):
            return channel.bake_image
    
    # If the channel has a direct image property, use it
    if hasattr(channel, 'image') and channel.image:
        return channel.image
    
    # Check if channel has a node_tree with image sources
    if hasattr(channel, 'node_tree') and channel.node_tree:
        node_tree = channel.node_tree
        # Look for image nodes in the tree
        for node in node_tree.nodes:
            if node.type == 'TEX_IMAGE' and hasattr(node, 'image') and node.image:
                return node.image
    
    return None


def update_active_channel_on_switch(group, context):
    """
    Called when the active channel index changes (e.g., Ctrl+Q).
    
    This function is the callback that gets executed whenever the user switches
    to a different channel. It updates the image editor to show the new channel's
    source image.
    
    Reference Pattern: UCUpaint v2.3.5 BakeTarget.py lines 19-29
    
    Args:
        group: The group/material data containing channels
        context: Blender context
    """
    try:
        if not hasattr(group, 'channels') or not hasattr(group, 'active_index'):
            return
        
        # Get the active channel safely
        if group.active_index < 0 or group.active_index >= len(group.channels):
            # If invalid index, clear the image editor
            update_image_editor_image(context, None)
            return
        
        active_channel = group.channels[group.active_index]
        
        # Get the source image from the active channel
        image = get_channel_source_image(active_channel)
        
        # Update the image editor to show this image
        update_image_editor_image(context, image)
        
    except Exception as e:
        print(f"Error updating channel on switch: {e}")
        # Fail silently to avoid breaking the UI update


# ============================================================================
# Integration Helper: Add this to your update_channel function
# ============================================================================

def update_channel_with_editor_sync(self, context):
    """
    Enhanced channel update function that includes image editor synchronization.
    
    This combines the existing channel update logic with automatic image editor
    updates. Drop this in to replace your current update_channel function.
    
    Usage in data.py:
        active_index: IntProperty(
            name="Active Channel Index",
            update=update_channel_with_editor_sync
        )
    """
    # Original Paint System logic
    try:
        from ..operators.common import PSContextMixin
        
        ps_ctx = PSContextMixin.parse_context(context)
        ps_mat_data = ps_ctx.ps_mat_data
        if ps_mat_data and ps_mat_data.preview_channel:
            try:
                bpy.ops.wm.paint_system_isolate_active_channel()
                bpy.ops.wm.paint_system_isolate_active_channel()
            except:
                pass
        
        active_channel = ps_ctx.active_channel if ps_ctx else None
        if active_channel and hasattr(active_channel, 'use_bake_image'):
            if active_channel.use_bake_image:
                try:
                    bpy.ops.object.mode_set(mode="OBJECT")
                except:
                    pass
        
        # Call the original update_active_image
        from ..paintsystem.data import update_active_image
        update_active_image(self, context)
    except:
        pass
    
    # NEW: Sync the image editor to show the active channel's image
    update_active_channel_on_switch(self, context)
