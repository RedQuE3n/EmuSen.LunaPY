"""The control kit: what each one shows, and what it reports itself as.

Accessibility is asserted here rather than left to a later pass, because LunaP
§24 is the record of what "we will do that later" produced: nine controls not in
the automation tree at all.
"""

import pytest

from PySide6.QtGui import QAccessible
from PySide6.QtWidgets import QLineEdit

from lunapy.controls import EmptyState, FieldRow, MeterEntry, MeterList, MeterRow, RgbaImageView
from lunapy.palette import LoadLevel
from lunapy.testing import assert_laid_out, capture, show
from lunapy.theme import STYLE_KEY


def accessible(widget):
    return QAccessible.queryAccessibleInterface(widget)


# -- MeterRow ------------------------------------------------------------


@pytest.mark.parametrize(
    "percent, expected",
    [(0, LoadLevel.NOMINAL), (59, LoadLevel.NOMINAL), (60, LoadLevel.BUSY),
     (84, LoadLevel.BUSY), (85, LoadLevel.HOT), (100, LoadLevel.HOT)],
)
def test_a_meter_colours_itself_by_band(app, percent, expected):
    meter = MeterRow("Core", percent, f"{percent}%")
    assert meter.set_percent(percent) is expected
    assert meter._bar.property(STYLE_KEY) == expected.value


def test_a_meter_clamps_rather_than_raising(app):
    """A source reporting 130% is reporting something real about itself; the bar
    has nowhere to draw it, and refusing to draw anything would be worse."""
    meter = MeterRow("Core", 130, "130%")
    assert meter._bar.value() == 100
    meter.set_percent(-20)
    assert meter._bar.value() == 0


def test_a_meter_names_itself_from_its_label(app):
    meter = MeterRow("Core load", 50, "50%")
    assert meter.accessibleName() == "Core load"


def test_the_value_text_is_a_description_not_a_range(app):
    """`percent` drives the bar's length and `value_text` is shown verbatim, and
    they need not agree: a row showing 13 of 128 slots sets percent to 10. A
    reader announcing "10 percent" over "13/128" would be saying a number the
    caller never asked for."""
    meter = MeterRow("Slots", 10, "13/128")
    assert meter.accessibleName() == "Slots"
    assert meter.accessibleDescription() == "13/128"


def test_a_meter_renders(app):
    assert_laid_out(show(MeterRow("Core", 70, "70%"), 320, 32), "meter_row")


# -- MeterList -----------------------------------------------------------


def test_a_meter_list_builds_a_row_each(app):
    meters = MeterList([MeterEntry("A", 10, "10%"), MeterEntry("B", 90, "90%")])
    assert len(meters.rows) == 2
    assert meters.rows[1].level is LoadLevel.HOT


def test_a_meter_list_rebuilds_wholesale(app):
    meters = MeterList([MeterEntry("A", 10, "10%")])
    meters.set_meters([MeterEntry("B", 20, "20%"), MeterEntry("C", 30, "30%")])
    assert [r._label.text() for r in meters.rows] == ["B", "C"]


def test_an_empty_meter_list_is_not_a_crash(app):
    assert MeterList([]).rows == []


def test_a_meter_list_is_unnamed_by_default(app):
    """What a run of meters is *about* is the caller's vocabulary. A toolkit
    supplying group headings would be guessing at domain language."""
    assert MeterList([MeterEntry("A", 1, "")]).accessibleName() == ""


# -- EmptyState ----------------------------------------------------------


def test_an_empty_state_hides_an_absent_detail(app):
    """So a bare "No results" leaves no gap where a second line would be."""
    assert not EmptyState("No results").has_detail
    assert EmptyState("No results", "Try a shorter search.").has_detail


def test_whitespace_is_not_a_detail(app):
    assert not EmptyState("No results", "   ").has_detail


def test_an_empty_state_is_readable(app):
    """The sharpest case in LunaP's accessibility pass: the one control whose
    whole job is explaining why a window is empty was the one thing a screen
    reader could not see (§24.1). A sighted user got the message; a reader got
    silence and an apparently empty window."""
    state = EmptyState("No cores loaded", "Open a ROM to begin.")
    assert state.accessibleName() == "No cores loaded"
    assert state.accessibleDescription() == "Open a ROM to begin."

    interface = accessible(state)
    assert interface is not None
    assert interface.text(QAccessible.Text.Name) == "No cores loaded"


def test_an_empty_state_renders(app):
    assert_laid_out(show(EmptyState("Nothing here", "And here is why."), 320, 120), "empty_state")


# -- FieldRow ------------------------------------------------------------


def test_a_field_lends_its_label_to_its_content(app):
    """The field's label is a sibling of the thing it labels, which is the
    problem. LunaP measured five text boxes in a settings window each announcing
    as an unnamed edit field (§24.1)."""
    box = QLineEdit()
    field = FieldRow("Save folder", box)
    assert field._label.buddy() is box


def test_a_field_does_not_overwrite_a_name_the_caller_set(app):
    """`setBuddy` rather than writing the name on, because a caller who has
    already named their widget keeps it. Setting the name directly would
    silently win that argument."""
    box = QLineEdit()
    box.setAccessibleName("Mine")
    field = FieldRow("Save folder", box)   # held; an unheld container frees its children
    assert box.accessibleName() == "Mine"


def test_a_field_hint_collapses_when_empty(app):
    assert not FieldRow("Name", QLineEdit()).has_hint
    assert FieldRow("Name", QLineEdit(), field_hint="Shown in the title bar.").has_hint


def test_a_field_renders(app):
    field = FieldRow("Profile", QLineEdit("default"), field_hint="Shown in the title bar.")
    assert_laid_out(show(field, 360, 60), "field_row")


# -- RgbaImageView -------------------------------------------------------


def test_an_image_view_shows_a_buffer(app):
    view = RgbaImageView()
    assert view.set_frame(bytes([255, 128, 0, 255] * (4 * 4)), 4, 4)
    assert view.frame_size == (4, 4)


@pytest.mark.parametrize(
    "rgba, width, height, why",
    [
        (b"", 0, 0, "a source with nothing to show"),
        (b"", 4, 4, "no data at all"),
        (bytes(4 * 4), 4, 4, "a buffer too short for its dimensions"),
        (bytes([0] * 64), -1, 4, "a negative dimension"),
    ],
)
def test_a_bad_buffer_clears_rather_than_raising(app, rgba, width, height, why):
    """A source with nothing to show reports exactly that, and it is not an
    error for it to say so."""
    view = RgbaImageView()
    view.set_frame(bytes([255] * 64), 4, 4)
    assert view.set_frame(rgba, width, height) is False, why
    assert view.frame_size == (0, 0)


def test_the_pixels_survive_the_buffer_they_came_from(app):
    """QImage over a buffer does not copy, so a frame built from a temporary
    would show freed memory. `copy()` is what makes the pixels ours."""
    view = RgbaImageView()
    view.set_frame(bytes([255, 0, 0, 255] * 16), 4, 4)
    show(view, 40, 40)
    first = capture(view).digest
    # The original bytes are long gone; the view must still render the same.
    assert capture(view).digest == first


def test_an_image_view_is_unnamed_on_purpose(app):
    """A toolkit-supplied name would be a guess presented as a description. A
    wrong alt text is believed; a missing one is asked about."""
    assert RgbaImageView().accessibleName() == ""
