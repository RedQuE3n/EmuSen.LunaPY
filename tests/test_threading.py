"""The three guards, and getting onto the UI thread.

`Latest` is tested with real worker threads rather than by mocking the
hand-off, because the bug it exists to avoid (LunaP §22.1) is a race between an
offer and a drain — and a test that serialises them cannot see it.
"""

import threading
import time

import pytest

from lunapy.threading import Debounce, Latest, Suppressor, is_ui_thread, post, run


def pump(app, seconds=0.05):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()


# -- Suppressor ----------------------------------------------------------


def test_a_suppressor_starts_open():
    assert not Suppressor().is_suppressing


def test_a_scope_suppresses_and_releases():
    s = Suppressor()
    with s.suppress():
        assert s.is_suppressing
    assert not s.is_suppressing


def test_nesting_stays_suppressed_until_the_outer_scope_closes():
    """A counter, not a boolean, and this is the whole reason.

    Every hand-rolled version assigns True then False, so a refresh calling a
    helper that refreshes something else re-enables notifications halfway
    through the outer update — at which point the guard is worse than absent,
    because the code reads as though it is protected.
    """
    s = Suppressor()
    with s.suppress():
        with s.suppress():
            assert s.is_suppressing
        assert s.is_suppressing, "the inner scope closing re-enabled notifications"
    assert not s.is_suppressing


def test_an_exception_does_not_leave_it_suppressed():
    """Otherwise one failed update suppresses notifications for the rest of the
    process, and nothing ever says why."""
    s = Suppressor()
    with pytest.raises(ValueError):
        with s.suppress():
            raise ValueError("mid-update")
    assert not s.is_suppressing


def test_exiting_a_scope_twice_cannot_reopen_an_outer_one():
    s = Suppressor()
    outer = s.suppress()
    outer.__enter__()
    inner = s.suppress()
    inner.__enter__()
    inner.__exit__()
    inner.__exit__()  # the double exit
    assert s.is_suppressing, "a double exit drove the depth below the outer scope"
    outer.__exit__()
    assert not s.is_suppressing


# -- Debounce ------------------------------------------------------------


def test_a_debounce_waits(app):
    calls = []
    d = Debounce(30, lambda: calls.append(1))
    d.poke()
    assert d.is_pending
    assert calls == []
    pump(app, 0.1)
    assert calls == [1]


def test_poking_again_restarts_the_clock(app):
    """A timer merely left running would fire `delay` after the FIRST poke
    instead of the last, which is the whole behaviour being bought."""
    calls = []
    d = Debounce(60, lambda: calls.append(1))
    for _ in range(4):
        d.poke()
        pump(app, 0.02)
    assert calls == [], "it fired while pokes were still arriving"
    pump(app, 0.12)
    assert calls == [1]


def test_cancel_drops_what_is_pending(app):
    calls = []
    d = Debounce(30, lambda: calls.append(1))
    d.poke()
    d.cancel()
    assert not d.is_pending
    pump(app, 0.1)
    assert calls == []


def test_flush_runs_now(app):
    """For Enter, where the user has said they are finished and waiting out the
    delay would just feel slow."""
    calls = []
    d = Debounce(500, lambda: calls.append(1))
    d.poke()
    d.flush()
    assert calls == [1]
    assert not d.is_pending


def test_flush_does_nothing_when_nothing_is_pending(app):
    calls = []
    Debounce(30, lambda: calls.append(1)).flush()
    assert calls == []


def test_the_action_may_poke_again(app):
    """Stopped before the action, not after: a search that discovers it needs a
    second pass must be able to ask for one."""
    calls = []
    d: Debounce

    def action():
        calls.append(1)
        if len(calls) == 1:
            d.poke()

    d = Debounce(20, action)
    d.poke()
    pump(app, 0.15)
    assert calls == [1, 1]


def test_a_non_positive_delay_is_refused(app):
    with pytest.raises(ValueError):
        Debounce(0, lambda: None)


# -- UI thread -----------------------------------------------------------


def test_the_test_runs_on_the_ui_thread(app):
    assert is_ui_thread()


def test_run_is_inline_on_the_ui_thread(app):
    """Not an optimisation. Always queuing would mean a caller on the UI thread
    does not see the effect until after it returns, so `slot.show(...)` followed
    by reading `slot.current` would find nothing there."""
    calls = []
    run(lambda: calls.append(1))
    assert calls == [1], "run() deferred work despite already being on the UI thread"


def test_post_always_defers(app):
    calls = []
    post(lambda: calls.append(1))
    assert calls == []
    pump(app, 0.05)
    assert calls == [1]


def test_run_from_a_worker_reaches_the_ui_thread(app):
    seen = []

    def worker():
        run(lambda: seen.append(threading.current_thread().name))

    thread = threading.Thread(target=worker, name="worker")
    thread.start()
    thread.join()
    pump(app, 0.1)
    assert seen == ["MainThread"], f"work ran on {seen}, not the UI thread"


# -- Latest --------------------------------------------------------------


def test_latest_presents_on_the_ui_thread(app):
    seen = []
    latest = Latest(lambda v: seen.append((v, threading.current_thread().name)))

    thread = threading.Thread(target=lambda: latest.offer("frame"))
    thread.start()
    thread.join()
    pump(app, 0.1)
    assert seen == [("frame", "MainThread")]


def test_latest_drops_everything_but_the_newest(app):
    """A stale frame is not worth drawing, it is worth skipping."""
    seen = []
    latest = Latest(lambda v: seen.append(v))
    for i in range(50):
        latest.offer(f"frame{i}")
    pump(app, 0.1)
    assert seen[-1] == "frame49"
    assert len(seen) < 50, "it queued rather than dropping"


def test_the_final_value_always_arrives(app):
    """**The bug this exists to avoid**, entered deliberately rather than hoped for.

    LunaP's three hand-written copies reset the scheduled flag AFTER presenting,
    so an offer arriving *during* a present could neither schedule (the flag
    still read set) nor be picked up (the flag then cleared with nothing
    queued). That value sat there until the next offer pushed it out. At 60fps
    nobody could see it; it shows when the stream STOPS, which is exactly when
    somebody is about to sit and look at the last value. LunaP §22.1.

    **The first version of this test hammered `offer` from a worker thread and
    could not fail.** Sabotaging the implementation — clearing the flag late,
    then also deleting the re-check, so it matched LunaP's broken copies exactly
    — left it green. The window is the microseconds inside `_present`, and a
    racing producer essentially never lands in it. docs/LunaPY.md §10.1.

    So the window is held open instead: `present` blocks until a worker has
    offered into it. That enters the race every run, and the test fails on
    either half of the fix being removed.
    """
    presenting = threading.Event()
    release = threading.Event()
    seen = []

    def present(value):
        seen.append(value)
        presenting.set()
        # Hold the drain open so the offer below lands mid-present, which is
        # the only moment the bug exists.
        release.wait(2.0)

    latest = Latest(present)

    def offer_during_the_present():
        assert presenting.wait(2.0), "the first value was never presented"
        latest.offer("FINAL")
        release.set()

    worker = threading.Thread(target=offer_during_the_present)
    worker.start()

    latest.offer("first")
    pump(app, 0.3)
    worker.join(2.0)
    pump(app, 0.3)

    assert seen[0] == "first"
    assert seen[-1] == "FINAL", (
        f"the value offered during the present was never shown (ended on {seen[-1]!r}). "
        "The scheduled flag is being cleared after the present rather than before it, "
        "and nothing re-checks afterwards."
    )


def test_offering_from_the_ui_thread_still_defers(app):
    """`offer` posts rather than presenting inline, so a producer that happens
    to be on the UI thread cannot re-enter its own present."""
    seen = []
    latest = Latest(lambda v: seen.append(v))
    latest.offer("a")
    assert seen == []
    pump(app, 0.05)
    assert seen == ["a"]
