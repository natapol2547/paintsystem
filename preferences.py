from dataclasses import dataclass

def addon_package() -> str:
    """Get the addon package name"""
    return __package__

@dataclass
class PaintSystemPreferences:
    # show_tooltips: bool
    # show_hex_color: bool
    # use_compact_design: bool
    # name_layers_group: bool
    # hide_norm_paint_tips: bool
    # hide_color_attr_tips: bool
    # loading_donations: bool

def get_preferences(context) -> PaintSystemPreferences:
    """Get the Paint System preferences"""
    ps = addon_package()
    # Be robust across classic add-ons and new Extensions, and during early init
    try:
        return context.preferences.addons[ps].preferences
    except Exception:
        # Fallback: return a safe default so UI can render without crashing
        return PaintSystemPreferences(
            show_tooltips=True,
            show_hex_color=False,
            use_compact_design=False,
            name_layers_group=True,
            hide_norm_paint_tips=False,
            hide_color_attr_tips=False,
        )