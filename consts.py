"""Shared constants and default configuration for Minimalistic Typing Panel."""

# Resolves to the top-level package name Anki loaded this addon under,
# whatever that folder ends up being called on disk. Using this (instead of
# a hard-coded string) is what lets every module call mw.addonManager.*
# with the right identifier.
ADDON_ID = __name__.split(".")[0]

ADDON_NAME = "Minimalistic Typing Panel"
ADDON_AUTHOR = "Adel Aitah"
ADDON_VERSION = "1.5.3"
ADDON_YEAR = "2026"
ADDON_ISSUES_URL = "https://github.com/Doummar/Minimalistic_Typing_Panel/issues"

# The short label used specifically for the Tools-menu entry (kept distinct
# from ADDON_NAME everywhere else, per explicit request).
TOOLS_MENU_LABEL = "Typing Panel"

# Single, unmodified keys Anki's reviewer already binds during review
# (grading, show-answer, etc). Used to warn a user who tries to bind one of
# the addon's own shortcuts to a key that would silently steal it away from
# Anki instead of doing what they expect.
RESERVED_REVIEW_KEYS = {"1", "2", "3", "4", "Space", "Return", "Enter", "Escape"}

DEFAULT_CONFIG = {
    # --- Appearance ---
    "font_size": 24,
    "font_family": "Arial",
    "font_color": "#ffffff",
    "bg_color": "#1e1e1e",
    "center_text": True,
    "hide_border": True,
    "opacity": 25,

    # --- Geometry ---
    "width": 500,
    "height": 300,
    "pos_x": 200,
    "pos_y": 200,
    "screen_name": "",           # which QScreen pos_x/pos_y were saved on
    "snap_edges": True,          # snap to screen edges when dragged close
    "per_deck_position": False,  # remember a separate position per deck
    "deck_positions": {},        # {deck_id_str: {"x", "y", "screen_name"}}

    # --- Behavior ---
    "locked": False,
    "auto_clear": True,
    "persist_text": False,       # keep scratchpad content across cards/sessions
    "saved_text": "",            # content saved when persist_text is enabled
    "enter_to_answer": True,
    "lock_on_answer": True,

    # --- Shortcuts ---
    "shortcut_toggle": "Ctrl+\\",
    "shortcut_clear": "",
    "shortcut_lock": "",

    # --- Keyboard Passthrough ---
    # Shortcuts that, while the panel has focus, are swallowed (not typed
    # as text) but still forwarded to Anki's own shortcut system, so any
    # other add-on bound to the same key (reveal add-ons, hint add-ons,
    # image occlusion, ...) still responds normally.
    "passthrough_shortcuts": [],

    # --- Internal ---
    "first_run": True,
}
