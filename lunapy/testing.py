"""The harness: bootstrap a headless application, capture a widget, assert it
actually rendered.

**This module raises `AssertionError` and imports no test framework**, which is
what lets it live in the package instead of beside it. LunaP had to ship
`EmuSen.LunaP.Testing` as a second NuGet package, because its assertions came
from xunit and taking that dependency in the toolkit itself would have broken
the rule the toolkit is built on. Python's `assert` is a keyword and
`AssertionError` is a builtin, so the same harness costs no dependency at all
and the layering rule holds with one package. `test_layering.py` is what keeps
that true.

The assertion that earns its keep is `assert_laid_out`. A window that failed to
lay out, or whose widgets never got their stylesheet, renders as one flat
colour — and counting distinct colours catches that where walking the widget
tree does not, because the tree of a window that rendered nothing looks exactly
like the tree of one that rendered correctly.
"""

from __future__ import annotations

import hashlib
import os
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Set before any QApplication is constructed, which is the only moment it is
# read. Importing this module does not create one, so an application that wants
# a real window (to look at a failing test by hand) can set the variable to
# something else first and this will leave its choice alone.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtGui import QImage  # noqa: E402  — must follow the line above
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402

from . import theme  # noqa: E402
from .palette import Variant  # noqa: E402

DUMP_VARIABLE = "LUNAPY_UI_DUMP"
BASELINE_VARIABLE = "LUNAPY_UI_BASELINE"
BASELINE_MODE_VARIABLE = "LUNAPY_UI_BASELINE_MODE"


@dataclass(frozen=True)
class RenderedFrame:
    """A captured widget, as plain RGBA8888.

    RGBA8888 and not ARGB32, which is the format most Qt examples reach for.
    `Format_ARGB32` stores a 32-bit integer, so on a little-endian machine
    `bits()` hands back **B, G, R, A** — and code that reads it as RGB gets
    colours that are correct on exactly one architecture. `Format_RGBA8888` is
    defined by its byte order rather than its word value, so the bytes below
    mean what they say everywhere.
    """

    rgba: bytes
    width: int
    height: int

    @property
    def digest(self) -> str:
        """A short content hash. Only ever asked whether two frames differ.

        LunaP hand-rolls FNV-1a here because C# has no cheap stdlib hash for a
        byte array. Python does, and it runs in C rather than in a per-byte
        interpreter loop — a 1200x800 frame is 3.8MB, which is a fraction of a
        millisecond through blake2b and roughly a second through a Python loop.
        The property being hashed is "these bytes are the same bytes", so any
        digest does; the fast one is simply free.
        """
        return hashlib.blake2b(self.rgba, digest_size=16).hexdigest()

    def distinct_colours(self, stop_at: int | None = None) -> int:
        """How many distinct RGB values are in the frame, alpha ignored.

        `stop_at` stops counting once the caller has seen enough. That is not a
        micro-optimisation: the flat-image check only ever asks "are there more
        than eight", and without the early exit every call walks every pixel of
        a full-size window in Python. With it, a healthy window answers after a
        few hundred pixels.
        """
        seen: set[bytes] = set()
        for i in range(0, len(self.rgba) - 3, 4):
            seen.add(self.rgba[i : i + 3])
            if stop_at is not None and len(seen) >= stop_at:
                break
        return len(seen)


def ui_app(variant: Variant = Variant.DARK) -> QApplication:
    """The one application a test run shares, themed and ready.

    Qt permits exactly one `QApplication` per process and returns None from
    `instance()` until it exists, so this is the accessor as well as the
    constructor. Tests must not build their own — a second one aborts the
    process rather than raising, which presents as a test run that simply stops
    with no failure reported.
    """
    app = QApplication.instance() or QApplication([])
    theme.apply(app, variant)
    return app


def show(widget: QWidget, width: int | None = None, height: int | None = None) -> QWidget:
    """Show a widget and let Qt lay it out, so it can be captured.

    Both halves matter. Without `show`, the widget has no style and no geometry;
    without draining the event loop, `show` has been *requested* and not yet
    done, and the capture races it.
    """
    if width and height:
        widget.resize(width, height)
    widget.show()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()
    return widget


def capture(widget: QWidget) -> RenderedFrame:
    """Render a shown widget offscreen into a frame."""
    if not widget.isVisible():
        raise RuntimeError(
            f"{type(widget).__name__} was never shown, so there is nothing to capture. "
            "Call lunapy.testing.show(widget) first."
        )

    size = widget.size()
    if size.width() <= 0 or size.height() <= 0:
        raise RuntimeError(
            f"{type(widget).__name__} laid out to {size.width()}x{size.height()}. "
            "An empty widget captures an empty frame, which would pass a colour count "
            "by having no pixels to disagree about."
        )

    image = QImage(size, QImage.Format.Format_RGBA8888)
    # A QImage is allocated uninitialized, and skipping this fill does not give
    # you a blank frame — it gives you whatever was in that memory.
    #
    # It only bites for a widget that paints nothing, which is why it is easy to
    # miss. Most widgets paint their own background: `render` includes
    # DrawWindowBackground by default and the palette supplies the Window role,
    # so the buffer ends up fully covered either way. Set WA_NoSystemBackground
    # and nothing is drawn at all — measured on a 200x100 widget, the capture
    # came back with **40 distinct colours** of stale heap. `assert_laid_out`
    # defaults to a floor of 8, so a widget that rendered absolutely nothing
    # would have sailed past the one assertion that exists to catch exactly that.
    #
    # `test_the_flat_guard_catches_a_widget_that_paints_nothing` is the guard.
    # The first version of it used a stylesheet background, which paints, so
    # deleting this line left the whole suite green. docs/LunaPY.md §4.1.
    image.fill(0)
    widget.render(image)
    return RenderedFrame(bytes(image.constBits()), image.width(), image.height())


def dump(name: str, frame: RenderedFrame) -> None:
    """Write a capture out as a PNG, if LUNAPY_UI_DUMP names a directory.

    Qt's own encoder, so the harness needs no imaging dependency of its own.
    """
    directory = os.environ.get(DUMP_VARIABLE)
    if not directory:
        return
    Path(directory).mkdir(parents=True, exist_ok=True)
    image = QImage(frame.rgba, frame.width, frame.height, QImage.Format.Format_RGBA8888)
    image.save(str(Path(directory) / f"{name}.png"))


def assert_laid_out(widget: QWidget, name: str, min_colours: int = 8) -> RenderedFrame:
    """The always-on assertion. A window that did not lay out is one flat colour.

    `min_colours` is 8 rather than 2 because antialiased text on a single
    background already produces a handful of edge shades. A window that has
    genuinely rendered nothing but its own background still clears 2 or 3, so a
    floor that low passes the exact failure this is here to catch.
    """
    frame = capture(widget)
    dump(name, frame)

    distinct = frame.distinct_colours(stop_at=min_colours + 1)
    if distinct <= min_colours:
        raise AssertionError(
            f"{name} rendered {distinct} distinct colours in "
            f"{frame.width}x{frame.height} — layout or theming probably failed. "
            f"Set {DUMP_VARIABLE} to a directory and look at it."
        )

    assert_matches_baseline(name, frame)
    return frame


def assert_stable(name: str, build: Callable[[], QWidget]) -> None:
    """Build and render twice; fail if the two differ.

    A widget that fails this shows something live — a clock, a pid, a counter —
    and can never be compared against a baseline. Finding that out here, with a
    message that says why, is much cheaper than finding it out as a baseline
    that fails once a day for reasons nobody can reproduce.
    """
    first = capture(show(build()))
    second = capture(show(build()))
    if first.digest != second.digest:
        raise AssertionError(
            f"{name} rendered differently on two identical builds, so it shows something "
            "live (a clock, a pid, a counter). It is not a valid baseline target."
        )


def assert_matches_baseline(name: str, frame: RenderedFrame) -> None:
    """Pixel-exact comparison, off unless LUNAPY_UI_BASELINE names a directory.

    Opt-in because a baseline is an artefact of one machine's font rendering and
    one Qt build. Committing one makes every other machine's suite red for a
    reason that has nothing to do with the change in front of it. It is a tool
    for bisecting a visual regression on the machine that has it, not a gate.
    """
    directory = os.environ.get(BASELINE_VARIABLE)
    if not directory:
        return

    path = Path(directory) / f"{name}.frame"
    mode = os.environ.get(BASELINE_MODE_VARIABLE, "compare").lower()

    if mode == "write":
        path.parent.mkdir(parents=True, exist_ok=True)
        # Dimensions then pixels, one file, so a half-written pair can never be
        # mistaken for a match.
        path.write_bytes(struct.pack("<II", frame.width, frame.height) + frame.rgba)
        return

    if not path.exists():
        raise AssertionError(
            f"No baseline for {name} at {path}. "
            f"Run once with {BASELINE_MODE_VARIABLE}=write first."
        )

    raw = path.read_bytes()
    width, height = struct.unpack("<II", raw[:8])
    baseline = RenderedFrame(raw[8:], width, height)

    if (baseline.width, baseline.height) != (frame.width, frame.height):
        raise AssertionError(
            f"{name} changed size: baseline {baseline.width}x{baseline.height}, "
            f"now {frame.width}x{frame.height}."
        )

    if baseline.digest != frame.digest:
        differing = sum(
            1
            for i in range(0, min(len(baseline.rgba), len(frame.rgba)) - 3, 4)
            if baseline.rgba[i : i + 3] != frame.rgba[i : i + 3]
        )
        raise AssertionError(f"{name} rendered {differing} pixels differently from its baseline.")
