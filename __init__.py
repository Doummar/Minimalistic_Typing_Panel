# Minimalistic Typing Panel
# Created by Adel Aitah
# GitHub: https://github.com/Doummar/Minimalistic_Typing_Panel
# Copyright (c) 2026 Adel Aitah — All rights reserved
"""
Minimalistic Typing Panel — Anki floating scratchpad
Clean, distraction-free overlay with transparency, 
auto-clear, and grading shortcut forwarding.
"""

from aqt import mw, gui_hooks
from aqt.qt import *
from aqt.utils import askUser, openLink

ADDON_NAME = "Minimalistic Typing Panel"
ADDON_AUTHOR  = "Adel Aitah"
ADDON_VERSION = "1.0.0"
ADDON_URL     = "https://github.com/Doummar/Minimalistic_Typing_Panel"

DEFAULT_CONFIG = {
    "font_size": 24, "font_color": "#ffffff", "bg_color": "#1e1e1e",
    "width": 500, "height": 300, "pos_x": 200, "pos_y": 200,
    "shortcut": "Ctrl+\\", "locked": False, "opacity": 25,
    "auto_clear": True, "center_text": True, "hide_border": True,
    "enter_to_answer": True, "lock_on_answer": True
}

# --- GUIDE DIALOG ---
class GuideDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(f"{ADDON_NAME} — Guide")
        self.setFixedWidth(500)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        header = QLabel(f"""
            <div style='font-family: Segoe UI, sans-serif;'>
                <h2 style='margin-bottom: 0px;'>⌨️ {ADDON_NAME}</h2>
                <p style='color: #666; margin-top: 5px;'>A clean, distraction-free floating scratchpad for Anki.</p>
                <hr>
            </div>
        """)
        layout.addWidget(header)

        content = QLabel(f"""
            <div style='font-family: Segoe UI, sans-serif; font-size: 13px;'>
                <b>What it does</b>
                <ul style='color: #444;'>
                    <li>Distraction-free scratchpad overlay</li>
                    <li>Transparent UI (Customizable opacity)</li>
                    <li>Auto-clear text on next card transition</li>
                    <li>Lock typing on Answer side to allow grading</li>
                    <li>Forwards Anki shortcuts (1-4, Space) when locked</li>
                </ul>
                <b>How to use</b>
                <ul style='color: #444;'>
                    <li>Toggle visibility with Shortcut (Default: <b>Ctrl+\\</b>)</li>
                    <li>Drag the panel to move it anywhere on screen</li>
                    <li>Type your thoughts before flipping the card</li>
                    <li>Press <b>Enter</b> to show answer (if enabled)</li>
                    <li>Grade cards using <b>1, 2, 3, 4</b> while panel is focused</li>
                </ul>
            </div>
        """)
        layout.addWidget(content)
        layout.addStretch()

        # Separator Line 1
        line1 = QFrame(); line1.setFrameShape(QFrame.Shape.HLine); line1.setStyleSheet("color: #ccc;"); layout.addWidget(line1)

        btn_layout = QHBoxLayout()
        self.btn_settings = QPushButton("Open Settings")
        self.btn_settings.clicked.connect(self.accept)
        
        self.btn_gotit = QPushButton("Got it ✔")
        self.btn_gotit.setStyleSheet("background-color: #2b82d9; color: white; font-weight: bold; padding: 6px 20px; border-radius: 5px;")
        self.btn_gotit.clicked.connect(self.close_all)
        
        btn_layout.addWidget(self.btn_settings); btn_layout.addStretch(); btn_layout.addWidget(self.btn_gotit)
        layout.addLayout(btn_layout)

        # Separator Line 2
        line2 = QFrame(); line2.setFrameShape(QFrame.Shape.HLine); line2.setStyleSheet("color: #ccc;"); layout.addWidget(line2)

        info_layout = QHBoxLayout()
        lbl_left = QLabel(f"{ADDON_NAME} v{ADDON_VERSION} — Created by {ADDON_AUTHOR}")
        lbl_left.setStyleSheet("color: #888; font-size: 10px;")
        lbl_right = QLabel("since 2026")
        lbl_right.setStyleSheet("color: #888; font-size: 10px;")
        info_layout.addWidget(lbl_left); info_layout.addStretch(); info_layout.addWidget(lbl_right)
        layout.addLayout(info_layout)

    def close_all(self):
        self.accept()
        if self.parent() and isinstance(self.parent(), QDialog):
            self.parent().accept()

# --- CUSTOM TEXT EDIT ---
class TypingEdit(QTextEdit):
    def keyPressEvent(self, event):
        conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG
        key = event.key()
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if conf.get("enter_to_answer", False) and mw.reviewer and mw.reviewer.state == "question":
                mw.reviewer._showAnswer(); event.accept(); return
        if self.isReadOnly() and mw.reviewer and mw.reviewer.state == "answer":
            if key == Qt.Key.Key_1: mw.reviewer._answerCard(1); event.accept(); return
            if key == Qt.Key.Key_2: mw.reviewer._answerCard(2); event.accept(); return
            if key == Qt.Key.Key_3: mw.reviewer._answerCard(3); event.accept(); return
            if key == Qt.Key.Key_4: mw.reviewer._answerCard(4); event.accept(); return
            if key == Qt.Key.Key_Space: mw.reviewer._answerCard(mw.reviewer._defaultEase()); event.accept(); return
        super().keyPressEvent(event)

# --- THE TYPING PANEL ---
class TypingPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.main_layout = QVBoxLayout(self); self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.container = QFrame(); self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 10, 10, 10); self.main_layout.addWidget(self.container)
        self.text_edit = TypingEdit(); self.container_layout.addWidget(self.text_edit)
        self._dragging = False; self._drag_pos = QPoint(); self._user_wants_visible = False 
        app = QApplication.instance()
        if app: app.applicationStateChanged.connect(self.on_app_state_changed)
        self.load_config()

    def on_app_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationInactive: self.hide()
        elif state == Qt.ApplicationState.ApplicationActive and self._user_wants_visible: self.show()

    def load_config(self):
        conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG
        self.move(conf.get("pos_x", 200), conf.get("pos_y", 200))
        self.resize(conf.get("width", 500), conf.get("height", 300))
        self.locked = conf.get("locked", False)
        opacity = conf.get('opacity', 25) / 100.0
        qcolor = QColor(conf.get('bg_color', '#1e1e1e'))
        rgba_bg = f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {opacity})"
        border_css = "none" if conf.get("hide_border", True) else "1px solid #444"
        self.container.setStyleSheet(f"QFrame {{ background-color: {rgba_bg}; border: {border_css}; border-radius: 12px; }}")
        self.text_edit.setAlignment(Qt.AlignmentFlag.AlignCenter if conf.get("center_text", True) else Qt.AlignmentFlag.AlignLeft)
        self.text_edit.setStyleSheet(f"QTextEdit {{ background: transparent; color: {conf.get('font_color', '#ffffff')}; font-size: {conf.get('font_size', 24)}px; border: none; }}")

    def save_position(self):
        conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG
        conf["pos_x"], conf["pos_y"] = self.x(), self.y()
        mw.addonManager.writeConfig(__name__, conf)

    def mousePressEvent(self, event):
        if not self.locked and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True; self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft(); event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging: self.move(event.globalPosition().toPoint() - self._drag_pos); event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging: self._dragging = False; self.save_position()

# --- THE SETTINGS DIALOG ---
class SettingsDialog(QDialog):
    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(f"{ADDON_NAME} Settings")
        self.setFixedWidth(380) # Better sizing for settings
        self.conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG.copy()
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        
        # Design
        app_grp = QGroupBox("Design"); app_layout = QVBoxLayout()
        self.center_cb = QCheckBox("Center text alignment"); self.center_cb.setChecked(self.conf.get('center_text', True))
        self.border_cb = QCheckBox("Hide outer border/edge"); self.border_cb.setChecked(self.conf.get('hide_border', True))
        self.op_label = QLabel(f"Opacity: {self.conf.get('opacity', 25)}%")
        self.op_slider = QSlider(Qt.Orientation.Horizontal); self.op_slider.setRange(0, 100); self.op_slider.setValue(self.conf.get('opacity', 25))
        self.op_slider.valueChanged.connect(lambda v: self.op_label.setText(f"Opacity: {v}%"))
        app_layout.addWidget(self.center_cb); app_layout.addWidget(self.border_cb); app_layout.addWidget(self.op_label); app_layout.addWidget(self.op_slider)
        btn_row = QHBoxLayout()
        self.btn_bg = QPushButton("Box Color"); self.btn_bg.clicked.connect(self.pick_bg)
        self.btn_fg = QPushButton("Text Color"); self.btn_fg.clicked.connect(self.pick_fg)
        btn_row.addWidget(self.btn_bg); btn_row.addWidget(self.btn_fg); app_layout.addLayout(btn_row); app_grp.setLayout(app_layout); layout.addWidget(app_grp)

        # Behavior
        beh_grp = QGroupBox("Behavior"); beh_layout = QVBoxLayout()
        self.enter_cb = QCheckBox("Press 'Enter' to show answer"); self.enter_cb.setChecked(self.conf.get('enter_to_answer', True))
        self.lock_ans_cb = QCheckBox("Lock typing on answer side"); self.lock_ans_cb.setChecked(self.conf.get('lock_on_answer', True))
        self.auto_clear = QCheckBox("Auto-clear on next card"); self.auto_clear.setChecked(self.conf.get('auto_clear', True))
        self.lock_cb = QCheckBox("Lock position (Disable drag)"); self.lock_cb.setChecked(self.conf.get('locked', False))
        beh_layout.addWidget(self.enter_cb); beh_layout.addWidget(self.lock_ans_cb); beh_layout.addWidget(self.auto_clear); beh_layout.addWidget(self.lock_cb); beh_grp.setLayout(beh_layout); layout.addWidget(beh_grp)

        # System
        sys_grp = QGroupBox("System"); sys_layout = QGridLayout()
        self.sh_label = QLabel(f"Shortcut: <b>{self.conf.get('shortcut', 'Ctrl+\\')}</b>")
        self.btn_sh = QPushButton("Record Shortcut"); self.btn_sh.clicked.connect(self.capture_shortcut)
        self.f_in = QSpinBox(); self.f_in.setRange(8, 72); self.f_in.setValue(self.conf.get('font_size', 24))
        self.w_in = QSpinBox(); self.w_in.setRange(100, 2000); self.w_in.setValue(self.conf.get('width', 500))
        self.h_in = QSpinBox(); self.h_in.setRange(50, 2000); self.h_in.setValue(self.conf.get('height', 300))
        sys_layout.addWidget(self.sh_label, 0, 0); sys_layout.addWidget(self.btn_sh, 0, 1)
        sys_layout.addWidget(QLabel("Font Size:"), 1, 0); sys_layout.addWidget(self.f_in, 1, 1)
        sys_layout.addWidget(QLabel("Width:"), 2, 0); sys_layout.addWidget(self.w_in, 2, 1)
        sys_layout.addWidget(QLabel("Height:"), 3, 0); sys_layout.addWidget(self.h_in, 3, 1)
        sys_grp.setLayout(sys_layout); layout.addWidget(sys_grp)

        # Help
        help_grp = QGroupBox("Help"); help_layout = QVBoxLayout()
        self.btn_guide = QPushButton("Open Help Guide"); self.btn_guide.clicked.connect(lambda: GuideDialog(self).exec())
        self.btn_report = QPushButton("🚩 Report an Issue"); self.btn_report.clicked.connect(lambda: openLink(ADDON_URL + "/issues"))
        self.btn_reset = QPushButton("↺ Reset to Default"); self.btn_reset.clicked.connect(self.reset_to_default)
        help_layout.addWidget(self.btn_guide); help_layout.addWidget(self.btn_report); help_layout.addWidget(self.btn_reset); help_grp.setLayout(help_layout); layout.addWidget(help_grp)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        btns.accepted.connect(self.save_settings); btns.rejected.connect(self.reject); layout.addWidget(btns)

    def pick_bg(self):
        c = QColorDialog.getColor(QColor(self.conf.get('bg_color', '#1e1e1e')), self)
        if c.isValid(): self.conf['bg_color'] = c.name()
    def pick_fg(self):
        c = QColorDialog.getColor(QColor(self.conf.get('font_color', '#ffffff')), self)
        if c.isValid(): self.conf['font_color'] = c.name()
    def capture_shortcut(self):
        self.btn_sh.setText("PRESS KEYS..."); self.btn_sh.setFocus()
    def keyPressEvent(self, event):
        if self.btn_sh.hasFocus():
            if event.key() in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta): return
            seq = QKeySequence(event.keyCombination()).toString()
            self.conf['shortcut'] = seq; self.sh_label.setText(f"Shortcut: <b>{seq}</b>")
            self.btn_sh.setText("Record Shortcut"); self.btn_sh.clearFocus()
        else: super().keyPressEvent(event)

    def reset_to_default(self):
        if askUser("Are you sure you want to reset all settings?"):
            self.conf = DEFAULT_CONFIG.copy()
            self.center_cb.setChecked(self.conf['center_text']); self.border_cb.setChecked(self.conf['hide_border'])
            self.op_slider.setValue(self.conf['opacity']); self.sh_label.setText(f"Shortcut: <b>{self.conf['shortcut']}</b>")
            self.f_in.setValue(self.conf['font_size']); self.w_in.setValue(self.conf['width']); self.h_in.setValue(self.conf['height'])

    def save_settings(self):
        self.conf.update({
            'font_size': self.f_in.value(), 'width': self.w_in.value(), 'height': self.h_in.value(),
            'locked': self.lock_cb.isChecked(), 'opacity': self.op_slider.value(), 
            'auto_clear': self.auto_clear.isChecked(), 'center_text': self.center_cb.isChecked(), 
            'hide_border': self.border_cb.isChecked(), 'enter_to_answer': self.enter_cb.isChecked(), 
            'lock_on_answer': self.lock_ans_cb.isChecked()
        })
        mw.addonManager.writeConfig(__name__, self.conf); get_panel().load_config(); refresh_shortcut(); self.accept()

# --- SYSTEM INIT ---
_panel = None; _shortcut = None
def get_panel():
    global _panel
    if _panel is None: _panel = TypingPanel(mw)
    return _panel

def refresh_shortcut():
    global _shortcut
    conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG
    if _shortcut: _shortcut.setParent(None); _shortcut.deleteLater()
    _shortcut = QShortcut(QKeySequence(conf.get('shortcut', 'Ctrl+\\')), mw)
    _shortcut.activated.connect(toggle_panel)

def toggle_panel():
    p = get_panel()
    if p.isVisible(): p.hide(); p._user_wants_visible = False
    else: p.show(); p.raise_(); p.activateWindow(); p.text_edit.setFocus(); p._user_wants_visible = True

def on_question_shown(*args):
    conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG
    p = get_panel()
    p.text_edit.setReadOnly(False)
    if conf.get("auto_clear", True):
        p.text_edit.clear()
        p.text_edit.setAlignment(Qt.AlignmentFlag.AlignCenter if conf.get("center_text", True) else Qt.AlignmentFlag.AlignLeft)

def on_answer_shown(*args):
    conf = mw.addonManager.getConfig(__name__) or DEFAULT_CONFIG
    if conf.get("lock_on_answer", True): get_panel().text_edit.setReadOnly(True)

def init():
    action = QAction(f"{ADDON_NAME} Settings...", mw)
    action.triggered.connect(lambda: SettingsDialog(mw).exec())
    mw.form.menuTools.addAction(action)
    refresh_shortcut()

gui_hooks.main_window_did_init.append(init)
gui_hooks.reviewer_did_show_question.append(on_question_shown)
gui_hooks.reviewer_did_show_answer.append(on_answer_shown)