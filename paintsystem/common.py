from dataclasses import dataclass

@dataclass
class PaintSystemPreferences:
    show_tooltips: bool
    show_hex_color: bool
    use_compact_design: bool
    name_layers_group: bool
    hide_norm_paint_tips: bool
    hide_color_attr_tips: bool
    loading_donations: bool