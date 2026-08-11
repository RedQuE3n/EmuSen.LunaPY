"""LunaPY — a small Qt toolkit: a theme, a fluent layout surface, and a harness
that can tell whether a window actually rendered.

**LunaPY imports PySide6 and the standard library, and nothing else.** That is
not modesty; it is the property that makes the toolkit usable from any project.
Every helper takes plain data or a callable, so nothing here can drag a domain
model into a window and nothing here needs to know what your program is for.
`tests/test_layering.py` enforces it rather than trusting it.

It is the Python counterpart of LunaP, the C#/Avalonia toolkit, and follows its
API where the two languages agree. Where they do not, `docs/LunaPY.md` records
which way the port went and why — Qt is not Avalonia, and pretending otherwise
would produce a toolkit that fights its own substrate.

`lunapy.testing` is deliberately not imported here. It sets `QT_QPA_PLATFORM`
on import, which is exactly right for a test run and exactly wrong for an
application that wants a window on a screen.
"""

from .fluent import (
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
from .palette import (
    BUSY_PERCENT,
    DARK,
    HOT_PERCENT,
    LIGHT,
    LoadLevel,
    Variant,
    contrast_ratio,
    level_for,
)
from .app import LunaApp
from .controls import EmptyState, FieldRow, MeterEntry, MeterList, MeterRow, RgbaImageView
from .panes import ConsolePane, FilterBar, PathPickerRow
from .placement import WindowPlacement, is_on_a_screen
from .settings import JsonSettingsStore, SettingsStore, set_diagnostics, set_store, store
from .theme import apply, apply_theme, controls_qss, loaded, restyle, set_load, set_style_key, variant
from .threading import Debounce, Latest, Suppressor, is_ui_thread, post, run
from .widgets import ButtonBar, Dropdown, LunaList, LunaSwitch, StatusBar, Tabs
from .windowing import (
    MessageWindow,
    PollingWindow,
    ToolWindow,
    WindowSlot,
    confirm,
    confirm_box,
    error,
    error_box,
    message,
    message_box,
    screen_rects,
)

__all__ = [
    # Fluent surface
    "button", "cols", "dock", "header", "hint", "mono", "row", "rows",
    "scroll", "section", "stack", "text", "tune",
    # Palette
    "BUSY_PERCENT", "DARK", "HOT_PERCENT", "LIGHT", "LoadLevel", "Variant",
    "contrast_ratio", "level_for",
    # Theme
    "apply", "apply_theme", "controls_qss", "loaded", "restyle", "set_load", "set_style_key", "variant",
    # Controls
    "EmptyState", "FieldRow", "MeterEntry", "MeterList", "MeterRow", "RgbaImageView",
    "ButtonBar", "Dropdown", "LunaList", "LunaSwitch", "StatusBar", "Tabs",
    "ConsolePane", "FilterBar", "PathPickerRow",
    # Threading
    "Debounce", "Latest", "Suppressor", "is_ui_thread", "post", "run",
    # Windowing
    "LunaApp", "MessageWindow", "PollingWindow", "ToolWindow", "WindowSlot", "screen_rects",
    "confirm", "confirm_box", "error", "error_box", "message", "message_box",
    # Settings and placement
    "JsonSettingsStore", "SettingsStore", "WindowPlacement", "is_on_a_screen",
    "set_diagnostics", "set_store", "store",
]

# Read from the installed distribution rather than written here, so this is not
# a second place the version can be spelled -- see pyproject.toml. The fallback
# is for running straight out of a source tree that was never installed, where
# there is no distribution to ask and "unknown" is the honest answer.
try:
    from importlib.metadata import PackageNotFoundError, version as _distribution_version

    __version__ = _distribution_version("emusen-lunapy")
except PackageNotFoundError:  # pragma: no cover - a source tree, not an install
    __version__ = "0.0.0+unknown"
