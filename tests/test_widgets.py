"""The input widgets.

Nearly every test here is about one distinction: **a selection change the user
made, versus one the program caused by rebuilding the list.** A handler that
cannot tell them apart re-runs the user's last action every time the data
refreshes.
"""

import pytest

from lunapy.testing import assert_laid_out, show
from lunapy.widgets import ButtonBar, Dropdown, LunaList, LunaSwitch, StatusBar, Tabs
from lunapy.fluent import button


# -- LunaList ------------------------------------------------------------


def test_a_list_hands_back_the_model_not_an_index(app):
    """The whole point: no shadow array, no index arithmetic, nothing to parse
    back out of a label."""
    items = [{"id": 1, "name": "ada"}, {"id": 2, "name": "grace"}]
    listing = LunaList(label=lambda p: p["name"], key=lambda p: p["id"])
    listing.refresh(items)
    listing.setCurrentRow(1)
    assert listing.selected == {"id": 2, "name": "grace"}


def test_a_list_of_strings_needs_no_projection(app):
    listing = LunaList()
    listing.refresh(["a", "b"])
    listing.setCurrentRow(0)
    assert listing.selected == "a"


def test_refresh_keeps_the_selection(app):
    """"Rebuild the list" and "keep the selection" are one operation that only
    looks like two — three LunaP sites wrote the dance separately (§21.1)."""
    listing = LunaList(label=lambda p: p["name"], key=lambda p: p["id"])
    listing.refresh([{"id": 1, "name": "ada"}, {"id": 2, "name": "grace"}])
    listing.setCurrentRow(1)

    # Rebuilt from scratch: different objects, same keys.
    listing.refresh([{"id": 1, "name": "ada"}, {"id": 2, "name": "grace"}, {"id": 3, "name": "kay"}])
    assert listing.selected["id"] == 2


def test_a_vanished_selection_becomes_nothing(app):
    """-1 is a real answer: the row it named no longer exists, and selecting its
    neighbour would be a guess."""
    listing = LunaList(label=lambda p: p["name"], key=lambda p: p["id"])
    listing.refresh([{"id": 1, "name": "ada"}, {"id": 2, "name": "grace"}])
    listing.setCurrentRow(1)
    listing.refresh([{"id": 1, "name": "ada"}])
    assert listing.selected is None


def test_refresh_does_not_look_like_a_user_choice(app):
    chosen = []
    listing = LunaList()
    listing.chose.connect(lambda item: chosen.append(item))
    listing.refresh(["a", "b"])
    listing.setCurrentRow(0)
    assert chosen == ["a"]

    chosen.clear()
    listing.refresh(["a", "b", "c"])
    assert chosen == [], "a refresh fired chose, so the handler re-ran the user's last action"


def test_select_by_model_is_not_a_user_choice(app):
    """A caller setting the selection already knows what it set."""
    chosen = []
    listing = LunaList()
    listing.chose.connect(lambda item: chosen.append(item))
    listing.refresh(["a", "b"])
    listing.select("b")
    assert listing.selected == "b"
    assert chosen == []


def test_selecting_none_clears(app):
    listing = LunaList()
    listing.refresh(["a", "b"])
    listing.select("a")
    listing.select(None)
    assert listing.selected is None


def test_models_survives_a_refresh(app):
    listing = LunaList()
    listing.refresh(["a", "b"])
    assert listing.models == ["a", "b"]


# -- Dropdown ------------------------------------------------------------


def test_a_dropdown_hands_back_the_value_not_the_text(app):
    box = Dropdown()
    box.fill([1, 2, 3], 2, label=lambda v: f"Option {v}")
    assert box.selected == 2
    assert box.currentText() == "Option 2"


def test_filling_does_not_look_like_a_user_choice(app):
    chosen = []
    box = Dropdown()
    box.chose.connect(lambda v: chosen.append(v))
    box.fill(["a", "b"], "a")
    assert chosen == [], "fill() fired chose for the reset"

    box.setCurrentIndex(1)
    assert chosen == ["b"]


def test_filling_with_an_absent_selection_selects_nothing(app):
    box = Dropdown()
    box.fill(["a", "b"], "zzz")
    assert box.selected is None


def test_refilling_replaces_the_values(app):
    box = Dropdown()
    box.fill(["a", "b"], "a")
    box.fill(["x", "y"], "y")
    assert box.selected == "y"


# -- LunaSwitch ----------------------------------------------------------


def test_a_switch_carries_its_own_label(app):
    """Qt has no toggle switch and this does not pretend otherwise. LunaP's
    wrapped Avalonia's, put the label in OnContent/OffContent, left Content
    null, and every switch on a settings page announced as an unnamed button
    (§24.1). A QCheckBox reports itself correctly, so the class of problem does
    not arise."""
    switch = LunaSwitch("Overwrite existing fields")
    assert switch.text() == "Overwrite existing fields"

    from PySide6.QtGui import QAccessible

    interface = QAccessible.queryAccessibleInterface(switch)
    assert interface is not None
    assert interface.text(QAccessible.Text.Name) == "Overwrite existing fields"


def test_a_switch_toggles(app):
    switch = LunaSwitch("On?")
    assert not switch.isChecked()
    switch.setChecked(True)
    assert switch.isChecked()


# -- Tabs ----------------------------------------------------------------


def test_tabs_add_and_trim(app):
    tabs = Tabs()
    from PySide6.QtWidgets import QWidget

    tabs.add("One", QWidget())
    tabs.add("Two", QWidget())
    tabs.add("Three", QWidget())
    assert tabs.count() == 3

    tabs.remove_from(1)
    assert tabs.count() == 1
    assert tabs.tabText(0) == "One"


def test_trimming_past_the_end_is_not_an_error(app):
    tabs = Tabs()
    tabs.remove_from(5)
    assert tabs.count() == 0


# -- ButtonBar and StatusBar ---------------------------------------------


def test_a_button_bar_holds_its_buttons(app):
    bar = ButtonBar(button("Cancel"), button("Apply"))
    assert [b.text() for b in bar.buttons] == ["Cancel", "Apply"]


def test_a_button_bar_reports_as_a_toolbar_not_a_list(app):
    """A row of OK/Cancel announced as a list of two items invites a reader to
    navigate it as data rather than to press one of them. LunaP §24.2."""
    assert ButtonBar().accessibleName() == "Actions"


def test_a_status_bar_names_itself_from_its_message(app):
    """The message is what this control *is*, so it is the name rather than a
    description. There is nothing else it could be called."""
    bar = StatusBar("Ready.")
    assert bar.accessibleName() == "Ready."
    bar.set_status("Applied 12 fields.")
    assert bar.status == "Applied 12 fields."
    assert bar.accessibleName() == "Applied 12 fields."


def test_a_status_bar_is_live_by_default_and_can_be_told_not_to_be(app):
    """A status line updating twice a second is a live region that never shuts
    up, so it is a default rather than a rule."""
    bar = StatusBar("Ready.")
    assert bar.is_live
    bar.set_live(False)
    assert not bar.is_live
    bar.set_status("Still fine.")  # must not raise with announcing off
    assert bar.status == "Still fine."


def test_the_bars_render(app):
    assert_laid_out(show(StatusBar("Ready."), 320, 32), "status_bar")
