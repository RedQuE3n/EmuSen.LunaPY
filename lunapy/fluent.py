"""Terse constructors for the layouts and controls a window is made of.

This is LunaP's `Fluent/Ui.cs` and `Fluent/LayoutExtensions.cs`, and it is the
one part of the port where Python is straightforwardly better. C# needed
extension methods to get `label.Width(80).Left()`, because you cannot add
arguments to an object after you have constructed it. Python can: keyword
arguments do the whole job, so the two files collapse into one and the chain
`Ui.Row(6, label.Width(80), entry.Grow())` becomes

    row(text("Volume", width=80), field, spacing=6)

`tune` exists for the other half of that — a widget you did not construct here,
a `QTreeView` or somebody's own subclass, which still needs the same vocabulary
applied to it. Every keyword in `tune` names the Qt call it makes, so there is
one vocabulary whether you built the widget or inherited it.

**Everything here returns a plain `QWidget`.** Containers are a widget with a
layout on them rather than a bare `QLayout`, so a container nests inside another
container with no special case, and `stack(row(...), row(...))` needs nobody to
know which of the two they are holding.
"""

from __future__ import annotations

from typing import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme

# Where `tune(w, align=...)` and `tune(w, dock=...)` park their answers until a
# container reads them. Qt has no per-widget alignment or dock side — both are
# properties of the *layout item*, which does not exist until the widget is
# added to something. Storing the intent on the widget lets a caller express it
# at construction time, which is the whole point of a fluent surface.
_ALIGN = "_luna_align"
_DOCK = "_luna_dock"

_ALIGNMENTS = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "right": Qt.AlignmentFlag.AlignRight,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "top": Qt.AlignmentFlag.AlignTop,
    "bottom": Qt.AlignmentFlag.AlignBottom,
    "middle": Qt.AlignmentFlag.AlignVCenter,
}


def tune(widget: QWidget, **props) -> QWidget:
    """Apply layout and accessibility properties to any widget, and return it.

    Unknown keywords raise rather than being ignored. A silently dropped
    `witdh=80` is a layout that is subtly wrong and gives no reason, which costs
    far more to find than the typo cost to make.
    """
    for name, value in props.items():
        if name == "width":
            widget.setFixedWidth(value)
        elif name == "height":
            widget.setFixedHeight(value)
        elif name == "min_size":
            widget.setMinimumSize(*value)
        elif name == "max_height":
            widget.setMaximumHeight(value)
        elif name == "max_width":
            widget.setMaximumWidth(value)
        elif name == "grow":
            policy = QSizePolicy.Policy.Expanding if value else QSizePolicy.Policy.Preferred
            widget.setSizePolicy(policy, widget.sizePolicy().verticalPolicy())
        elif name == "grow_v":
            policy = QSizePolicy.Policy.Expanding if value else QSizePolicy.Policy.Preferred
            widget.setSizePolicy(widget.sizePolicy().horizontalPolicy(), policy)
        elif name == "align":
            if value not in _ALIGNMENTS:
                raise ValueError(f"align={value!r}; expected one of {sorted(_ALIGNMENTS)}")
            widget.setProperty(_ALIGN, value)
        elif name == "dock":
            if value not in ("top", "bottom", "left", "right"):
                raise ValueError(f"dock={value!r}; expected top, bottom, left or right")
            widget.setProperty(_DOCK, value)
        elif name == "visible":
            widget.setVisible(value)
        elif name == "name":
            widget.setObjectName(value)
        elif name == "tooltip":
            widget.setToolTip(value)
        elif name == "style_key":
            theme.set_style_key(widget, value)
        elif name == "wrap":
            widget.setWordWrap(value)
        elif name == "bold":
            font = widget.font()
            font.setBold(value)
            widget.setFont(font)
        elif name == "font_size":
            font = widget.font()
            font.setPointSize(value)
            widget.setFont(font)
        # Accessibility is a keyword rather than a separate call on purpose. It
        # is not a thing you remember to go back and add — LunaP §24 is what
        # happens when it is.
        elif name == "accessible_name":
            widget.setAccessibleName(value)
        elif name == "help_text":
            widget.setAccessibleDescription(value)
        else:
            raise TypeError(f"tune() got an unexpected keyword {name!r}")
    return widget


def _add(layout, child: QWidget) -> None:
    """Add a child, honouring the alignment it was tuned with."""
    align = child.property(_ALIGN)
    if align:
        layout.addWidget(child, 0, _ALIGNMENTS[align])
    else:
        layout.addWidget(child)


def _box(layout_type, children: Iterable[QWidget], spacing: int, margin: int, **props) -> QWidget:
    host = QWidget()
    layout = layout_type(host)
    layout.setSpacing(spacing)
    layout.setContentsMargins(margin, margin, margin, margin)
    for child in children:
        _add(layout, child)
    return tune(host, **props) if props else host


def stack(*children: QWidget, spacing: int = 0, margin: int = 0, **props) -> QWidget:
    """Children top to bottom."""
    return _box(QVBoxLayout, children, spacing, margin, **props)


def row(*children: QWidget, spacing: int = 0, margin: int = 0, **props) -> QWidget:
    """Children left to right."""
    return _box(QHBoxLayout, children, spacing, margin, **props)


def dock(*children: QWidget, spacing: int = 0, margin: int = 0, **props) -> QWidget:
    """Each child consumes an edge in order; the last one fills what is left.

    This reproduces Avalonia's `DockPanel` semantics rather than approximating
    them, and the difference shows up the moment somebody docks two things to
    the same side. Docking top, then left, then top again should put the second
    top strip *below* the left sidebar's top edge, because the sidebar already
    took its slice out of the middle. A flat implementation — one vertical box
    for the top/bottom docks, one horizontal for left/right — gets that case
    wrong, so this nests instead: every child wraps the remainder of the list.

    Qt has no `DockPanel`. `QDockWidget` is a different thing entirely (a
    floating, user-draggable panel around a `QMainWindow`) and is not what this
    is for.
    """
    children = list(children)
    if not children:
        return QWidget()

    def build(index: int) -> QWidget:
        child = children[index]
        if index == len(children) - 1:
            return child  # the filler

        side = child.property(_DOCK) or "top"
        rest = build(index + 1)
        vertical = side in ("top", "bottom")
        host = QWidget()
        layout = (QVBoxLayout if vertical else QHBoxLayout)(host)
        layout.setSpacing(spacing)
        layout.setContentsMargins(0, 0, 0, 0)
        first, second = (child, rest) if side in ("top", "left") else (rest, child)
        layout.addWidget(first)
        layout.addWidget(second)
        # The remainder gets the stretch, which is what "the last child fills"
        # means once the panel is expressed as nested boxes.
        layout.setStretch(0 if second is child else 1, 1)
        return host

    outer = QWidget()
    shell = QVBoxLayout(outer)
    shell.setContentsMargins(margin, margin, margin, margin)
    shell.addWidget(build(0))
    return tune(outer, **props) if props else outer


def _apply_spec(spec: str, set_stretch, set_minimum) -> int:
    """Parse an Avalonia-style track spec: `"Auto,*,2*,120"`.

    `Auto` sizes to content, `*` takes a share of what is left, `2*` takes twice
    that share, and a bare number is a fixed size in pixels. Kept identical to
    the string LunaP already uses so a layout can be read across both projects
    without translating it.
    """
    tracks = [t.strip() for t in spec.split(",") if t.strip()]
    for i, track in enumerate(tracks):
        if track.lower() == "auto":
            set_stretch(i, 0)
        elif track.endswith("*"):
            weight = track[:-1]
            set_stretch(i, int(weight) if weight else 1)
        else:
            set_stretch(i, 0)
            set_minimum(i, int(track))
    return len(tracks)


def cols(spec: str, *children: QWidget, spacing: int = 0, margin: int = 0, **props) -> QWidget:
    """Children left to right into the tracks named by `spec`, one each."""
    host = QWidget()
    grid = QGridLayout(host)
    grid.setSpacing(spacing)
    grid.setContentsMargins(margin, margin, margin, margin)
    _apply_spec(spec, grid.setColumnStretch, grid.setColumnMinimumWidth)
    for i, child in enumerate(children):
        align = child.property(_ALIGN)
        if align:
            grid.addWidget(child, 0, i, _ALIGNMENTS[align])
        else:
            grid.addWidget(child, 0, i)
    return tune(host, **props) if props else host


def rows(spec: str, *children: QWidget, spacing: int = 0, margin: int = 0, **props) -> QWidget:
    """Children top to bottom into the tracks named by `spec`, one each.

    The column half existed in LunaP first and the row half was added later;
    §21.2 records that a header-and-body table had been keeping two column
    strings in step by hand in the meantime. Both are here from the start.
    """
    host = QWidget()
    grid = QGridLayout(host)
    grid.setSpacing(spacing)
    grid.setContentsMargins(margin, margin, margin, margin)
    _apply_spec(spec, grid.setRowStretch, grid.setRowMinimumHeight)
    for i, child in enumerate(children):
        align = child.property(_ALIGN)
        if align:
            grid.addWidget(child, i, 0, _ALIGNMENTS[align])
        else:
            grid.addWidget(child, i, 0)
    return tune(host, **props) if props else host


def scroll(content: QWidget, **props) -> QScrollArea:
    """A scroll area that actually resizes its content.

    `setWidgetResizable(True)` is not a default and its absence is the single
    most common Qt scroll-area bug: without it the content keeps its size hint
    forever, so a panel that should fill the width sits in a narrow column on
    the left and nothing about the code says why.
    """
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setWidget(content)
    return tune(area, **props) if props else area


def section(header_text: str, *content: QWidget, spacing: int = 8, **props) -> QWidget:
    """A section header and its content, at the 8px gap the dashboards settled on.

    Takes any number of children. LunaP's first version took exactly one, and
    §21.2 records the consequence: eight places wrote a bold label by hand
    rather than use the helper at all, because they had two things to put in a
    section and the helper could not hold them.
    """
    return stack(header(header_text), *content, spacing=spacing, **props)


def _label(text_value: str, style_key: str | None, **props) -> QLabel:
    label = QLabel(text_value)
    if style_key:
        # Set before the first polish, so no repolish is needed. `set_style_key`
        # is for the widget that is already on screen; see `theme.set_style_key`.
        label.setProperty(theme.STYLE_KEY, style_key)
    return tune(label, **props) if props else label


def header(text_value: str, **props) -> QLabel:
    return _label(text_value, "section_header", **props)


def hint(text_value: str, **props) -> QLabel:
    return _label(text_value, "hint", **props)


def mono(text_value: str = "", **props) -> QLabel:
    return _label(text_value, "mono", **props)


def text(text_value: str = "", **props) -> QLabel:
    return _label(text_value, None, **props)


def button(label: str, on_click: Callable[[], None] | None = None, **props) -> QPushButton:
    """A button and what it does, in one expression.

    `on_click` takes no arguments. Qt hands a `checked` flag to `clicked`, which
    almost no caller wants and which turns into a confusing `TypeError` in a
    lambda somebody wrote in a hurry, so it is swallowed here.
    """
    widget = QPushButton(label)
    if on_click is not None:
        widget.clicked.connect(lambda _checked=False: on_click())
    return tune(widget, **props) if props else widget
