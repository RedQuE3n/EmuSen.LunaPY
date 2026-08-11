"""FilterBar, PathPickerRow, ConsolePane."""

import time

import pytest

from lunapy.panes import ConsolePane, FilterBar, PathPickerRow
from lunapy.testing import assert_laid_out, show


def pump(app, seconds=0.05):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        app.processEvents()


# -- FilterBar -----------------------------------------------------------


def test_a_filter_with_no_delay_fires_on_every_keystroke(app):
    """Zero is a real state, not a zero-length timer. A timer with a zero
    interval still defers to the next event-loop pass, which would turn a
    documented "synchronous" into "one frame later" for every existing caller."""
    changes = []
    bar = FilterBar(search_delay_ms=0)
    bar.changed.connect(lambda: changes.append(bar.search_text))

    bar._search.setText("a")
    bar._search.setText("ab")
    assert changes == ["a", "ab"]


def test_a_filter_with_a_delay_waits(app):
    """Neither behaviour is wrong at ten entries and both are wrong at ten
    thousand — LunaP §21.1 found two consumers re-reading storage on every
    keystroke."""
    changes = []
    bar = FilterBar(search_delay_ms=40)
    bar.changed.connect(lambda: changes.append(bar.search_text))

    bar._search.setText("a")
    bar._search.setText("ab")
    bar._search.setText("abc")
    assert changes == [], "it fired while keystrokes were still arriving"
    assert bar.is_pending

    pump(app, 0.12)
    assert changes == ["abc"], "one notification, carrying the final text"


def test_the_text_is_current_even_while_a_notification_waits(app):
    """`search_text` updates on every keystroke regardless; only the
    notification waits. A caller reading it for some other reason always sees
    what is actually in the box."""
    bar = FilterBar(search_delay_ms=500)
    bar._search.setText("abc")
    assert bar.search_text == "abc"


def test_enter_flushes_rather_than_waiting(app):
    changes = []
    submits = []
    bar = FilterBar(search_delay_ms=500)
    bar.changed.connect(lambda: changes.append(bar.search_text))
    bar.submitted.connect(lambda: submits.append(1))

    bar._search.setText("abc")
    bar._search.returnPressed.emit()
    assert changes == ["abc"], "Enter did not flush the pending notification"
    assert submits == [1]


def test_setting_the_text_without_notifying(app):
    """For a filter cleared by a Reset button, where re-running the search is
    the caller's decision rather than this control's."""
    changes = []
    bar = FilterBar(search_delay_ms=0)
    bar.changed.connect(lambda: changes.append(1))

    bar.set_search_text("typed")
    assert changes == [1]

    bar.set_search_text("", notify=False)
    assert changes == [1], "a silent set still notified"
    assert bar.search_text == ""


def test_the_facet_is_hidden_unless_asked_for(app):
    assert not FilterBar()._facet.isVisible()


def test_choosing_a_facet_is_a_change(app):
    changes = []
    bar = FilterBar(facet_label="Console:")
    bar.changed.connect(lambda: changes.append(1))
    bar.facet.fill(["All", "NES"], "All")
    assert changes == [], "filling the facet fired a change"
    bar.facet.setCurrentIndex(1)
    assert changes == [1]


def test_a_filter_renders(app):
    assert_laid_out(show(FilterBar("Search fields…"), 320, 40), "filter_bar")


# -- PathPickerRow -------------------------------------------------------


def test_a_path_row_reports_what_is_typed(app):
    changes = []
    picker = PathPickerRow("Save folder", "/tmp")
    picker.changed.connect(changes.append)
    assert picker.path == "/tmp"

    picker.set_path("/var")
    assert picker.path == "/var"
    assert changes == ["/var"]


def test_the_box_stays_editable(app):
    """A picker that only accepts what the dialog returns is a picker you cannot
    paste a path into, and pasting is how anybody with the path in their
    clipboard expects to use it."""
    picker = PathPickerRow("Save folder")
    assert not picker._edit.isReadOnly()


def test_a_path_row_lends_its_label(app):
    picker = PathPickerRow("Save folder")
    assert picker._label.buddy() is picker._edit
    assert picker._edit.accessibleName() == "Save folder"


def test_a_cancelled_dialog_does_not_clear_the_path(app, monkeypatch):
    """An empty return means cancelled, which must not wipe a path the user had
    already typed."""
    from PySide6.QtWidgets import QFileDialog

    picker = PathPickerRow("Save folder", "/home/me/work")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: ""))
    picker._on_browse()
    assert picker.path == "/home/me/work"


def test_a_chosen_directory_is_taken(app, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    picker = PathPickerRow("Save folder", "/home/me/work")
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: "/chosen"))
    picker._on_browse()
    assert picker.path == "/chosen"


# -- ConsolePane ---------------------------------------------------------


def test_a_console_echoes_the_command_and_the_response(app):
    console = ConsolePane(handler=lambda line: f"you said: {line}")
    console.submit("hello")
    assert "> hello" in console.text
    assert "you said: hello" in console.text


def test_a_console_without_a_handler_still_shows_the_command(app):
    console = ConsolePane()
    console.submit("hello")
    assert "> hello" in console.text


def test_a_handler_that_raises_does_not_take_the_window_with_it(app):
    """A console exists to be typed into by somebody who does not yet know what
    works, so a bad command is the normal case rather than a fault."""
    def explode(line):
        raise ValueError("no such command")

    console = ConsolePane(handler=explode)
    console.submit("bogus")
    assert "error: no such command" in console.text


def test_an_empty_line_does_nothing(app):
    console = ConsolePane(handler=lambda line: "ran")
    console.submit("")
    assert console.text == ""
    assert console.history == []


def test_history_records_what_was_run(app):
    console = ConsolePane(handler=lambda line: "")
    console.submit("one")
    console.submit("two")
    assert console.history == ["one", "two"]


def test_the_transcript_is_bounded(app):
    """A transcript with no limit is a memory leak with a scrollbar: it grows
    until the process dies, and it dies during the long session where somebody
    actually needed the log."""
    console = ConsolePane(handler=lambda line: "", max_lines=10)
    for i in range(100):
        console.submit(f"line{i}")
    assert len(console.text.splitlines()) <= 10


def test_a_console_renders(app):
    console = ConsolePane(handler=lambda line: "ok")
    console.submit("hello")
    assert_laid_out(show(console, 360, 200), "console_pane")
