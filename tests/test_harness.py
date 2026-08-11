"""The harness testing itself.

Every guard here is made to fail on purpose before it is trusted. A harness is
the one place where a test that cannot fail does the most damage: it does not
merely miss its own bug, it certifies every other test in the suite.
"""

import os

import pytest

from PySide6.QtWidgets import QWidget

from lunapy import Variant, theme
from lunapy.fluent import button, header, hint, row, stack, text
from lunapy.testing import (
    DUMP_VARIABLE,
    RenderedFrame,
    assert_laid_out,
    assert_stable,
    capture,
    dump,
    show,
)


def a_real_window():
    return stack(
        header("Audio"),
        row(text("Volume"), text("60%"), spacing=6),
        hint("Applies to every profile"),
        button("Prune"),
        spacing=8,
        margin=8,
    )


def test_a_real_window_lays_out(app):
    frame = assert_laid_out(show(a_real_window(), 320, 160), "real_window")
    assert frame.width == 320 and frame.height == 160


def test_the_flat_guard_fails_on_a_flat_widget(app):
    """The sabotage that matters most.

    A window that failed to lay out, or whose widgets never got their
    stylesheet, renders as one flat colour. If this assertion ever stops firing,
    every `assert_laid_out` in every consumer becomes decoration.
    """
    flat = QWidget()
    flat.setStyleSheet("background: #1E1E1E;")
    show(flat, 120, 60)

    with pytest.raises(AssertionError, match="distinct colours"):
        assert_laid_out(flat, "flat")


def test_the_flat_guard_catches_a_widget_that_paints_nothing(app):
    """The case the flat guard above does *not* cover, and the one that pins
    `image.fill(0)` in `capture`.

    A widget with WA_NoSystemBackground draws no background at all, so the
    capture buffer keeps whatever it was allocated with. Measured without the
    fill: 40 distinct colours of stale heap on a 200x100 widget — comfortably
    past the floor of 8, so the assertion that exists to catch a window which
    rendered nothing would have certified it instead.

    The flat test above uses a stylesheet background, which *does* paint, which
    is why removing the fill left it green. Two tests because they are two
    failures: one for a widget that painted one colour, one for a widget that
    painted none.
    """
    from PySide6.QtCore import Qt

    unpainted = QWidget()
    unpainted.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
    show(unpainted, 200, 100)

    # Deterministically zeroed, not whatever was in that memory.
    frame = capture(unpainted)
    assert frame.distinct_colours() == 1, (
        f"an unpainted widget captured {frame.distinct_colours()} colours; the capture "
        "buffer is not being zeroed, so assert_laid_out can pass on noise"
    )

    with pytest.raises(AssertionError, match="distinct colours"):
        assert_laid_out(unpainted, "unpainted")


def test_capture_refuses_a_widget_that_was_never_shown(app):
    """An unshown widget has no style and no geometry, so its capture is a
    frame about nothing. Rendering it anyway would produce a plausible-looking
    image that means nothing."""
    with pytest.raises(RuntimeError, match="never shown"):
        capture(a_real_window())


def test_capture_refuses_a_widget_that_laid_out_to_nothing(app):
    """An empty frame passes a colour count by having no pixels to disagree
    about, which is the flat-widget failure wearing a different hat."""
    empty = QWidget()
    empty.resize(0, 0)
    empty.show()
    app.processEvents()
    with pytest.raises(RuntimeError, match="captures an empty frame"):
        capture(empty)


def test_the_frame_is_rgba_not_bgra(app):
    """Format_ARGB32 hands back B,G,R,A on a little-endian machine, so a frame
    read as RGB is wrong on exactly one architecture and right on the other.
    Pinned with a colour whose channels are all different."""
    swatch = QWidget()
    swatch.setStyleSheet("background: #FF8000;")
    show(swatch, 20, 20)
    frame = capture(swatch)
    assert frame.rgba[0:3] == bytes((0xFF, 0x80, 0x00))


def test_distinct_colours_stops_early_when_asked(app):
    """The early exit is not a micro-optimisation: without it every flat check
    walks every pixel of a full-size window in Python."""
    frame = capture(show(a_real_window(), 320, 160))
    assert frame.distinct_colours(stop_at=3) == 3
    assert frame.distinct_colours() > 3


def test_two_identical_builds_are_stable(app):
    assert_stable("real_window", lambda: show(a_real_window(), 320, 160))


def test_assert_stable_catches_something_live(app):
    """A widget showing a counter can never be a baseline target, and finding
    that out here beats finding it out as a baseline that fails once a day."""
    counter = iter(range(1000))

    def build():
        return show(stack(text(f"tick {next(counter)}"), margin=8), 200, 60)

    with pytest.raises(AssertionError, match="something live"):
        assert_stable("live", build)


def test_the_digest_distinguishes_frames(app):
    one = capture(show(a_real_window(), 320, 160))
    two = capture(show(stack(header("Different"), margin=8), 320, 160))
    assert one.digest != two.digest
    assert one.digest == RenderedFrame(one.rgba, one.width, one.height).digest


def test_dump_writes_a_png_when_asked(app, tmp_path, monkeypatch):
    monkeypatch.setenv(DUMP_VARIABLE, str(tmp_path))
    frame = capture(show(a_real_window(), 320, 160))
    dump("dumped", frame)
    written = tmp_path / "dumped.png"
    assert written.exists() and written.stat().st_size > 0


def test_dump_is_silent_when_not_asked(app, tmp_path, monkeypatch):
    monkeypatch.delenv(DUMP_VARIABLE, raising=False)
    dump("not_dumped", capture(show(a_real_window(), 320, 160)))
    assert not (tmp_path / "not_dumped.png").exists()


def test_a_baseline_round_trips(app, tmp_path, monkeypatch):
    """Write once, then compare — the two halves of the opt-in baseline path."""
    monkeypatch.setenv("LUNAPY_UI_BASELINE", str(tmp_path))
    monkeypatch.setenv("LUNAPY_UI_BASELINE_MODE", "write")
    assert_laid_out(show(a_real_window(), 320, 160), "baselined")

    monkeypatch.setenv("LUNAPY_UI_BASELINE_MODE", "compare")
    assert_laid_out(show(a_real_window(), 320, 160), "baselined")


def test_a_baseline_notices_a_size_change(app, tmp_path, monkeypatch):
    monkeypatch.setenv("LUNAPY_UI_BASELINE", str(tmp_path))
    monkeypatch.setenv("LUNAPY_UI_BASELINE_MODE", "write")
    assert_laid_out(show(a_real_window(), 320, 160), "sized")

    monkeypatch.setenv("LUNAPY_UI_BASELINE_MODE", "compare")
    with pytest.raises(AssertionError, match="changed size"):
        assert_laid_out(show(a_real_window(), 300, 160), "sized")


def test_a_missing_baseline_says_how_to_make_one(app, tmp_path, monkeypatch):
    monkeypatch.setenv("LUNAPY_UI_BASELINE", str(tmp_path))
    monkeypatch.setenv("LUNAPY_UI_BASELINE_MODE", "compare")
    with pytest.raises(AssertionError, match="write"):
        assert_laid_out(show(a_real_window(), 320, 160), "never_written")


def test_baselines_are_off_unless_the_variable_is_set(app, monkeypatch):
    """Opt-in, because a baseline is an artefact of one machine's font
    rendering. Committing one makes every other machine's suite red for a reason
    that has nothing to do with the change in front of it."""
    monkeypatch.delenv("LUNAPY_UI_BASELINE", raising=False)
    assert_laid_out(show(a_real_window(), 320, 160), "unbaselined")
