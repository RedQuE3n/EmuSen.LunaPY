"""Composite panes: a filter bar, a path picker, a console.

Each of these is a small arrangement of widgets plus one behaviour that every
hand-rolled version got slightly differently. The behaviour is the reason they
are here; the arrangement is incidental.
"""

from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from .fluent import tune
from .threading import Debounce, Suppressor
from .widgets import Dropdown


class FilterBar(QWidget):
    """A search box, optionally preceded by a labelled facet dropdown.

    **`search_delay_ms` defaults to 0, and that is a compatibility decision
    rather than a preference.** Zero raises `changed` on every keystroke, which
    is what a filter over ten rows should do. Two LunaP consumers wanted it
    non-zero and both re-read storage on every keystroke without it (§21.1) —
    neither is wrong at ten entries and both are wrong at ten thousand.

    Zero is a real state, not a zero-length timer. A timer with a zero interval
    still defers to the next event-loop pass, which would turn a documented
    "synchronous" into "one frame later" for every existing caller.

    `search_text` updates on every keystroke regardless; only the notification
    waits. A caller reading the text in response to something else always sees
    what is actually in the box.
    """

    changed = Signal()
    submitted = Signal()

    def __init__(
        self,
        placeholder: str = "Search",
        facet_label: str = "",
        search_delay_ms: int = 0,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._filling = Suppressor()
        self._debounce: Debounce | None = None

        self._facet_label = QLabel(facet_label)
        self._facet = Dropdown()
        self._search = QLineEdit()
        self._search.setPlaceholderText(placeholder)
        self._search.setAccessibleName(placeholder)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(self._facet_label)
        layout.addWidget(self._facet)
        layout.addWidget(self._search)

        self.set_facet_visible(bool(facet_label))
        self.set_search_delay(search_delay_ms)

        self._search.textChanged.connect(self._on_typed)
        self._search.returnPressed.connect(self._on_return)
        self._facet.chose.connect(lambda _value: self._emit_changed())

    # -- Text ------------------------------------------------------------

    @property
    def search_text(self) -> str:
        return self._search.text()

    def set_search_text(self, value: str, notify: bool = True) -> None:
        """Set the box's contents. `notify=False` sets it without pretending
        the user typed it — for a filter cleared by a Reset button, where
        re-running the search is the caller's decision, not this control's."""
        if notify:
            self._search.setText(value)
            return
        with self._filling.suppress():
            self._search.setText(value)

    # -- The facet -------------------------------------------------------

    @property
    def facet(self) -> Dropdown:
        return self._facet

    def set_facet_visible(self, visible: bool) -> None:
        self._facet_label.setVisible(visible)
        self._facet.setVisible(visible)

    def set_facet_label(self, label: str) -> None:
        self._facet_label.setText(label)
        self._facet.setAccessibleName(label)
        self._facet_label.setBuddy(self._facet)

    # -- Timing ----------------------------------------------------------

    def set_search_delay(self, delay_ms: int) -> None:
        if delay_ms <= 0:
            if self._debounce is not None:
                self._debounce.cancel()
            self._debounce = None
            return
        self._debounce = Debounce(delay_ms, self._emit_changed, self)

    @property
    def is_pending(self) -> bool:
        return self._debounce is not None and self._debounce.is_pending

    def _on_typed(self, _text: str) -> None:
        if self._filling.is_suppressing:
            return
        if self._debounce is None:
            self._emit_changed()
        else:
            self._debounce.poke()

    def _on_return(self) -> None:
        # Enter means "I am finished", so anything waiting runs now rather than
        # after a delay that would just feel slow.
        if self._debounce is not None:
            self._debounce.flush()
        self.submitted.emit()

    def _emit_changed(self) -> None:
        self.changed.emit()


class PathPickerRow(QWidget):
    """A label, a path box, and a Browse button.

    The box stays editable. A picker that only accepts what the dialog returns
    is a picker you cannot paste a path into, and pasting is how anybody with
    the path already in their clipboard expects to use it.
    """

    changed = Signal(str)

    def __init__(
        self,
        label: str = "",
        path: str = "",
        directory: bool = True,
        caption: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self._directory = directory
        self._caption = caption or label or ("Choose folder" if directory else "Choose file")

        self._label = QLabel(label)
        self._edit = QLineEdit(path)
        self._browse = QPushButton("Browse…")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        layout.addWidget(tune(self._label, width=140))
        layout.addWidget(self._edit)
        layout.addWidget(self._browse)

        self._label.setBuddy(self._edit)
        self._edit.setAccessibleName(label)
        self._browse.setAccessibleName(f"Browse for {label}" if label else "Browse")

        self._edit.textChanged.connect(self.changed.emit)
        self._browse.clicked.connect(self._on_browse)

    @property
    def path(self) -> str:
        return self._edit.text()

    def set_path(self, path: str) -> None:
        self._edit.setText(path)

    def _on_browse(self) -> None:
        if self._directory:
            chosen = QFileDialog.getExistingDirectory(self, self._caption, self.path)
        else:
            chosen, _filter = QFileDialog.getOpenFileName(self, self._caption, self.path)
        # An empty return means the dialog was cancelled, which must not clear a
        # path the user had already typed.
        if chosen:
            self.set_path(chosen)


class ConsolePane(QWidget):
    """A scrolling transcript and a command line.

    Takes a `Callable[[str], str]` — a line in, a response out — so this pane
    cannot know what your commands mean. That is the seam that lets one console
    serve a debugger, a REPL and a query tool.

    **Bounded, and that is not a detail.** A transcript with no limit is a
    memory leak with a scrollbar: a console attached to anything chatty grows
    until the process dies, and it dies during the long-running session where
    somebody actually needed the log. `max_lines` trims from the top.
    """

    def __init__(
        self,
        handler: Callable[[str], str] | None = None,
        prompt: str = "> ",
        max_lines: int = 2000,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.handler = handler
        self.prompt = prompt

        self._output = QPlainTextEdit()
        self._output.setReadOnly(True)
        self._output.setMaximumBlockCount(max_lines)
        self._output.setAccessibleName("Console output")

        self._input = QLineEdit()
        self._input.setAccessibleName("Console input")
        self._input.returnPressed.connect(self._on_return)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(self._output)
        layout.addWidget(self._input)

        self._history: list[str] = []
        self._history_index = 0

    def append(self, line: str) -> None:
        self._output.appendPlainText(line)
        # Follow the tail. Without this the view stays where it was and a
        # console that is being written to looks frozen.
        bar = self._output.verticalScrollBar()
        bar.setValue(bar.maximum())

    @property
    def text(self) -> str:
        return self._output.toPlainText()

    @property
    def history(self) -> list[str]:
        return list(self._history)

    def submit(self, line: str) -> None:
        """Run a line as though it had been typed. Public so a test, or a
        toolbar button, can drive the console without synthesising keystrokes."""
        if not line:
            return
        self._history.append(line)
        self._history_index = len(self._history)
        self.append(f"{self.prompt}{line}")

        if self.handler is None:
            return
        try:
            response = self.handler(line)
        except Exception as error:
            # A command that raises must not take the window with it. A console
            # exists to be typed into by somebody who does not yet know what
            # works, so a bad command is the normal case rather than a fault.
            self.append(f"error: {error}")
            return
        if response:
            self.append(response)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Up:
            self._recall(-1)
            event.accept()
            return
        if event.key() == Qt.Key.Key_Down:
            self._recall(1)
            event.accept()
            return
        super().keyPressEvent(event)

    def _recall(self, step: int) -> None:
        if not self._history:
            return
        self._history_index = max(0, min(len(self._history), self._history_index + step))
        if self._history_index == len(self._history):
            self._input.clear()
        else:
            self._input.setText(self._history[self._history_index])

    def _on_return(self) -> None:
        line = self._input.text().strip()
        self._input.clear()
        self.submit(line)
