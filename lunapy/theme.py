"""Where the palette meets Qt: a QPalette, a stylesheet, and the repolish that
Qt will not do for you.

Two mechanisms, not one, and the split is the whole design of this file:

- **QPalette** carries the base roles — window, text, base, button. It is
  role-based and inherits down the widget tree the way you would expect.
- **QSS** carries only what a palette has no role for: the three text styles,
  the load ramp on a meter, semantic accents.

Doing all of it in QSS is the obvious first attempt and it is wrong. A rule like
`QWidget { background: #1E1E1E }` cascades to *every* descendant, including the
ones that paint their own background — the viewport of a scroll area, the
drop-down of a combo box — so a stylesheet that looks right on a bare window
starts producing dark rectangles inside controls that never asked for one. A
palette does not have that failure mode because a role is asked for, not
inherited blindly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Mapping

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication, QWidget

if TYPE_CHECKING:
    from .themes import Theme

from .palette import (
    COLUMNS,
    HEADER_FONT_SIZE,
    HINT_FONT_SIZE,
    MONO_FONT,
    LoadLevel,
    Variant,
    level_for,
)

# The dynamic property a widget carries to select a style. QSS reaches it with
# an attribute selector — `QLabel[luna="section_header"]`. One property name for
# every style key means a theme author has one thing to learn, and it means the
# repolish helper below has one property to watch.
STYLE_KEY = "luna"

# Dark by default, and that is the absence of a behaviour change rather than a
# preference — LunaP §23.3. Module state rather than a parameter threaded
# through every call because it answers "what is on screen right now", which is
# a property of the running application and not of any one widget.
_variant = Variant.DARK


def variant() -> Variant:
    """The variant currently applied. `Variant.DARK` before `apply` is called."""
    return _variant


def qpalette(v: Variant, colours: Mapping[str, str] | None = None) -> QPalette:
    """The base roles, as Qt's own palette object.

    `colours` overrides the variant's column, which is how a loaded theme
    reaches the same two generators rather than getting its own. Two code paths
    producing a palette is how a theme comes out right in one of them.
    """
    c = colours or COLUMNS[v]
    surface, text = QColor(c["surface"]), QColor(c["text"])
    field, muted = QColor(c["input_surface"]), QColor(c["muted"])

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, surface)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, field)
    p.setColor(QPalette.ColorRole.AlternateBase, surface)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, field)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.ToolTipBase, field)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)

    # Disabled text is a role in its own right. Left unset it stays the enabled
    # colour, and a greyed-out control that is not actually grey reads as an
    # enabled control that ignores clicks.
    for group in (QPalette.ColorGroup.Disabled,):
        p.setColor(group, QPalette.ColorRole.WindowText, muted)
        p.setColor(group, QPalette.ColorRole.Text, muted)
        p.setColor(group, QPalette.ColorRole.ButtonText, muted)

    return p


def qss(
    v: Variant,
    colours: Mapping[str, str] | None = None,
    mono_font: str = MONO_FONT,
    hint_size: float = HINT_FONT_SIZE,
    header_size: float = HEADER_FONT_SIZE,
) -> str:
    """The stylesheet half: style keys, and the accents a palette has no role for.

    Every input is a parameter with the palette's own value as its default, so a
    loaded theme overriding a font or a size reaches this one generator instead
    of getting a second one. Two code paths producing stylesheets is how a theme
    comes out right in one of them and subtly wrong in the other.
    """
    c = colours or COLUMNS[v]
    return f"""
    QLabel[{STYLE_KEY}="section_header"] {{
        color: {c["section_header"]};
        font-size: {header_size}px;
        font-weight: bold;
    }}
    QLabel[{STYLE_KEY}="hint"] {{
        color: {c["muted"]};
        font-size: {hint_size}px;
    }}
    QLabel[{STYLE_KEY}="mono"] {{
        font-family: {mono_font};
    }}
    QLabel[{STYLE_KEY}="warning"] {{ color: {c["warning"]}; }}
    QLabel[{STYLE_KEY}="error"]   {{ color: {c["error"]}; }}
    QLabel[{STYLE_KEY}="success"] {{ color: {c["success"]}; }}
    QLabel[{STYLE_KEY}="info"]    {{ color: {c["info"]}; }}

    /* The load ramp reaches a meter through the same property, so a dashboard
       sets `level` and the theme decides what that looks like. A dashboard that
       set the colour itself would be a dashboard a theme cannot reach. */
    QProgressBar {{ background: {c["input_surface"]}; text-align: center; }}
    QProgressBar[{STYLE_KEY}="nominal"]::chunk {{ background: {c["nominal"]}; }}
    QProgressBar[{STYLE_KEY}="busy"]::chunk    {{ background: {c["busy"]}; }}
    QProgressBar[{STYLE_KEY}="hot"]::chunk     {{ background: {c["hot"]}; }}
    """ + controls_qss(v, colours)


def controls_qss(v: Variant, colours: Mapping[str, str] | None = None) -> str:
    """The whole standard control set, drawn from the palette.

    **LunaP has no counterpart to this file and did not need one**, which is the
    single biggest structural difference between the two toolkits. Avalonia
    ships `FluentTheme`: a complete, modern control theme, so LunaP's
    `Theme/Controls.axaml` styles only LunaP's *own* controls and lets Fluent
    draw every button, text box and tab. Qt ships Fusion, which is complete and
    dated — so a LunaPY application that styled only its own controls would be a
    handful of nice widgets sitting in a window from 2005.

    Everything here resolves from palette tokens, including the five §14 added
    for exactly this purpose, so a loaded theme reaches all of it. A stylesheet
    with a hex literal in it is a stylesheet a theme cannot change.

    Kept in its own function rather than inlined so `qss` stays readable and so
    an application that wants only the LunaPY-specific rules can say so.
    """
    c = colours or COLUMNS[v]
    return f"""
    /* Base. Deliberately narrow: QWidget as a bare selector would cascade a
       background into every descendant, including those that paint their own —
       which is the failure this file's module docstring describes. Containers
       get their background from the QPalette instead; this sets only colour. */
    QWidget {{ color: {c["text"]}; }}

    QToolTip {{
        background: {c["input_surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        padding: 4px 6px;
    }}

    /* Buttons */
    QPushButton, QToolButton {{
        background: {c["raised"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 4px;
        padding: 5px 12px;
        min-height: 18px;
    }}
    QPushButton:hover, QToolButton:hover {{ background: {c["hover"]}; }}
    QPushButton:pressed, QToolButton:pressed {{ background: {c["input_surface"]}; }}
    QPushButton:default {{ border: 1px solid {c["selection"]}; }}
    QPushButton:disabled, QToolButton:disabled {{
        color: {c["muted"]};
        border: 1px solid {c["border"]};
        background: {c["surface"]};
    }}
    QToolButton {{ padding: 4px; }}
    QToolButton:checked {{ background: {c["selection"]}; color: {c["selection_text"]}; }}

    /* Text entry */
    QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
        background: {c["input_surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 4px;
        padding: 4px 6px;
        selection-background-color: {c["selection"]};
        selection-color: {c["selection_text"]};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c["selection"]}; }}
    QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
        background: {c["surface"]};
        color: {c["muted"]};
    }}

    /* Combo box */
    QComboBox {{
        background: {c["raised"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 4px;
        padding: 4px 6px;
        min-height: 18px;
    }}
    QComboBox:hover {{ background: {c["hover"]}; }}
    QComboBox:focus {{ border: 1px solid {c["selection"]}; }}
    QComboBox:disabled {{ color: {c["muted"]}; background: {c["surface"]}; }}
    QComboBox::drop-down {{ border: none; width: 18px; }}
    QComboBox QAbstractItemView {{
        background: {c["input_surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        selection-background-color: {c["selection"]};
        selection-color: {c["selection_text"]};
        outline: none;
    }}

    /* Check boxes and radios. The indicator is sized and coloured but not
       redrawn: a stylesheet that replaces the indicator image has to supply one
       per state per variant, and a missing state renders as nothing at all —
       which is a checkbox you cannot tell the state of. */
    QCheckBox, QRadioButton {{ spacing: 6px; background: transparent; }}
    QCheckBox::indicator, QRadioButton::indicator {{ width: 14px; height: 14px; }}
    QCheckBox::indicator {{
        border: 1px solid {c["border"]};
        border-radius: 3px;
        background: {c["input_surface"]};
    }}
    QCheckBox::indicator:checked {{
        background: {c["selection"]};
        border: 1px solid {c["selection"]};
    }}
    QRadioButton::indicator {{
        border: 1px solid {c["border"]};
        border-radius: 7px;
        background: {c["input_surface"]};
    }}
    QRadioButton::indicator:checked {{
        background: {c["selection"]};
        border: 4px solid {c["input_surface"]};
    }}
    QCheckBox:disabled, QRadioButton:disabled {{ color: {c["muted"]}; }}

    /* Item views */
    QListWidget, QListView, QTreeWidget, QTreeView, QTableWidget, QTableView {{
        background: {c["input_surface"]};
        alternate-background-color: {c["surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-radius: 4px;
        outline: none;
    }}
    QListWidget::item, QListView::item, QTreeView::item, QTableView::item {{
        padding: 3px 4px;
        border: none;
    }}
    QListWidget::item:hover, QListView::item:hover, QTreeView::item:hover {{
        background: {c["hover"]};
    }}
    QListWidget::item:selected, QListView::item:selected,
    QTreeView::item:selected, QTableView::item:selected {{
        background: {c["selection"]};
        color: {c["selection_text"]};
    }}
    /* `text`, not `muted`. A column header reads quieter than its rows and the
       obvious way to get that is the muted grey — which measures 3.39:1 on the
       dark raised face, below the 4.5:1 floor for body text. A header is text
       somebody reads to know what a column is; making it fail contrast to look
       quieter is exactly the trade this project refuses. The weight and the
       background carry the hierarchy instead. docs/LunaPY.md §14.1. */
    QHeaderView::section {{
        background: {c["raised"]};
        color: {c["text"]};
        font-weight: bold;
        border: none;
        border-bottom: 1px solid {c["border"]};
        border-right: 1px solid {c["border"]};
        padding: 4px 6px;
    }}
    QTableCornerButton::section {{ background: {c["raised"]}; border: none; }}

    /* Tabs */
    QTabWidget::pane {{
        border: 1px solid {c["border"]};
        border-radius: 4px;
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {c["muted"]};
        border: 1px solid transparent;
        border-top-left-radius: 4px;
        border-top-right-radius: 4px;
        padding: 6px 12px;
        margin-right: 2px;
    }}
    QTabBar::tab:hover {{ color: {c["text"]}; background: {c["hover"]}; }}
    QTabBar::tab:selected {{
        background: {c["input_surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        border-bottom-color: {c["input_surface"]};
    }}

    /* Scrollbars. Thin, no arrow buttons — the buttons are a hit target nobody
       uses and they cost 32px of a 12px-wide bar. */
    QScrollBar:vertical {{ background: transparent; width: 12px; margin: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 0; }}
    QScrollBar::handle:vertical, QScrollBar::handle:horizontal {{
        background: {c["border"]};
        border-radius: 5px;
        min-height: 28px;
        min-width: 28px;
        margin: 2px;
    }}
    QScrollBar::handle:hover {{ background: {c["muted"]}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    /* Grouping and separators */
    QGroupBox {{
        border: 1px solid {c["border"]};
        border-radius: 4px;
        margin-top: 10px;
        padding-top: 8px;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 8px;
        padding: 0 4px;
        color: {c["section_header"]};
    }}
    QSplitter::handle {{ background: {c["border"]}; }}
    QSplitter::handle:horizontal {{ width: 1px; }}
    QSplitter::handle:vertical {{ height: 1px; }}
    QFrame[frameShape="4"], QFrame[frameShape="5"] {{ color: {c["border"]}; }}

    /* Menus and toolbars */
    QMenuBar {{ background: {c["surface"]}; color: {c["text"]}; }}
    QMenuBar::item {{ background: transparent; padding: 5px 9px; }}
    QMenuBar::item:selected {{ background: {c["hover"]}; }}
    QMenu {{
        background: {c["input_surface"]};
        color: {c["text"]};
        border: 1px solid {c["border"]};
        padding: 4px;
    }}
    QMenu::item {{ padding: 5px 22px; border-radius: 3px; }}
    QMenu::item:selected {{ background: {c["selection"]}; color: {c["selection_text"]}; }}
    QMenu::separator {{ height: 1px; background: {c["border"]}; margin: 4px 6px; }}
    QToolBar {{
        background: {c["surface"]};
        border: none;
        border-bottom: 1px solid {c["border"]};
        spacing: 4px;
        padding: 3px;
    }}
    QToolBar::separator {{ width: 1px; background: {c["border"]}; margin: 4px 3px; }}
    QStatusBar {{ background: {c["surface"]}; color: {c["muted"]}; }}
    QStatusBar::item {{ border: none; }}

    /* Progress and sliders */
    QProgressBar {{
        border: 1px solid {c["border"]};
        border-radius: 4px;
        color: {c["meter_text"]};
    }}
    QProgressBar::chunk {{ border-radius: 3px; }}
    QSlider::groove:horizontal {{
        background: {c["input_surface"]};
        border: 1px solid {c["border"]};
        height: 4px;
        border-radius: 2px;
    }}
    QSlider::handle:horizontal {{
        background: {c["selection"]};
        border: none;
        width: 12px;
        margin: -5px 0;
        border-radius: 6px;
    }}
    """


def apply(app: QApplication, v: Variant | None = None) -> None:
    """Put a variant on the application. Safe to call again to switch."""
    global _variant
    if v is not None:
        _variant = v

    # Fusion, always, and this is the single most consequential line in the file.
    # Qt's native styles — `windows11`, `macos` — route many colours through the
    # platform theme and quietly ignore both the palette and large parts of the
    # stylesheet, so a toolkit that themes itself has to opt out of them. It is
    # the same decision a Tk build of this would make in pinning `clam`, and it
    # is the reason a LunaPY window looks the same on every desktop instead of
    # looking themed on one and half-themed on the next.
    app.setStyle("Fusion")
    app.setPalette(qpalette(_variant))
    app.setStyleSheet(qss(_variant))
    _loaded.clear()


# The theme currently loaded from a file, if any. Kept so `loaded()` can answer
# "what is on screen" — an application with a theme switcher needs to tick the
# right entry in its menu, and asking the stylesheet is not an answer.
_loaded: dict[str, object] = {}


def apply_theme(app: QApplication, loaded_theme: "Theme", v: Variant | None = None) -> None:
    """Apply a theme loaded from a file, over a base variant.

    The theme's palette overrides sit on top of the base column rather than
    replacing it, so a file that sets three colours is a valid theme. Requiring
    every key would mean every theme on disk breaks the day a key is added to
    the kit — the same argument `themes` makes for skipping unknown tokens
    instead of refusing the file.

    Its rule block is appended **after** the generated stylesheet, so a theme
    that wants to restate something the kit already styles wins. QSS resolves
    later rules of equal specificity last, which is the behaviour a theme author
    expects from having written CSS before.
    """
    global _variant
    if v is not None:
        _variant = v

    colours = loaded_theme.column(_variant)
    app.setStyle("Fusion")
    app.setPalette(qpalette(_variant, colours))
    app.setStyleSheet(
        qss(
            _variant,
            colours,
            mono_font=loaded_theme.fonts.get("mono_font", MONO_FONT),
            hint_size=loaded_theme.sizes.get("hint_font_size", HINT_FONT_SIZE),
            header_size=loaded_theme.sizes.get("header_font_size", HEADER_FONT_SIZE),
        )
        + "\n"
        + loaded_theme.rules
    )
    _loaded.clear()
    _loaded["theme"] = loaded_theme


def loaded() -> "Theme | None":
    """The theme loaded from a file, or `None` if the built-in palette is in force."""
    return _loaded.get("theme")  # type: ignore[return-value]


def set_style_key(widget: QWidget, key: str | None) -> QWidget:
    """Give a widget a style key, and make Qt actually notice.

    **The repolish is the entire point of this function existing.** Setting the
    property alone works before the widget is first shown and silently does
    nothing after, because Qt resolves stylesheet rules once at polish time and
    a property change is not a signal it watches. Measured: a label given
    `section_header` after being shown keeps rendering at the plain text colour
    (`#848287`) until it is unpolished and polished again, at which point it
    becomes `#0905fe` in the probe palette. See `docs/LunaPY.md` §3.2.

    This is the mirror image of LunaP §12.3 rather than a port of it. There, the
    hazard was that swapping the application's styles *stripped* controls that
    were already realized, so a theme switch needed `Restyle(root)`. Qt
    re-polishes live widgets on `setStyleSheet` by itself, so theme switching
    here is free — and the trap moved to the per-widget case instead. Same class
    of bug, opposite trigger, which is why both projects need a repolish helper
    and neither one's reasoning transfers.
    """
    widget.setProperty(STYLE_KEY, key)
    restyle(widget)
    return widget


def set_load(widget: QWidget, percent: float) -> LoadLevel:
    """Style a meter by what its number means, and return the band it landed in."""
    band = level_for(percent)
    set_style_key(widget, band.value)
    return band


def restyle(widget: QWidget, recursive: bool = False) -> None:
    """Re-run the style pass on a widget whose selectors may now match differently.

    `recursive` walks children too. It is off by default because the common
    caller is `set_style_key`, which changed exactly one widget, and unpolishing
    a large tree is visible work — Qt tears down and rebuilds every child's
    style data. Pass it when you have changed something an ancestor selector
    depends on, where the children's rules really did change with it.
    """
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    if recursive:
        for child in widget.findChildren(QWidget):
            style.unpolish(child)
            style.polish(child)
    widget.update()
