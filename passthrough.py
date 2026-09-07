"""Generic keyboard-shortcut passthrough.

Lets a keystroke that was typed into some other widget (here, the Typing
Panel's text box) still reach whatever would have handled it had it been a
real physical key press while Anki's reviewer had focus.

Investigation summary (see the chat message accompanying this change for
the full report): a real key press resolves through Qt's shortcut map
first, and only falls through to the focused widget -- for the reviewer,
that's mw.web, a QWebEngineView -- if nothing claimed it as a shortcut.
Reaching mw.web matters because a significant class of add-on (one-by-one
reveal / hint-style tools in particular) is commonly implemented as plain
JavaScript inside the card template itself, listening for `keydown` on
`document`/`window` -- there's no QShortcut object for those at all, so a
mechanism that only scans QShortcuts can never reach them.

This module therefore forwards through two layers, tried in that same
order, and stops at the first one that actually has something to receive
the key -- never both, since a real key press is never delivered to both
a matching shortcut *and* the focused widget:

  1. Shortcut layer: every enabled QShortcut anywhere under Anki's main
     window (mw) -- covers native Anki shortcuts and any add-on using the
     standard `gui_hooks.state_shortcuts_will_change` hook or a raw
     QShortcut(key, mw, ...).
  2. Webview layer: a synthetic QKeyEvent delivered to mw.web's focus
     proxy -- the same widget Anki's own webview.py treats as the real
     input target for the page -- so it reaches Chromium and the DOM
     exactly as an unclaimed physical key would, for add-ons (or card
     templates) that listen for keydown in JavaScript instead.

Neither layer knows or cares which add-on, if any, is listening -- this
module has no add-on-specific logic of any kind, by design.
"""
from aqt import mw
from aqt.qt import QApplication, QEvent, QKeyEvent, QKeySequence, Qt, QShortcut, QWidget


def find_matching_shortcuts(sequence: QKeySequence) -> list:
    """Enabled main-window/application shortcuts that match `sequence`.

    Child-widget shortcuts are deliberately excluded: a real key press would
    only activate those while their owning widget was in the active shortcut
    context, which is not true while the floating panel has focus.
    This implementation is robust across PyQt5/PyQt6 where QShortcut may
    not expose parentWidget().
    """
    if sequence.isEmpty():
        return []

    matches = []
    for sc in mw.findChildren(QShortcut):
        if not sc.isEnabled():
            continue

        # Some QShortcut implementations can raise or behave oddly when
        # accessing key(); guard conservatively.
        try:
            sc_key = sc.key()
        except Exception:
            continue

        if sc_key != sequence:
            continue

        # Prefer parentWidget() when available; fall back to parent().
        parent = getattr(sc, "parentWidget", None)
        if parent is None:
            try:
                parent = sc.parent()
            except Exception:
                parent = None

        # Walk up to a top-level QWidget so shortcuts attached to a child
        # object still resolve to mw when appropriate.
        try:
            p = parent
            while p is not None and not isinstance(p, QWidget):
                # QObject.parent() is a method; call it if present.
                parent_fn = getattr(p, "parent", None)
                if callable(parent_fn):
                    p = parent_fn()
                else:
                    break
            parent = p
        except Exception:
            # If anything unexpected happens during walk, keep the original
            # parent and proceed conservatively.
            parent = parent

        if parent is mw and sc.context() in (
            Qt.ShortcutContext.WindowShortcut,
            Qt.ShortcutContext.ApplicationShortcut,
        ):
            matches.append(sc)

    return matches


def _dispatch_to_shortcuts(sequence: QKeySequence) -> bool:
    """Layer 1: fire one unambiguous, eligible main-window shortcut.

    Qt emits ``activatedAmbiguously`` rather than ``activated`` when a key
    collides with another shortcut. Do not run every matching callback here:
    that would turn a single key press into unrelated actions.
    """
    matches = find_matching_shortcuts(sequence)
    if len(matches) != 1:
        # An ambiguous shortcut is still consumed by Qt; it must not fall
        # through to the reviewer webview as if no shortcut existed.
        return bool(matches)
    matches[0].activated.emit()
    return True


def _text_for_key(key: int, modifiers: Qt.KeyboardModifier) -> str:
    """Best-effort reconstruction of the character a real press of `key`
    (+ `modifiers`) would have produced, for the synthetic event's `text`
    field. Chromium derives a DOM event's `key`/`code` mainly from the Qt
    key code and modifiers rather than this field, so an empty string for
    anything outside plain, unmodified letters is a reasonable fallback,
    not a functional gap.
    """
    if Qt.Key.Key_A <= key <= Qt.Key.Key_Z:
        letter = chr(key)  # Qt.Key_A..Key_Z == ord('A')..ord('Z')
        return letter if modifiers & Qt.KeyboardModifier.ShiftModifier else letter.lower()
    return ""


def _dispatch_to_webview(sequence: QKeySequence) -> bool:
    """Layer 2: deliver a synthetic key press + release to the reviewer's
    webview, reaching Chromium and the page's own JS keydown listeners --
    covering add-ons (and card templates) that never register a QShortcut
    at all. Returns whether there was a target to deliver to.
    """
    if sequence.isEmpty() or sequence.count() < 1:
        return False

    target = mw.web.focusProxy() if mw.web else None
    if target is None:
        return False

    combo = sequence[0]
    key = combo.key()
    modifiers = combo.keyboardModifiers()
    text = _text_for_key(key, modifiers)

    QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyPress, key, modifiers, text))
    QApplication.sendEvent(target, QKeyEvent(QEvent.Type.KeyRelease, key, modifiers, text))
    return True


def dispatch(sequence: QKeySequence) -> bool:
    """Forward `sequence` as faithfully as possible to whatever would have
    handled a real physical press of it. Tries the shortcut layer first;
    only falls through to the webview layer if nothing matched there,
    mirroring the mutual exclusivity of real Qt event resolution rather
    than firing every mechanism unconditionally.

    Returns whether anything was actually reached, so callers can tell the
    user when a configured passthrough shortcut has nothing listening for
    it on either path.
    """
    if _dispatch_to_shortcuts(sequence):
        return True
    return _dispatch_to_webview(sequence)