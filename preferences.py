from dataclasses import dataclass

def addon_package() -> str:
    """Get the addon package name"""
    return __package__

@dataclass
class PaintSystemPreferences:
    show_tooltips: bool
    show_hex_color: bool
    show_more_color_picker_settings: bool
    use_compact_design: bool
    color_picker_scale: float
    hide_norm_paint_tips: bool
    hide_color_attr_tips: bool
    loading_donations: bool
    use_legacy_ui: bool
    show_hsv_sliders_rmb: bool
    show_active_palette_rmb: bool
    show_rmb_layers_panel: bool

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
            show_more_color_picker_settings=False,
            use_compact_design=False,
            color_picker_scale=1.0,
            hide_norm_paint_tips=False,
            hide_color_attr_tips=False,
            loading_donations=False,
            use_legacy_ui=False,
            show_hsv_sliders_rmb=True,
            show_active_palette_rmb=True,
            show_rmb_layers_panel=True,
        )