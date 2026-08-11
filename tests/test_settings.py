"""The settings seam.

No Qt in this file — where a record goes is not a question about widgets, and
these run without an application.

The contract tests run against **both** stores. That is the point of having two:
a seam that only its first implementation satisfies is not a seam, and running
the same tests over both is what keeps that honest.
"""

import sqlite3
import sys
from pathlib import Path

import pytest

from lunapy import settings
from lunapy.settings import (
    JsonSettingsStore,
    SettingsStore,
    SqliteSettingsStore,
    default_config_root,
)


@pytest.fixture(params=["sqlite", "json"])
def store(request, tmp_path):
    if request.param == "sqlite":
        return SqliteSettingsStore(tmp_path / "settings.db")
    return JsonSettingsStore(tmp_path / "json")


# -- The contract, over both stores --------------------------------------


def test_a_value_round_trips(store):
    assert store.save(None, "a", {"x": 1})
    assert store.load(None, "a") == {"x": 1}


def test_a_value_survives_a_reopen(store):
    """A settings store that only works within one process is not a settings
    store."""
    store.save(None, "a", {"x": 1})
    reopened = type(store)(store.path if isinstance(store, SqliteSettingsStore) else store.root)
    assert reopened.load(None, "a") == {"x": 1}


def test_a_category_separates_records(store):
    store.save("themes", "a", {"x": 1})
    store.save("windows", "a", {"x": 2})
    assert store.load("themes", "a") == {"x": 1}
    assert store.load("windows", "a") == {"x": 2}
    # The root is its own category, not a catch-all.
    assert store.load(None, "a") is None


def test_the_root_category_is_not_confused_with_a_named_one(store):
    """`None` is stored as the empty string rather than SQL NULL: SQLite
    permits NULL in a PRIMARY KEY column unless it is NOT NULL, and NULLs do
    not compare equal, so the same (NULL, name) pair could be inserted twice
    and `load` would return whichever row it reached first."""
    store.save(None, "a", {"root": True})
    store.save("", "a", {"empty": True})
    assert store.load(None, "a") == store.load("", "a")

    store.save(None, "b", {"first": True})
    store.save(None, "b", {"second": True})
    assert store.load(None, "b") == {"second": True}
    assert store.keys(None).count("b") == 1


def test_saving_twice_updates_rather_than_duplicates(store):
    store.save(None, "a", {"v": 1})
    store.save(None, "a", {"v": 2})
    assert store.load(None, "a") == {"v": 2}
    assert store.keys(None) == ["a"]


def test_a_missing_record_is_none_not_an_error(store):
    assert store.load(None, "never_written") is None


def test_delete_removes_one_and_leaves_the_others(store):
    store.save("windows", "editor", {"x": 1})
    store.save("windows", "settings", {"x": 2})
    assert store.delete("windows", "editor")
    assert store.load("windows", "editor") is None
    assert store.load("windows", "settings") == {"x": 2}


def test_deleting_something_absent_is_not_a_failure(store):
    assert store.delete(None, "never_written")


def test_keys_lists_a_category_in_order(store):
    store.save("windows", "zebra", {})
    store.save("windows", "alpha", {})
    store.save("other", "ignored", {})
    assert store.keys("windows") == ["alpha", "zebra"]


def test_keys_of_an_empty_category_is_empty(store):
    assert store.keys("never_used") == []


def test_an_unserialisable_value_returns_false(store):
    assert store.save(None, "a", {"x": object()}) is False


def test_values_may_be_any_json_shape(store):
    for name, value in [("l", [1, 2]), ("s", "text"), ("n", 3), ("b", True), ("z", None)]:
        assert store.save(None, name, value)
        assert store.load(None, name) == value


def test_a_custom_store_satisfies_the_protocol():
    """Four methods, and deliberately no `directory()`.

    The first version of the protocol had one, ported from LunaP, and it was a
    leak of the only implementation that existed at the time: "which folder is
    this category in" is meaningless to a database. This test would have passed
    on a store that could not answer it, which is how the leak was found.
    """

    class InMemory:
        def __init__(self):
            self.data = {}

        def load(self, category, name):
            return self.data.get((category, name))

        def save(self, category, name, value):
            self.data[(category, name)] = value
            return True

        def delete(self, category, name):
            self.data.pop((category, name), None)
            return True

        def keys(self, category):
            return sorted(n for c, n in self.data if c == category)

    assert isinstance(InMemory(), SettingsStore)


# -- SQLite specifics ----------------------------------------------------


def test_the_database_is_created_with_its_parent_directory(tmp_path):
    store = SqliteSettingsStore(tmp_path / "deep" / "nested" / "settings.db")
    assert store.save(None, "a", {"x": 1})
    assert (tmp_path / "deep" / "nested" / "settings.db").exists()


def test_wal_is_enabled(tmp_path):
    """So a second instance reading settings does not block the first writing
    them."""
    store = SqliteSettingsStore(tmp_path / "settings.db")
    store.save(None, "a", {"x": 1})
    with sqlite3.connect(tmp_path / "settings.db") as connection:
        assert connection.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"


def test_a_corrupt_value_is_none_and_is_reported(tmp_path):
    store = SqliteSettingsStore(tmp_path / "settings.db")
    store.save(None, "a", {"x": 1})
    with sqlite3.connect(tmp_path / "settings.db") as connection:
        connection.execute("UPDATE settings SET value = '{not json'")
        connection.commit()

    reported = []
    settings.set_diagnostics(reported.append)
    try:
        assert store.load(None, "a") is None
    finally:
        settings.set_diagnostics(None)
    assert reported and "Falling back to defaults" in reported[0]


def test_an_unreadable_database_returns_none_rather_than_raising(tmp_path):
    """A settings file that will not open must not take the program with it."""
    path = tmp_path / "settings.db"
    path.write_text("this is not a database, it is a text file")
    store = SqliteSettingsStore(path)
    settings.set_diagnostics(None)
    assert store.load(None, "a") is None
    assert store.save(None, "a", {"x": 1}) is False
    assert store.keys(None) == []


def test_two_writers_do_not_clobber_each_other(tmp_path):
    """The race that one-document-per-store had and rows do not.

    Two stores over one database, interleaved: with a single JSON document each
    save is a read-modify-write of everything, so the second writer's copy —
    read before the first writer saved — overwrites it. As rows, both survive.
    """
    first = SqliteSettingsStore(tmp_path / "settings.db")
    second = SqliteSettingsStore(tmp_path / "settings.db")

    first.save("windows", "editor", {"x": 1})
    second.save("windows", "settings", {"x": 2})

    assert first.load("windows", "editor") == {"x": 1}
    assert first.load("windows", "settings") == {"x": 2}


# -- JSON specifics ------------------------------------------------------


def test_json_writes_one_readable_file_per_record(tmp_path):
    store = JsonSettingsStore(tmp_path)
    store.save("windows", "editor", {"x": 1})
    written = tmp_path / "windows" / "editor.json"
    assert written.exists()
    assert "\n" in written.read_text(), "a settings file is something a person opens"


def test_json_reports_a_corrupt_file(tmp_path):
    store = JsonSettingsStore(tmp_path)
    (tmp_path / "broken.json").write_text("{not json at all")

    reported = []
    settings.set_diagnostics(reported.append)
    try:
        assert store.load(None, "broken") is None
    finally:
        settings.set_diagnostics(None)
    assert len(reported) == 1 and "Falling back to defaults" in reported[0]


def test_json_is_silent_without_a_sink(tmp_path, capsys):
    """A toolkit that writes to stderr uninvited corrupts the output of the
    command-line tool that embedded it."""
    store = JsonSettingsStore(tmp_path)
    (tmp_path / "broken.json").write_text("{nope")
    settings.set_diagnostics(None)
    assert store.load(None, "broken") is None
    assert capsys.readouterr().err == ""


def test_json_write_is_atomic(tmp_path):
    """An interrupted save must leave the previous file intact rather than a
    truncated one. The SQLite store gets this from a transaction and needs no
    equivalent test."""
    store = JsonSettingsStore(tmp_path)
    store.save(None, "a", {"first": True})

    original = JsonSettingsStore._write_atomic
    JsonSettingsStore._write_atomic = staticmethod(
        lambda path, contents: (_ for _ in ()).throw(OSError("interrupted"))
    )
    try:
        assert store.save(None, "a", {"second": True}) is False
    finally:
        JsonSettingsStore._write_atomic = staticmethod(original)

    assert store.load(None, "a") == {"first": True}


def test_json_leaves_no_temporary_files_behind(tmp_path):
    store = JsonSettingsStore(tmp_path)
    store.save(None, "a", {"x": 1})
    store.save(None, "a", {"x": 2})
    assert sorted(p.name for p in tmp_path.iterdir()) == ["a.json"]


def test_the_json_temporary_lives_beside_its_destination(tmp_path, monkeypatch):
    """`os.replace` is only atomic within a filesystem. A temporary in /tmp
    would silently become copy-then-delete on any machine where /tmp is a
    different mount, which is most of them."""
    import tempfile as tempfile_module

    seen = {}
    real_mkstemp = tempfile_module.mkstemp

    def spy(*args, **kwargs):
        seen["dir"] = kwargs.get("dir")
        return real_mkstemp(*args, **kwargs)

    monkeypatch.setattr(tempfile_module, "mkstemp", spy)
    JsonSettingsStore(tmp_path).save("nested", "a", {"x": 1})
    assert Path(seen["dir"]) == tmp_path / "nested"


def test_json_keeps_its_own_directory_method(tmp_path):
    """Not part of the protocol, but a real property of this store — a host
    keeping themes as files needs to know where they go."""
    store = JsonSettingsStore(tmp_path)
    assert store.directory(None) == tmp_path
    assert store.directory("themes") == tmp_path / "themes"


# -- The module-level store ----------------------------------------------


def test_the_default_store_is_sqlite_and_resolved_lazily(tmp_path):
    """A host assigning a store during startup must never be a moment too late:
    importing lunapy.windowing must not be what decides where settings live."""
    settings.set_store(None)
    replacement = SqliteSettingsStore(tmp_path / "settings.db")
    settings.set_store(replacement)
    assert settings.store() is replacement

    settings.set_store(None)
    assert isinstance(settings.store(), SqliteSettingsStore)
    settings.set_store(None)


@pytest.mark.parametrize(
    "platform, env, expected",
    [
        ("linux", {"XDG_CONFIG_HOME": "/xdg"}, Path("/xdg/probe")),
        ("win32", {"APPDATA": "/appdata"}, Path("/appdata/probe")),
    ],
)
def test_the_default_root_follows_each_platform(monkeypatch, platform, env, expected):
    monkeypatch.setattr(sys, "platform", platform)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert default_config_root("probe") == expected


def test_the_default_root_falls_back_to_a_name(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    monkeypatch.setattr(sys, "argv", [""])
    assert default_config_root() == Path("/xdg/LunaPY")


def test_the_default_database_sits_under_the_config_root(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", "/xdg")
    assert SqliteSettingsStore.for_application("probe").path == Path("/xdg/probe/settings.db")
