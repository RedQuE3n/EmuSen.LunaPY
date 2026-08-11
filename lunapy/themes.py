"""Loading a theme from a file: a palette in CSS custom properties, plus rules.

A palette is a list of colours, and a heavyweight markup format is a heavy way
to write one. So a theme is a `.css` file::

    /* Nocturne. */
    :root {
      --luna-surface:        #12131A;
      --luna-section-header: #7AA2F7;
      --luna-mono-font:      "Fira Code", monospace;
      --luna-hint-font-size: 12;
    }

    QLabel[luna="section_header"] { font-weight: normal; }

**`:root` is the palette**, and `--luna-section-header` is the key
`section_header` in kebab-case. Everything outside `:root` is passed through to
Qt as stylesheet rules.

**This is a much smaller job than LunaP's, and the reason is worth recording.**
LunaP had to *compile* its CSS into Avalonia `Styles` — a selector vocabulary,
per-element allow-lists of states and parts, property resolution through the
property registry — because Avalonia's own styling language is XAML, and
`AvaloniaRuntimeXamlLoader` will instantiate arbitrary types out of a file in
`/etc`. §12.2 argues at length for a restricted parser over that loader, on
capability grounds.

Qt's styling language **is** CSS-shaped and already restricted by construction:
QSS sets properties on widgets and cannot construct anything. So the pass-through
that would have been reckless in Avalonia is the safe default here, and the only
part needing a parser is the palette.

**Failure is two-tier**, and the split is the design:

- A **syntax** error refuses the whole file and leaves the previous theme in
  force — an unbalanced brace, a declaration with no colon.
- An **unknown token** is reported and skipped, and the rest of the theme
  applies. A theme written against a later LunaPY has to keep loading;
  refusing the file would make every palette key added to the kit a breaking
  change for every theme on disk.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

from .palette import COLUMNS, DARK, Variant
from .settings import report

SUFFIX = ".css"

# `--luna-section-header` -> `section_header`.
_TOKEN = re.compile(r"^--luna-([a-z0-9-]+)$")
_ROOT_BLOCK = re.compile(r":root\s*\{(.*?)\}", re.DOTALL)
_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)


@dataclass
class Theme:
    """A parsed theme: palette overrides, extra stylesheet rules, and what went
    wrong along the way."""

    name: str = ""
    colours: dict[str, str] = field(default_factory=dict)
    fonts: dict[str, str] = field(default_factory=dict)
    sizes: dict[str, float] = field(default_factory=dict)
    rules: str = ""
    warnings: list[str] = field(default_factory=list)

    def column(self, base: Variant = Variant.DARK) -> Mapping[str, str]:
        """This theme's colours over a base column.

        Over a base rather than replacing it, so a theme that sets three colours
        is a valid theme. Requiring every key would mean every theme breaks the
        day a key is added, which is the same argument the unknown-token rule
        makes from the other direction.
        """
        return {**COLUMNS[base], **self.colours}


def _strip_comments(source: str) -> str:
    """Replace comments with whitespace of the same shape rather than deleting
    them, so a warning after a twenty-line comment block still names the right
    line. It is the one part of a hand-written parser that silently drifts."""
    return _COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), source)


def _check_syntax(source: str) -> str | None:
    """Return a reason to refuse the whole file, or `None`."""
    if source.count("{") != source.count("}"):
        return "unbalanced braces"
    if "/*" in source:
        return "unterminated comment"
    return None


def parse(source: str, name: str = "") -> Theme | None:
    """Parse a theme. `None` means the file was refused; check `warnings` on a
    returned theme for the things that were skipped."""
    stripped = _strip_comments(source)
    if (problem := _check_syntax(stripped)) is not None:
        report(f"{name or 'theme'}: {problem}. Theme not applied.")
        return None

    parsed = Theme(name=name)

    root = _ROOT_BLOCK.search(stripped)
    if root is not None:
        _parse_palette(root, stripped, parsed)

    # Everything that is not the :root block is stylesheet, handed to Qt as-is.
    parsed.rules = _ROOT_BLOCK.sub("", stripped).strip()
    return parsed


def _parse_palette(root, whole: str, parsed: Theme) -> None:
    block = root.group(1)
    block_start = root.start(1)

    # Walked with a running offset rather than by looking each chunk up with
    # `block.index(raw)`. Two reasons, and both were bugs: `index` finds the
    # FIRST occurrence, so two identical declarations both report the first
    # one's line; and a chunk begins where the previous semicolon left off,
    # which is before its own leading newline — so the line came out one short
    # for every declaration that started on a fresh line, which is all of them
    # in a normally formatted file.
    position = 0
    for raw in block.split(";"):
        leading = len(raw) - len(raw.lstrip())
        declaration_start = block_start + position + leading
        position += len(raw) + 1  # the +1 is the semicolon that was split out

        declaration = raw.strip()
        if not declaration:
            continue
        line = whole[:declaration_start].count("\n") + 1

        if ":" not in declaration:
            parsed.warnings.append(f"line {line}: '{declaration}' has no colon; skipped")
            continue

        key, _, value = declaration.partition(":")
        match = _TOKEN.match(key.strip())
        if match is None:
            parsed.warnings.append(f"line {line}: '{key.strip()}' is not a --luna- token; skipped")
            continue

        token = match.group(1).replace("-", "_")
        value = value.strip()

        # THE KEY'S SUFFIX DECIDES THE TYPE, NOT THE VALUE'S SHAPE.
        #
        # Inferring from the value was the obvious alternative and is a coin
        # flip: `monospace` and `gainsboro` are the same token shape. The cost
        # of this rule is real and worth stating — a future palette key that is
        # neither a size, a font nor a colour needs a line here, and until then
        # it is read as a colour and reported as unparsable.
        if token.endswith("_size"):
            try:
                parsed.sizes[token] = float(value)
            except ValueError:
                parsed.warnings.append(f"line {line}: '{value}' is not a number; skipped")
        elif token.endswith("_font"):
            parsed.fonts[token] = value
        elif token not in DARK:
            parsed.warnings.append(f"line {line}: '{token}' is not a palette key; skipped")
        elif (colour := _parse_colour(value)) is None:
            parsed.warnings.append(f"line {line}: '{value}' is not a colour; skipped")
        else:
            parsed.colours[token] = colour


def _parse_colour(value: str) -> str | None:
    """Accept `#RGB` and `#RRGGBB`, normalised to `#RRGGBB`.

    Deliberately narrow. The palette's own values are six-digit hex and the
    contrast arithmetic in `palette` reads exactly that, so accepting `rgb()`
    or a named colour here would mean a theme could set a colour that the
    contrast tests cannot measure — which is worse than not accepting it.
    """
    text = value.strip().lower()
    if not text.startswith("#"):
        return None
    digits = text[1:]
    if len(digits) == 3 and all(c in "0123456789abcdef" for c in digits):
        return "#" + "".join(c * 2 for c in digits).upper()
    if len(digits) == 6 and all(c in "0123456789abcdef" for c in digits):
        return "#" + digits.upper()
    return None


def load(path: Path | str) -> Theme | None:
    """Parse a theme file. `None` for missing, unreadable or refused."""
    path = Path(path)
    try:
        source = path.read_text(encoding="utf-8")
    except OSError as error:
        report(f"{path}: {error}. Theme not applied.")
        return None
    return parse(source, name=path.stem)


def available(directory: Path | str) -> list[str]:
    """Every theme name in a directory, without parsing any of them."""
    try:
        return sorted(p.stem for p in Path(directory).glob(f"*{SUFFIX}"))
    except OSError as error:
        report(f"{directory}: {error}.")
        return []


def find(directory: Path | str, name: str) -> Theme | None:
    return load(Path(directory) / f"{name}{SUFFIX}")
