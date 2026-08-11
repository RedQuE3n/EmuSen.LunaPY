"""Where a remembered window was, and the rule that decides whether to trust it.

Separate from `windowing` on purpose, and the reason is the screen rule. "Is
this saved rectangle still on a monitor that exists?" is the one piece of window
restoration that can genuinely go wrong in a way the user cannot recover from,
and it is arithmetic over rectangles — so it lives here, takes plain tuples, and
is tested without a display, a window or a `QApplication`.

No Qt in this module. `windowing` asks Qt what the screens are and passes the
answer in.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, Sequence

from . import settings

# Every window is its own record inside this category, keyed by `window_key`.
#
# It was one document holding every window, which is how LunaP does it and how
# this started. That made saving one window a read-modify-write of the whole
# thing, so two windows closing in the same instant lost one of the two updates
# — recorded at the time as a real race and an acceptable one. One record per
# window removes it instead of tolerating it, and costs nothing.
CATEGORY = "windows"

# A rectangle as (x, y, width, height), in the same screen pixels Qt reports.
Rect = tuple[int, int, int, int]


@dataclass(frozen=True)
class WindowPlacement:
    """Where a window was, as plain data."""

    x: int
    y: int
    width: int
    height: int
    maximized: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "WindowPlacement | None":
        """Parse one saved entry, or `None` if it is not one.

        Hand-editing `windows.json` is a thing people do, and so is a half-
        written file from an older version. Every field is checked rather than
        trusted, because the failure of trusting them is a `TypeError` during
        window construction — which reads as the application being broken rather
        than as one setting being wrong.
        """
        if not isinstance(raw, dict):
            return None
        try:
            return cls(
                x=int(raw["x"]),
                y=int(raw["y"]),
                width=int(raw["width"]),
                height=int(raw["height"]),
                maximized=bool(raw.get("maximized", False)),
            )
        except (KeyError, TypeError, ValueError):
            return None

    @property
    def bounds(self) -> Rect:
        return self.x, self.y, self.width, self.height


# Every function here reaches `settings.store()` freshly rather than capturing
# it, because a host may replace the store after this module is first imported.


def load(key: str) -> WindowPlacement | None:
    return WindowPlacement.from_dict(settings.store().load(CATEGORY, key))


def save(key: str, window_placement: WindowPlacement) -> bool:
    return settings.store().save(CATEGORY, key, window_placement.as_dict())


def forget(key: str) -> bool:
    return settings.store().delete(CATEGORY, key)


def remembered() -> list[str]:
    """Every window key that has a saved placement."""
    return settings.store().keys(CATEGORY)


def _intersects(a: Rect, b: Rect) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def is_on_a_screen(screens: Sequence[Rect] | Iterable[Rect], bounds: Rect) -> bool:
    """Would a window at `bounds` be reachable on any of these screens?

    **The failure this prevents is unrecoverable from inside the application.**
    A window restored onto a monitor that is no longer attached opens at
    coordinates with no pixels behind them: it cannot be seen, so it cannot be
    dragged back, and the only fix is to find and edit `windows.json` — which
    assumes the user knows the file exists.

    Intersection rather than containment, deliberately. A window half off the
    right edge of a screen is a window somebody can grab the titlebar of and
    move; requiring it to fit entirely would reject a lot of placements that
    people chose on purpose, and the point is reachability rather than tidiness.

    An empty screen list returns `True`. Nothing to check against is not the
    same as "off screen" — refusing there would strand every window at the
    default position on any platform whose screen enumeration this code does not
    understand.
    """
    screens = list(screens)
    if not screens:
        return True
    return any(_intersects(screen, bounds) for screen in screens)
