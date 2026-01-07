import bpy
from bl_ui.properties_paint_common import (
    UnifiedPaintPanel,
)

def get_unified_settings(context: bpy.types.Context, unified_name: str):
    tool_settings = UnifiedPaintPanel.paint_settings(context)
    if hasattr(context.tool_settings, "unified_paint_settings"):
        ups = context.tool_settings.unified_paint_settings
    elif hasattr(tool_settings, "unified_paint_settings"):
        ups = tool_settings.unified_paint_settings
    else:
        return None
        
    brush = tool_settings.brush
    prop_owner = brush
    if unified_name and getattr(ups, unified_name):
        prop_owner = ups
    return prop_owner