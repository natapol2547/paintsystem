def get_layer_image_resolution(unlinked_layer, require_non_correct_aspect=False, include_corrected_non_square=False):
    if not unlinked_layer:
        return None

    layer = unlinked_layer.get_layer_data() if hasattr(unlinked_layer, "get_layer_data") else unlinked_layer
    if not layer or layer.type != 'IMAGE' or not layer.image:
        return None

    width, height = layer.image.size
    if width <= 0 or height <= 0:
        return None

    correct_image_aspect = getattr(layer, "correct_image_aspect", True)

    if require_non_correct_aspect and correct_image_aspect:
        return None

    if include_corrected_non_square and correct_image_aspect and width != height:
        return int(width), int(height)

    if not correct_image_aspect:
        return int(width), int(height)

    return None


def get_preferred_channel_image_resolution(channel, require_non_correct_aspect=False, include_corrected_non_square=False):
    if not channel:
        return None

    if channel.layers and channel.active_index >= 0:
        active_index = min(channel.active_index, len(channel.layers) - 1)
        resolution = get_layer_image_resolution(
            channel.layers[active_index],
            require_non_correct_aspect=require_non_correct_aspect,
            include_corrected_non_square=include_corrected_non_square,
        )
        if resolution:
            return resolution

    for unlinked_layer in channel.flattened_unlinked_layers:
        resolution = get_layer_image_resolution(
            unlinked_layer,
            require_non_correct_aspect=require_non_correct_aspect,
            include_corrected_non_square=include_corrected_non_square,
        )
        if resolution:
            return resolution

    return None


def get_preferred_group_image_resolution(group, require_non_correct_aspect=False, include_corrected_non_square=False):
    if not group:
        return None

    if group.channels and group.active_index >= 0:
        active_index = min(group.active_index, len(group.channels) - 1)
        resolution = get_preferred_channel_image_resolution(
            group.channels[active_index],
            require_non_correct_aspect=require_non_correct_aspect,
            include_corrected_non_square=include_corrected_non_square,
        )
        if resolution:
            return resolution

    for channel in group.channels:
        resolution = get_preferred_channel_image_resolution(
            channel,
            require_non_correct_aspect=require_non_correct_aspect,
            include_corrected_non_square=include_corrected_non_square,
        )
        if resolution:
            return resolution

    return None
