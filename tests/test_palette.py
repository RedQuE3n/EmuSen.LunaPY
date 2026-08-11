"""The palette's two columns, and the contrast floors that hold them.

No Qt in this file. The palette is arithmetic over hex strings, so these run
without an application, a display or a style — which is what you want from the
tests that carry the accessibility claim.
"""

import pytest

from lunapy.palette import (
    BUSY_PERCENT,
    COLUMNS,
    DARK,
    HOT_PERCENT,
    LIGHT,
    LoadLevel,
    Variant,
    contrast_ratio,
    level_for,
    relative_luminance,
    rgb,
)

# Colours that are drawn as text and are therefore held to WCAG AA for body
# text, 4.5:1. The load ramp is not in this list: it is a fill behind a meter,
# a graphical object rather than a glyph, and AA asks 3:1 of those.
TEXT_KEYS = [
    "text",
    "meter_text",
    "muted",
    "section_header",
    "warning",
    "error",
    "success",
    "info",
]

RAMP_KEYS = ["nominal", "busy", "hot"]

AA_TEXT = 4.5
AA_GRAPHICAL = 3.0

# Three dark-column foregrounds sit below the text floor. They are recorded
# here with the number each one actually measures rather than being fixed in
# passing or hidden behind a lowered global floor — a palette literal is a
# deliberate one-line decision, and adjusting one while doing something else is
# how a palette stops being deliberate. docs/LunaPY.md §2.1 has the finding,
# including which of these LunaP itself had already recorded and which two this
# port found.
#
# If you improve one of these, this test goes red. That is the intent: the fix
# is to change the number here and say so in the record, not to widen the
# tolerance.
DARK_SHORTFALLS = {
    "muted": 4.22,
    "error": 4.19,
    "success": 3.93,
}


def test_the_two_columns_carry_the_same_keys():
    """A key added to one column and not the other is a crash in one variant only.

    It would present as an application that works until somebody switches to
    light, which is the kind of bug that reaches a user because the person who
    added the key never runs in the other variant.
    """
    assert set(DARK) == set(LIGHT)


def test_every_column_is_reachable_by_variant():
    assert set(COLUMNS) == set(Variant)
    for v in Variant:
        assert set(COLUMNS[v]) == set(DARK)


def test_every_value_is_a_six_digit_hex_colour():
    for name, column in (("dark", DARK), ("light", LIGHT)):
        for key, value in column.items():
            assert value.startswith("#"), f"{name}.{key} = {value!r}"
            assert len(value) == 7, f"{name}.{key} = {value!r}"
            rgb(value)  # raises if it is not parseable


@pytest.mark.parametrize("key", TEXT_KEYS)
def test_light_foregrounds_clear_aa(key):
    """Every light foreground at 4.5:1 or better against the light surface.

    This is the floor the light column was derived against, so it is the
    assertion that stops the derivation decaying. A plausible-looking `#9A9A9A`
    for `muted` measures 2.54:1 and fails here.
    """
    ratio = contrast_ratio(LIGHT[key], LIGHT["surface"])
    assert ratio >= AA_TEXT, f"light {key} {LIGHT[key]} measures {ratio:.2f}:1 on {LIGHT['surface']}"


@pytest.mark.parametrize("key", TEXT_KEYS)
def test_dark_foregrounds_clear_aa_or_are_recorded(key):
    ratio = contrast_ratio(DARK[key], DARK["surface"])
    if key in DARK_SHORTFALLS:
        assert ratio == pytest.approx(DARK_SHORTFALLS[key], abs=0.01), (
            f"dark {key} now measures {ratio:.2f}:1, not the {DARK_SHORTFALLS[key]}:1 on record. "
            "Update DARK_SHORTFALLS and docs/LunaPY.md §2.1 — do not widen the tolerance."
        )
    else:
        assert ratio >= AA_TEXT, f"dark {key} {DARK[key]} measures {ratio:.2f}:1"


@pytest.mark.parametrize("key", RAMP_KEYS)
@pytest.mark.parametrize("column", [DARK, LIGHT], ids=["dark", "light"])
def test_the_load_ramp_clears_the_graphical_floor(column, key):
    """The ramp is a fill, measured against the surface it is drawn on.

    Against `input_surface` and not `surface`, because that is where a meter's
    chunk actually sits — the theme paints the trough with the input surface.
    Measuring against the window background would be measuring a pairing that
    never appears on screen.
    """
    ratio = contrast_ratio(column[key], column["input_surface"])
    assert ratio >= AA_GRAPHICAL, f"{key} {column[key]} measures {ratio:.2f}:1"


@pytest.mark.parametrize("column", [DARK, LIGHT], ids=["dark", "light"])
def test_selected_text_clears_aa_on_the_selection(column):
    """`selection` is a strong accent carrying white text on either variant, so
    both columns share it. It has to earn that."""
    ratio = contrast_ratio(column["selection_text"], column["selection"])
    assert ratio >= AA_TEXT, f"{ratio:.2f}:1 on {column['selection']}"


@pytest.mark.parametrize("column", [DARK, LIGHT], ids=["dark", "light"])
@pytest.mark.parametrize("face", ["raised", "hover"])
def test_body_text_clears_aa_on_every_chrome_face(column, face):
    """A button's label sits on `raised` and a hovered row's on `hover`, not on
    `surface`. Text is only accessible on the surface it is actually drawn on —
    a check the original palette had no reason to make, because it had no
    chrome faces to draw on."""
    ratio = contrast_ratio(column["text"], column[face])
    assert ratio >= AA_TEXT, f"text on {face} measures {ratio:.2f}:1"


def test_a_header_uses_text_rather_than_muted_on_a_raised_face():
    """Pins the §14.1 decision. `muted` on the dark `raised` face measures
    3.39:1, below the body-text floor, so the theme uses `text` with weight
    instead. This is what stops somebody quietly putting the grey back to make
    headers look calmer."""
    assert contrast_ratio(DARK["muted"], DARK["raised"]) < AA_TEXT, (
        "muted now clears AA on the dark raised face; if that is deliberate, "
        "update docs/LunaPY.md §14.1 and this test"
    )
    for column in (DARK, LIGHT):
        assert contrast_ratio(column["text"], column["raised"]) >= AA_TEXT


def test_the_focus_ring_clears_the_graphical_floor():
    """**The floor that decided the selection colour.**

    `selection` is the focus ring as well as the selected-row background, and a
    focus indicator is the one boundary WCAG 1.4.11 most cares about. It must
    clear 3:1 against the surface it is drawn on — which for an input is
    `input_surface`, the darkest case.

    This is what caught #2F6FB5 at **2.96:1**, failing by 0.04. Two floors pull
    opposite ways here: lighter helps the ring and hurts white-on-selection, so
    the value lives in a narrow window and both ends are asserted.
    """
    for column in (DARK, LIGHT):
        ring = contrast_ratio(column["selection"], column["input_surface"])
        assert ring >= AA_GRAPHICAL, f"focus ring measures {ring:.2f}:1"
        legible = contrast_ratio(column["selection_text"], column["selection"])
        assert legible >= AA_TEXT, f"selected text measures {legible:.2f}:1"


def test_the_border_contrast_shortfall_is_recorded():
    """**A measured shortfall, stated rather than fixed in passing.**

    WCAG 1.4.11 asks 3:1 of the boundary of a UI component that needs it to be
    identified. `border` measures **1.53:1** against `surface` in both columns,
    so a resting control outline is subtle by that standard.

    Not changed, for §2.1's reason: this literal is load-bearing for the whole
    chrome and adjusting it while doing something else is how a palette stops
    being deliberate. What carries identification instead is the fill — every
    input has its own `input_surface`, distinct from the window — and the focus
    ring above, which does clear the floor. Recorded so somebody can decide on
    evidence. docs/LunaPY.md §14.1.
    """
    for column in (DARK, LIGHT):
        assert contrast_ratio(column["border"], column["surface"]) == pytest.approx(1.53, abs=0.01)


def test_contrast_is_symmetric_and_bounded():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0, abs=0.01)
    assert contrast_ratio("#777777", "#777777") == pytest.approx(1.0, abs=0.01)


def test_luminance_endpoints():
    assert relative_luminance("#000000") == pytest.approx(0.0)
    assert relative_luminance("#FFFFFF") == pytest.approx(1.0)


def test_rgb_accepts_a_bare_hex_and_rejects_a_short_one():
    assert rgb("1E1E1E") == (30, 30, 30)
    assert rgb("#1E1E1E") == (30, 30, 30)
    with pytest.raises(ValueError):
        rgb("#1E1")


@pytest.mark.parametrize(
    "percent, expected",
    [
        (0, LoadLevel.NOMINAL),
        (59.9, LoadLevel.NOMINAL),
        (BUSY_PERCENT, LoadLevel.BUSY),      # the boundary is inclusive
        (84.9, LoadLevel.BUSY),
        (HOT_PERCENT, LoadLevel.HOT),
        (100, LoadLevel.HOT),
        (250, LoadLevel.HOT),                # over 100 is still hot, not an error
    ],
)
def test_the_load_ramp_bands(percent, expected):
    assert level_for(percent) == expected


def test_the_contrast_guard_can_fail():
    """The sabotage: the floor must reject a colour that genuinely fails it.

    A contrast test that passes everything is the same as no contrast test, and
    an arithmetic slip in `relative_luminance` — the 2.4 exponent, the 0.03928
    branch — would produce exactly that without changing any other result
    visibly.
    """
    plausible_but_wrong = "#9A9A9A"
    assert contrast_ratio(plausible_but_wrong, LIGHT["surface"]) < AA_TEXT
