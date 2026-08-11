"""The palette, in two columns, and the contrast arithmetic that pins them.

**This module imports nothing but the standard library, and that is deliberate.**
A colour is arithmetic, not a widget: keeping the palette Qt-free means the
contrast floors below are tested without ever starting a QApplication, so the
test that matters most for accessibility is also the one least able to break for
environmental reasons. `theme` is where these values meet Qt.

The values are ported unchanged from LunaP's `Theme/Palette.axaml`. They were
not re-chosen here — a palette literal is a deliberate one-line decision, and
re-deriving one during a port is how two projects that are supposed to look
alike stop looking alike. LunaP §2.1 is the audit that produced the dark
column; §23.2 is the re-derivation that produced the light one.
"""

from __future__ import annotations

import enum
from typing import Mapping


class Variant(enum.Enum):
    """Which column of the palette is in force.

    There is no `SYSTEM` member. Following the desktop is a *policy*, decided in
    `theme.apply`, and a palette that could report "system" would force every
    caller that wanted a colour to resolve that policy for itself. LunaP §23.3
    is the argument for why the default is Dark rather than the desktop's
    choice: every consumer has been dark since the toolkit existed, and
    following the desktop by default means an application looks different after
    a version bump its author took for something else.
    """

    DARK = "dark"
    LIGHT = "light"


# Surfaces, text and the two semantic families. Keys are snake_case because this
# is Python; they map one-to-one onto LunaP's `Luna*Color` resource keys, and
# `test_palette.py` pins the two lists together so a key added on one side and
# not the other is a failure rather than a silent divergence.
DARK: Mapping[str, str] = {
    # Surfaces
    "surface": "#1E1E1E",
    "input_surface": "#252526",
    "void": "#000000",
    # Chrome. These five are NOT in LunaP's palette, and why is worth stating:
    # Avalonia ships FluentTheme, a complete modern control theme, so LunaP only
    # ever had to style its own controls. Qt ships Fusion, which is functional
    # and dated, so LunaPY has to draw the whole control set itself — and that
    # needs a border, a raised face, a hover tint and a selection colour, none
    # of which a palette of foregrounds has. Hard-coding them in the stylesheet
    # would put five colours where a theme cannot reach them. docs/LunaPY.md §14.
    "border": "#3A3D41",
    "raised": "#2D2F34",
    "hover": "#33363B",
    "selection": "#3577BE",
    "selection_text": "#FFFFFF",
    # Text
    "text": "#D4D4D4",
    "meter_text": "#DCDCDC",
    "muted": "#808080",
    "section_header": "#9CDCFE",
    "warning": "#D08770",
    # Outcome. Deliberately NOT the load ramp below: LunaP §22.9 refused to give
    # an input conflict the same key as a hot subsystem, because sharing a key
    # encodes a relationship between the two that does not exist.
    "error": "#CD5C5C",
    "success": "#2E8B57",
    "info": "#DAA520",
    # The load ramp: what "getting busy" looks like, in one place, so no two
    # dashboards disagree about it.
    "nominal": "#32CD32",
    "busy": "#FFD700",
    "hot": "#FF4500",
}

# A re-derivation, not an inversion. A hue that carries on #1E1E1E is usually
# far too pale to carry on #F3F3F3, so each one was darkened until it read
# against the light surface rather than being flipped about the mid-point.
LIGHT: Mapping[str, str] = {
    "surface": "#F3F3F3",
    "input_surface": "#FFFFFF",
    # Still black, and deliberately not a light equivalent. This is the
    # letterbox behind a rendered frame — the absence of a picture rather than a
    # surface — and it is black on any desktop for the same reason a cinema's
    # masking is.
    "void": "#000000",
    "border": "#C4C7CC",
    "raised": "#FAFAFA",
    "hover": "#E8EAED",
    # The same blue in both columns. A selection is a strong accent rather than
    # a surface tint, and it carries white text on either background — so
    # re-deriving it per variant would change a colour that was already correct.
    #
    # #3577BE sits in a narrow window and was measured into it. It has to clear
    # 3:1 against the DARK input surface, because this is also the focus ring
    # and a focus indicator is the one boundary WCAG 1.4.11 most cares about;
    # and it has to keep white text at 4.5:1, because it is also the selected-row
    # background. Those two pull opposite ways — lighter helps the first and
    # hurts the second. The first attempt, #2F6FB5, measured 2.96:1 as a ring
    # and failed by 0.04. docs/LunaPY.md §14.1.
    "selection": "#3577BE",
    "selection_text": "#FFFFFF",
    "text": "#1F1F1F",
    "meter_text": "#2A2A2A",
    "muted": "#5F5F5F",
    "section_header": "#0A5A96",
    "warning": "#A34B1E",
    "error": "#B3261E",
    "success": "#1B6E3C",
    "info": "#7A5B00",
    "nominal": "#1B7A1B",
    "busy": "#8A6300",
    "hot": "#B32D12",
}

COLUMNS: Mapping[Variant, Mapping[str, str]] = {
    Variant.DARK: DARK,
    Variant.LIGHT: LIGHT,
}

# Type. Not variant-keyed: a font stack and two sizes do not change with the
# lighting. The stack is ordered Windows, macOS, then whatever the desktop calls
# its monospace default — Qt walks it left to right and takes the first hit.
MONO_FONT = "Consolas, Menlo, monospace"
HINT_FONT_SIZE = 11
HEADER_FONT_SIZE = 14


class LoadLevel(enum.Enum):
    """How hard something is working, in the three bands every dashboard shares."""

    NOMINAL = "nominal"
    BUSY = "busy"
    HOT = "hot"


# The one place that decides what "getting busy" means. Two dashboards that each
# pick their own threshold will eventually show the same machine as busy and
# nominal at the same moment, which is a bug nobody files because each window
# looks self-consistent.
BUSY_PERCENT = 60.0
HOT_PERCENT = 85.0


def level_for(percent: float) -> LoadLevel:
    if percent >= HOT_PERCENT:
        return LoadLevel.HOT
    if percent >= BUSY_PERCENT:
        return LoadLevel.BUSY
    return LoadLevel.NOMINAL


def rgb(hex_colour: str) -> tuple[int, int, int]:
    """`"#1E1E1E"` -> `(30, 30, 30)`. Accepts the leading hash or not."""
    value = hex_colour.lstrip("#")
    if len(value) != 6:
        raise ValueError(f"expected a 6-digit hex colour, got {hex_colour!r}")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def relative_luminance(hex_colour: str) -> float:
    """WCAG 2.x relative luminance, 0.0 (black) to 1.0 (white).

    The 0.03928 branch and the 2.4 exponent are the sRGB transfer function; they
    are not a fudge factor and changing either silently moves every contrast
    figure this project reports. WCAG 2.1, "relative luminance".
    """

    def channel(raw: int) -> float:
        c = raw / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in rgb(hex_colour))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(foreground: str, background: str) -> float:
    """The WCAG contrast ratio between two colours, 1.0 to 21.0.

    Symmetric — the order of the arguments does not change the answer, which is
    why the parameter names are a convenience rather than a constraint.
    """
    a, b = relative_luminance(foreground), relative_luminance(background)
    lighter, darker = max(a, b), min(a, b)
    return (lighter + 0.05) / (darker + 0.05)
