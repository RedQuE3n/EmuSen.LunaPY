"""The seam between LunaPY and wherever a host keeps its settings.

LunaPY needs to store a handful of small records — where each window was, which
theme is chosen — and it must not decide *where*. An application with its own
config directory, its own database, or a policy about what may touch the disk
should be able to say so, and saying so is four methods rather than a fork.

**A store is a keyed record store, not a file system.** `load`, `save`,
`delete`, `keys`, over a `(category, name)` pair. Nothing above this line knows
whether that becomes a row or a file.

Loading is **best-effort everywhere**. A settings record that will not parse
must not take the program with it: a window whose remembered position is
unreadable should open at the default position, not fail to open. `report` is
the hook that stops that happening in silence, because "it quietly ignored your
config" is its own kind of bug.

No Qt in this module. Where a record goes is not a question about widgets.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable, Protocol, runtime_checkable

DATABASE_NAME = "settings.db"


@runtime_checkable
class SettingsStore(Protocol):
    """Four methods. Implement this to keep settings somewhere of your own.

    There is deliberately **no `directory()`**. The first version of this
    protocol had one, ported from LunaP's `ISettingsStore`, and it was a leak of
    the only implementation that existed at the time: "which folder is this
    category in" is answerable by a store that writes files and meaningless to
    one backed by a database. A seam that only its first implementation can
    satisfy is not a seam. `JsonSettingsStore.directory` still exists, as a
    property of that store rather than of the interface.
    """

    def load(self, category: str | None, name: str) -> Any | None:
        """Parsed contents, or `None` for missing, unreadable or corrupt.

        Returning `None` rather than raising is the contract that makes every
        caller's fallback path the normal path instead of an exception handler.
        """

    def save(self, category: str | None, name: str, value: Any) -> bool:
        """`False` when the write failed. A setting that cannot reach storage
        must not take the program with it."""

    def delete(self, category: str | None, name: str) -> bool:
        """`True` if the record is gone, including if it was never there."""

    def keys(self, category: str | None) -> list[str]:
        """Every name in a category. Empty when there are none or on failure."""


def default_config_root(program_name: str | None = None) -> Path:
    """Where an application that has said nothing gets its own folder.

    Follows each platform's own convention rather than inventing one, because a
    dotfile in `$HOME` on a machine with an XDG config directory is litter, and
    a `.config` directory on Windows is a folder nobody's backup policy knows
    about.
    """
    name = program_name or Path(sys.argv[0]).stem or "LunaPY"

    if sys.platform == "win32":
        root = os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming"
    elif sys.platform == "darwin":
        root = Path.home() / "Library" / "Application Support"
    else:
        root = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"

    return Path(root) / name


class SqliteSettingsStore:
    """The default store: one SQLite database, one row per record.

    `sqlite3` is in the standard library, so this costs nothing against the rule
    that LunaPY imports PySide6 and stdlib only.

    **Why this rather than a JSON file, which came first.** Two properties, and
    the second is the one that changed a recorded hazard into a non-issue:

    - **Durability is the database's problem, not ours.** A transaction either
      lands or it does not. The write-temporary-then-rename dance
      `JsonSettingsStore` performs — and the filesystem trap that goes with it —
      has no counterpart here.
    - **Concurrent writers no longer clobber each other.** Every window's
      placement was previously one key inside a single `windows.json`, so saving
      one meant reading, modifying and rewriting the whole document. Two windows
      closing in the same instant lost one of the two updates. As rows, each
      window writes only itself and SQLite serialises the writers, so the race
      is gone rather than tolerated. `docs/LunaPY.md` §7.2.

    **What it costs**, stated rather than glossed: a settings file somebody can
    open in a text editor and fix. That was a real property and it is spent
    here. `JsonSettingsStore` remains for a host that wants it back, which is
    also the demonstration that the seam above is a real one.
    """

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self._initialised = False

    @classmethod
    def for_application(cls, program_name: str | None = None) -> "SqliteSettingsStore":
        return cls(default_config_root(program_name) / DATABASE_NAME)

    # A category of `None` is stored as the empty string, never as SQL NULL.
    # SQLite permits NULL in a PRIMARY KEY column unless it is declared NOT
    # NULL, and NULLs do not compare equal to each other — so a nullable
    # category would let the same (NULL, name) pair be inserted repeatedly and
    # `load` would return whichever row it happened to reach first. The mapping
    # is done in one place so no query has to remember it.
    @staticmethod
    def _category(category: str | None) -> str:
        return "" if category is None else category

    def _connect(self) -> sqlite3.Connection:
        """A connection per operation.

        Settings are written a handful of times in a session, so the cost is
        irrelevant, and it sidesteps `sqlite3`'s same-thread check entirely — a
        shared connection would have to be either thread-confined or opened with
        `check_same_thread=False`, and the second one trades a loud error for a
        silent corruption the first time a background job saves something.
        """
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path)
        if not self._initialised:
            connection.execute(
                """CREATE TABLE IF NOT EXISTS settings (
                       category TEXT NOT NULL,
                       name     TEXT NOT NULL,
                       value    TEXT NOT NULL,
                       PRIMARY KEY (category, name)
                   )"""
            )
            # WAL so a second instance of the application reading settings does
            # not block the first one writing them. It is a persistent property
            # of the database file, so setting it on every connect is a no-op
            # after the first.
            connection.execute("PRAGMA journal_mode=WAL")
            connection.commit()
            self._initialised = True
        return connection

    def load(self, category: str | None, name: str) -> Any | None:
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT value FROM settings WHERE category = ? AND name = ?",
                    (self._category(category), name),
                ).fetchone()
        except sqlite3.Error as error:
            report(f"{self.path} [{category}/{name}]: {error}. Falling back to defaults.")
            return None

        if row is None:
            return None
        try:
            return json.loads(row[0])
        except ValueError as error:
            report(f"{self.path} [{category}/{name}]: {error}. Falling back to defaults.")
            return None

    def save(self, category: str | None, name: str, value: Any) -> bool:
        try:
            encoded = json.dumps(value, sort_keys=True)
        except TypeError as error:
            report(f"{self.path} [{category}/{name}]: {error}. Setting not saved.")
            return False

        try:
            with self._connect() as connection:
                connection.execute(
                    """INSERT INTO settings (category, name, value) VALUES (?, ?, ?)
                       ON CONFLICT (category, name) DO UPDATE SET value = excluded.value""",
                    (self._category(category), name, encoded),
                )
            return True
        except (sqlite3.Error, OSError) as error:
            report(f"{self.path} [{category}/{name}]: {error}. Setting not saved.")
            return False

    def delete(self, category: str | None, name: str) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM settings WHERE category = ? AND name = ?",
                    (self._category(category), name),
                )
            return True
        except (sqlite3.Error, OSError) as error:
            report(f"{self.path} [{category}/{name}]: {error}. Not deleted.")
            return False

    def keys(self, category: str | None) -> list[str]:
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    "SELECT name FROM settings WHERE category = ? ORDER BY name",
                    (self._category(category),),
                ).fetchall()
            return [row[0] for row in rows]
        except (sqlite3.Error, OSError) as error:
            report(f"{self.path} [{category}]: {error}.")
            return []


class JsonSettingsStore:
    """Indented JSON files under a directory, one file per record.

    No longer the default — see `SqliteSettingsStore` for what replaced it and
    why — and kept for two reasons. A host that wants settings a person can open
    in an editor and repair should be able to have them; and a second
    implementation is the only thing that proves `SettingsStore` is a seam
    rather than a description of whatever the first one happened to do. It was
    what caught `directory()` not belonging in the protocol.
    """

    def __init__(self, root: Path | str):
        self.root = Path(root)

    @classmethod
    def for_application(cls, program_name: str | None = None) -> "JsonSettingsStore":
        return cls(default_config_root(program_name))

    def directory(self, category: str | None) -> Path:
        """This store's own, deliberately not part of `SettingsStore`."""
        return self.root if category is None else self.root / category

    def _path_for(self, category: str | None, name: str) -> Path:
        return self.directory(category) / f"{name}.json"

    def load(self, category: str | None, name: str) -> Any | None:
        path = self._path_for(category, name)
        try:
            if not path.exists():
                return None
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            report(f"{path}: {error}. Falling back to defaults.")
            return None

    def save(self, category: str | None, name: str, value: Any) -> bool:
        path = self._path_for(category, name)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._write_atomic(path, json.dumps(value, indent=2, sort_keys=True))
            return True
        except (OSError, TypeError) as error:
            report(f"{path}: {error}. Setting not saved.")
            return False

    def delete(self, category: str | None, name: str) -> bool:
        try:
            self._path_for(category, name).unlink(missing_ok=True)
            return True
        except OSError as error:
            report(f"{self._path_for(category, name)}: {error}. Not deleted.")
            return False

    def keys(self, category: str | None) -> list[str]:
        try:
            directory = self.directory(category)
            if not directory.is_dir():
                return []
            return sorted(p.stem for p in directory.glob("*.json"))
        except OSError as error:
            report(f"{self.directory(category)}: {error}.")
            return []

    @staticmethod
    def _write_atomic(path: Path, contents: str) -> None:
        """Full write, then rename.

        An interrupted save must leave the previous file intact rather than a
        truncated one — and a truncated JSON file is worse than a missing one,
        because `load` reports it as corrupt every time the program starts
        instead of quietly using defaults once.

        The temporary file is made in the destination's own directory because
        `os.replace` is only atomic within a filesystem; `/tmp` is frequently a
        different one, and the rename would silently become copy-then-delete.

        None of this is needed by the SQLite store, where a transaction already
        provides it. It is the clearest single illustration of what moving to a
        database bought.
        """
        handle, temporary = tempfile.mkstemp(dir=path.parent, prefix=path.name, suffix=".tmp")
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as file:
                file.write(contents)
            os.replace(temporary, path)
        except BaseException:
            Path(temporary).unlink(missing_ok=True)
            raise


# The host points LunaPY at its own settings and its own log through these.
_store: SettingsStore | None = None
_diagnostics: Callable[[str], None] | None = None


def store() -> SettingsStore:
    """The active store, defaulting on first use rather than at import.

    Resolved lazily so that a host assigning one during startup is never a
    moment too late — importing `lunapy.windowing` must not be the thing that
    decides where an application's settings live.
    """
    global _store
    if _store is None:
        _store = SqliteSettingsStore.for_application()
    return _store


def set_store(new_store: SettingsStore | None) -> None:
    """Point LunaPY somewhere else. `None` restores the default on next use."""
    global _store
    _store = new_store


def set_diagnostics(sink: Callable[[str], None] | None) -> None:
    """Where "this record would not load, and why" goes. `None` discards.

    Discarding is what tests and any caller with nowhere to print want, and it
    is the default: a toolkit that writes to stderr uninvited is a toolkit that
    corrupts the output of the command-line tool that embedded it.
    """
    global _diagnostics
    _diagnostics = sink


def report(message: str) -> None:
    if _diagnostics is not None:
        _diagnostics(message)
