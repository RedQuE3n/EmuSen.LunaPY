"""The input half of the kit: things you operate.

The recurring theme in this file is **a selection change that is a real user
choice, versus one the program caused by rebuilding the list.** Every widget
here that holds a selection draws that line, because a handler that cannot tell
the difference re-runs the user's last action every time the data refreshes —
which is the bug `Suppressor` was extracted for (LunaP §21.1).
"""

from __future__ import annotations

from typing import Any, Callable, Generic, Iterable, Sequence, TypeVar

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QTabWidget,
    QWidget,
)

from .fluent import row, tune
from .threading import Suppressor

T = TypeVar("T")


class LunaList(QListWidget, Generic[T]):
    """A list that keeps hold of the type it was given.

    Five places in LunaP projected a model to a string, put the strings in a
    list box, and kept a parallel array to map the selected index back. One then
    parsed the label apart again to recover a field it already had::

        SystemsList.ItemsSource = systems.Select(s => $"{s.System}  ({s.Count})")
        // The list label carries its own count, so the name has to come back off it

    **Parsing a display string to recover a model field is the shape of a
    missing control.**

    Takes projections, not an interface. A list demanding an `IListItem` would
    be a list only an application that had adopted LunaPY's vocabulary could
    use — §1's rule again.
    """

    #: Emitted only for a real user choice, never for a selection restored
    #: during `refresh`.
    chose = Signal(object)

    def __init__(
        self,
        label: Callable[[T], str] | None = None,
        key: Callable[[T], Any] | None = None,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        #: What each row reads as. Defaults to `str`, so a list of strings needs
        #: no ceremony.
        self.label: Callable[[T], str] = label or (lambda item: str(item))
        #: What makes two items "the same item" across a refresh. Defaults to
        #: the item itself, which is right for a cached model and wrong for rows
        #: rebuilt from storage on every poll — those need a real key, and the
        #: whole point of `refresh` is that it then works.
        self.key: Callable[[T], Any] = key or (lambda item: item)

        self._models: list[T] = []
        self._filling = Suppressor()
        self.currentRowChanged.connect(self._on_row_changed)

    @property
    def models(self) -> list[T]:
        """Not `items`, which would collide with `QListWidget.item` and leave
        two names meaning different things depending on which type the caller
        happens to be holding."""
        return list(self._models)

    @property
    def selected(self) -> T | None:
        """The selected model, not the row. This is the whole point: no shadow
        array, no index arithmetic, nothing to parse out of a label."""
        index = self.currentRow()
        return self._models[index] if 0 <= index < len(self._models) else None

    def refresh(self, items: Iterable[T]) -> None:
        """Replace the contents **and put the selection back**.

        That second half is the other thing the hand-rolled versions were doing,
        and LunaP §21.1 found three sites writing the dance separately. It
        belongs in one place because "rebuild the list" and "keep the selection"
        are one operation that only looks like two.
        """
        previous = self.selected
        wanted = self.key(previous) if previous is not None else None

        self._models = list(items)
        with self._filling.suppress():
            self.clear()
            for item in self._models:
                self.addItem(self.label(item))
            # -1 when the previously selected item is gone, which is a real
            # answer: the row it named no longer exists, and selecting its
            # neighbour would be a guess.
            self.setCurrentRow(self._index_of(wanted) if wanted is not None else -1)

    def select(self, item: T | None) -> None:
        """Select by model rather than by index. Does not emit `chose` — a
        caller setting the selection already knows what it set."""
        with self._filling.suppress():
            self.setCurrentRow(-1 if item is None else self._index_of(self.key(item)))

    def _index_of(self, wanted_key: Any) -> int:
        for index, item in enumerate(self._models):
            if self.key(item) == wanted_key:
                return index
        return -1

    def _on_row_changed(self, _row: int) -> None:
        if not self._filling.is_suppressing:
            self.chose.emit(self.selected)


class Dropdown(QComboBox):
    """A combo box whose selection change is a plain callback, and which can be
    refilled without pretending the user did it."""

    chose = Signal(object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._values: list[Any] = []
        self._filling = Suppressor()
        self.currentIndexChanged.connect(self._on_index_changed)

    @property
    def selected(self) -> Any | None:
        index = self.currentIndex()
        return self._values[index] if 0 <= index < len(self._values) else None

    def fill(
        self,
        items: Sequence[Any],
        selected: Any = None,
        label: Callable[[Any], str] | None = None,
    ) -> None:
        """Replace the items and the selection together, without `chose` firing
        for the reset."""
        to_text = label or (lambda item: str(item))
        self._values = list(items)
        with self._filling.suppress():
            self.clear()
            for item in self._values:
                self.addItem(to_text(item))
            self.setCurrentIndex(self._values.index(selected) if selected in self._values else -1)

    def _on_index_changed(self, _index: int) -> None:
        if not self._filling.is_suppressing:
            self.chose.emit(self.selected)


class LunaSwitch(QCheckBox):
    """An on/off control with its label beside it.

    **Qt has no toggle switch, and this does not pretend otherwise.** LunaP
    wraps Avalonia's `ToggleSwitch`; Qt's nearest honest equivalent is a check
    box, so that is what this is. Faking a switch would mean a custom-painted
    control with its own accessibility story to get wrong, to buy an appearance
    — and LunaP §24.1 measured what that costs: its switch put the label in
    `OnContent`/`OffContent`, left `Content` null, and every switch on a
    settings page announced as an unnamed button.

    A `QCheckBox` carries its label natively and reports itself correctly, so
    the entire class of problem does not arise here.
    """

    def __init__(self, label: str = "", parent: QWidget | None = None):
        super().__init__(label, parent)

    def set_label(self, label: str) -> None:
        self.setText(label)


class Tabs(QTabWidget):
    """A tab widget with the two chores the frontends hand-wrote."""

    def add(self, header: str, content: QWidget) -> int:
        return self.addTab(content, header)

    def remove_from(self, index: int) -> None:
        """Drop everything after the tabs declared up front, for a set rebuilt
        when the underlying collection changes."""
        while self.count() > index:
            self.removeTab(self.count() - 1)


class ButtonBar(QWidget):
    """A right-aligned run of buttons, for the bottom of a window.

    **Reported as a toolbar, not a list**, and the correction is worth the line.
    A generic items control announces as a list, so a row of OK/Cancel buttons
    reads as a list of two items — inviting a reader to navigate it as data
    rather than to press one of them. Toolbar is the accessibility vocabulary
    for exactly this: a run of commands. LunaP §24.2.
    """

    def __init__(self, *buttons: QWidget, parent: QWidget | None = None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(6)
        self._layout.addStretch(1)
        for button in buttons:
            self._layout.addWidget(button)
        self.setAccessibleName("Actions")

    def add(self, button: QWidget) -> QWidget:
        self._layout.addWidget(button)
        return button

    @property
    def buttons(self) -> list[QWidget]:
        return [
            self._layout.itemAt(i).widget()
            for i in range(self._layout.count())
            if self._layout.itemAt(i).widget() is not None
        ]


class StatusBar(QWidget):
    """The bottom strip: a message on the left, actions on the right.

    **The one place in the toolkit where text arrives to be read rather than
    found.** "Applied 12 cheats", "Save failed" — a sighted user catches that
    from the corner of their eye without going to look for it, and the
    equivalent for a reader is a live region.

    It is a default rather than a rule: a status line updating twice a second is
    a live region that never shuts up, so `set_live(False)` turns it off.
    """

    def __init__(self, status: str = "", parent: QWidget | None = None):
        super().__init__(parent)
        self._label = QLabel(status)
        self._actions = ButtonBar()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._label)
        layout.addStretch(1)
        layout.addWidget(self._actions)
        self._live = True
        self.set_status(status)

    def set_status(self, status: str) -> None:
        self._label.setText(status)
        # The message is what this control *is*, so it is the name rather than
        # a description. There is nothing else it could be called.
        self.setAccessibleName(status)
        if self._live:
            self._announce()

    @property
    def status(self) -> str:
        return self._label.text()

    @property
    def actions(self) -> ButtonBar:
        return self._actions

    def set_live(self, live: bool) -> None:
        self._live = live

    @property
    def is_live(self) -> bool:
        return self._live

    def _announce(self) -> None:
        # Qt's accessibility update is how a live region reaches a reader. It is
        # a no-op when nothing is listening, which is why this is safe to call
        # on every status change including under the offscreen platform.
        from PySide6.QtGui import QAccessible, QAccessibleEvent

        QAccessible.updateAccessibility(
            QAccessibleEvent(self, QAccessible.Event.NameChanged)
        )
