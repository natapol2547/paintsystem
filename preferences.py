from dataclasses import dataclass

def addon_package() -> str:
    """Get the addon package name"""
    return __package__

@dataclass
class PaintSystemPreferences:
    show_tooltips: bool = True
    show_hex_color: bool = False
    show_more_color_picker_settings: bool = False
    use_compact_design: bool = False
    color_picker_scale: float = 1.0
    color_picker_scale_rmb: float = 1.2
    hide_norm_paint_tips: bool = False
    hide_color_attr_tips: bool = False
    use_legacy_ui: bool = False
    show_hsv_sliders_rmb: bool = True
    show_active_palette_rmb: bool = True
    show_brush_settings_rmb: bool = True
    loading_donations: bool = False
    version_check_interval_days: int = 1
    version_check_interval_hours: int = 0
    version_check_interval_minutes: int = 0
    update_state: str = 'UNAVAILABLE'

def get_preferences(context) -> PaintSystemPreferences:
    """Get the Paint System preferences"""
    ps = addon_package()
    # Be robust across classic add-ons and new Extensions, and during early init
    try:
        return context.preferences.addons[ps].preferences
    except Exception:
        # Fallback: return a safe default so UI can render without crashing
        return PaintSystemPreferences()