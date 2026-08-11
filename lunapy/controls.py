"""The display half of the kit: things that show you something.

Every control here takes **plain data or a callable**, never an interface of
LunaPY's. A meter row takes `(str, float, str)`; it can never take your
telemetry type. That is §1's rule expressed one control at a time, and it is
what stops a kit becoming usable only by an application that has adopted its
vocabulary.

These are compositions rather than templated controls, which is most of why this
file is a fraction of the size of LunaP's `Controls/`. Avalonia needed a
`TemplatedControl` plus a `ControlTheme` in XAML plus a `StyleKeyOverride` for
each one — and LunaP §5.5 and §14.1 record the style-key trap biting twice. A
`QWidget` with a layout and a stylesheet rule has no equivalent hazard, because
there is no template to fail to find.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from . import theme
from .fluent import hint, row, stack, text, tune
from .palette import LoadLevel, level_for


class MeterRow(QWidget):
    """One row of a load dashboard: a label, a bar, and a value.

    `value_text` is shown verbatim, and the caller decides whether that is
    "62.0%" or "13/128". It is deliberately **not** derived from `percent`: half
    the uses are counts rather than proportions, and a row showing 13 of 128
    slots sets `percent` to 10 for the bar's length while the text says
    "13/128".

    That is also why the accessible name is the label and the value text is the
    *description* rather than a range value. A reader announcing "10 percent"
    over the top of "13 of 128" would be saying a number the caller never asked
    for, and for the counting half of the uses it is simply wrong.
    """

    def __init__(self, label: str = "", percent: float = 0.0, value_text: str = ""):
        super().__init__()
        self._label = QLabel(label)
        self._bar = QProgressBar()
        self._bar.setRange(0, 100)
        self._bar.setTextVisible(False)
        self._value = QLabel(value_text)

        # Built directly on `self` rather than by taking `row(...).layout()`.
        # That shortcut is the §3.3 lifetime hazard in one line: the widget
        # `row` returns is a temporary, so moving its layout here leaves nothing
        # holding the container, CPython collects it, and the C++ destructor
        # takes the three children with it. The next touch of `self._bar` raises
        # "Internal C++ object already deleted" — which is how this was found,
        # after the hazard had been written down and cited.
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addWidget(tune(self._label, width=120))
        layout.addWidget(tune(self._bar, grow=True))
        layout.addWidget(tune(self._value, width=72), 0, Qt.AlignmentFlag.AlignRight)

        self.set_label(label)
        self.set_percent(percent)
        self.set_value_text(value_text)

    def set_label(self, label: str) -> None:
        self._label.setText(label)
        # A meter reads as one bar named for what it measures, not as a group
        # containing an anonymous one — so the name goes on the widget and the
        # inner QProgressBar is left unnamed rather than announcing itself as a
        # second, nameless node saying the same thing.
        self.setAccessibleName(label)

    def set_percent(self, percent: float) -> LoadLevel:
        """Set the bar and its colour. Returns the band it landed in."""
        self._bar.setValue(max(0, min(100, int(percent))))
        return theme.set_load(self._bar, percent)

    def set_value_text(self, value_text: str) -> None:
        self._value.setText(value_text)
        self.setAccessibleDescription(value_text)

    @property
    def level(self) -> LoadLevel:
        return level_for(self._bar.value())


@dataclass(frozen=True)
class MeterEntry:
    """One meter, as plain data. The layering rule is why this exists rather
    than `MeterList` taking your own type."""

    label: str
    percent: float
    value_text: str = ""


class MeterList(QWidget):
    """A vertical run of meters.

    Grouping stays with the caller. What a run of meters is *about* — "Core
    load", "Audio" — is the caller's vocabulary, and a toolkit that supplied
    group headings would be guessing at domain language. `setAccessibleName` is
    where the caller says.

    Rebuilt wholesale rather than diffed. A dashboard has single-digit rows and
    refreshes a few times a second; diffing would be more code, more state and
    more ways to be wrong, to save work that does not register.
    """

    def __init__(self, meters: Sequence[MeterEntry] = ()):
        super().__init__()
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(4)
        self._rows: list[MeterRow] = []
        self.set_meters(meters)

    def set_meters(self, meters: Sequence[MeterEntry]) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item.widget() is not None:
                item.widget().deleteLater()
        self._rows = []
        for entry in meters:
            meter = MeterRow(entry.label, entry.percent, entry.value_text)
            self._rows.append(meter)
            self._layout.addWidget(meter)

    @property
    def rows(self) -> list[MeterRow]:
        return list(self._rows)


class EmptyState(QWidget):
    """"There is nothing here, and here is why."

    Two lines because every hand-rolled version wanted both: what is missing,
    and what would put something there. `detail` is optional and hides when
    empty, so a bare "No results" leaves no gap.

    Not a `hint`, and the distinction matters. A hint is an aside *under*
    something else and is 11pt by definition; an empty state **is** the
    something else — it is the window's whole content when there is nothing to
    show. LunaP §22.9 drew that line after finding a consumer explaining in a
    comment why it could not use the hint style.

    **This was the sharpest case in LunaP's accessibility pass** (§24.1): the
    one control whose entire job is explaining why a window is empty was the one
    thing a screen reader could not see, because both its lines were template
    parts and the control had no peer to speak for them. A sighted user got "No
    cores loaded — open a ROM to begin"; a reader got silence and an apparently
    empty window. Qt has no equivalent hazard — the labels are real children and
    are in the tree — but the name is set explicitly anyway, so the control
    announces as one thing rather than as two loose strings.
    """

    def __init__(self, message: str = "", detail: str = ""):
        super().__init__()
        self._message = QLabel(message)
        self._message.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._message.setWordWrap(True)
        self._detail = hint(detail, wrap=True)
        self._detail.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout = QVBoxLayout(self)
        layout.setSpacing(6)
        layout.addStretch(1)
        layout.addWidget(self._message)
        layout.addWidget(self._detail)
        layout.addStretch(1)

        self.set_message(message)
        self.set_detail(detail)

    def set_message(self, message: str) -> None:
        self._message.setText(message)
        self.setAccessibleName(message)

    def set_detail(self, detail: str) -> None:
        self._detail.setText(detail)
        self._detail.setVisible(bool(detail.strip()))
        self.setAccessibleDescription(detail)

    @property
    def has_detail(self) -> bool:
        # `isHidden`, not `isVisible`. A widget whose window has not been shown
        # reports isVisible() == False whatever you asked for, so the obvious
        # spelling answers "is my parent on screen" rather than "did I hide
        # this deliberately" — and every test on an unshown control fails for a
        # reason that has nothing to do with the control.
        return not self._detail.isHidden()


class FieldRow(QWidget):
    """A settings field: a label, an optional grey explanation, and your control.

    **The field's label is a sibling of the thing it labels, which is the
    problem this solves.** A caller writes `FieldRow("Save folder", QLineEdit())`.
    The line edit is what the keyboard lands on and it has no name of its own;
    the words live in a label next door, which a screen reader has no reason to
    associate with it. LunaP measured exactly this before fixing it: tabbing
    through a settings window reached five text boxes and every one announced as
    an unnamed edit field (§24.1).

    `setBuddy` is Qt's own answer and is used rather than writing the name onto
    the caller's widget, because it does not overwrite anything — a caller who
    has already named their widget keeps that name. Setting the name directly
    would silently win that argument with no way to say "no, mine".
    """

    def __init__(self, label: str = "", content: QWidget | None = None, field_hint: str = ""):
        super().__init__()
        self._label = QLabel(label)
        self._label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)
        self._hint = hint(field_hint, wrap=True)
        self._content = content or QWidget()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(row(tune(self._label, width=140), tune(self._content, grow=True), spacing=8))
        layout.addWidget(self._hint)

        self.set_label(label)
        self.set_hint(field_hint)

    def set_label(self, label: str) -> None:
        self._label.setText(label)
        self.setAccessibleName(label)
        self._pair_label_to_content()

    def set_hint(self, field_hint: str) -> None:
        """Left empty, the hint collapses rather than reserving blank space."""
        self._hint.setText(field_hint)
        self._hint.setVisible(bool(field_hint.strip()))
        self.setAccessibleDescription(field_hint)

    @property
    def content(self) -> QWidget:
        return self._content

    @property
    def has_hint(self) -> bool:
        # `isHidden`, not `isVisible` — see EmptyState.has_detail.
        return not self._hint.isHidden()

    def _pair_label_to_content(self) -> None:
        self._label.setBuddy(self._content)


class RgbaImageView(QWidget):
    """Shows a raw RGBA8888 buffer, reusing its image across frames.

    **Unnamed on purpose.** This shows a live buffer of pixels — a rendered
    page, a game frame — and only the caller knows what is in it. A
    toolkit-supplied name would be a guess presented as a description, which is
    worse for a reader than an image the toolkit admits it cannot describe: a
    wrong alt text is believed, a missing one is asked about.
    `setAccessibleName` is where the caller says.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._label = QLabel(self)
        self._label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        self._size: tuple[int, int] = (0, 0)

    def set_frame(self, rgba: bytes, width: int, height: int) -> bool:
        """Show a buffer. A 0x0 or short buffer clears rather than raising —
        a source with nothing to show reports exactly that, and it is not an
        error for it to say so."""
        if width <= 0 or height <= 0 or len(rgba) < width * height * 4:
            self.clear()
            return False

        # The bytes must outlive the QImage: QImage over a buffer does not copy,
        # and a frame built from a temporary would show freed memory. `copy()`
        # is what makes the pixels ours.
        image = QImage(rgba, width, height, width * 4, QImage.Format.Format_RGBA8888).copy()
        self._label.setPixmap(QPixmap.fromImage(image))
        self._size = (width, height)
        return True

    def clear(self) -> None:
        self._label.clear()
        self._size = (0, 0)

    @property
    def frame_size(self) -> tuple[int, int]:
        return self._size
