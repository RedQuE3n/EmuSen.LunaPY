"""The bootstrap, and remembering which theme was chosen.

LunaP §17's hazard is the reason this exists: a consumer who hand-rolls three
quarters of the bootstrap silently drops the quarter they did not know about,
and the drop is invisible because everything still starts.
"""

import pytest

from lunapy import settings, theme
from lunapy.app import CATEGORY, CHOSEN, LunaApp
from lunapy.palette import Variant
from lunapy.settings import SqliteSettingsStore
from lunapy.windowing import MessageWindow
from lunapy.testing import assert_laid_out, show


@pytest.fixture(autouse=True)
def isolated(tmp_path, app):
    settings.set_store(SqliteSettingsStore(tmp_path / "settings.db"))
    LunaApp.theme_directory = tmp_path / "themes"
    (tmp_path / "themes").mkdir()
    yield
    LunaApp.theme_directory = None
    settings.set_store(None)
    theme.apply(app, Variant.DARK)


def write_theme(tmp_path, name, source):
    (tmp_path / "themes" / f"{name}.css").write_text(source)


def test_configure_returns_the_one_application(app):
    assert LunaApp.configure() is app


def test_available_lists_themes_on_disk(tmp_path):
    write_theme(tmp_path, "nocturne", ":root { --luna-surface: #12131A; }")
    write_theme(tmp_path, "dawn", ":root { --luna-surface: #FFFFFF; }")
    assert LunaApp.available() == ["dawn", "nocturne"]


def test_available_is_empty_with_no_directory():
    """A toolkit that reads a directory nobody configured is a toolkit that
    reads a directory nobody audited."""
    LunaApp.theme_directory = None
    assert LunaApp.available() == []


def test_applying_a_theme_remembers_the_choice(app, tmp_path):
    write_theme(tmp_path, "nocturne", ":root { --luna-surface: #12131A; }")
    assert LunaApp.apply_named(app, "nocturne")
    assert LunaApp.chosen() == "nocturne"
    assert settings.store().load(CATEGORY, CHOSEN) == "nocturne"


def test_the_saved_theme_is_re_applied(app, tmp_path):
    """The quarter of the bootstrap a hand-rolled one drops."""
    from PySide6.QtGui import QPalette

    write_theme(tmp_path, "nocturne", ":root { --luna-surface: #12131A; }")
    LunaApp.apply_named(app, "nocturne")

    theme.apply(app, Variant.DARK)          # back to the built-in palette
    assert theme.loaded() is None

    assert LunaApp.apply_saved(app)
    assert app.palette().color(QPalette.ColorRole.Window).name().upper() == "#12131A"


def test_no_saved_theme_is_silent(app):
    assert LunaApp.apply_saved(app) is False


def test_a_deleted_theme_falls_back_to_the_built_in_palette(app, tmp_path):
    """An application starting with a theme the user deleted should look like
    the default, not like whatever happened to load first."""
    write_theme(tmp_path, "nocturne", ":root { --luna-surface: #12131A; }")
    LunaApp.apply_named(app, "nocturne")
    (tmp_path / "themes" / "nocturne.css").unlink()

    reported = []
    settings.set_diagnostics(reported.append)
    try:
        assert LunaApp.apply_saved(app) is False
    finally:
        settings.set_diagnostics(None)

    assert theme.loaded() is None
    assert any("would not load" in r for r in reported)


def test_choosing_none_restores_the_built_in_palette(app, tmp_path):
    write_theme(tmp_path, "nocturne", ":root { --luna-surface: #12131A; }")
    LunaApp.apply_named(app, "nocturne")
    assert LunaApp.apply_named(app, None)
    assert LunaApp.chosen() is None
    assert theme.loaded() is None


def test_a_theme_warning_is_reported_when_it_is_applied(app, tmp_path):
    """Parsing reports through `Theme.warnings`; applying is where a user is
    actually present to be told."""
    write_theme(tmp_path, "odd", ":root { --luna-invented: #FFFFFF; --luna-surface: #101010; }")
    reported = []
    settings.set_diagnostics(reported.append)
    try:
        assert LunaApp.apply_named(app, "odd")
    finally:
        settings.set_diagnostics(None)
    assert any("invented" in r for r in reported)


# -- MessageWindow -------------------------------------------------------


def test_a_message_window_shows_its_body(app):
    window = MessageWindow("Build output", "wrote 71 fields\n")
    assert window.body.startswith("wrote 71 fields")
    window.append("done.")
    assert "done." in window.body


def test_a_message_window_is_read_only_and_selectable(app):
    """The first thing anybody does with an error is copy it somewhere."""
    window = MessageWindow("Failed", "Traceback...")
    assert window._body.isReadOnly()
    assert window._body.textInteractionFlags() != 0


def test_a_message_window_closes_on_escape(app):
    """Unlike ToolWindow's default. This one holds no input, so Escape cannot
    mean "stop what I am typing"."""
    window = MessageWindow("Build output", "text")
    assert window.closes_on_escape


def test_a_message_window_renders(app):
    window = MessageWindow("Build output", "wrote 71 fields\nvalidated 71\n")
    show(window, 640, 420)
    assert_laid_out(window, "message_window")
    window.close()
