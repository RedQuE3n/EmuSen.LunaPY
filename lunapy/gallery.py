"""Every control in the kit, on one window, against the current theme.

**The fastest way to see what a theme you are writing actually does.** A theme
author changing `--luna-muted` wants to know what moved, and the alternative is
opening whichever application happens to use the most controls and hoping it
covers them.

It earns its place a second way, which LunaP did not have: the gallery is a
window containing one of everything, so a render test over it is a render test
over the whole kit. `test_gallery.py` asserts it lays out, which catches a
control that renders as nothing without needing a test per control to notice.
"""

from __future__ import annotations

from PySide6.QtWidgets import QLineEdit, QWidget

from .controls import EmptyState, FieldRow, MeterEntry, MeterList, MeterRow, RgbaImageView
from .fluent import button, header, hint, mono, row, scroll, section, stack, text, tune
from .panes import ConsolePane, FilterBar, PathPickerRow
from .palette import Variant
from .widgets import ButtonBar, Dropdown, LunaList, LunaSwitch, StatusBar, Tabs
from .windowing import ToolWindow


def gallery_content() -> QWidget:
    """The kit, as a widget. Separate from the window so a test can render it
    without a window, and so an application can embed it in a settings page."""
    meters = MeterList(
        [
            MeterEntry("Nominal", 20, "20%"),
            MeterEntry("Busy", 70, "70%"),
            MeterEntry("Hot", 95, "95%"),
            MeterEntry("As a count", 10, "13/128"),
        ]
    )

    people = LunaList[str](label=lambda p: p.title())
    people.refresh(["ada", "grace", "katherine"])

    console = ConsolePane(handler=lambda line: f"you said: {line}")
    console.append("A console takes a callable, so it cannot know what your")
    console.append("commands mean. This one echoes.")

    picker = PathPickerRow("Save folder", "/tmp", directory=True)
    field = FieldRow("Profile name", QLineEdit("default"), field_hint="Shown in the title bar.")

    choices = Dropdown()
    choices.fill(["Every page", "Odd pages", "Even pages"], "Every page")

    tabs = Tabs()
    tabs.add("Text", stack(
        header("A section header"),
        text("Body text, the default."),
        hint("A hint: eleven point, muted, an aside under something else."),
        mono("mono_text(0x1E1E1E)"),
        spacing=4,
    ))
    tabs.add("Empty", EmptyState("Nothing here", "An empty state is the content, not an aside."))
    tabs.add("Image", RgbaImageView())

    return scroll(stack(
        section("Meters", meters),
        section("Fields", field, picker, row(text("Pages", width=140), choices, spacing=8)),
        section("Choosing", people, FilterBar("Filter people…", search_delay_ms=0)),
        section("Switches", LunaSwitch("Overwrite existing fields"), LunaSwitch("Flatten first")),
        section("Tabs", tabs),
        section("Console", tune(console, min_size=(0, 120))),
        StatusBar("Ready."),
        ButtonBar(button("Cancel"), button("Apply")),
        spacing=12,
        margin=12,
    ))


class GalleryWindow(ToolWindow):
    def __init__(self, variant: Variant | None = None):
        super().__init__()
        self.setWindowTitle("LunaPY gallery")
        self.window_key = "lunapy_gallery"
        self.set_content(gallery_content())
        self.resize(560, 700)


def main() -> int:
    """`python -m lunapy.gallery` — the whole kit, on a real screen."""
    import sys

    from PySide6.QtWidgets import QApplication

    from . import theme

    app = QApplication(sys.argv)
    theme.apply(app)
    window = GalleryWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
