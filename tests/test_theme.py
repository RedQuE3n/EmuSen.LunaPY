"""The theme: two mechanisms, a variant switch, and the repolish trap.

The trap test is the one that earns its keep. Everything else here would be
caught by looking at a window; a style key that silently fails to apply after
the widget is on screen looks exactly like a theme that does not have a rule for
it, which sends you to the wrong file.
"""

import pytest

from lunapy import Variant, theme
from lunapy.fluent import header, row, stack, text, tune
from lunapy.palette import DARK, LIGHT
from lunapy.testing import capture, show

from PySide6.QtWidgets import QLabel, QProgressBar


def glyph_colour(widget) -> tuple[int, int, int]:
    """The rendered pixel furthest from the background = the glyph core.

    Not the most common non-background pixel, which is what the first version of
    this helper measured and why it reported every style as identical: at these
    font sizes antialias edges outnumber glyph cores several times over, so
    "most common" finds the faintest edge shade of whatever the text is.
    """
    frame = capture(widget)
    background = frame.rgba[0:3]
    best, best_distance = background, -1
    for i in range(0, len(frame.rgba) - 3, 4):
        pixel = frame.rgba[i : i + 3]
        distance = sum((pixel[c] - background[c]) ** 2 for c in range(3))
        if distance > best_distance:
            best, best_distance = pixel, distance
    return tuple(best)


def test_the_stylesheet_carries_the_active_column(app):
    theme.apply(app, Variant.DARK)
    assert DARK["section_header"] in theme.qss(Variant.DARK)

    theme.apply(app, Variant.LIGHT)
    assert LIGHT["section_header"] in theme.qss(Variant.LIGHT)
    assert DARK["section_header"] not in theme.qss(Variant.LIGHT)


def test_the_palette_carries_the_surface(app):
    from PySide6.QtGui import QPalette

    dark = theme.qpalette(Variant.DARK)
    light = theme.qpalette(Variant.LIGHT)
    assert dark.color(QPalette.ColorRole.Window).name().upper() == DARK["surface"]
    assert light.color(QPalette.ColorRole.Window).name().upper() == LIGHT["surface"]


def test_variant_defaults_to_dark_and_follows_apply(app):
    """Dark is the default, and that is the absence of a behaviour change.

    If this ever needs changing, it is a major version — an application that
    looks different after a version bump its author took for something else is
    the exact failure LunaP §23.3 refused.
    """
    theme.apply(app, Variant.DARK)
    assert theme.variant() is Variant.DARK
    theme.apply(app, Variant.LIGHT)
    assert theme.variant() is Variant.LIGHT


def test_a_style_key_set_before_showing_applies(app):
    """The easy half: built with the key, so the first polish sees it."""
    theme.apply(app, Variant.DARK)
    plain = show(text("Audio"), 140, 30)
    styled = show(header("Audio"), 140, 30)
    assert glyph_colour(plain) != glyph_colour(styled)


def test_a_style_key_set_after_showing_needs_the_repolish(app):
    """The trap, pinned in both directions.

    Qt resolves stylesheet rules once at polish time and does not watch dynamic
    properties, so `setProperty` alone is silent after the widget is on screen.
    This test asserts the silence *and* asserts that `set_style_key` breaks it —
    if only the second half were here, a `set_style_key` that had lost its
    repolish would still pass on a widget that happened not to be shown yet.
    """
    theme.apply(app, Variant.DARK)
    plain = show(text("Audio"), 140, 30)
    before = glyph_colour(plain)

    # The naive way: silent.
    plain.setProperty(theme.STYLE_KEY, "section_header")
    assert glyph_colour(plain) == before, (
        "Qt applied a dynamic property change without a repolish. If this is now "
        "true, theme.set_style_key's reason for existing has changed — see "
        "docs/LunaPY.md §3.2."
    )

    # The supported way.
    theme.set_style_key(plain, "section_header")
    assert glyph_colour(plain) != before


def test_switching_the_theme_restyles_widgets_already_on_screen(app):
    """The half Qt does for free, and the reason `Restyle(root)` did not port.

    LunaP §12.3 found that mutating `Application.Styles` in Avalonia strips
    every already-realized control of its styling. Qt re-polishes on
    `setStyleSheet` by itself. Asserted rather than assumed, because the whole
    design of `theme.apply` rests on it.
    """
    theme.apply(app, Variant.DARK)
    label = show(header("Audio"), 140, 30)
    dark_glyph = glyph_colour(label)

    theme.apply(app, Variant.LIGHT)
    app.processEvents()
    assert glyph_colour(label) != dark_glyph


def test_set_load_picks_the_band_and_styles_the_meter(app):
    from lunapy.palette import LoadLevel

    meter = QProgressBar()
    meter.setValue(90)
    assert theme.set_load(meter, 90) is LoadLevel.HOT
    assert meter.property(theme.STYLE_KEY) == "hot"

    assert theme.set_load(meter, 10) is LoadLevel.NOMINAL
    assert meter.property(theme.STYLE_KEY) == "nominal"


def test_restyle_recursive_reaches_children(app):
    theme.apply(app, Variant.DARK)
    child = text("Audio")
    parent = show(stack(child), 140, 40)
    # Nothing to assert about colour here — the point is that it does not throw
    # on a real tree, since the recursive walk is the path with a cost and so
    # the path least likely to be exercised by accident.
    theme.restyle(parent, recursive=True)
    assert child.isVisible()
