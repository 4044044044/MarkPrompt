"""Theme palettes for the native interface."""
DEFAULT_THEME = {
    "drop_panel": "#141414", "drop_edge": "#383838", "scroll_track": "#181818", "drop_unknown_color": "#a0a0a0",
    "background": "#000000", "panel": "#000000", "foreground": "#d4d4d4",
    "selection_background": "#d6d1c7", "selection_foreground": "#1e1c19",
    "muted": "#a0a0a0", "heading": "#e8e8e8", "command": "#79caff",
    "string": "#ffd479", "success": "#8fda8c", "warning": "#ffd479",
    "error": "#ff8c8c", "border": "#d4d4d4",
    # Use a distinct foreground for unsaved lines.
    "unsaved": "#ffa657",
    # Hit backgrounds can coexist with dirty-line foregrounds.
    "search_hit": "#2d5a8c",
    # Completion colors.
    "ac_bg": "#000000", "ac_border": "#ffffff", "ac_count_bg": "#000000",
    "ac_count_fg": "#888888", "ac_active_bg": "#333333",
    "ac_cmd_fg": "#ffffff", "ac_desc_active_fg": "#cccccc",
    # Scrollbar colors.
    "sb_track_fill": "#050505", "sb_track_outline": "#787878",
    "sb_button_outline": "#8a8a8a", "sb_thumb_fill": "#a8a8a8",
    # Dialog colors.
    "dialog_ink": "#ffffff", "dialog_paper": "#000000", "dialog_muted": "#a0a0a0",
}

LIGHT_THEME = {
    "drop_panel": "#fffdf8", "drop_edge": "#c7bfae", "scroll_track": "#ded6c8", "drop_unknown_color": "#6f6f6f",
    "background": "#faf7f1", "panel": "#f4efe4", "foreground": "#33291a",
    "selection_background": "#f0ce86", "selection_foreground": "#241b10",
    "muted": "#7d7159", "heading": "#1c150c", "command": "#0b5290",
    "string": "#7a5200", "success": "#2a6b2a", "warning": "#7a5200",
    "error": "#a8231c", "border": "#3a2f1e",
    "unsaved": "#b14a09", "search_hit": "#c6d9ee",
    "ac_bg": "#fffdf8", "ac_border": "#0b5290", "ac_count_bg": "#f4efe4",
    "ac_count_fg": "#8a7d63", "ac_active_bg": "#eee7d6",
    "ac_cmd_fg": "#1c150c", "ac_desc_active_fg": "#4a3f2c",
    "sb_track_fill": "#efe9dc", "sb_track_outline": "#b9ad93",
    "sb_button_outline": "#a99c80", "sb_thumb_fill": "#c3b79c",
    "dialog_ink": "#1c150c", "dialog_paper": "#faf7f1", "dialog_muted": "#7d7159",
}

THEMES = {"dark": DEFAULT_THEME, "light": LIGHT_THEME}

DEFAULT_THEME_NAME = "dark"

