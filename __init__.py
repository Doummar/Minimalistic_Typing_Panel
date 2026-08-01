# Minimalistic Typing Panel
# Created by Adel Aitah
# Copyright (c) 2026 Adel Aitah — All rights reserved.
#
# A small always-on-top typing panel for use during review.

from aqt import gui_hooks, mw
from aqt.qt import QAction, QShortcut
from aqt.reviewer import Reviewer
from aqt.utils import tooltip

from .config_utils import get_config, write_config
from .consts import ADDON_NAME, ADDON_VERSION, TOOLS_MENU_LABEL
from .guide_dialog import GuideDialog
from .panel import TypingPanel
from .settings_dialog import SettingsDialog

_panel: TypingPanel = None
_shortcuts = {}  # config key -> QShortcut instance
_guide_dialog: GuideDialog = None  # keeps the non-modal first-run guide alive


def get_panel() -> TypingPanel:
    global _panel
    if _panel is None:
        _panel = TypingPanel(mw)
    return _panel


# ----------------------------------------------------------------------
# Shortcuts
# ----------------------------------------------------------------------
def refresh_shortcuts():
    for sc in _shortcuts.values():
        sc.setParent(None)
        sc.deleteLater()
    _shortcuts.clear()

    conf = get_config()

    if conf.get("shortcut_toggle"):
        sc = QShortcut(conf["shortcut_toggle"], mw)
        sc.activated.connect(lambda: get_panel().toggle())
        _shortcuts["shortcut_toggle"] = sc

    if conf.get("shortcut_clear"):
        sc = QShortcut(conf["shortcut_clear"], mw)
        sc.activated.connect(_clear_panel_text)
        _shortcuts["shortcut_clear"] = sc

    if conf.get("shortcut_lock"):
        sc = QShortcut(conf["shortcut_lock"], mw)
        sc.activated.connect(_toggle_lock)
        _shortcuts["shortcut_lock"] = sc


def _clear_panel_text():
    get_panel().clear_text()


def _toggle_lock():
    conf = get_config()
    conf["locked"] = not conf.get("locked", False)
    write_config(conf)
    get_panel().load_config()


# ----------------------------------------------------------------------
# Review hooks
# ----------------------------------------------------------------------
def on_question_shown(card):
    panel = get_panel()
    panel.on_deck_switched()

    conf = get_config()
    if conf.get("auto_clear", True) and not conf.get("persist_text", False):
        panel.clear_text()
    panel.text_edit.setReadOnly(False)


def on_answer_shown(card):
    conf = get_config()
    if conf.get("lock_on_answer", True):
        get_panel().text_edit.setReadOnly(True)


# ----------------------------------------------------------------------
# Yielding to Anki's own windows (Edit Current, Browser, Add Cards, ...)
# ----------------------------------------------------------------------
# The panel is WindowStaysOnTopHint so it can float above the reviewer, but
# that hint isn't scoped to the reviewer -- it puts the panel above *any*
# other window, including ones like Edit Current that open on top of the
# card being reviewed. dialog_manager_did_open_dialog fires for every
# window Anki opens through its dialog registry (Edit Current, Browser,
# Add Cards, Preferences, ...), which is exactly the set of windows that
# can end up fighting the panel for top-most position, so we use it to
# hide the panel for as long as one of them is open. See
# TypingPanel.register_blocking_dialog for the close-side handling.
def on_dialog_opened(_dialog_manager, _dialog_name, dialog_instance):
    if dialog_instance is not None:
        get_panel().register_blocking_dialog(dialog_instance)


# ----------------------------------------------------------------------
# Menu
# ----------------------------------------------------------------------
def open_settings():
    SettingsDialog(mw).exec()


def _add_menu_action():
    # Per request, only this Tools-menu entry uses the short name; every
    # other user-facing label (Add-ons list, dialog titles, tooltips) keeps
    # the full ADDON_NAME.
    action = QAction(TOOLS_MENU_LABEL, mw)
    action.setStatusTip(f"{ADDON_NAME} v{ADDON_VERSION}")
    action.triggered.connect(open_settings)
    mw.form.menuTools.addAction(action)


# ----------------------------------------------------------------------
# Startup: warn once, quietly, if Anki's private reviewer API has moved
# ----------------------------------------------------------------------
def _check_private_api_surface():
    missing = [
        name for name in ("_showAnswer", "_answerCard", "_defaultEase")
        if not hasattr(Reviewer, name)
    ]
    if missing:
        tooltip(
            f"{ADDON_NAME}: this version of Anki no longer exposes "
            f"{', '.join(missing)} on the reviewer, so grading-shortcut "
            "forwarding from the panel won't work. Everything else is unaffected.",
            period=6000,
        )


def init():
    _add_menu_action()
    refresh_shortcuts()
    _check_private_api_surface()

    # Route the native "Config" button in Tools > Add-ons to our own
    # Settings dialog instead of Anki's raw JSON editor.
    mw.addonManager.setConfigAction(__name__, open_settings)

    conf = get_config()
    if conf.get("first_run", True):
        conf["first_run"] = False
        write_config(conf)
        # Non-modal: doesn't block the rest of Anki while it's up. Kept as a
        # module-level reference so it isn't garbage collected while shown.
        global _guide_dialog
        _guide_dialog = GuideDialog(mw)
        _guide_dialog.show()


gui_hooks.main_window_did_init.append(init)
gui_hooks.reviewer_did_show_question.append(on_question_shown)
gui_hooks.reviewer_did_show_answer.append(on_answer_shown)
gui_hooks.dialog_manager_did_open_dialog.append(on_dialog_opened)
