"""Getting work onto the UI thread, and three guards for what happens there.

Qt does more of this than Avalonia did, and the port is smaller because of it: a
queued signal connection already marshals across threads, so most of what
`UiThread` existed for is free. `run`/`post` remain because "am I already on the
UI thread" is still a question with two different right answers.

`Latest`, `Suppressor` and `Debounce` port whole. They were extracted in LunaP
because three applications had written them by hand — `Latest` three times,
byte-identical (LunaP §21.1).
"""

from __future__ import annotations

import threading
from typing import Callable, Generic, TypeVar

from PySide6.QtCore import QObject, Qt, QThread, QTimer, Signal

T = TypeVar("T")


# -- Getting onto the UI thread ------------------------------------------


class _Poster(QObject):
    """Carries a callable to the UI thread through a queued signal.

    A queued connection is Qt's own cross-thread hand-off: emitting from any
    thread appends to the receiving thread's event queue, and the slot runs
    there. This object is created on the UI thread, so that is where its slot
    runs no matter who emits.
    """

    fired = Signal(object)

    def __init__(self):
        super().__init__()
        self.fired.connect(self._call, Qt.ConnectionType.QueuedConnection)

    @staticmethod
    def _call(work):
        work()


_poster: _Poster | None = None
_poster_lock = threading.Lock()


def _ui_poster() -> _Poster:
    global _poster
    with _poster_lock:
        if _poster is None:
            from PySide6.QtWidgets import QApplication

            app = QApplication.instance()
            if app is None:
                raise RuntimeError(
                    "lunapy.threading needs a QApplication before it can reach the UI thread."
                )
            _poster = _Poster()
            # Constructed on whichever thread got here first, which may not be
            # the UI thread — a worker calling `post` before anything else has.
            # Its slot runs on the thread it *lives* on, so it is moved
            # explicitly rather than left wherever it was born.
            _poster.moveToThread(app.thread())
        return _poster


def is_ui_thread() -> bool:
    """Whether the caller is already the UI thread.

    Worth having in its own right: the honest answer to "should this be
    marshalled" is sometimes "no", and code that cannot ask has to guess.
    """
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    return app is not None and QThread.currentThread() == app.thread()


def run(work: Callable[[], None]) -> None:
    """Run now if already on the UI thread, otherwise queue it.

    **The inline half is not an optimisation.** Always queuing would mean a
    caller already on the UI thread does not see the effect until after it
    returns, so `slot.show(...)` followed by reading `slot.current` would find
    nothing there. A seam whose observable behaviour depends on which thread
    called it is worse than no seam.

    Not everything belongs here. LunaP §11.2 records a caller for which
    marshalling was exactly wrong, because its work had to run on the thread
    owning an emulator core. There is no flag to pass for that — a flag would
    move the same decision somewhere less visible.
    """
    if is_ui_thread():
        work()
    else:
        post(work)


def post(work: Callable[[], None]) -> None:
    """Always queue, never inline.

    For a caller that must not re-enter itself — raising an event from inside a
    layout pass — and needs the work to happen after the current one finishes
    rather than inside it.
    """
    _ui_poster().fired.emit(work)


# -- The three guards ----------------------------------------------------


class Suppressor:
    """"I am writing to these controls; their change handlers must not write back."

    Six hand-written booleans across two applications in LunaP, all guarding the
    same thing (§21.1)::

        self._filling = Suppressor()

        def refresh(self):
            with self._filling.suppress():
                self.list.rebuild(rows)
                self.list.select(chosen)

        def on_selection_changed(self):
            if self._filling.is_suppressing:
                return

    **A counter, not a boolean, and that is the one thing it adds over what it
    replaces.** Every hand-rolled version assigns True and then False, so a
    nested update — a refresh calling a helper that refreshes something else —
    re-enables notifications halfway through the outer one. At that point the
    guard is worse than absent, because the code reads as though it is
    protected.

    **Not thread-safe, deliberately.** This guards UI event handlers, which are
    a UI-thread concern. Making it atomic would invite use as a general mutual
    exclusion primitive, which it is not and should not become.
    """

    def __init__(self):
        self._depth = 0

    @property
    def is_suppressing(self) -> bool:
        return self._depth > 0

    def suppress(self) -> "_SuppressScope":
        """Open a scope. Use it with `with`, so an exception thrown mid-update
        cannot leave notifications suppressed for the rest of the process."""
        return _SuppressScope(self)


class _SuppressScope:
    def __init__(self, owner: Suppressor):
        self._owner: Suppressor | None = owner

    def __enter__(self) -> "Suppressor":
        assert self._owner is not None
        self._owner._depth += 1
        return self._owner

    def __exit__(self, *exc) -> bool:
        # Cleared after the first exit, so re-entering or double-exiting the
        # same scope object cannot drive the depth below zero and reopen an
        # outer scope that is still meant to be closed.
        if self._owner is not None:
            self._owner._depth -= 1
            self._owner = None
        return False


class Debounce(QObject):
    """"Wait until they stop typing, then do the expensive thing once."

    **Trailing edge only.** `poke` restarts the clock; the action runs once,
    `delay_ms` after the last poke. A leading-edge variant is a different
    control with a different feel, and is not offered rather than offered badly
    — the search boxes this exists for all want the trailing edge, because the
    first keystroke of a word is the least informative one.

    **UI thread only.** `QTimer` fires on the thread that owns it, so the action
    runs there and the caller never marshals; the cost is that `poke` must be
    called from the UI thread too. That matches every use it was written for —
    they are all reacting to a keystroke. A worker-thread producer wants
    `Latest` instead.
    """

    def __init__(self, delay_ms: int, action: Callable[[], None], parent: QObject | None = None):
        super().__init__(parent)
        if delay_ms <= 0:
            raise ValueError(f"delay_ms must be positive, got {delay_ms}")
        self._action = action
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self._fire)

    @property
    def is_pending(self) -> bool:
        return self._timer.isActive()

    def poke(self) -> None:
        """Restart the delay.

        Stop-then-start rather than leaving a running timer alone: a timer that
        is merely still active would fire `delay` after the *first* poke instead
        of the last, which is the whole behaviour being bought here.
        """
        self._timer.stop()
        self._timer.start()

    def cancel(self) -> None:
        """Drop anything pending. For a window closing, or a filter cleared by
        something other than typing."""
        self._timer.stop()

    def flush(self) -> None:
        """Run now if something is pending. For Enter, where the user has said
        they are finished and waiting out the delay would just feel slow."""
        if not self._timer.isActive():
            return
        self._timer.stop()
        self._action()

    def _fire(self) -> None:
        # Stopped before the action, not after: the action is allowed to poke
        # again (a search that discovers it needs a second pass), and stopping
        # afterwards would silently cancel that.
        self._timer.stop()
        self._action()


class Latest(Generic[T]):
    """"A worker produces faster than the screen can show it; show the newest."

    A frame source, a telemetry poll and a log tail all want this, and none of
    them wants a queue: a stale frame is not worth drawing, it is worth
    skipping.

    The contract: `offer` is safe from any thread and never blocks. `present`
    runs on the UI thread, at most once per value still current when it gets
    there, and never concurrently with itself.
    """

    def __init__(self, present: Callable[[T], None]):
        self._present = present
        self._lock = threading.Lock()
        self._pending: T | None = None
        self._scheduled = False

    def offer(self, value: T) -> None:
        """Hand over a value. The previous one, if unshown, is dropped."""
        with self._lock:
            self._pending = value
            # At most one callback outstanding. A second offer arriving before
            # the first is drained only replaces the value; it queues no more
            # work.
            if self._scheduled:
                return
            self._scheduled = True
        post(self._drain)

    def _drain(self) -> None:
        with self._lock:
            value = self._pending
            self._pending = None
            # CLEARED BEFORE PRESENTING, NOT AFTER, which is the one place this
            # differs from the three hand-written copies LunaP replaced. They
            # reset the flag after the hand-off, so an offer arriving *during*
            # the present could neither schedule (the flag still read set) nor
            # be picked up (the flag then cleared with nothing queued). That
            # value sat there until the next offer pushed it out.
            #
            # At 60 frames a second nobody could see it — the next frame arrived
            # 16ms later carrying the fix. It shows when the stream STOPS: pause
            # the producer and the final value is the one at risk, which is the
            # one somebody is about to sit and look at. LunaP §22.1.
            self._scheduled = False

        if value is not None:
            self._present(value)

        # LUNAP HAS A SECOND MECHANISM HERE AND THIS PORT DOES NOT NEED ONE.
        #
        # Its `Drain` re-checks `_pending` after presenting and reschedules if
        # something arrived. That closes a window its implementation really has:
        # it uses `Interlocked.Exchange` on `_pending` and then a separate one
        # on `_scheduled`, so between those two atomic operations an offer can
        # land, find the flag still set, and queue nothing.
        #
        # The block above holds one lock across both, so that gap does not
        # exist, and any offer arriving after it sees `_scheduled` clear and
        # schedules for itself. Ported faithfully at first and then removed,
        # because sabotage proved it dead: deleting the re-check alone leaves
        # the suite green, while deleting the early clear turns it red.
        # Defensive code no test can distinguish is weight, not safety —
        # docs/LunaPY.md §10.1.
