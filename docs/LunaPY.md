# LunaPY — design record

What each part is, what was tried and rejected, and the findings that cost
something to learn. Kept from the first commit.

LunaPY is the Python counterpart of **LunaP**, the C#/Avalonia toolkit at
`github.com/RedQuE3n/EmuSen.LunaP`. Citations of the form *LunaP §n* point at
that project's `docs/LunaP.md`. Where the two disagree, this file says which way
the port went and why — Qt is not Avalonia, and a port that pretends otherwise
produces a toolkit fighting its own substrate.

---

## 1. What it is, and the rule that keeps it useful

A theme, a fluent layout surface, and a harness that can tell whether a window
actually rendered. It is the chrome around whatever your application does.

**LunaPY imports PySide6 and the standard library, and nothing else.** That is
not modesty. It is the property that lets one toolkit serve every Python project
here, because it guarantees that taking LunaPY cannot drag in a decision made
for some other program. Every helper takes plain data or a callable, so nothing
here can pull a domain model into a window and nothing here needs to know what
the program is for.

`tests/test_layering.py` enforces it by parsing every module's AST and rejecting
any top-level import that is neither `PySide6` nor in
`sys.stdlib_module_names`. It walks the whole tree rather than the module body,
so an import tucked inside a function three levels down is caught too.

LunaP arrived at this test at its §22.7, after the toolkit had already been cut
loose from the project it grew inside; until then the rule was maintained by
hand. It is here from the first commit instead, because the rule is cheap to
keep and expensive to restore — by the time a stray import has been in the tree
a month, removing it is a refactor rather than a deletion.

### 1.1 Why Qt, and what it decided

LunaP is not a windowing toolkit; it is a layer over one, and Avalonia carries
the hard parts. So the first decision for a Python counterpart was what plays
Avalonia's part, and everything else is downstream of it.

**Tkinter was rejected**, despite being the standard library and therefore free.
It can carry the fluent surface, the windowing layer and the threading helpers,
and it can carry none of the theme or accessibility work — the two tracks LunaP
spent the most to learn. `ttk` theming is element-layout based, several native
themes ignore colour settings outright, and there is no automation tree to
assert an accessible name against. A toolkit meant to serve every Python project
here for years cannot start by writing off accessibility, particularly with
BIMA — a tool used in a university Financial Aid office — as its first consumer.

**PySide6 was taken.** It is the only Python option shaped like Avalonia: QSS
for templated theming, palette variants, `QAccessible` as a real automation
tree, and an offscreen platform plugin for headless render tests.

Also considered: **PyQt6**, rejected on licence — GPL-3.0 or commercial, which
is the same objection that rejected PyMuPDF in BIMA. **wxPython**, whose licence
is effectively permissive, but whose theming story is thinner. **Toga**, BSD-3
and native, but too immature to build a decade of windows on.

Rejected without being tried: making the backend a seam so LunaPY could ride Tk
*or* Qt. A two-backend widget toolkit is several times the work of either, and
LunaP did not hedge — its layering rule exists *because* it bet on one substrate.

### 1.2 PySide6, and a licence a consumer inherits

**PySide6 is LGPL-3.0.** LunaPY is MIT. That combination is legitimate and it is
not free of consequence, which is why it is written down here rather than left
to a licence audit six months from now.

The LGPL's condition is that a user can relink the library. A Python application
that installs PySide6 from PyPI as a normal dependency satisfies that
trivially — the shared objects are right there and replaceable — so MIT on the
tin holds for LunaPY's own code, and a closed application may use it.

What a consumer inherits: Qt's terms, transitively. That is a term the MIT
notice does not mention, and anyone taking LunaPY should know it before they
ship rather than after. This is the same reasoning that keeps AGPL packages out
of BIMA, applied honestly to a weaker copyleft rather than used to wave it
through — LGPL is a real term, just a survivable one.

It is also worth recording what this **costs**.

**Correction.** This section said "PySide6 is roughly 100MB installed". That was
an estimate presented as a measurement, and it was wrong by a factor of six.
Measured at PySide6 6.11.1 on Python 3.14, in a venv also holding LunaPY,
pikepdf, pypdf, pillow, lxml and pytest:

| Installed | `site-packages/PySide6` | whole venv |
|---|---|---|
| `PySide6` (metapackage) | 648MB | 721MB |
| `PySide6-Essentials` | 232MB | 305MB |

Neither number is 100MB, and the gap between the two rows is the finding. The
`PySide6` metapackage is `PySide6-Essentials` plus `PySide6-Addons`, and Addons
is 36 modules — Qt3D, QtCharts, QtDataVisualization, QtMultimedia, QtWebEngine,
QtPdf and the rest — of which LunaPY imports **none**. It names three Qt modules
in total: `QtCore`, `QtGui`, `QtWidgets`. So 416MB of that install was Qt
nothing here could reach.

The dependency is `PySide6-Essentials>=6.5` as a result. This constrains nobody:
`PySide6` itself depends on `PySide6-Essentials`, so an application that wants
QtCharts installs the metapackage and both requirements resolve. What it stops
is a consumer who wants none of Addons paying for all of it. Both suites were
run against an Essentials-only venv before the change was made — LunaPY's 345
and BIMA's 194, all passing.

**Why this needed a test rather than care.** The saving is invisible on a
developer machine that already has the metapackage. `from PySide6.QtCharts
import QChart` would import cleanly, the suite would stay green, the wheel would
build, and the next person to `pip install emusen-lunapy` into a clean
environment would get a quarter-gigabyte of Qt3D with no diagnostic anywhere.
Nothing at runtime can notice a dependency that is satisfied. So
`tests/test_layering.py::test_no_module_reaches_outside_pyside6_essentials`
pins the import surface to those three modules, and adding a fourth is a
decision that has to come back to this section. It was sabotaged with a
`QtCharts` import in `fluent.py` and failed naming the module (§8).

What remains true is the shape of the original point: 305MB against Tkinter's
zero is still a real number for a tool distributed to office machines, and it is
still the price of the theme and accessibility tracks. It is now a measured
price rather than a guessed one.

### 1.3 The name

`lunapy` was already taken on PyPI. The distribution is **`emusen-lunapy`** and
the import is **`lunapy`**.

The prefix is the one LunaP's NuGet id already carries from where both were
written, so it identifies the pair rather than inventing a third name for the
same thing. It carries no dependency on anything of EmuSen's, and
`test_layering.py` asserts exactly that.

---

## 2. The palette

Ported unchanged from LunaP's `Theme/Palette.axaml` — both columns, key for
key. The values were **not** re-chosen during the port. A palette literal is a
deliberate one-line decision (LunaP §2.1), and re-deriving one while doing
something else is how two projects that are meant to look alike stop looking
alike.

`lunapy/palette.py` imports nothing but the standard library, which is
deliberate: a colour is arithmetic, not a widget, so the contrast floors below
are tested without ever starting a `QApplication`. The test carrying the
accessibility claim is also the one least able to break for environmental
reasons.

`tests/test_palette.py` pins that both columns carry the same keys. A key added
to one and not the other is a crash in one variant only — an application that
works until somebody switches to light, which reaches a user because the person
who added the key never runs in the other variant.

### 2.1 Contrast, measured — and two shortfalls LunaP had not recorded

The independent Python implementation of WCAG relative luminance reproduces
LunaP's recorded figure exactly: `LunaMuted` on the dark surface measures
**4.22:1**. Two implementations in two languages agreeing to two decimal places
is a reasonable cross-check that the arithmetic is right in both.

Every **light** foreground clears the 4.5:1 AA floor for body text, as LunaP
§23.2 claims. Measured, lowest first:

| key | colour | on `#F3F3F3` |
|---|---|---|
| `warning` | `#A34B1E` | 5.28 |
| `busy` (ramp) | `#8A6300` | 5.43 |
| `nominal` (ramp) | `#1B7A1B` | 5.46 |
| `success` | `#1B6E3C` | 5.66 |
| `info` | `#7A5B00` | 5.69 |
| `muted` | `#5F5F5F` | 5.75 |
| `error` | `#B3261E` | 5.89 |
| `section_header` | `#0A5A96` | 6.49 |
| `meter_text` | `#2A2A2A` | 12.94 |
| `text` | `#1F1F1F` | 14.85 |

The **dark** column has three foregrounds below the text floor, not one:

| key | colour | on `#1E1E1E` | recorded in LunaP? |
|---|---|---|---|
| `success` | `#2E8B57` | **3.93** | no |
| `error` | `#CD5C5C` | **4.19** | no |
| `muted` | `#808080` | **4.22** | yes, §23.4 |

**This is a correction to LunaP's record, not to its code.** §23.4 states the
shortfall as a single value — "`LunaMuted` on the dark surface measures 4.22:1"
— and leaves the impression that it is the only one. It is the worst of the
*text* greys, but `error` and `success` are both below it, and `success` is the
worst in the palette by a clear margin. The likely reason is chronology: the
semantic colours arrived at LunaP §22.9, taken from six sites that had already
hard-coded IndianRed, SeaGreen and Goldenrod, and the contrast work at §23
measured the greys it had set out to measure.

Nothing is changed here, for §23.4's own reason: a palette literal is not
adjusted in passing while doing something else. The three are recorded in
`DARK_SHORTFALLS` with the number each actually measures, and the test asserts
the *measured value* rather than a lowered floor. Improving one of these turns
the suite red on purpose — the fix is to change the number and say so, not to
widen a tolerance.

The load ramp is held to 3:1 rather than 4.5:1, and against `input_surface`
rather than `surface`. It is a fill behind a meter — a graphical object, which
is what AA asks 3:1 of — and the trough is painted with the input surface, so
measuring against the window background would be measuring a pairing that never
appears on screen. All six ramp values clear it.

---

## 3. The theme

### 3.1 Two mechanisms, and why not one

`QPalette` carries the base roles — window, text, base, button. QSS carries only
what a palette has no role for: the three text styles, the load ramp, semantic
accents.

Doing all of it in QSS is the obvious first attempt and it is wrong. A rule like
`QWidget { background: #1E1E1E }` cascades to *every* descendant, including
those that paint their own background — a scroll area's viewport, a combo box's
popup — so a stylesheet that looks right on a bare window starts producing dark
rectangles inside controls that never asked for one. A palette has no such
failure mode, because a role is asked for rather than inherited blindly.

`app.setStyle("Fusion")` is the single most consequential line in `theme.py`.
Qt's native styles route many colours through the platform theme and quietly
ignore both the palette and much of the stylesheet, so a toolkit that themes
itself has to opt out of them. It is the same decision a Tk build would make in
pinning `clam`, and it is why a LunaPY window looks the same on every desktop
rather than themed on one and half-themed on the next.

### 3.2 The repolish trap — LunaP §12.3, inverted

LunaP §12.3 found that **mutating `Application.Styles` at runtime strips every
already-realized control of its styling**, so a theme switcher needed
`LunaTheme.Restyle(root)` to detach and reattach the content.

Qt does not have that problem. `app.setStyleSheet()` re-polishes live widgets by
itself; measured, a header label already on screen changes colour across a
variant switch with no help. `Restyle` did not need porting.

**The trap moved instead.** Qt resolves stylesheet rules once at polish time and
does not watch dynamic properties, so setting a style key on a widget that is
already shown is *silent*:

```
plain label                          #848287
setProperty("luna", "section_header") #848287   <- nothing happened
unpolish + polish                    #0905fe   <- now it applied
```

Same class of bug, opposite trigger: LunaP's fired on a global style change and
spared individual widgets; Qt's fires on an individual widget and spares the
global change. Both projects therefore need a repolish helper, and neither one's
reasoning transfers to the other. `theme.set_style_key` is that helper, and
`test_a_style_key_set_after_showing_needs_the_repolish` pins **both** halves —
that the naive way is silent, and that the supported way is not. Asserting only
the second half would leave a `set_style_key` that had lost its repolish passing
on any widget that happened not to be shown yet.

`restyle(recursive=True)` is off by default. Unpolishing a large tree is visible
work — Qt tears down and rebuilds every child's style data — and the common
caller changed exactly one widget.

### 3.3 A lifetime hazard the C# original does not have

A container built by the fluent surface is owned by the Python reference to it
and nothing else; it has no Qt parent until somebody adds it to a layout. Drop
that reference and CPython collects the host, whose C++ destructor takes every
child with it. The next touch of a child raises `RuntimeError: Internal C++
object (PySide6.QtWidgets.QLabel) already deleted` from inside shiboken.

Found by writing `stack(a, b, c).layout()` in a test — the host is a temporary,
so the children were gone before the assertion ran.

This has no equivalent in LunaP: the CLR keeps a managed control alive as long
as anything references it, and Avalonia's tree does not own its children's
lifetimes the way a C++ parent pointer does. It is not fixable from inside the
toolkit — it is what object ownership means in PySide — so it is pinned by
`test_an_unheld_container_takes_its_children_with_it`, which asserts the
`RuntimeError` and names itself in the traceback.

---

## 4. The harness

`lunapy/testing.py` raises `AssertionError` and imports no test framework, which
is what lets it live **inside** the package. LunaP had to ship
`EmuSen.LunaP.Testing` as a second NuGet package, because its assertions came
from xunit and taking that dependency in the toolkit would have broken the rule
the toolkit is built on. Python's `assert` is a keyword and `AssertionError` is
a builtin, so the same harness costs no dependency and the layering rule holds
with one package. `test_the_harness_takes_no_test_framework` keeps that true —
the temptation is `pytest.fail` for a better message.

The assertion that earns its keep is `assert_laid_out`. A window that failed to
lay out, or whose widgets never got their stylesheet, renders as one flat
colour, and counting distinct colours catches that where walking the widget tree
does not — the tree of a window that rendered nothing looks exactly like the
tree of one that rendered correctly.

Frames are `Format_RGBA8888`, not the `Format_ARGB32` most Qt examples reach
for. ARGB32 stores a 32-bit word, so on a little-endian machine `bits()` hands
back **B, G, R, A**, and code reading it as RGB is correct on exactly one
architecture. RGBA8888 is defined by byte order, so the bytes mean what they say
everywhere. Pinned by `test_the_frame_is_rgba_not_bgra` with `#FF8000`, whose
channels are all different.

`RenderedFrame.digest` uses blake2b where LunaP hand-rolls FNV-1a. C# has no
cheap stdlib hash for a byte array; Python does, and it runs in C rather than a
per-byte interpreter loop. The property being hashed is "these bytes are the
same bytes", so any digest does — the fast one is simply free.

### 4.1 The fill, and a guard that was green for the wrong reason

`capture` fills the image with zeroes before rendering. A `QImage` is allocated
uninitialized, so without the fill a capture contains whatever was in that
memory.

**The guard for this was written first and did not work, and the reason is the
useful part.** The original flat-widget test styled a `QWidget` with
`background: #1E1E1E`. Deleting `image.fill(0)` left the whole suite green.

The measurement explains it. Most widgets paint their own background, because
`render` includes `DrawWindowBackground` by default and the palette supplies the
Window role, so the buffer is covered either way:

```
plain widget              no fill = 1e1e1eff / 1 colour   fill(0) = 1e1e1eff / 1 colour
WA_NoSystemBackground     no fill = c05cc4ad / 40 colours fill(0) = 00000000 / 1 colour
WA_TranslucentBackground  no fill = 3063c4ad / 5 colours  fill(0) = 00000000 / 1 colour
```

A widget with `WA_NoSystemBackground` paints nothing at all, and the stale heap
underneath it came back with **40 distinct colours** on a 200×100 widget.
`assert_laid_out` defaults to a floor of 8. A widget that rendered absolutely
nothing would have sailed past the one assertion that exists to catch precisely
that — and the amount of noise is a property of what the allocator last held, so
it would have passed on some runs and not others.

There are now two tests, because these are two failures: one for a widget that
painted a single colour, one for a widget that painted none. Deleting the fill
turns the second red.

The general lesson is the one LunaP §3.1 states one level down: **a guard that
has never been made to fail is not yet a guard.** This one was written, looked
correct, and certified nothing.

### 4.2 Baselines, and why they are not committed

Pixel-exact comparison is opt-in behind `LUNAPY_UI_BASELINE`, with
`LUNAPY_UI_BASELINE_MODE=write` to record one.

A baseline is an artefact of one machine's font rendering and one Qt build.
Committing one makes every other machine's suite red for a reason that has
nothing to do with the change in front of it. It is a tool for bisecting a
visual regression on the machine that has it, not a gate — so `baselines/` and
`work/` are gitignored.

`assert_stable` is the companion: it builds and renders twice and fails if the
two differ, because a widget showing a clock, a pid or a counter can never be a
baseline target. Finding that out with a message that says so is much cheaper
than finding it out as a baseline that fails once a day for reasons nobody can
reproduce.

`LUNAPY_UI_DUMP` names a directory and writes every capture in the run to it as
a PNG, through Qt's own encoder, so the harness needs no imaging dependency.

---

## 5. What Qt gives for free that LunaP had to build

Recorded because it is the difference between the two projects, and because
somebody reading LunaP's §24 will otherwise look for its counterpart here.

**Accessibility is largely already done.** LunaP §24's measurement was nine
controls not in the automation tree *at all*, needing `LunaAutomationPeer` to
put them there. Qt puts `QWidget` subclasses in the tree by default and names
them from the text they already carry. Measured on a probe window that was told
nothing:

```
Client: ''
  StaticText: 'Audio'
  StaticText: 'Volume'
  ProgressBar: 'Volume'      <- from setAccessibleName; a bar has no text of its own
  Button: 'Prune'            <- from its own label, unprompted
```

So LunaPY's accessibility work starts where LunaP's §24.4 "what is still
missing" left off: naming only what Qt genuinely cannot infer. `tune` takes
`accessible_name` and `help_text` as ordinary keywords for that reason —
accessibility is not a thing you remember to go back and add, and LunaP §24 is
what happens when it is.

**What is *not* free**, and is not claimed: this is measured against Qt's
automation tree, not against a running screen reader. Same limit LunaP §24.4
states about Avalonia's.

---

## 6. The windowing layer

`ToolWindow` is deliberately thin and **both of its features are opt-in**. A
base class that changes behaviour merely by being inherited cannot be adopted
incrementally — LunaP §9.1 refused one for the same reason — so a window with no
`window_key` is never remembered, and Escape closes nothing unless asked.

Escape is off by default because Escape inside a text field means "stop what I
am typing", not "throw away this window", and a base class cannot know which
kind of window it is being mixed into.

`ToolWindow` also carries a `closed` signal, which Qt does not provide.
`QObject.destroyed` fires when the object is *deleted*, and for a window without
`WA_DeleteOnClose` that is a different and much later moment than the user
clicking the close button.

### 6.1 Placement, and a window nobody can reach

Geometry is saved on `closeEvent`, while the geometry is still real, and
restored on the first `showEvent` only.

**Once, not on every show.** `showEvent` fires again when a window is restored
from minimised — measured trace: `showMinimized` produces `hide` then
`state:min`, and `showNormal` produces `show` then `state:normal`. Restoring
placement on each of those fights the user: they move the window, minimise it,
restore it, and it jumps back to where it was three days ago.

**A maximised window's own bounds are the screen's**, so saving them would lose
the size to restore to. Measured: a window at `(120,80,400,300)` that is then
maximised reports `geometry() == (2,2,796,796)` and
`normalGeometry() == (120,80,400,300)`.

This is a place the port got *simpler*. Avalonia's `Window` exposes only the live
bounds, so LunaP has to reload the previously saved placement and copy the old
values forward when it detects a maximised window. Qt tracks the normal
geometry itself, so that workaround did not port — one line replaces six.

`normalGeometry()` is empty for a window maximised without ever having been
shown normally, and saving a zero-sized rectangle would restore a window nobody
can see, so it falls back to `geometry()`.

**The screen rule is the one that matters.** `placement.is_on_a_screen` decides
whether a saved position is still reachable, and it lives in its own module
taking plain `(x, y, w, h)` tuples, tested with no display, no window and no
`QApplication`.

The failure it prevents cannot be recovered from inside the application: a
window restored onto a monitor that is no longer attached opens at coordinates
with no pixels behind them. It cannot be seen, so it cannot be dragged back, and
the only fix is reaching into the settings store by hand — which assumes the
user knows it exists, and since §7.2 that means a SQLite database rather than a
text file they could open. The rule matters more for it. When the rule rejects a
position the size is still
restored and only the position is dropped, so the window opens where the window
manager puts it at the size the user chose.

Two decisions inside the rule:

- **Intersection, not containment.** A window half off the right edge still has
  a titlebar somebody can grab. Requiring it to fit entirely would reject a lot
  of placements people chose on purpose, and the property being tested is
  reachability rather than tidiness. Sabotaging this to containment turns six
  tests red.
- **An empty screen list returns `True`.** Nothing to check against is not the
  same as "off screen"; refusing there would strand every window at the default
  position on any platform whose screen enumeration this code does not
  understand.

### 6.2 `PollingWindow`, and the timer that stops

A window that re-reads its source on a timer, and **stops while hidden or
minimised**. That is the whole reason it exists: five windows in LunaP
hand-rolled a refresh timer and none of them stopped, so a minimised dashboard
went on querying its source forever (LunaP §8.2).

Restoring refreshes immediately as well as restarting the timer, because
otherwise the first thing seen after restoring is however stale the data went
while the window was away.

Occlusion is not portably detectable, so this covers the two states that are.
A window fully buried under another one keeps polling — a known limit, recorded
rather than left to be discovered.

`is_polling` is public so a test can assert that a hidden window stopped without
racing a clock to prove a negative. Under the offscreen platform a `QTimer`
really does tick while `processEvents` is drained — measured at 20 ticks in
200ms on a 10ms interval — so all of this is tested headlessly.

`abc` is not used to enforce `refresh`. `QWidget`'s metaclass and `ABCMeta`
conflict, and the workarounds cost more than the guarantee is worth, so the base
raises `NotImplementedError` naming the subclass instead: the same failure, one
line later.

### 6.3 `WindowSlot`

"At most one of these, else bring it forward" — the pattern seven call sites in
LunaP hand-wrote before it was extracted, each with its own idea of what to do
when the window was already open (LunaP §8.3).

It is a `QObject` because it watches its window with an event filter on
`QEvent.Close`. Connecting to `destroyed` instead would leave the slot believing
a window nobody can see is still open, for the reason §6 gives.

`refresh_if_open` never creates and never raises the window: a background event
that changed the data should not pop up a window nobody asked for, or take focus
from what the user is doing.

### 6.4 Dialogs come in two pieces

Each dialog is a builder that configures a `QMessageBox` and returns it, plus a
one-line wrapper that shows it.

That split is not ceremony. `exec` spins a modal event loop, so a test that
called it would hang forever with nothing able to click. The builder carries
every decision worth testing — which button is default, what the buttons say,
which icon — and the wrapper is left with nothing in it that can be wrong. It is
the same shape BIMA uses for its overlay: the drawing is testable headlessly and
the window is a thin shell over it.

**Cancel is the default button on a confirmation**, and is also the escape
button. Return on a dialog somebody did not read should do the harmless thing;
confirmations exist for actions worth a second look, and defaulting to the
destructive button removes the second look.

---

## 7. Settings

A handful of small records get stored — where each window was, which theme is
chosen — and LunaPY must not decide *where*. `settings.SettingsStore` is a
four-method `Protocol` over a `(category, name)` pair: `load`, `save`, `delete`,
`keys`. Runtime-checkable, so a host finds out it got the shape wrong at startup
rather than at first save.

**Loading is best-effort everywhere.** A settings record that will not parse
must not take the program with it: a window whose remembered position is
unreadable should open at the default position, not fail to open. Every failure
path returns `None`, `False` or `[]` rather than raising, which makes each
caller's fallback the normal path instead of an exception handler.

`set_diagnostics` is the hook that stops that happening in silence, and it
defaults to discarding. A toolkit that writes to stderr uninvited corrupts the
output of the command-line tool that embedded it — which matters here, because
the first consumer is a tool with a scriptable half.

The store is resolved lazily on first use rather than at import, so a host that
assigns one during startup is never a moment too late. Importing
`lunapy.windowing` must not be the thing that decides where an application's
settings live.

### 7.1 The protocol leaked its first implementation

The first version had a fifth method, `directory(category)`, ported from LunaP's
`ISettingsStore` where it exists so a host can find the folder its themes live
in.

It should not have been in the protocol, and adding a second implementation is
what showed it. "Which folder is this category in" is answerable by a store that
writes files and **meaningless to one backed by a database**. A store cannot
implement it without either lying or raising, and an interface method that one
of its two implementations cannot answer is not an interface method.

`JsonSettingsStore.directory` still exists, as a property of that store.

**The general lesson is the one this project keeps re-learning at different
scales:** a seam with one implementation is not yet a seam, it is a description
of whatever the first implementation happened to do. §1's layering rule survives
because a test enforces it; this one had nothing enforcing it, and the shape was
wrong from the first commit until something else had to fit through it.

### 7.2 SQLite, and a race recorded as acceptable that is now gone

The default store is **`SqliteSettingsStore`** — one database, one row per
record, `sqlite3` from the standard library so it costs nothing against §1.

The change was asked for, and it turned out to retire a hazard this document had
already written down as tolerable. **What §7.1 of the previous draft said:**

> `windows.json` holds every window keyed by `window_key`, read-modify-written
> as a whole. Two windows closing in the same instant can therefore lose one of
> the two updates. That is a real race and an acceptable one: the stake is a
> window position, and the alternative is a lock file that outlives a crash and
> stops every window being remembered at all.

That reasoning was sound about the alternative it considered and wrong about the
alternatives available. The race came from *one document holding every window*,
not from files as such. As rows, each window writes only itself and SQLite
serialises the writers — so the race is **gone rather than tolerated**, and no
lock file is involved. Pinned by `test_two_writers_do_not_clobber_each_other`.

Durability comes with it. A transaction either lands or it does not, so the
write-temporary-then-rename dance in §7.3 has no counterpart in the SQLite
store.

**A trap worth knowing.** A `None` category is stored as the empty string, never
as SQL NULL. **SQLite permits NULL in a `PRIMARY KEY` column** unless it is
declared `NOT NULL`, and NULLs do not compare equal to each other — so a
nullable category would let the same `(NULL, name)` pair be inserted repeatedly,
and `load` would return whichever row it reached first. Sabotaging the mapping
turns **six** tests red, including one where saving the same key twice produces
two rows.

WAL is enabled so a second instance of an application reading settings does not
block the first one writing them. It is a persistent property of the database
file, so setting it on each connect is a no-op after the first.

Connections are opened **per operation**. Settings are written a handful of
times in a session, so the cost is irrelevant, and it sidesteps `sqlite3`'s
same-thread check entirely: a shared connection would have to be either
thread-confined or opened with `check_same_thread=False`, and the second trades
a loud error for a silent corruption the first time a background job saves
something.

**What this costs, stated rather than glossed:** a settings file somebody can
open in a text editor and repair. That was a real property — "text as the
interchange format where a human might need to read it" is a principle worth
keeping — and it is spent here. A `sqlite3` shell is not the same as `$EDITOR`.

### 7.3 What the JSON store is still for

`JsonSettingsStore` is no longer the default and is not deprecated. It exists
for a host that wants the property §7.2 gave up, and it is the only thing that
demonstrates `SettingsStore` is a seam — it is what caught §7.1.

Its saves are full-write-then-rename. An interrupted save must leave the
previous file intact rather than a truncated one, and a truncated JSON file is
worse than a missing one: it reports as corrupt on every start instead of
quietly using defaults once.

The temporary is created in the **destination's own directory**, not in `/tmp`.
`os.replace` is only atomic within a filesystem, and `/tmp` is frequently a
different mount — the rename would silently degrade to copy-then-delete, which
is exactly the non-atomic behaviour the code was written to avoid. Pinned by a
test that spies on `mkstemp`'s `dir` argument, because nothing about the
resulting file would reveal the difference.

All of that is machinery the SQLite store gets from a transaction, and it is the
clearest single illustration of what moving to a database bought.

The contract tests run over **both** stores from one parametrised fixture. That
is the whole point of having two.

---

## 8. Guards made to fail on purpose

Every guard in this project is sabotaged before it is trusted, because a test
that cannot fail is not a test. What each sabotage turned red:

| Sabotage | Result |
|---|---|
| Remove the repolish from `set_style_key` | `test_a_style_key_set_after_showing_needs_the_repolish` |
| Import an installed but forbidden module | `test_imports_only_qt_and_the_standard_library[fluent.py]` |
| `from PySide6.QtCharts import QChart` in `fluent.py` | `test_no_module_reaches_outside_pyside6_essentials` (see §1.2) |
| Remove `image.fill(0)` from `capture` | `test_the_flat_guard_catches_a_widget_that_paints_nothing` |
| Restore placement on every show | `test_placement_is_restored_once_not_on_every_show` |
| Save live `geometry()` when maximised | `test_a_maximized_window_remembers_the_size_to_restore_to` |
| Skip the screen check on restore | `test_a_placement_off_every_screen_keeps_the_size_and_drops_the_position` |
| Never stop the poll timer | 4 tests, including `test_closing_stops_the_timer` |
| Containment instead of intersection | 6 tests, including the edge-touch case |
| Store a `None` category as SQL NULL | 6 tests, including saving one key twice producing two rows |
| Let `sqlite3` errors propagate | `test_an_unreadable_database_returns_none_rather_than_raising` |
| Drop the WAL pragma | `test_wal_is_enabled` |
| Clear `Latest`'s flag after presenting | `test_the_final_value_always_arrives` (see §10.1) |
| `Suppressor` as a boolean, not a counter | 2 tests, including the nesting case |
| `LunaList.refresh` without suppressing | `test_refresh_does_not_look_like_a_user_choice` |
| Refuse a theme file on an unknown token | 3 tests in `test_themes.py` |
| Delete comments instead of blanking them | `test_a_warning_after_a_comment_block_names_the_right_line` |

Two of these are worth more than the others.

**`image.fill(0)` is recorded in §4.1**, because the guard was written first,
looked correct, and certified nothing — the first version of it used a widget
that painted its own background.

**§10.1 is the second time a guard was green for the wrong reason**, and the
more interesting one: the `Latest` test looked like a stress test and was a coin
flip weighted at approximately one. The same sabotage then showed a second piece
of defensive code was doing nothing at all, and it was removed.

**The forbidden-import sabotage failed on the first attempt for a reason that
was not the guard's fault**: it imported `numpy`, which is not installed, so
collection died with `ModuleNotFoundError` before the layering test ran at all.
The guard parses ASTs and never imports anything, so it would have caught it;
the *sabotage* was wrong. Re-run against `pytest` — installed, not permitted,
not stdlib — it turned red as designed. Worth recording because a sabotage that
errors instead of failing looks superficially like a guard working.

---

## 9. Where this is thin

Named so nobody mistakes an absence for a decision:

- **A buried window keeps polling.** §6.2 — occlusion is not portably
  detectable. A window fully behind another one is not distinguishable from one
  in front, so only hidden and minimised are covered.
- **Accessibility is measured against Qt's automation tree, not a screen
  reader.** §5, and the same limit LunaP §24.4 states about Avalonia's.
- **Three dark foregrounds sit below the AA contrast floor.** §2.1, recorded
  with measurements rather than adjusted in passing.
- **`is_ui_thread` answers `False` when there is no `QApplication`**, rather
  than raising. That is right for a library being imported by a script, and it
  means `run` on a bare interpreter posts into a poster that then raises. There
  is no test for the bare-interpreter path because the harness always has an
  application.
- **The theme loader takes six-digit hex only.** §12 — `rgb()` and the named
  colours are refused on purpose, because the contrast arithmetic reads hex.
- **No `MessageWindow`.** LunaP has one; `windowing.message` covers what BIMA
  and the gallery needed, and a whole window class with no consumer would be a
  guess.

---

## 10. Threading

Qt does more of this than Avalonia did, and the port shrank accordingly: a
queued signal connection already marshals across threads, so most of what
`UiThread` existed for is free. `run` and `post` remain, because "am I already
on the UI thread" is a question with two different right answers — and `run`
being *inline* when already there is not an optimisation. Always queuing would
mean a caller on the UI thread does not see the effect until after it returns,
so `slot.show(...)` followed by reading `slot.current` would find nothing. A
seam whose observable behaviour depends on which thread called it is worse than
no seam.

`Suppressor` is a counter rather than a boolean, and that is the one thing it
adds over the six hand-written flags LunaP replaced (§21.1). A nested update —
a refresh calling a helper that refreshes something else — re-enables
notifications halfway through the outer one with a boolean, at which point the
guard is worse than absent because the code reads as though it is protected.

`Debounce` is trailing-edge only. A leading-edge variant is a different control
with a different feel and is not offered rather than offered badly: the search
boxes it exists for all want the trailing edge, because the first keystroke of a
word is the least informative one.

### 10.1 A guard that could not fail, found by sabotage, twice

`Latest` exists to avoid one specific bug, recorded at LunaP §22.1: its three
hand-written copies cleared the scheduled flag **after** presenting, so an offer
arriving during a present could neither schedule nor be picked up, and sat there
until the next offer pushed it out. At 60fps nobody could see it; it shows when
the stream stops, which is exactly when somebody is about to sit and look at the
last value.

**The first test written for it could not fail.** It hammered `offer` from a
worker thread twenty times over and asserted the final value arrived. Sabotaging
the implementation to match LunaP's broken copies exactly — late clear *and* no
re-check — left it green every run.

The reason is that the race window is the microseconds inside `_present`, and a
racing producer essentially never lands in it. The test looked like a stress
test and was a coin flip weighted at approximately one.

The rewrite holds the window open: `present` blocks on an event until a worker
has offered into it, so every run enters the race. It now fails on the sabotage.

**Then the same sabotage answered a second question nobody had asked.** Removing
only the trailing re-check left the suite green, while removing only the early
clear turned it red — so the re-check was doing nothing. It was ported faithfully
from LunaP, where it closes a window that genuinely exists: `Interlocked.Exchange`
on `_pending` and a second one on `_scheduled` are two atomic operations with a
gap between them, and an offer landing in that gap queues nothing. This port
holds one lock across both, so the gap is not there.

It has been removed. **Defensive code that no test can distinguish is weight,
not safety** — and this is the second time in this project that a guard was
green for the wrong reason (§4.1 is the first). Both were found the same way,
which is the argument for the habit rather than for either fix.

---

## 11. The control kit

Deferred until there was a consumer, then built. Every control takes **plain
data or a callable**, never an interface of LunaPY's — a meter row takes
`(str, float, str)` and can never take your telemetry type.

This file is a fraction of the size of LunaP's `Controls/`, and the reason is
structural rather than a matter of doing less. Avalonia needs a
`TemplatedControl` plus a `ControlTheme` in XAML plus a `StyleKeyOverride` per
control, and LunaP §5.5 and §14.1 record the style-key trap biting twice — the
second time throwing rather than degrading to blank. A `QWidget` with a layout
has no template to fail to find.

**`LunaSwitch` is a `QCheckBox`, and does not pretend otherwise.** Qt has no
toggle switch. Faking one means a custom-painted control with its own
accessibility story to get wrong, in exchange for an appearance — and LunaP
§24.1 measured what that cost: its switch put the label in `OnContent` and
`OffContent`, left `Content` null, and every switch on a settings page announced
as an unnamed button. A check box carries its label natively and reports itself
correctly, so the entire class of problem does not arise.

The recurring theme across `widgets.py` is **a selection change the user made
versus one the program caused by rebuilding the list**. Every widget holding a
selection draws that line, because a handler that cannot tell them apart re-runs
the user's last action every time the data refreshes.

`LunaList` is the clearest case. Five places in LunaP projected a model to a
string, kept a parallel array to map the index back, and one then parsed the
label apart again to recover a field it already had. **Parsing a display string
to recover a model field is the shape of a missing control.**

### 11.1 `isVisible` cannot answer "did I hide this"

`EmptyState.has_detail` and `FieldRow.has_hint` read `isHidden()`, not
`isVisible()`.

A widget whose window has not been shown reports `isVisible() == False`
regardless of what was asked for, so the obvious spelling answers "is my parent
on screen" rather than "did I hide this deliberately". Both properties were
written the obvious way first and both failed on their first test, on a control
that had been built but not shown — which is every control in a unit test.

### 11.2 The lifetime hazard caught its own author

`MeterRow` builds its layout directly on `self`. The first version wrote
`row(...).layout()` and moved it across, which is §3.3's hazard in one line: the
widget `row` returns is a temporary, nothing holds it, CPython collects it, and
the C++ destructor takes the three children with it.

Worth recording because §3.3 had already been written, cited and tested by the
time this was typed. **Knowing about a footgun is not the same as not firing
it**, and the value of the guard is that it turned a confusing
`RuntimeError: Internal C++ object already deleted` into a named test the
traceback points at.

---

## 12. The theme loader

A theme is a `.css` file: `:root` holds the palette as `--luna-*` custom
properties, and everything outside it is passed to Qt as stylesheet rules.

**This is a much smaller job than LunaP's**, and the difference is worth the
paragraph. LunaP had to *compile* its CSS into Avalonia `Styles` — a selector
vocabulary, per-element allow-lists of states and parts, property resolution
through the property registry — and §12.2 argues at length for that restricted
parser over `AvaloniaRuntimeXamlLoader`, on the grounds that the loader will
instantiate arbitrary Avalonia types out of a file in `/etc`.

Qt's styling language **is** CSS-shaped and already restricted by construction:
QSS sets properties on widgets and cannot construct anything. So the
pass-through that would have been reckless in Avalonia is the safe default here,
and the only part needing a parser is the palette.

**The key's suffix decides the type, not the value's shape.** `…_size` is a
number, `…_font` a font family, everything else a colour. Inferring from the
value was the obvious alternative and is a coin flip: `monospace` and
`gainsboro` are the same token shape. The cost is real and stated — a future
palette key that is none of the three needs a line in the parser, and until then
it is read as a colour and reported as unparsable.

Colours are **six-digit hex only** (three-digit expands). `rgb()` and the named
colours are refused deliberately: `palette.contrast_ratio` reads hex, so
accepting a form it cannot measure would let a theme set a colour the
accessibility tests cannot check. Narrower than LunaP's, on purpose.

**Failure is two-tier, and the split is the design.** A *syntax* error — an
unbalanced brace, an unterminated comment — refuses the whole file and leaves
the previous theme in force. An *unknown* token, a bad colour, a declaration
with no colon is reported and skipped, and the rest applies. A theme written
against a later LunaPY has to keep loading; refusing the file would make every
palette key added to the kit a breaking change for every theme on disk.

### 12.1 Line numbers, and two ways to get them wrong

Warnings name the file's own line numbers, which required getting two things
right and both were wrong first.

Comments are replaced by **whitespace of the same shape** rather than deleted,
so a warning after a twenty-line comment block still names the right line. LunaP
§12.2 flags this as the one part of a hand-written parser that silently drifts,
which is why it was ported deliberately.

The second was not in LunaP's record. Declarations were located with
`block.index(raw)`, which finds the *first* occurrence — so two identical
declarations both blamed the first one's line — and which measures from where
the previous semicolon left off, *before* the chunk's own leading newline, so
every declaration starting on a fresh line reported one line short. That is
every declaration in a normally formatted file. It now walks a running offset,
and both cases are pinned.

---

## 13. The gallery

Every control in the kit on one window, against the current theme. The fastest
way to see what a theme you are writing actually does.

It earns its place a second way that LunaP's did not: **a render test over the
gallery is a render test over the whole kit.** One window containing one of
everything means `assert_laid_out` catches a control that renders as nothing,
without needing a per-control test to notice.

It is rendered in **both variants**, which is LunaP §23.1's lesson applied one
level up. Its harness pinned Dark, so a defect that only appeared in Light was
invisible to every test it had — *a harness that fixes an environment variable
cannot test behaviour across that variable*. A third test asserts the two
variants do not render identically, because rendering in both proves nothing if
the variant never reached the pixels.

`gallery_content()` is separate from `GalleryWindow` so a test can render it
without a window, and so an application can embed it in its own settings page.
`python -m lunapy.gallery` opens it for real.
