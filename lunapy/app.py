"""The bootstrap: one call that replaces the setup a `main()` usually spells out.

    from lunapy.app import LunaApp

    def main() -> int:
        app = LunaApp.configure("bima")
        window = Editor()
        window.show()
        return app.exec()

It creates the `QApplication`, applies the variant, and **applies the theme the
user last chose** — that last part being the whole reason this exists rather
than three lines in each program. LunaP §17 records the hazard directly: a
consumer who hand-rolls three quarters of the bootstrap silently drops the
quarter they did not know about, and the dropped quarter is invisible because
everything still starts.

The Linux-specific half of LunaP's bootstrap did not port. It forces X11
because Avalonia's `UsePlatformDetect` does not choose X11 on a Wayland session
(LunaP §3). Qt's platform plugin selection handles Wayland natively, so
overriding it here would be replacing a working default with a worse one — and
the `QT_QPA_PLATFORM` environment variable is the supported way to say
otherwise, which `lunapy.testing` already uses to select `offscreen`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from . import settings, theme, themes
from .palette import Variant

#: Where the chosen theme is remembered. A category of its own so an application
#: browsing its own settings does not have to step over LunaPY's.
CATEGORY = "lunapy"
CHOSEN = "theme"


class LunaApp:
    """Static helpers. There is no instance — this is a bootstrap, not an object."""

    #: Where `available()` and `apply_named()` look for `.css` themes. An
    #: application sets this once; `None` means themes are not offered, which is
    #: the default because a toolkit that reads a directory nobody configured is
    #: a toolkit that reads a directory nobody audited.
    theme_directory: Path | None = None

    @staticmethod
    def configure(
        program_name: str | None = None,
        variant: Variant = Variant.DARK,
        argv: list[str] | None = None,
    ) -> QApplication:
        """Create (or find) the application, themed and ready.

        `program_name` names the settings folder. Passing it explicitly is worth
        the argument: the default derives from `sys.argv[0]`, which is the
        script name — so a program launched as `python -m bima` and as
        `bima` would otherwise keep two separate sets of settings and appear to
        forget everything when somebody changed how they start it.
        """
        app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
        if program_name:
            settings.set_store(settings.SqliteSettingsStore.for_application(program_name))

        theme.apply(app, variant)
        LunaApp.apply_saved(app, variant)
        app.setApplicationName(program_name or "LunaPY")
        return app

    # -- Themes ----------------------------------------------------------

    @staticmethod
    def available() -> list[str]:
        """Every theme name on disk. Empty when no directory is configured."""
        if LunaApp.theme_directory is None:
            return []
        return themes.available(LunaApp.theme_directory)

    @staticmethod
    def chosen() -> str | None:
        """The theme name the user last picked, whether or not it still exists."""
        value = settings.store().load(CATEGORY, CHOSEN)
        return value if isinstance(value, str) else None

    @staticmethod
    def apply_named(app: QApplication, name: str | None, variant: Variant | None = None) -> bool:
        """Apply a theme by name and remember the choice. `None` restores the
        built-in palette.

        Returns whether the theme was applied. A name that no longer resolves
        falls back to the built-in palette rather than leaving the previous one
        in force — an application starting with a theme the user deleted should
        look like the default, not like whatever happened to load first.
        """
        if name is None:
            theme.apply(app, variant)
            settings.store().delete(CATEGORY, CHOSEN)
            return True

        if LunaApp.theme_directory is None:
            settings.report("No theme directory configured; using the built-in palette.")
            theme.apply(app, variant)
            return False

        loaded = themes.find(LunaApp.theme_directory, name)
        if loaded is None:
            settings.report(f"Theme {name!r} would not load; using the built-in palette.")
            theme.apply(app, variant)
            return False

        for warning in loaded.warnings:
            settings.report(f"{name}: {warning}")
        theme.apply_theme(app, loaded, variant)
        settings.store().save(CATEGORY, CHOSEN, name)
        return True

    @staticmethod
    def apply_saved(app: QApplication, variant: Variant | None = None) -> bool:
        """Re-apply whatever was last chosen. Silent when nothing was.

        Separate from `configure` so an application that builds its own
        `QApplication` can still get this without taking the rest of the
        bootstrap — which is exactly the §17 hazard, made avoidable rather than
        merely documented.
        """
        name = LunaApp.chosen()
        if name is None:
            return False
        return LunaApp.apply_named(app, name, variant)
