"""The fluent surface: does a layout expression produce the layout it reads as?

These assert structure and geometry rather than pixels. A widget in the wrong
box is a fact about the tree, and asserting it through a render would be
measuring the theme at the same time.
"""

import pytest

from PySide6.QtWidgets import QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from lunapy.fluent import (
    button,
    cols,
    dock,
    header,
    hint,
    mono,
    row,
    rows,
    scroll,
    section,
    stack,
    text,
    tune,
)
from lunapy import theme
from lunapy.testing import show


def test_stack_and_row_choose_their_orientation(app):
    assert isinstance(stack(text("a"), text("b")).layout(), QVBoxLayout)
    assert isinstance(row(text("a"), text("b")).layout(), QHBoxLayout)


def test_children_arrive_in_order(app):
    a, b, c = text("a"), text("b"), text("c")
    panel = stack(a, b, c)          # held: see test_an_unheld_container_takes_its_children_with_it
    layout = panel.layout()
    assert [layout.itemAt(i).widget() for i in range(layout.count())] == [a, b, c]


def test_an_unheld_container_takes_its_children_with_it(app):
    """The lifetime hazard every constructor in this module shares.

    A container built here is owned by the Python reference to it and nothing
    else — it has no Qt parent until somebody adds it to a layout. Drop that
    reference and CPython collects the host, whose C++ destructor takes every
    child with it, and the next touch of a child raises "Internal C++ object
    already deleted" from inside shiboken.

    Found by writing `stack(a, b, c).layout()` in a test and having the children
    vanish before the assertion. It is not fixable from inside the toolkit —
    it is what object ownership means in PySide — so it is pinned here instead,
    where it names itself. docs/LunaPY.md §3.3.
    """
    import gc

    child = text("a")
    stack(child)            # deliberately not held
    gc.collect()

    with pytest.raises(RuntimeError, match="already deleted"):
        child.text()


def test_spacing_and_margin_reach_the_layout(app):
    panel = stack(text("a"), text("b"), spacing=8, margin=4)
    assert panel.layout().spacing() == 8
    assert panel.layout().contentsMargins().left() == 4


def test_containers_nest_without_a_special_case(app):
    """The reason every constructor returns a widget rather than a layout."""
    panel = stack(row(text("a"), text("b")), row(text("c")))
    assert panel.layout().count() == 2
    assert isinstance(panel.layout().itemAt(0).widget().layout(), QHBoxLayout)


def test_the_text_styles_carry_their_style_key(app):
    assert header("H").property(theme.STYLE_KEY) == "section_header"
    assert hint("h").property(theme.STYLE_KEY) == "hint"
    assert mono("m").property(theme.STYLE_KEY) == "mono"
    assert text("t").property(theme.STYLE_KEY) is None


def test_section_takes_more_than_one_child(app):
    """LunaP's first version took exactly one, and LunaP §21.2 records the cost:
    eight places wrote a bold label by hand rather than use a helper that could
    not hold what they had."""
    panel = section("Audio", text("a"), text("b"), text("c"))
    assert panel.layout().count() == 4  # the header plus three
    assert panel.layout().itemAt(0).widget().property(theme.STYLE_KEY) == "section_header"


def test_button_calls_back_without_the_checked_flag(app):
    calls = []
    b = button("Prune", lambda: calls.append(1))
    b.click()
    assert calls == [1]


def test_button_without_a_handler_is_inert(app):
    button("Prune").click()  # must not raise


def test_tune_returns_the_widget_it_was_given(app):
    label = text("a")
    assert tune(label, width=80) is label
    assert label.width() == 80


def test_tune_rejects_an_unknown_keyword(app):
    """A silently dropped `witdh=80` is a layout that is subtly wrong and gives
    no reason, which costs far more to find than the typo cost to make."""
    with pytest.raises(TypeError, match="witdh"):
        tune(text("a"), witdh=80)


def test_tune_rejects_a_bad_alignment(app):
    with pytest.raises(ValueError, match="align"):
        tune(text("a"), align="sideways")


def test_tune_sets_accessibility_from_the_same_vocabulary(app):
    label = text("a", accessible_name="Volume", help_text="How loud")
    assert label.accessibleName() == "Volume"
    assert label.accessibleDescription() == "How loud"


def test_alignment_reaches_the_layout_item(app):
    from PySide6.QtCore import Qt

    child = text("a", align="right")
    panel = row(child)
    assert panel.layout().itemAt(0).alignment() & Qt.AlignmentFlag.AlignRight


def test_cols_assigns_one_child_per_track(app):
    a, b, c = text("a"), text("b"), text("c")
    panel = cols("Auto,*,120", a, b, c)
    grid = panel.layout()
    assert [grid.getItemPosition(i)[:2] for i in range(grid.count())] == [(0, 0), (0, 1), (0, 2)]


def test_rows_assigns_down_instead_of_across(app):
    a, b = text("a"), text("b")
    panel = rows("Auto,*", a, b)
    grid = panel.layout()
    assert [grid.getItemPosition(i)[:2] for i in range(grid.count())] == [(0, 0), (1, 0)]


def test_a_track_spec_maps_star_to_stretch_and_a_number_to_a_minimum(app):
    panel = cols("Auto,*,2*,120", text("a"), text("b"), text("c"), text("d"))
    grid = panel.layout()
    assert grid.columnStretch(0) == 0
    assert grid.columnStretch(1) == 1
    assert grid.columnStretch(2) == 2
    assert grid.columnStretch(3) == 0
    assert grid.columnMinimumWidth(3) == 120


def test_scroll_resizes_its_content(app):
    """Without `setWidgetResizable(True)` the content keeps its size hint
    forever, which is the most common Qt scroll-area bug and is invisible in the
    code that causes it."""
    area = scroll(stack(text("a")))
    assert isinstance(area, QScrollArea)
    assert area.widgetResizable()


def test_dock_puts_the_last_child_in_the_filling_position(app):
    """A docked strip keeps its own height; the filler takes what is left."""
    strip = tune(text("strip"), dock="top", height=20)
    filler = text("body")
    panel = show(dock(strip, filler), 200, 200)
    assert strip.height() == 20
    assert filler.height() > strip.height()


def test_dock_nests_so_a_second_top_sits_inside_the_first_side(app):
    """The case a flat implementation gets wrong.

    Docking top, then left, then filling should leave the left sidebar starting
    *below* the top strip, because the strip took its slice out of the whole
    width first. A flat implementation — one vertical box for top/bottom, one
    horizontal for left/right — puts the sidebar alongside the strip instead,
    and the difference only shows once both are present.
    """
    strip = tune(text("strip"), dock="top", height=20)
    side = tune(text("side"), dock="left", width=40)
    body = text("body")
    panel = show(dock(strip, side, body), 200, 200)  # held; see the lifetime test above

    strip_bottom = strip.mapToGlobal(strip.rect().bottomLeft()).y()
    side_top = side.mapToGlobal(side.rect().topLeft()).y()
    assert side_top >= strip_bottom, (
        "the sidebar starts above the top strip's bottom edge, so dock() flattened "
        "instead of nesting"
    )


def test_dock_of_nothing_is_a_widget_not_a_crash(app):
    assert isinstance(dock(), QWidget)
