# LunaPY

A small Qt toolkit: a theme, a fluent layout surface, and a test harness that
can tell whether a window actually rendered. It is the chrome around whatever
your application does.

The Python counterpart of [LunaP](https://github.com/RedQuE3n/EmuSen.LunaP),
which does the same job for C# and Avalonia. Named for Luna-P, Chibiusa's
floating gadget ball, which becomes whichever tool is needed.

## The rule it is built on

**LunaPY imports PySide6 and the standard library, and nothing else.**

That is not modesty, it is the thing that makes it usable. Every helper takes
plain data or a callable, so nothing here can drag your domain model into a
window, and nothing here needs to know what your program is for.
`tests/test_layering.py` parses every module and fails on anything else, so the
rule is enforced rather than remembered.

## Installing

    pip install emusen-lunapy

`emusen-lunapy` on PyPI, `lunapy` in an import statement — `lunapy` alone was
taken. The prefix is the one LunaP's package id already carries from where both
were written; nothing here depends on anything of EmuSen's, and a test asserts
exactly that.

## Using it

**Layout**, without a `.ui` file and without a wall of `addWidget`:

```python
from lunapy import stack, row, section, header, hint, text, button, tune

panel = section("Audio",
    row(text("Volume", width=80), volume_slider, spacing=6),
    row(text("Device", width=80), device_box, spacing=6),
    hint("Applies to every profile"),
    button("Reset", on_reset),
)
```

C# needed extension methods to get `label.Width(80).Left()`, because you cannot
add arguments to an object after constructing it. Python can, so the modifiers
are just keywords — and `tune(widget, **props)` applies the same vocabulary to a
widget you did not build here:

```python
tune(tree_view, grow=True, min_size=(240, 120), accessible_name="Fields")
```

Every keyword names the Qt call it makes. An unknown one raises rather than
being ignored, because a silently dropped `witdh=80` is a layout that is subtly
wrong and gives no reason.

`stack`, `row`, `dock`, `cols`, `rows`, `scroll`, `section`, `header`, `hint`,
`mono`, `text`, `button`, `tune`. Everything returns a plain `QWidget`, so
containers nest with no special case.

**The theme:**

```python
from lunapy import apply, Variant
apply(app)                      # dark, the default
apply(app, Variant.LIGHT)
```

Two columns, ported key for key from LunaP. Every light foreground is held to
4.5:1 against the light surface by a test. Three dark foregrounds sit below that
floor — `success` at 3.93, `error` at 4.19, `muted` at 4.22 — and they are
recorded with the number each measures rather than quietly adjusted. Two of the
three were not in LunaP's own record; `docs/LunaPY.md` §2.1 is the correction.

**Style keys** select a look from the theme:

```python
from lunapy import set_style_key
set_style_key(status_label, "error")
```

Use this rather than `setProperty`. Qt resolves stylesheet rules once at polish
time and does not watch dynamic properties, so setting one on a widget that is
already on screen is **silent** — §3.2 has the measurement, and it is the mirror
image of a finding LunaP recorded going the other way.

**Windows** that remember where they were:

```python
from lunapy import ToolWindow, WindowSlot

class SettingsWindow(ToolWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Settings")
        self.window_key = "settings"      # opt in; without a key nothing is remembered
        self.set_content(section("Audio", volume_row, device_row))

settings_window = WindowSlot()            # at most one, else bring it forward
settings_window.show(SettingsWindow)
```

`PollingWindow` refreshes on a cadence and **stops while hidden or minimised**,
which is the only reason it exists — five windows in LunaP hand-rolled that
timer and none of them stopped.

A saved position is checked against the attached screens before it is used. A
window restored onto a monitor that is no longer there opens where it cannot be
seen, so it cannot be dragged back, and the only fix is editing the settings
store by hand.

## Settings

Records go through a four-method seam, so a host decides where they live:

```python
from lunapy import set_store, set_diagnostics
from lunapy.settings import SqliteSettingsStore
set_store(SqliteSettingsStore("/path/to/settings.db"))
set_diagnostics(logger.warning)
```

The default is **SQLite** under each platform's own config directory — one row
per record, so two windows closing at the same instant cannot lose each other's
placement, and durability is a transaction's problem rather than ours.
`JsonSettingsStore` is there for a host that wants settings a person can open in
an editor; the contract tests run over both. `docs/LunaPY.md` §7.2 records what
the database bought and what it cost.

Loading is best-effort everywhere: a record that will not parse costs a window
its position, not the program its start. `set_diagnostics` is what stops that
being silent, and it defaults to discarding — a toolkit that writes to stderr
uninvited corrupts the output of the tool that embedded it.

## Testing your own windows

```python
from lunapy.testing import ui_app, show, assert_laid_out

def test_the_settings_panel_lays_out(app):
    panel = show(build_settings_panel(), 420, 300)
    assert_laid_out(panel, "settings")
```

`assert_laid_out` is the one that earns its keep: a window that failed to lay
out, or whose widgets never got their stylesheet, renders as one flat colour,
and counting distinct colours catches that where walking the widget tree does
not.

Importing `lunapy.testing` sets `QT_QPA_PLATFORM=offscreen`, so no window is
ever put on a screen. Set `LUNAPY_UI_DUMP` to a directory to get a PNG of every
capture in the run.

The harness lives in the package rather than beside it, because it raises
`AssertionError` and imports no test framework. LunaP needed a second NuGet
package for the same thing; a keyword and a builtin made that unnecessary here.

## Building and testing

    python -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python -m pytest

190 tests, all headless. Every guard is made to fail on purpose before it is
trusted; `docs/LunaPY.md` §8 is the table of what each sabotage turned red, and
§4.1 is the one that did not fail the first time and what that turned out to
mean.

## What is not here yet

The fluent surface, the theme, the harness, the windowing layer and the settings
seam are in. Still to come: the control kit, the threading helpers, the theme
loader and the gallery. `docs/LunaPY.md` §9 names each one so an absence is not
mistaken for a decision.

## Documentation

`docs/LunaPY.md` is the design record: what each part is, what was tried and
rejected, and the findings that cost something to learn. Where LunaPY departs
from LunaP it says which way the port went and why — Qt is not Avalonia, and
several of LunaP's hardest-won findings either invert or evaporate here.

## Licence

**MIT.** Link it into anything, including a closed application.

Its one dependency, **PySide6, is LGPL-3.0**, and a consumer inherits that
transitively. Installing it from PyPI as a normal dependency satisfies the
relink condition, so MIT on the tin holds for LunaPY's own code — but it is a
term the MIT notice does not mention, and `docs/LunaPY.md` §1.2 says so plainly
rather than leaving it to a licence audit six months later.
