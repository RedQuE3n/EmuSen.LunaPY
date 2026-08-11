"""Placement: the saved rectangle, and the rule that decides whether to trust it.

No Qt in this file either. The screen rule is the one piece of window
restoration that can strand a window somewhere the user cannot reach, so it is
arithmetic over tuples and it is tested without a display.
"""

import pytest

from lunapy import placement, settings
from lunapy.placement import WindowPlacement, is_on_a_screen
from lunapy.settings import SqliteSettingsStore


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    settings.set_store(SqliteSettingsStore(tmp_path / "settings.db"))
    yield
    settings.set_store(None)


# -- The screen rule -----------------------------------------------------

ONE_SCREEN = [(0, 0, 1920, 1080)]
TWO_SCREENS = [(0, 0, 1920, 1080), (1920, 0, 1920, 1080)]


@pytest.mark.parametrize(
    "screens, bounds, expected, why",
    [
        (ONE_SCREEN, (100, 100, 800, 600), True, "well inside"),
        (ONE_SCREEN, (0, 0, 1920, 1080), True, "exactly the screen"),
        (TWO_SCREENS, (2000, 100, 800, 600), True, "on the second monitor"),
        (ONE_SCREEN, (2000, 100, 800, 600), False, "on a monitor that is gone"),
        (ONE_SCREEN, (-900, 100, 800, 600), False, "off the left edge entirely"),
        (ONE_SCREEN, (0, -700, 800, 600), False, "above the top edge entirely"),
        # Intersection, not containment: a window half off the right edge still
        # has a titlebar somebody can grab, and requiring containment would
        # reject placements people chose deliberately.
        (ONE_SCREEN, (1700, 100, 800, 600), True, "half off the right edge"),
        (ONE_SCREEN, (-400, 100, 800, 600), True, "half off the left edge"),
        # Nothing to check against is not the same as "off screen".
        ([], (5000, 5000, 800, 600), True, "no screens enumerated"),
    ],
)
def test_the_screen_rule(screens, bounds, expected, why):
    assert is_on_a_screen(screens, bounds) is expected, why


def test_an_edge_touch_does_not_count_as_on_screen():
    """A window whose right edge exactly meets the screen's left edge shares no
    pixel with it. Pinned because a `<=` here would silently accept a window
    one pixel from being invisible."""
    assert is_on_a_screen([(0, 0, 100, 100)], (100, 0, 50, 50)) is False
    assert is_on_a_screen([(0, 0, 100, 100)], (99, 0, 50, 50)) is True


# -- The saved record ----------------------------------------------------


def test_a_placement_round_trips():
    saved = WindowPlacement(10, 20, 300, 400, maximized=True)
    assert placement.save("editor", saved)
    assert placement.load("editor") == saved


def test_two_windows_share_one_file():
    placement.save("editor", WindowPlacement(0, 0, 100, 100))
    placement.save("settings", WindowPlacement(5, 5, 200, 200))
    assert placement.load("editor").width == 100
    assert placement.load("settings").width == 200


def test_an_unknown_key_is_none():
    assert placement.load("never_saved") is None


def test_forget_removes_one_without_disturbing_the_others():
    placement.save("editor", WindowPlacement(0, 0, 100, 100))
    placement.save("settings", WindowPlacement(5, 5, 200, 200))
    assert placement.forget("editor")
    assert placement.load("editor") is None
    assert placement.load("settings") is not None


def test_forgetting_something_unknown_is_not_a_failure():
    assert placement.forget("never_saved")


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "not a dict",
        {},
        {"x": 1, "y": 2, "width": 3},                    # missing height
        {"x": "left", "y": 2, "width": 3, "height": 4},  # not a number
        [1, 2, 3, 4],
    ],
)
def test_a_malformed_entry_is_none_rather_than_a_crash(raw):
    """Hand-editing windows.json is a thing people do, and so is a half-written
    file from an older version. Trusting the fields turns one bad setting into
    a TypeError during window construction, which reads as the application
    being broken."""
    assert WindowPlacement.from_dict(raw) is None


def test_maximized_defaults_to_false_when_absent():
    """An older file that predates the flag must still restore its geometry."""
    parsed = WindowPlacement.from_dict({"x": 1, "y": 2, "width": 3, "height": 4})
    assert parsed == WindowPlacement(1, 2, 3, 4, maximized=False)


def test_a_stored_record_of_the_wrong_shape_loses_placement_not_the_program(tmp_path):
    """The store hands back whatever was written. A record from an older
    version, or one somebody edited, must cost the window its position and
    nothing else."""
    settings.store().save(placement.CATEGORY, "editor", {"nonsense": True})
    assert placement.load("editor") is None


def test_remembered_lists_the_saved_keys():
    placement.save("editor", WindowPlacement(0, 0, 100, 100))
    placement.save("settings", WindowPlacement(5, 5, 200, 200))
    assert placement.remembered() == ["editor", "settings"]


def test_each_window_is_its_own_record():
    """Not one document holding every window, which is how this started and how
    LunaP still does it. As rows, two windows closing in the same instant each
    write only themselves — see docs/LunaPY.md §7.2."""
    placement.save("editor", WindowPlacement(0, 0, 100, 100))
    assert settings.store().keys(placement.CATEGORY) == ["editor"]
