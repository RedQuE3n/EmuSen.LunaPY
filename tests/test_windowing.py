"""The windows themselves, headless.

`show`/`hide`/`close` and the state changes all fire under the offscreen
platform, and a QTimer really ticks while `processEvents` is being drained —
measured at 20 ticks in 200ms on a 10ms interval — so the polling window can be
tested without racing a wall clock.
"""

import time

import pytest

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QMessageBox

from lunapy import placement, settings
from lunapy.fluent import header, stack, text
from lunapy.placement import WindowPlacement
from lunapy.settings import SqliteSettingsStore
from lunapy.testing import assert_laid_out, show
from lunapy.windowing import (
    PollingWindow,
    ToolWindow,
    WindowSlot,
    confirm_box,
    error_box,
    message_box,
    screen_rects,
)


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    settings.set_store(SqliteSettingsStore(tmp_path / "settings.db"))
    yield
    settings.set_store(None)


def pump(app, seconds=0.05):
    """Drain the event loop for a while, so timers tick and state settles."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()


# -- ToolWindow ----------------------------------------------------------


def test_a_tool_window_renders_its_content(app):
    window = ToolWindow()
    window.set_content(stack(header("Audio"), text("Volume"), spacing=8))
    show(window, 320, 160)
    assert_laid_out(window, "tool_window")


def test_set_content_replaces_rather_than_stacks(app):
    window = ToolWindow()
    window.set_content(text("first"))
    window.set_content(text("second"))
    assert window.layout().count() == 1


def test_without_a_key_nothing_is_remembered(app):
    """A transient dialog that reappears exactly where it was three days ago is
    worse than one the window manager places."""
    window = ToolWindow()
    show(window, 200, 150)
    window.close()
    assert placement.remembered() == []


def test_with_a_key_geometry_survives_a_close(app):
    window = ToolWindow()
    window.window_key = "editor"
    window.setGeometry(140, 90, 360, 240)
    show(window)
    window.close()

    saved = placement.load("editor")
    assert saved is not None
    assert (saved.width, saved.height) == (360, 240)
    assert saved.maximized is False


def test_a_remembered_window_reopens_where_it_was(app):
    placement.save("editor", WindowPlacement(150, 100, 380, 260))
    window = ToolWindow()
    window.window_key = "editor"
    show(window)
    assert (window.width(), window.height()) == (380, 260)
    assert (window.x(), window.y()) == (150, 100)


def test_a_placement_off_every_screen_keeps_the_size_and_drops_the_position(app):
    """The failure this prevents is unrecoverable from inside the application:
    a window at coordinates with no pixels behind them cannot be seen, so it
    cannot be dragged back."""
    far_away = (99000, 99000)
    placement.save("editor", WindowPlacement(*far_away, 380, 260))

    window = ToolWindow()
    window.window_key = "editor"
    show(window)

    assert (window.width(), window.height()) == (380, 260)
    assert (window.x(), window.y()) != far_away


def test_placement_is_restored_once_not_on_every_show(app):
    """showEvent fires again on restore-from-minimised. Restoring twice fights
    the user: they move the window, minimise it, and it jumps back."""
    placement.save("editor", WindowPlacement(150, 100, 380, 260))
    window = ToolWindow()
    window.window_key = "editor"
    show(window)

    window.move(400, 300)
    window.showMinimized()
    pump(app)
    window.showNormal()
    pump(app)

    assert (window.x(), window.y()) == (400, 300)


def test_a_maximized_window_remembers_the_size_to_restore_to(app):
    """`geometry()` on a maximised window is the screen's, so saving it would
    lose the restore size. Qt keeps the pre-maximise rectangle in
    `normalGeometry`; LunaP had to reload the previous saved value instead."""
    window = ToolWindow()
    window.window_key = "editor"
    window.setGeometry(120, 80, 400, 300)
    show(window)
    window.showMaximized()
    pump(app)
    window.close()

    saved = placement.load("editor")
    assert saved.maximized is True
    assert (saved.width, saved.height) == (400, 300), (
        "the maximised window saved its screen-sized bounds, so reopening it and "
        "un-maximising would lose the size the user chose"
    )


def test_escape_is_off_by_default(app):
    """Escape inside a text field means "stop what I am typing", not "throw
    away this window"."""
    window = ToolWindow()
    show(window, 200, 150)
    window.keyPressEvent(_escape())
    assert window.isVisible()


def test_escape_closes_when_asked(app):
    window = ToolWindow()
    window.closes_on_escape = True
    show(window, 200, 150)
    window.keyPressEvent(_escape())
    pump(app)
    assert not window.isVisible()


def _escape():
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent

    return QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)


def test_the_closed_signal_fires(app):
    window = ToolWindow()
    fired = []
    window.closed.connect(lambda: fired.append(1))
    show(window, 200, 150)
    window.close()
    assert fired == [1]


def test_screen_rects_reports_something(app):
    rects = screen_rects()
    assert rects and all(len(r) == 4 and r[2] > 0 and r[3] > 0 for r in rects)


# -- PollingWindow -------------------------------------------------------


class Counter(PollingWindow):
    refresh_interval = 10

    def __init__(self):
        super().__init__()
        self.refreshes = 0
        self.set_content(text("counting"))

    def refresh(self):
        self.refreshes += 1


def test_a_polling_window_refreshes_on_a_timer(app):
    window = Counter()
    show(window, 200, 100)
    pump(app, 0.15)
    assert window.refreshes > 2
    window.close()


def test_polling_stops_while_hidden(app):
    """Five windows in LunaP hand-rolled a refresh timer and none of them
    stopped while hidden, so a minimised dashboard queried its source
    forever."""
    window = Counter()
    show(window, 200, 100)
    pump(app, 0.05)
    assert window.is_polling

    window.hide()
    pump(app, 0.05)
    assert not window.is_polling

    at_rest = window.refreshes
    pump(app, 0.1)
    assert window.refreshes == at_rest, "a hidden window went on refreshing"


def test_polling_stops_while_minimized(app):
    window = Counter()
    show(window, 200, 100)
    pump(app, 0.05)
    window.showMinimized()
    pump(app, 0.05)
    assert not window.is_polling
    window.close()


def test_restoring_refreshes_immediately(app):
    """Otherwise the first thing seen after restoring is however stale the data
    went while the window was hidden."""
    window = Counter()
    show(window, 200, 100)
    pump(app, 0.05)
    window.hide()
    pump(app, 0.05)

    before = window.refreshes
    window.show()
    app.processEvents()
    assert window.refreshes == before + 1
    window.close()


def test_closing_stops_the_timer(app):
    window = Counter()
    show(window, 200, 100)
    pump(app, 0.05)
    window.close()
    pump(app, 0.05)
    assert not window.is_polling


def test_refresh_now_does_not_wait_for_a_tick(app):
    window = Counter()
    show(window, 200, 100)
    app.processEvents()
    before = window.refreshes
    window.refresh_now()
    assert window.refreshes == before + 1
    window.close()


def test_a_polling_window_without_refresh_says_so(app):
    """`abc` is not used because QWidget's metaclass and ABCMeta conflict; the
    failure arrives one line later instead of at class definition."""

    class Incomplete(PollingWindow):
        refresh_interval = 10

    window = Incomplete()
    with pytest.raises(NotImplementedError, match="Incomplete"):
        window.start_polling()


# -- WindowSlot ----------------------------------------------------------


def test_a_slot_opens_one_window(app):
    slot = WindowSlot()
    assert not slot.is_open
    window = slot.show(ToolWindow)
    assert slot.is_open and slot.current is window
    window.close()


def test_a_second_show_reuses_the_first_window(app):
    slot = WindowSlot()
    created = []

    def make():
        created.append(1)
        return ToolWindow()

    first = slot.show(make)
    second = slot.show(make)
    assert first is second
    assert created == [1]
    first.close()


def test_a_second_show_can_refresh_what_is_already_open(app):
    slot = WindowSlot()
    refreshed = []
    window = slot.show(ToolWindow)
    slot.show(ToolWindow, refresh=lambda w: refreshed.append(w))
    assert refreshed == [window]
    window.close()


def test_closing_the_window_empties_the_slot(app):
    """`destroyed` fires only when the object is deleted, which for a window
    without WA_DeleteOnClose is long after the user closed it — the slot would
    go on believing an invisible window is open."""
    slot = WindowSlot()
    window = slot.show(ToolWindow)
    window.close()
    app.processEvents()
    assert not slot.is_open and slot.current is None


def test_a_slot_reopens_after_a_close(app):
    slot = WindowSlot()
    first = slot.show(ToolWindow)
    first.close()
    app.processEvents()
    second = slot.show(ToolWindow)
    assert second is not first
    second.close()


def test_refresh_if_open_never_creates(app):
    """A background event that changed the data should not pop up a window
    nobody asked for, or steal focus from what the user is doing."""
    slot = WindowSlot()
    called = []
    assert slot.refresh_if_open(lambda w: called.append(w)) is False
    assert called == []
    assert not slot.is_open


def test_refresh_if_open_reaches_an_open_window(app):
    slot = WindowSlot()
    window = slot.show(ToolWindow)
    called = []
    assert slot.refresh_if_open(lambda w: called.append(w)) is True
    assert called == [window]
    window.close()


def test_a_slot_closes_what_it_holds(app):
    slot = WindowSlot()
    slot.show(ToolWindow)
    slot.close()
    app.processEvents()
    assert not slot.is_open


def test_closing_an_empty_slot_is_not_an_error(app):
    WindowSlot().close()


# -- Dialogs -------------------------------------------------------------
#
# The builders are tested; the `exec` wrappers are not, because `exec` spins a
# modal event loop and a test that called it would hang with nothing able to
# click. That is the whole reason the split exists.


def test_a_confirmation_defaults_to_cancel(app):
    """Return on a dialog somebody did not read should do the harmless thing.
    Confirmations exist for actions worth a second look, and defaulting to the
    destructive button removes the second look."""
    box = confirm_box(None, "Prune", "Delete every field?")
    assert box.buttonRole(box.defaultButton()) == QMessageBox.ButtonRole.RejectRole
    assert box.buttonRole(box.escapeButton()) == QMessageBox.ButtonRole.RejectRole


def test_a_confirmation_takes_its_own_labels(app):
    box = confirm_box(None, "Prune", "Sure?", confirm_label="Delete", cancel_label="Keep")
    labels = {b.text().replace("&", "") for b in box.buttons()}
    assert labels == {"Delete", "Keep"}


def test_the_dialogs_carry_their_severity(app):
    assert error_box(None, "t", "m").icon() == QMessageBox.Icon.Critical
    assert message_box(None, "t", "m").icon() == QMessageBox.Icon.Information
    assert confirm_box(None, "t", "m").icon() == QMessageBox.Icon.Question


def test_the_dialogs_carry_their_text(app):
    box = error_box(None, "Could not save", "The file is read-only.")
    assert box.windowTitle() == "Could not save"
    assert box.text() == "The file is read-only."
