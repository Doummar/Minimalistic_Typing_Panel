"""A short help guide, shown on first run and reachable any time from
Settings. On first run it's shown non-modally (see __init__.py) so it
doesn't block the rest of Anki while it's up."""
from aqt.qt import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, Qt, QVBoxLayout

from .consts import ADDON_NAME, ADDON_VERSION, TOOLS_MENU_LABEL

_WHAT_IT_DOES = [
    "Floating panel you can type notes into during review",
    "Drag it anywhere — it snaps to screen edges when dragged close",
    "Remembers its position per screen, and optionally per deck",
    "Customizable colors, font, size, and background opacity",
    "Auto-clears each new card, or keeps text as a persistent scratchpad",
    "On the answer side it can forward 1–4 / Space to Anki's own grading "
    "shortcuts once locked read-only",
    "Press Enter to reveal the answer",
    "Recognizes your own configured shortcuts too (Keyboard Passthrough) — "
    "so a reveal or hint add-on's key still works while you're typing",
    "Hides automatically when Anki loses focus",
]

_HOW_TO_USE = [
    "Toggle the panel with your configured shortcut (default Ctrl+\\)",
    "Drag the thin strip at the top of the panel to move it",
    "Press Escape while it's focused to hide it",
    "Lock it in place from Settings to stop accidental dragging",
    "Use your Clear-text shortcut, if set, to wipe it instantly",
    "Use your Lock-toggle shortcut, if set, to lock/unlock on the fly",
    "Record Keyboard Passthrough shortcuts in Settings, then just press "
    "them while typing — they're forwarded, not typed as text",
]

_SETTINGS_ITEMS = [
    "Colors, font, and background opacity",
    "Panel size and position memory (per screen / per deck)",
    "Auto-clear vs. persistent scratchpad",
    "Enter-to-answer and read-only-on-answer behavior",
    "Shortcuts for toggle, clear, and lock",
    "Keyboard Passthrough — record any number of shortcuts to forward to "
    "other add-ons",
]


def _hline() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def _bullets(items) -> QLabel:
    label = QLabel("\n".join(f"•  {item}" for item in items))
    label.setWordWrap(True)
    label.setStyleSheet("font-size: 12px;")
    return label


def _heading(text: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet("font-weight: bold; font-size: 12px;")
    return label


class GuideDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{ADDON_NAME} — Guide")
        self.setMinimumWidth(440)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)

        title = QLabel(ADDON_NAME)
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel("A small floating panel you can type notes into during review.")
        subtitle.setWordWrap(True)
        layout.addWidget(subtitle)

        layout.addWidget(_hline())

        layout.addWidget(_heading("What it does"))
        layout.addWidget(_bullets(_WHAT_IT_DOES))

        layout.addWidget(_heading("How to use"))
        layout.addWidget(_bullets(_HOW_TO_USE))

        layout.addWidget(_heading(f"Settings (Tools → {TOOLS_MENU_LABEL})"))
        layout.addWidget(_bullets(_SETTINGS_ITEMS))

        layout.addWidget(_hline())

        btn_row = QHBoxLayout()
        self.btn_settings = QPushButton("Open Settings")
        self.btn_settings.clicked.connect(self.open_settings)

        self.btn_gotit = QPushButton("Got it \u2714")
        self.btn_gotit.setStyleSheet(
            "background-color: #2b82d9; color: white; font-weight: bold; "
            "padding: 6px 20px; border-radius: 5px;"
        )
        self.btn_gotit.clicked.connect(self._on_got_it)

        btn_row.addWidget(self.btn_settings)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_gotit)
        layout.addLayout(btn_row)

        layout.addWidget(_hline())

        version_label = QLabel(f"v{ADDON_VERSION}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # No explicit color here (unlike the old footer's hardcoded gray,
        # which was unreadable against Anki's dark theme) -- this inherits
        # the dialog's normal palette text color, the same one the title
        # and headings above already use, so it stays readable in both
        # light and dark theme.
        version_label.setStyleSheet("font-size: 10px;")
        layout.addWidget(version_label)

    def _on_got_it(self):
        # "Got it" dismisses the guide -- and every other window branded
        # "Typing Panel" that's open because of it.
        from . import get_panel
        from .settings_dialog import SettingsDialog

        parent = self.parent()
        self.accept()
        if isinstance(parent, SettingsDialog):
            # Closing Settings through its own reject() (same as clicking
            # Cancel there) cleanly reverts any live-preview changes *and*
            # already knows whether to hide the panel based on whether it
            # was visible before Settings was opened -- so we defer to it
            # instead of also forcing the panel closed ourselves here.
            parent.reject()
        else:
            # Standalone guide (e.g. first run): nothing else is managing
            # the panel's visibility, so hide it directly.
            get_panel().request_hide()

    def open_settings(self):
        # Close the guide first, whether it was opened standalone (first
        # run) or from inside the Settings dialog. Only actually launch a
        # new Settings dialog in the former case -- if we were already
        # inside one, it's still open underneath and unsaved edits in it
        # are left untouched.
        from .settings_dialog import SettingsDialog  # local import: avoids a
        # circular import, since settings_dialog.py also imports this module

        parent = self.parent()
        self.accept()
        if not isinstance(parent, SettingsDialog):
            from aqt import mw
            SettingsDialog(mw).exec()
