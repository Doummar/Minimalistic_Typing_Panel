"""The floating typing panel widget and its embedded text editor."""
from aqt import mw
from aqt.qt import (
    QApplication, QColor, QEvent, QFrame, QKeySequence, QLabel, QObject,
    QPoint, Qt, QTextCursor, QTextEdit, QTimer, QVBoxLayout, QWidget,
)
from aqt.utils import tooltip

from . import passthrough
from .config_utils import get_config, write_config

SNAP_MARGIN = 24  # px; how close to a screen edge before the panel snaps to it
TEXT_SAVE_DEBOUNCE_MS = 600  # wait for a pause in typing before writing to disk


class _DialogCloseWatcher(QObject):
    """Watches a single window opened through Anki's dialog manager (Edit
    Current, Browser, Add Cards, ...) and tells the panel when that window
    disappears.

    We rely on QEvent.Type.Hide rather than closeEvent()/destroyed() because
    it's a plain Qt widget-lifecycle event available on every QWidget -- it
    doesn't depend on any Anki-internal close/cleanup method, which keeps
    this working even if those private methods change in a future release.
    """

    def __init__(self, panel: "TypingPanel", key: int):
        super().__init__(panel)
        self._panel = panel
        self._key = key

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.Hide:
            obj.removeEventFilter(self)
            self._panel._on_blocking_dialog_closed(self._key)
            self.deleteLater()
        return False


class TypingEdit(QTextEdit):
    """The text box itself.

    While the panel is locked read-only on the answer side, this forwards a
    handful of Anki's own review shortcuts (grading keys, space to answer
    with the default ease) to the reviewer, since normal typing is disabled
    at that point anyway. Escape always hides the panel, regardless of
    lock state.
    """

    def __init__(self, panel: "TypingPanel"):
        super().__init__()
        self._panel = panel

    def keyPressEvent(self, event):
        conf = get_config()
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self._panel.request_hide()
            event.accept()
            return

        if key not in (
            Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta,
        ):
            # Modifier-only presses can't match a recorded combination (the
            # recorder itself never records one, see SettingsDialog
            # .keyPressEvent), so skip the check for those and fall
            # through to normal QTextEdit handling.
            sequence = QKeySequence(event.keyCombination())
            if self._panel.try_passthrough(sequence):
                event.accept()
                return

        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if conf.get("enter_to_answer", False) and mw.reviewer and mw.reviewer.state == "question":
                self._safe_call(mw.reviewer, "_showAnswer")
                event.accept()
                return

        if self.isReadOnly() and mw.reviewer and mw.reviewer.state == "answer":
            if key == Qt.Key.Key_1:
                self._safe_call(mw.reviewer, "_answerCard", 1); event.accept(); return
            if key == Qt.Key.Key_2:
                self._safe_call(mw.reviewer, "_answerCard", 2); event.accept(); return
            if key == Qt.Key.Key_3:
                self._safe_call(mw.reviewer, "_answerCard", 3); event.accept(); return
            if key == Qt.Key.Key_4:
                self._safe_call(mw.reviewer, "_answerCard", 4); event.accept(); return
            if key == Qt.Key.Key_Space:
                ok, ease = self._safe_call(mw.reviewer, "_defaultEase")
                if ok:
                    self._safe_call(mw.reviewer, "_answerCard", ease)
                event.accept()
                return

        super().keyPressEvent(event)

    @staticmethod
    def _safe_call(obj, method_name, *args):
        # mw.reviewer._showAnswer / _answerCard / _defaultEase are private,
        # undocumented Anki APIs that can be renamed or change signature
        # between versions. Guarding every call means a future Anki update
        # degrades this one convenience feature instead of throwing an
        # unhandled exception while the user is mid-keystroke.
        fn = getattr(obj, method_name, None)
        if fn is None:
            return False, None
        try:
            return True, (fn(*args) if args else fn())
        except Exception:
            return False, None


class TypingPanel(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)

        self.container = QFrame(self)
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.setContentsMargins(10, 10, 10, 10)
        self.main_layout.addWidget(self.container)

        self.text_edit = TypingEdit(self)
        self.container_layout.addWidget(self.text_edit)
        self.text_edit.textChanged.connect(self.on_text_changed_by_user)

        # Small corner badge shown whenever dragging is disabled, so a
        # locked panel doesn't just look "stuck" for no visible reason.
        self.lock_indicator = QLabel("Locked", self.container)
        self.lock_indicator.setStyleSheet(
            "QLabel { font-size: 10px; color: #dddddd; background-color: rgba(0, 0, 0, 130); "
            "padding: 1px 6px; border-radius: 4px; }"
        )
        self.lock_indicator.adjustSize()
        self.lock_indicator.hide()

        self.locked = False
        self._dragging = False
        self._drag_pos = QPoint()
        self._user_wants_visible = False
        self._current_deck_key = None

        # Whether Anki (the OS-level application) currently has focus. Kept
        # as explicit state, rather than only reacting to the state-change
        # signal in the moment, so _update_visibility() can treat it as just
        # another input alongside _user_wants_visible and _blocking_dialogs.
        # Assumed True at startup; on_app_state_changed() corrects this the
        # first time Anki actually loses/regains focus.
        self._app_active = True

        # ids of currently-open dialog-manager windows (Edit Current,
        # Browser, Add Cards, ...) that are forcing the panel to stay
        # hidden. A set rather than a plain int counter, so that Anki
        # re-firing the "dialog opened" hook for a window that's already
        # open (it does this on repeat Edit clicks -- see
        # DialogManager.open(), which reuses + re-raises an existing
        # instance instead of creating a new one) can't push the count out
        # of sync with the number of *distinct* windows actually open.
        self._blocking_dialogs = set()

        # Parsed QKeySequence objects for the user's configured passthrough
        # shortcuts (see try_passthrough below). Rebuilt only when config
        # is (re)loaded -- not on every keystroke -- so checking a typed
        # key against this list stays a cheap in-memory comparison against
        # a handful of entries rather than re-reading + re-parsing config
        # on every character typed.
        self._passthrough_sequences = []

        # Debounce writing scratchpad text to disk so persist_text mode
        # doesn't hit addonManager.writeConfig on every single keystroke.
        self._text_save_timer = QTimer(self)
        self._text_save_timer.setSingleShot(True)
        self._text_save_timer.setInterval(TEXT_SAVE_DEBOUNCE_MS)
        self._text_save_timer.timeout.connect(self._save_text_now)

        app = QApplication.instance()
        if app:
            app.applicationStateChanged.connect(self.on_app_state_changed)

        self.load_config()

    # ------------------------------------------------------------------
    # Visibility
    # ------------------------------------------------------------------
    # Every method below that can affect whether the panel should be on
    # screen -- toggling, the app losing/regaining focus, a blocking dialog
    # opening or closing -- only updates the relevant piece of state
    # (_user_wants_visible, _app_active, _blocking_dialogs) and then calls
    # _update_visibility(). That's the single place that ever calls
    # show()/hide()/raise() on the widget itself, so the actual on-screen
    # state can't drift out of sync with what these three inputs say it
    # should be, no matter which combination of events led there.
    def _can_show(self) -> bool:
        """Whether anything is currently forcing the panel to stay hidden,
        independent of whether the user wants it visible."""
        return not self._blocking_dialogs

    def _update_visibility(self):
        should_be_visible = self._user_wants_visible and self._app_active and self._can_show()
        if should_be_visible:
            if not self.isVisible():
                self.show()
            self.raise_()
        else:
            if self.isVisible():
                self.hide()

    def on_app_state_changed(self, state):
        if state == Qt.ApplicationState.ApplicationInactive:
            self._app_active = False
        elif state == Qt.ApplicationState.ApplicationActive:
            self._app_active = True
        else:
            return  # other transitional states (Suspended, Hidden, ...): no change
        self._update_visibility()

    def request_hide(self):
        self._user_wants_visible = False
        self._update_visibility()

    def request_show(self):
        # Set first so the preference survives even if we can't actually
        # show right now -- e.g. _on_blocking_dialog_closed() will honor it
        # automatically once the last blocking dialog closes.
        self._user_wants_visible = True
        if not self._can_show():
            tooltip(
                "Typing panel will reappear once the open editor window is closed.",
                period=2500,
            )
        self._update_visibility()

    def toggle(self):
        # Based on current on-screen visibility, not stored intent: if the
        # panel is suppressed by a blocking dialog, isVisible() is False, so
        # toggle re-runs request_show() -- which is itself gated and will
        # just re-show the "still blocked" tooltip. That's the right
        # behavior here; toggling on stored intent instead would let a
        # press while suppressed silently flip _user_wants_visible back to
        # False, which looks like nothing happened rather than "still
        # blocked."
        if self.isVisible():
            self.request_hide()
        else:
            self.request_show()

    # ------------------------------------------------------------------
    # Yielding to Anki's own top-level windows (Edit Current, Browser, ...)
    # ------------------------------------------------------------------
    # WindowStaysOnTopHint is required for the panel to float above the
    # reviewer, but it's global -- it also puts the panel above unrelated
    # Anki windows like the Edit Current dialog, since neither is a Qt
    # child of the other. Rather than removing the hint (which would break
    # the panel's core purpose), we keep the panel hidden for as long as any
    # such window is open, regardless of how a show is later requested, and
    # restore it once every one of them has closed -- without ever touching
    # _user_wants_visible, so the user's own show/hide choice is unaffected
    # by this purely programmatic, temporary suppression.
    def register_blocking_dialog(self, instance: QWidget):
        """Call when Anki opens a dialog-manager window (Edit Current,
        Browser, Add Cards, ...). Suppresses the panel while at least one
        such window is open, and arranges to restore it once every one of
        them has closed."""
        key = id(instance)
        if key in self._blocking_dialogs:
            return  # already tracking this window (e.g. it was re-activated)

        self._blocking_dialogs.add(key)
        self._update_visibility()

        # Two independent signals for "this window is gone," kept as
        # redundant safeguards rather than either/or: the Hide event fires
        # promptly on a normal close, while destroyed() is a fallback that
        # fires on outright deletion even in the rare case a Hide event
        # doesn't arrive (e.g. the window is torn down without going through
        # a normal close). Both funnel into the same idempotent handler, so
        # whichever fires first "wins" and the other is a harmless no-op.
        watcher = _DialogCloseWatcher(self, key)
        instance.installEventFilter(watcher)
        instance.destroyed.connect(lambda: self._on_blocking_dialog_closed(key))

    def _on_blocking_dialog_closed(self, key: int):
        self._blocking_dialogs.discard(key)
        self._update_visibility()

    # ------------------------------------------------------------------
    # Config -> visuals
    # ------------------------------------------------------------------
    def load_config(self, conf: dict = None):
        """Apply a config dict to the widget. If conf is omitted, reload
        from disk. Settings dialog passes a not-yet-saved conf here for live
        preview; nothing in this method writes to disk."""
        conf = conf if conf is not None else get_config()

        self.locked = conf.get("locked", False)
        self.lock_indicator.setVisible(self.locked)

        self._passthrough_sequences = [
            QKeySequence(s) for s in conf.get("passthrough_shortcuts", []) if s
        ]

        self.resize(conf.get("width", 500), conf.get("height", 300))
        self._apply_position(conf)

        opacity = max(0, min(100, conf.get("opacity", 25))) / 100.0
        qcolor = QColor(conf.get("bg_color", "#1e1e1e"))
        rgba_bg = f"rgba({qcolor.red()}, {qcolor.green()}, {qcolor.blue()}, {opacity})"
        border_css = "none" if conf.get("hide_border", True) else "1px solid #444"
        self.container.setStyleSheet(
            f"QFrame {{ background-color: {rgba_bg}; border: {border_css}; border-radius: 12px; }}"
        )

        font_family = conf.get("font_family") or "Arial"
        self.text_edit.setStyleSheet(
            f"QTextEdit {{ background: transparent; color: {conf.get('font_color', '#ffffff')}; "
            f"font-size: {conf.get('font_size', 24)}px; font-family: '{font_family}'; border: none; }}"
        )

        if conf.get("persist_text", False):
            saved = conf.get("saved_text", "")
            if saved and not self.text_edit.toPlainText():
                block = self.text_edit.blockSignals(True)
                self.text_edit.setPlainText(saved)
                self.text_edit.blockSignals(block)

        # QTextEdit.clear() / setPlainText() both replace the underlying
        # document, which silently resets alignment back to left. Applying
        # it last -- after any text mutation above -- is what makes "Center
        # text" actually stick instead of reverting on the next card.
        self._apply_alignment(conf)

        self._position_lock_indicator()

    def _apply_alignment(self, conf: dict = None):
        conf = conf if conf is not None else get_config()
        self.text_edit.setAlignment(
            Qt.AlignmentFlag.AlignCenter if conf.get("center_text", True) else Qt.AlignmentFlag.AlignLeft
        )

    def clear_text(self):
        """Clear the panel's text without losing the configured alignment
        (see _apply_alignment's docstring-equivalent comment in load_config)."""
        self.text_edit.clear()
        self._apply_alignment()

    # ------------------------------------------------------------------
    # Keyboard shortcut passthrough
    # ------------------------------------------------------------------
    def try_passthrough(self, sequence: QKeySequence) -> bool:
        """If `sequence` matches one of the user's configured passthrough
        shortcuts, forward it to Anki's own shortcut system (see
        passthrough.py) instead of letting it reach the text box as a
        normal keystroke. Returns whether it was handled this way.

        Called from TypingEdit.keyPressEvent for every keystroke, so the
        non-matching (i.e. normal typing) case needs to stay cheap: it's
        just one QKeySequence equality check per configured entry against
        an already-parsed, in-memory list.
        """
        if sequence.isEmpty() or sequence not in self._passthrough_sequences:
            return False

        # Snapshot exactly what "the user is mid-typing" means right now,
        # so it can be put back afterward no matter what the target
        # shortcut's callback does as a side effect (redrawing the
        # reviewer, opening something, etc.) -- that callback is another
        # add-on's code we don't control.
        cursor = self.text_edit.textCursor()
        anchor_pos, current_pos = cursor.anchor(), cursor.position()
        scroll_v = self.text_edit.verticalScrollBar().value()
        scroll_h = self.text_edit.horizontalScrollBar().value()

        reached = passthrough.dispatch(sequence)

        self.text_edit.setFocus()
        restored = self.text_edit.textCursor()
        restored.setPosition(anchor_pos)
        restored.setPosition(current_pos, QTextCursor.MoveMode.KeepAnchor)
        self.text_edit.setTextCursor(restored)
        self.text_edit.verticalScrollBar().setValue(scroll_v)
        self.text_edit.horizontalScrollBar().setValue(scroll_h)

        if not reached:
            tooltip(
                f"Nothing responded to '{sequence.toString()}' -- forwarded, "
                "but no matching shortcut or reviewer target was found.",
                period=2500,
            )
        return True

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._position_lock_indicator()

    def _position_lock_indicator(self):
        self.lock_indicator.adjustSize()
        self.lock_indicator.move(max(0, self.container.width() - self.lock_indicator.width() - 8), 6)

    # ------------------------------------------------------------------
    # Geometry: off-screen recovery, per-screen memory, per-deck memory
    # ------------------------------------------------------------------
    def _apply_position(self, conf: dict):
        x, y = conf.get("pos_x", 200), conf.get("pos_y", 200)
        screen_name = conf.get("screen_name", "")

        if conf.get("per_deck_position", False):
            entry = conf.get("deck_positions", {}).get(self._deck_key())
            if entry:
                x = entry.get("x", x)
                y = entry.get("y", y)
                screen_name = entry.get("screen_name", screen_name)

        screen = self._find_screen(screen_name) or self.screen() or QApplication.primaryScreen()
        x, y = self._clamp_to_screen(x, y, screen)
        self.move(x, y)

    @staticmethod
    def _find_screen(screen_name: str):
        if not screen_name:
            return None
        for s in QApplication.screens():
            if s.name() == screen_name:
                return s
        return None

    def _clamp_to_screen(self, x: int, y: int, screen):
        # Keeps the panel reachable even if it was last positioned on a
        # monitor that's since been unplugged, resized, or rearranged.
        if not screen:
            return x, y
        geo = screen.availableGeometry()
        w = self.width() or 500
        h = self.height() or 300
        x = max(geo.left(), min(x, geo.right() - w))
        y = max(geo.top(), min(y, geo.bottom() - h))
        return x, y

    def _deck_key(self) -> str:
        try:
            did = mw.col.decks.get_current_id() if mw.col else None
        except Exception:
            did = None
        return str(did) if did is not None else "default"

    def on_deck_switched(self):
        conf = get_config()
        if not conf.get("per_deck_position", False):
            self._current_deck_key = None
            return
        key = self._deck_key()
        if key != self._current_deck_key:
            self._current_deck_key = key
            self._apply_position(conf)

    # ------------------------------------------------------------------
    # Dragging, with edge snapping
    # ------------------------------------------------------------------
    def mousePressEvent(self, event):
        if not self.locked and event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._dragging:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._dragging:
            self._dragging = False
            self._snap_to_edges_if_enabled()
            self.save_position()

    def _snap_to_edges_if_enabled(self):
        conf = get_config()
        if not conf.get("snap_edges", True):
            return
        screen = self.screen() or QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        x, y = self.x(), self.y()
        w, h = self.width(), self.height()

        if abs(x - geo.left()) <= SNAP_MARGIN:
            x = geo.left()
        elif abs((x + w) - geo.right()) <= SNAP_MARGIN:
            x = geo.right() - w

        if abs(y - geo.top()) <= SNAP_MARGIN:
            y = geo.top()
        elif abs((y + h) - geo.bottom()) <= SNAP_MARGIN:
            y = geo.bottom() - h

        self.move(x, y)

    def save_position(self):
        # Only writes once per drag (on release), which already keeps disk
        # writes to a sane rate without needing a separate debounce timer.
        conf = get_config()
        screen = self.screen() or QApplication.primaryScreen()
        screen_name = screen.name() if screen else ""

        if conf.get("per_deck_position", False):
            positions = dict(conf.get("deck_positions", {}))
            positions[self._deck_key()] = {"x": self.x(), "y": self.y(), "screen_name": screen_name}
            conf["deck_positions"] = positions
        else:
            conf["pos_x"], conf["pos_y"], conf["screen_name"] = self.x(), self.y(), screen_name

        write_config(conf)

    # ------------------------------------------------------------------
    # Scratchpad text persistence (debounced)
    # ------------------------------------------------------------------
    def on_text_changed_by_user(self):
        conf = get_config()
        if conf.get("persist_text", False):
            self._text_save_timer.start()

    def _save_text_now(self):
        conf = get_config()
        if conf.get("persist_text", False):
            conf["saved_text"] = self.text_edit.toPlainText()
            write_config(conf)
