"""The windows: a base that remembers where it was, one that refreshes itself,
a slot that holds at most one, and the two dialogs every application writes.

`ToolWindow` is deliberately thin and both of its features are opt-in. A base
class that changes behaviour merely by being inherited is a base class nobody
can adopt incrementally — so a window with no `window_key` is never remembered,
and Escape does not close anything unless asked.
"""

from __future__ import annotations

from typing import Callable, Generic, TypeVar

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QKeyEvent
from PySide6.QtWidgets import QMessageBox, QVBoxLayout, QWidget

from . import placement
from .placement import WindowPlacement, Rect


def screen_rects() -> list[Rect]:
    """Every attached screen, as plain rectangles the placement rule can read."""
    return [
        (g.x(), g.y(), g.width(), g.height())
        for g in (screen.geometry() for screen in QGuiApplication.screens())
    ]


class ToolWindow(QWidget):
    """The base every LunaPY window shares.

    Set `window_key` to opt into geometry persistence. Without one nothing is
    remembered, which is the right default: a transient dialog that reappears
    exactly where it was three days ago is worse than one that appears where the
    window manager wants it.
    """

    #: Emitted after the window is closed. Qt has no such signal on QWidget —
    #: `destroyed` fires only when the object is deleted, which for a window
    #: without WA_DeleteOnClose is a different and much later moment.
    closed = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.window_key: str | None = None

        # Off by default: Escape inside a text field means "stop what I am
        # typing", not "throw away this window".
        self.closes_on_escape = False

        # `showEvent` fires on every show, including a restore from minimised.
        # Restoring placement more than once would fight the user: they move the
        # window, minimise it, restore it, and it jumps back.
        self._placement_restored = False

    def set_content(self, content: QWidget, margin: int = 8) -> QWidget:
        """Put a single widget in the window. Returns it, so it can be kept."""
        layout = self.layout() or QVBoxLayout(self)
        layout.setContentsMargins(margin, margin, margin, margin)
        while layout.count():
            layout.takeAt(0)
        layout.addWidget(content)
        return content

    # -- Qt lifecycle ----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if not self._placement_restored:
            self._placement_restored = True
            self.restore_placement()

    def closeEvent(self, event):
        # Captured before the close completes, while the geometry is still real.
        self.remember_placement()
        super().closeEvent(event)
        self.closed.emit()

    def keyPressEvent(self, event: QKeyEvent):
        if self.closes_on_escape and event.key() == Qt.Key.Key_Escape:
            event.accept()
            self.close()
            return
        super().keyPressEvent(event)

    # -- Placement -------------------------------------------------------

    def restore_placement(self) -> bool:
        """Put the window back where it was. `False` if there was nothing to use."""
        if not self.window_key:
            return False
        saved = placement.load(self.window_key)
        if saved is None:
            return False

        if saved.width > 0 and saved.height > 0:
            self.resize(saved.width, saved.height)

        # Size first, then position, then check — the check needs the size the
        # window is actually going to have, not the one it was constructed with.
        if placement.is_on_a_screen(screen_rects(), saved.bounds):
            self.move(saved.x, saved.y)

        if saved.maximized:
            self.showMaximized()
        return True

    def remember_placement(self) -> bool:
        if not self.window_key:
            return False

        maximized = self.isMaximized()
        rect = self.normalGeometry() if maximized else self.geometry()

        # `normalGeometry` keeps the pre-maximise rectangle, which is what a
        # restore wants — measured: a window at (120,80,400,300) that is then
        # maximised reports geometry (2,2,796,796) and normalGeometry
        # (120,80,400,300). LunaP had to reload the previously saved placement
        # to recover this, because Avalonia's Window exposes only the live
        # bounds; Qt tracks it, so that workaround did not port.
        #
        # It is empty for a window maximised without ever having been shown
        # normally, and saving a zero-sized rectangle would restore a window
        # nobody can see.
        if not rect.isValid() or rect.width() <= 0 or rect.height() <= 0:
            rect = self.geometry()

        return placement.save(
            self.window_key,
            WindowPlacement(rect.x(), rect.y(), rect.width(), rect.height(), maximized),
        )


class PollingWindow(ToolWindow):
    """A window that re-reads its source on a timer, and stops while hidden.

    The stopping is the point. Five windows in LunaP hand-rolled a refresh timer
    and **none of them stopped while hidden**, so a minimised dashboard went on
    querying its source forever. LunaP §8.2.

    Subclasses set `refresh_interval` and implement `refresh`. Neither is
    enforced through `abc`: `QWidget`'s metaclass and `ABCMeta` conflict, and
    the workarounds cost more than the guarantee is worth here, so the base
    raises `NotImplementedError` instead — same failure, one line later.
    """

    #: Milliseconds between refreshes.
    refresh_interval: int = 1000

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._timer: QTimer | None = None
        self._started = False

    def refresh(self) -> None:
        raise NotImplementedError(f"{type(self).__name__} must implement refresh()")

    @property
    def is_polling(self) -> bool:
        """Whether the timer is running right now.

        Public so a test can assert that a hidden window stopped, without
        racing a clock to prove a negative.
        """
        return self._timer is not None and self._timer.isActive()

    def start_polling(self) -> None:
        """Begin, with an immediate first paint.

        Calling this at the end of a subclass's `__init__` gets the first
        refresh before the window is shown; `showEvent` calls it anyway, so
        forgetting is late rather than fatal.
        """
        if self._started:
            return
        self._started = True
        self._timer = QTimer(self)
        self._timer.setInterval(self.refresh_interval)
        self._timer.timeout.connect(self.refresh)
        self._sync_timer()
        self.refresh()

    def refresh_now(self) -> None:
        """Repaint without waiting for the next tick, for a caller that has just
        changed what this window is looking at."""
        if self._started:
            self.refresh()

    def stop_polling(self) -> None:
        if self._timer is not None:
            self._timer.stop()

    # -- Qt lifecycle ----------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.start_polling()
        self._sync_timer()

    def hideEvent(self, event):
        super().hideEvent(event)
        self._sync_timer()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange:
            self._sync_timer()

    def closeEvent(self, event):
        self.stop_polling()
        super().closeEvent(event)

    def _sync_timer(self) -> None:
        """Run only while the window can actually be seen.

        Occlusion is not portably detectable, so this covers the two states that
        are: hidden and minimised. A window buried under another one keeps
        polling, and that is a known limit rather than an oversight.
        """
        if self._timer is None:
            return

        should_run = self.isVisible() and not self.isMinimized()
        if should_run == self._timer.isActive():
            return

        if should_run:
            self._timer.start()
            # Otherwise the first thing seen after restoring is however stale
            # the data went while the window was hidden.
            self.refresh()
        else:
            self._timer.stop()


W = TypeVar("W", bound=QWidget)


class WindowSlot(QObject, Generic[W]):
    """At most one of these, else bring the existing one forward.

    The pattern seven call sites in LunaP hand-wrote before it was extracted
    (§8.3), each with its own idea of what to do when the window was already
    open.

    A `QObject` because it watches its window through an event filter. The
    alternative — connecting to `destroyed` — fires only when the object is
    deleted, which for a window without `WA_DeleteOnClose` happens long after
    the user closed it, so the slot would go on believing a window nobody can
    see is still open.
    """

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._current: W | None = None

    @property
    def current(self) -> W | None:
        return self._current

    @property
    def is_open(self) -> bool:
        return self._current is not None

    def show(self, create: Callable[[], W], refresh: Callable[[W], None] | None = None) -> W:
        """Create the window, or refresh and raise the one already open."""
        existing = self._current
        if existing is not None:
            if refresh is not None:
                refresh(existing)
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing

        window = create()
        self._current = window
        window.installEventFilter(self)
        window.show()
        return window

    def refresh_if_open(self, refresh: Callable[[W], None]) -> bool:
        """Never creates and never raises.

        A background event that changed the data should not pop up a window
        nobody asked for, or steal focus from what the user is doing.
        """
        if self._current is None:
            return False
        refresh(self._current)
        return True

    def close(self) -> None:
        if self._current is not None:
            self._current.close()

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Close and watched is self._current:
            self._current = None
            watched.removeEventFilter(self)
        return False


class MessageWindow(ToolWindow):
    """A window that shows a body of text, for output too long to be a dialog.

    A `QMessageBox` is the wrong shape past a few lines: it is modal, it cannot
    be scrolled comfortably, and it cannot be left open beside the thing it is
    describing. Build output, a validation report and an exception trace all
    want to be read *while* looking at what produced them.

    Selectable and read-only, because the first thing anybody does with an error
    is copy it somewhere.
    """

    def __init__(
        self,
        title: str = "",
        body: str = "",
        monospace: bool = True,
        parent: QWidget | None = None,
    ):
        from PySide6.QtWidgets import QPlainTextEdit

        super().__init__(parent)
        self.setWindowTitle(title)
        self.closes_on_escape = True

        self._body = QPlainTextEdit()
        self._body.setReadOnly(True)
        self._body.setPlainText(body)
        self._body.setAccessibleName(title or "Message")
        if monospace:
            from .palette import MONO_FONT
            from .theme import STYLE_KEY

            self._body.setProperty(STYLE_KEY, "mono")
            self._body.setStyleSheet(f"QPlainTextEdit {{ font-family: {MONO_FONT}; }}")

        self.set_content(self._body)
        self.resize(640, 420)

    def set_body(self, body: str) -> None:
        self._body.setPlainText(body)

    @property
    def body(self) -> str:
        return self._body.toPlainText()

    def append(self, line: str) -> None:
        self._body.appendPlainText(line)


# -- Dialogs -------------------------------------------------------------
#
# Each comes in two pieces: a builder that configures a QMessageBox and returns
# it, and a one-line wrapper that shows it. That split is not ceremony — `exec`
# spins a modal event loop, so a test that called it would hang forever with no
# way to click anything. The builder is what carries the decisions (which button
# is default, what the buttons say) and it is testable headlessly, leaving the
# wrapper with nothing in it that can be wrong.


def confirm_box(
    parent: QWidget | None,
    title: str,
    message: str,
    confirm_label: str = "OK",
    cancel_label: str = "Cancel",
) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Question)
    accept = box.addButton(confirm_label, QMessageBox.ButtonRole.AcceptRole)
    reject = box.addButton(cancel_label, QMessageBox.ButtonRole.RejectRole)

    # Cancel is the default, so that Return on a dialog somebody did not read
    # does the harmless thing. Confirmations exist for actions worth a second
    # look, and defaulting to the destructive button removes the second look.
    box.setDefaultButton(reject)
    box.setEscapeButton(reject)
    return box


def confirm(parent: QWidget | None, title: str, message: str, **labels) -> bool:
    box = confirm_box(parent, title, message, **labels)
    box.exec()
    return box.buttonRole(box.clickedButton()) == QMessageBox.ButtonRole.AcceptRole


def error_box(parent: QWidget | None, title: str, message: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Critical)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    return box


def error(parent: QWidget | None, title: str, message: str) -> None:
    error_box(parent, title, message).exec()


def message_box(parent: QWidget | None, title: str, message: str) -> QMessageBox:
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setText(message)
    box.setIcon(QMessageBox.Icon.Information)
    box.setStandardButtons(QMessageBox.StandardButton.Ok)
    return box


def message(parent: QWidget | None, title: str, message_text: str) -> None:
    message_box(parent, title, message_text).exec()
