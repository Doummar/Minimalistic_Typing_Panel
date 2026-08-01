"""The Settings dialog: appearance, position, behavior, and shortcut
configuration, organized into focused tabs with a live preview against the
actual floating panel."""
from copy import deepcopy

from aqt.qt import (
    QCheckBox, QColor, QColorDialog, QDialog, QDialogButtonBox, QFont,
    QFontComboBox, QFormLayout, QGroupBox, QHBoxLayout, QKeySequence,
    QLabel, QListWidget, QPushButton, Qt, QSlider, QSpinBox, QTabWidget,
    QVBoxLayout, QWidget,
)
from aqt.utils import askUser, tooltip

from .config_utils import get_config, write_config
from .consts import ADDON_NAME, RESERVED_REVIEW_KEYS

_SHORTCUT_LABELS = {
    "shortcut_toggle": "Show / hide panel",
    "shortcut_clear": "Clear text",
    "shortcut_lock": "Toggle lock",
}

# Sentinel used as self._recording_key while recording a new entry to add
# to passthrough_shortcuts, distinguishing that mode from recording one of
# the fixed single-value shortcuts above (which use their real config key).
_RECORDING_NEW_PASSTHROUGH = "__passthrough_new__"

# Widgets whose value should be pulled from / pushed into self.conf in bulk.
# Populated once all widgets exist (see _register_synced_widgets).
_SYNCED_WIDGET_ATTRS = (
    "f_in", "w_in", "h_in", "center_cb", "border_cb", "op_slider",
    "locked_cb", "snap_cb", "per_deck_cb", "autoclear_cb", "persist_cb",
    "enter_cb", "lockans_cb", "font_combo",
)


class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{ADDON_NAME} — Settings")
        self.setMinimumWidth(460)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.conf = get_config()
        self._recording_key = None
        self._shortcut_value_labels = {}

        # If the panel is currently hidden, the live preview below would
        # have nothing to show. Reveal it for the duration of this dialog
        # and put it back the way it was afterward (see reject()/save_settings()).
        from . import get_panel
        panel = get_panel()
        self._panel_was_visible = panel.isVisible()
        if not self._panel_was_visible:
            panel.request_show()

        self.setup_ui()
        self._apply_conf_to_widgets(preview=False)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def setup_ui(self):
        layout = QVBoxLayout(self)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        # Four focused tabs instead of a flat list, so a setting lives in
        # the one place you'd actually go looking for it: how it looks,
        # where/how big it sits on screen, how it behaves during review,
        # and how you trigger it.
        tabs.addTab(self._build_appearance_tab(), "Appearance")
        tabs.addTab(self._build_position_tab(), "Size && Position")
        tabs.addTab(self._build_review_tab(), "Review Behavior")
        tabs.addTab(self._build_shortcuts_tab(), "Shortcuts")

        help_box = QGroupBox("Help")
        help_layout = QVBoxLayout(help_box)

        self.btn_guide = QPushButton("Open Help Guide")
        self.btn_guide.clicked.connect(self._open_guide)
        help_layout.addWidget(self.btn_guide)

        self.btn_report = QPushButton("Report an Issue")
        self.btn_report.clicked.connect(self._report_issue)
        help_layout.addWidget(self.btn_report)

        self.btn_reset = QPushButton("\u21BA Reset to Default")
        self.btn_reset.setToolTip("Restore every setting on every tab to its original default.")
        self.btn_reset.clicked.connect(self.reset_to_default)
        help_layout.addWidget(self.btn_reset)

        layout.addWidget(help_box)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.save_settings)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _open_guide(self):
        from .guide_dialog import GuideDialog  # local import: sidesteps a
        # circular import (guide_dialog imports this module for its own
        # "Open Settings" button)
        GuideDialog(self).exec()

    def _report_issue(self):
        from aqt.utils import openLink
        from .consts import ADDON_ISSUES_URL
        openLink(ADDON_ISSUES_URL)

    # -- Tab 1: Appearance ------------------------------------------------
    def _build_appearance_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        color_box = QGroupBox("Colors && Font")
        form = QFormLayout(color_box)

        self.pick_bg = QPushButton()
        self.pick_bg.setToolTip("Background color of the panel.")
        self.pick_bg.clicked.connect(self._pick_bg_color)
        form.addRow("Background color:", self.pick_bg)

        self.pick_fg = QPushButton()
        self.pick_fg.setToolTip("Color of the typed text.")
        self.pick_fg.clicked.connect(self._pick_font_color)
        form.addRow("Text color:", self.pick_fg)

        self.font_combo = QFontComboBox()
        self.font_combo.setToolTip("Font used for the typed text.")
        self.font_combo.currentFontChanged.connect(self._on_font_family_changed)
        form.addRow("Font family:", self.font_combo)

        self.f_in = QSpinBox()
        self.f_in.setRange(8, 72)
        self.f_in.setSuffix(" px")
        self.f_in.valueChanged.connect(lambda v: self._set_and_preview("font_size", v))
        form.addRow("Font size:", self.f_in)

        outer.addWidget(color_box)

        style_box = QGroupBox("Panel Style")
        form2 = QFormLayout(style_box)

        self.center_cb = QCheckBox("Center text")
        self.center_cb.stateChanged.connect(lambda s: self._set_and_preview("center_text", bool(s)))
        form2.addRow(self.center_cb)

        self.border_cb = QCheckBox("Hide border")
        self.border_cb.stateChanged.connect(lambda s: self._set_and_preview("hide_border", bool(s)))
        form2.addRow(self.border_cb)

        op_row = QHBoxLayout()
        self.op_slider = QSlider(Qt.Orientation.Horizontal)
        self.op_slider.setRange(0, 100)
        self.op_slider.setToolTip("How see-through the panel's background is.")
        self.op_label = QLabel("25%")
        self.op_label.setMinimumWidth(36)
        self.op_slider.valueChanged.connect(self._on_opacity_changed)
        op_row.addWidget(self.op_slider)
        op_row.addWidget(self.op_label)
        form2.addRow("Background opacity:", op_row)

        outer.addWidget(style_box)

        note = QLabel(
            "Changes preview live on the panel; click Save to keep them. "
            "If the panel was hidden, it's shown temporarily while this window is open."
        )
        note.setStyleSheet("color: gray; font-size: 11px;")
        note.setWordWrap(True)
        outer.addWidget(note)
        outer.addStretch()

        return w

    # -- Tab 2: Size & Position --------------------------------------------
    def _build_position_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        size_box = QGroupBox("Size")
        form = QFormLayout(size_box)

        self.w_in = QSpinBox()
        self.w_in.setRange(100, 2000)
        self.w_in.setSuffix(" px")
        self.w_in.valueChanged.connect(lambda v: self._set_and_preview("width", v))
        form.addRow("Panel width:", self.w_in)

        self.h_in = QSpinBox()
        self.h_in.setRange(50, 2000)
        self.h_in.setSuffix(" px")
        self.h_in.valueChanged.connect(lambda v: self._set_and_preview("height", v))
        form.addRow("Panel height:", self.h_in)

        outer.addWidget(size_box)

        pos_box = QGroupBox("Dragging && Position Memory")
        form2 = QFormLayout(pos_box)

        self.locked_cb = QCheckBox("Lock panel position (disable dragging)")
        self.locked_cb.stateChanged.connect(lambda s: self._set_and_preview("locked", bool(s)))
        form2.addRow(self.locked_cb)

        self.snap_cb = QCheckBox("Snap to screen edges while dragging")
        self.snap_cb.stateChanged.connect(lambda s: self._set_and_preview("snap_edges", bool(s)))
        form2.addRow(self.snap_cb)

        self.per_deck_cb = QCheckBox("Remember a separate position per deck")
        self.per_deck_cb.setToolTip(
            "When on, moving the panel while reviewing one deck won't affect "
            "where it appears for other decks."
        )
        self.per_deck_cb.stateChanged.connect(lambda s: self._set_and_preview("per_deck_position", bool(s)))
        form2.addRow(self.per_deck_cb)

        outer.addWidget(pos_box)
        outer.addStretch()

        return w

    # -- Tab 3: Review Behavior --------------------------------------------
    def _build_review_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        text_box = QGroupBox("Text Handling")
        form = QFormLayout(text_box)

        self.autoclear_cb = QCheckBox("Auto-clear text when the next card loads")
        self.autoclear_cb.stateChanged.connect(lambda s: self._set_and_preview("auto_clear", bool(s)))
        form.addRow(self.autoclear_cb)

        self.persist_cb = QCheckBox("Keep text as a persistent scratchpad")
        self.persist_cb.setToolTip(
            "Text stays across cards and Anki restarts instead of clearing. "
            "Overrides auto-clear above while enabled."
        )
        self.persist_cb.stateChanged.connect(self._on_persist_changed)
        form.addRow(self.persist_cb)

        outer.addWidget(text_box)

        flow_box = QGroupBox("Grading Shortcuts")
        form2 = QFormLayout(flow_box)

        self.enter_cb = QCheckBox("Press Enter to show the answer")
        self.enter_cb.stateChanged.connect(lambda s: self._set_and_preview("enter_to_answer", bool(s)))
        form2.addRow(self.enter_cb)

        self.lockans_cb = QCheckBox("Make the panel read-only on the answer side")
        self.lockans_cb.setToolTip(
            "While read-only, the panel forwards 1–4 and Space to Anki's own "
            "grading shortcuts instead of typing them."
        )
        self.lockans_cb.stateChanged.connect(lambda s: self._set_and_preview("lock_on_answer", bool(s)))
        form2.addRow(self.lockans_cb)

        outer.addWidget(flow_box)
        outer.addStretch()

        return w

    def _on_persist_changed(self, state):
        checked = bool(state)
        self._set_and_preview("persist_text", checked)
        # auto_clear has no effect while persist_text is on; gray it out so
        # the relationship between the two is visible, not just documented
        # in a tooltip.
        self.autoclear_cb.setDisabled(checked)

    # -- Tab 4: Shortcuts ---------------------------------------------------
    def _build_shortcuts_tab(self) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)

        box = QGroupBox("Panel Shortcuts")
        form = QFormLayout(box)

        note = QLabel(
            "Click Record, then press a key combination. Avoid Anki's own review "
            "keys (1–4, Space, Enter, Escape) unless you mean to override them."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        form.addRow(note)

        for key in ("shortcut_toggle", "shortcut_clear", "shortcut_lock"):
            row = QHBoxLayout()
            value_label = QLabel()
            value_label.setStyleSheet("font-family: monospace;")
            self._shortcut_value_labels[key] = value_label

            record_btn = QPushButton("Record…")
            record_btn.clicked.connect(lambda _, k=key: self._start_recording(k))

            clear_btn = QPushButton("Clear")
            clear_btn.clicked.connect(lambda _, k=key: self._clear_shortcut(k))

            row.addWidget(value_label, 1)
            row.addWidget(record_btn)
            row.addWidget(clear_btn)
            form.addRow(_SHORTCUT_LABELS[key] + ":", row)

        outer.addWidget(box)
        outer.addWidget(self._build_passthrough_box())
        outer.addStretch()

        return w

    def _build_passthrough_box(self) -> QGroupBox:
        box = QGroupBox("Keyboard Passthrough")
        outer = QVBoxLayout(box)

        note = QLabel(
            "Shortcuts recorded here are swallowed by the panel (they won't be "
            "typed as text), but are still forwarded to Anki -- so any other "
            "add-on bound to the same key, such as a one-by-one reveal add-on, "
            "a hint add-on, or an image occlusion tool, still responds normally "
            "without you needing to click out of the panel first."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray; font-size: 11px;")
        outer.addWidget(note)

        self.passthrough_list = QListWidget()
        self.passthrough_list.setToolTip(
            "Keys typed into the panel that match one of these are passed "
            "through to Anki instead of being typed."
        )
        outer.addWidget(self.passthrough_list)

        self.passthrough_record_label = QLabel("")
        self.passthrough_record_label.setStyleSheet("color: gray; font-size: 11px;")
        outer.addWidget(self.passthrough_record_label)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("Add Shortcut…")
        add_btn.clicked.connect(self._start_recording_passthrough)
        remove_btn = QPushButton("Remove Selected")
        remove_btn.clicked.connect(self._remove_selected_passthrough)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(remove_btn)
        btn_row.addStretch()
        outer.addLayout(btn_row)

        return box

    # ------------------------------------------------------------------
    # Applying conf <-> widgets
    # ------------------------------------------------------------------
    def _apply_conf_to_widgets(self, preview: bool = True):
        c = self.conf
        widgets = [getattr(self, name) for name in _SYNCED_WIDGET_ATTRS]
        for widget in widgets:
            widget.blockSignals(True)

        self._update_color_button(self.pick_bg, c["bg_color"])
        self._update_color_button(self.pick_fg, c["font_color"])
        self.font_combo.setCurrentFont(QFont(c["font_family"]))
        self.f_in.setValue(c["font_size"])
        self.w_in.setValue(c["width"])
        self.h_in.setValue(c["height"])
        self.center_cb.setChecked(c["center_text"])
        self.border_cb.setChecked(c["hide_border"])
        self.op_slider.setValue(c["opacity"])
        self.op_label.setText(f"{c['opacity']}%")
        self.locked_cb.setChecked(c["locked"])
        self.snap_cb.setChecked(c["snap_edges"])
        self.per_deck_cb.setChecked(c["per_deck_position"])
        self.autoclear_cb.setChecked(c["auto_clear"])
        self.persist_cb.setChecked(c["persist_text"])
        self.enter_cb.setChecked(c["enter_to_answer"])
        self.lockans_cb.setChecked(c["lock_on_answer"])

        for widget in widgets:
            widget.blockSignals(False)

        self.autoclear_cb.setDisabled(c["persist_text"])

        for key, label in self._shortcut_value_labels.items():
            label.setText(c.get(key) or "(none)")
        self._refresh_passthrough_list()

        if preview:
            self.preview()

    @staticmethod
    def _update_color_button(button: QPushButton, hex_color: str):
        button.setText(hex_color)
        button.setStyleSheet(f"background-color: {hex_color};")

    def _set_and_preview(self, key, value):
        self.conf[key] = value
        self.preview()

    def _on_font_family_changed(self, font):
        self._set_and_preview("font_family", font.family())

    def _on_opacity_changed(self, value):
        self.op_label.setText(f"{value}%")
        self._set_and_preview("opacity", value)

    def _pick_bg_color(self):
        color = QColorDialog.getColor(QColor(self.conf["bg_color"]), self, "Background color")
        if color.isValid():
            self.conf["bg_color"] = color.name()
            self._update_color_button(self.pick_bg, color.name())
            self.preview()

    def _pick_font_color(self):
        color = QColorDialog.getColor(QColor(self.conf["font_color"]), self, "Text color")
        if color.isValid():
            self.conf["font_color"] = color.name()
            self._update_color_button(self.pick_fg, color.name())
            self.preview()

    # ------------------------------------------------------------------
    # Live preview against the real panel
    # ------------------------------------------------------------------
    def preview(self):
        from . import get_panel
        get_panel().load_config(self.conf)

    # ------------------------------------------------------------------
    # Shortcut recording
    # ------------------------------------------------------------------
    # Both the fixed single-value shortcuts (Panel Shortcuts box) and the
    # open-ended passthrough list (Keyboard Passthrough box) are captured
    # through this same keyPressEvent-based recorder; only what happens
    # once a key combination is captured differs, based on whether
    # self._recording_key holds a real config key or the
    # _RECORDING_NEW_PASSTHROUGH sentinel.
    def _start_recording(self, key: str):
        self._recording_key = key
        self._shortcut_value_labels[key].setText("Press a key…")
        self.setFocus()

    def _start_recording_passthrough(self):
        self._recording_key = _RECORDING_NEW_PASSTHROUGH
        self.passthrough_record_label.setText("Press a key… (Esc to cancel)")
        self.setFocus()

    def _clear_shortcut(self, key: str):
        self.conf[key] = ""
        self._shortcut_value_labels[key].setText("(none)")

    def _remove_selected_passthrough(self):
        row = self.passthrough_list.currentRow()
        if row < 0:
            return
        existing = list(self.conf.get("passthrough_shortcuts", []))
        del existing[row]
        self.conf["passthrough_shortcuts"] = existing
        self._refresh_passthrough_list()
        self.preview()

    def _refresh_passthrough_list(self):
        self.passthrough_list.clear()
        self.passthrough_list.addItems(self.conf.get("passthrough_shortcuts", []))

    def keyPressEvent(self, event):
        if not self._recording_key:
            super().keyPressEvent(event)
            return

        key = event.key()
        if key in (
            Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
        ):
            return  # wait for a real key, modifiers alone don't count

        recording_key = self._recording_key

        if key == Qt.Key.Key_Escape and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            # Escape with no modifiers cancels recording rather than being
            # recorded, since it's also this dialog's natural "back out" key.
            self._recording_key = None
            self._reset_recording_display(recording_key)
            return

        seq = QKeySequence(event.keyCombination()).toString()
        self._recording_key = None

        if not self._confirm_shortcut_seq(seq, exclude_key=recording_key):
            self._reset_recording_display(recording_key)
            return

        if recording_key == _RECORDING_NEW_PASSTHROUGH:
            self._add_passthrough_shortcut(seq)
        else:
            self.conf[recording_key] = seq
            self._shortcut_value_labels[recording_key].setText(seq)

    def _reset_recording_display(self, recording_key: str):
        """Put the relevant bit of UI back to its non-recording state,
        whichever kind of recording (single shortcut vs. new passthrough
        entry) was just cancelled or rejected."""
        if recording_key == _RECORDING_NEW_PASSTHROUGH:
            self.passthrough_record_label.setText("")
        else:
            self._shortcut_value_labels[recording_key].setText(self.conf.get(recording_key) or "(none)")

    def _confirm_shortcut_seq(self, seq: str, *, exclude_key: str = None) -> bool:
        """Shared collision checks for a freshly recorded key combination,
        used by both single-value shortcuts and passthrough entries.
        Returns whether the caller should go ahead and accept `seq`."""
        if seq in RESERVED_REVIEW_KEYS:
            if not askUser(
                f"'{seq}' is a key Anki uses during review (grading or answering). "
                "Binding it here means the panel will intercept it instead. Use it anyway?",
                parent=self,
                defaultno=True,
            ):
                return False

        norm = QKeySequence(seq)
        colliding_labels = [
            _SHORTCUT_LABELS[k]
            for k in ("shortcut_toggle", "shortcut_clear", "shortcut_lock")
            if k != exclude_key and self.conf.get(k) and QKeySequence(self.conf[k]) == norm
        ]
        if colliding_labels:
            if not askUser(
                f"'{seq}' is already used for: {', '.join(colliding_labels)}. Use it here too?",
                parent=self,
                defaultno=True,
            ):
                return False

        return True

    def _add_passthrough_shortcut(self, seq: str):
        self.passthrough_record_label.setText("")
        existing = self.conf.get("passthrough_shortcuts", [])

        # Compare via QKeySequence rather than the raw strings, so two
        # different textual representations of the same combination are
        # still recognized as a duplicate.
        norm = QKeySequence(seq)
        if any(QKeySequence(s) == norm for s in existing):
            tooltip("That shortcut is already in the passthrough list.", parent=self)
            return

        self.conf["passthrough_shortcuts"] = existing + [seq]
        self._refresh_passthrough_list()
        self.preview()

    # ------------------------------------------------------------------
    # Reset / Save / Cancel
    # ------------------------------------------------------------------
    def reset_to_default(self):
        from .consts import DEFAULT_CONFIG
        # A full reset means a full reset -- matches the previous behavior
        # and avoids surprising leftovers from deck_positions/saved_text.
        self.conf = deepcopy(DEFAULT_CONFIG)
        self._apply_conf_to_widgets(preview=True)
        tooltip("Settings reset to default (not yet saved).", parent=self)

    def save_settings(self):
        write_config(self.conf)
        from . import refresh_shortcuts, get_panel
        refresh_shortcuts()
        # Belt-and-suspenders: every individual edit above is supposed to
        # keep the live panel in sync via preview(), but re-loading here
        # from what was just written to disk guarantees the running panel
        # actually matches the saved config once Save is clicked, even if
        # some future edit path forgets to call preview().
        get_panel().load_config()
        if not self._panel_was_visible:
            get_panel().request_hide()
        self.accept()

    def reject(self):
        # Undo whatever the live preview was showing and fall back to what's
        # actually saved on disk, since Cancel means none of this happened.
        # Also put the panel's visibility back the way it was, since we may
        # have shown it ourselves just so the preview had something to show.
        from . import get_panel
        panel = get_panel()
        panel.load_config()
        if not self._panel_was_visible:
            panel.request_hide()
        super().reject()
