"""Loading a theme from a file.

The two-tier failure rule is what most of this file is about: a syntax error
refuses the whole file, an unknown token is skipped and reported. Getting that
backwards either makes every new palette key a breaking change for every theme
on disk, or lets half a broken file apply.
"""

import pytest

from lunapy import settings, themes
from lunapy.palette import DARK, Variant
from lunapy.themes import available, find, load, parse


@pytest.fixture(autouse=True)
def collect_warnings():
    reported = []
    settings.set_diagnostics(reported.append)
    yield reported
    settings.set_diagnostics(None)


# -- The palette half ----------------------------------------------------


def test_root_tokens_become_palette_overrides():
    theme = parse(":root { --luna-surface: #12131A; --luna-section-header: #7AA2F7; }")
    assert theme.colours == {"surface": "#12131A", "section_header": "#7AA2F7"}


def test_a_theme_sits_over_a_base_column():
    """A file that sets three colours is a valid theme. Requiring every key
    would mean every theme breaks the day a key is added to the kit."""
    theme = parse(":root { --luna-surface: #000000; }")
    column = theme.column(Variant.DARK)
    assert column["surface"] == "#000000"
    assert column["text"] == DARK["text"], "an unset key lost its base value"


def test_short_hex_expands():
    theme = parse(":root { --luna-surface: #abc; }")
    assert theme.colours["surface"] == "#AABBCC"


@pytest.mark.parametrize("value", ["#12131A", "#12131a", "#ABC"])
def test_accepted_colour_forms(value):
    assert parse(f":root {{ --luna-surface: {value}; }}").colours


@pytest.mark.parametrize("value", ["rgb(1,2,3)", "gainsboro", "#12", "#1234567", "not-a-colour"])
def test_rejected_colour_forms_are_skipped_not_fatal(value, collect_warnings):
    """Deliberately narrow. The contrast arithmetic reads six-digit hex, so
    accepting a form it cannot measure would let a theme set a colour the
    accessibility tests cannot check."""
    theme = parse(f":root {{ --luna-surface: {value}; --luna-text: #FFFFFF; }}")
    assert theme is not None, "a bad colour refused the whole file"
    assert "surface" not in theme.colours
    assert theme.colours["text"] == "#FFFFFF", "the rest of the theme did not apply"
    assert any("not a colour" in w for w in theme.warnings)


def test_the_suffix_decides_the_type_not_the_value():
    """Inferring from the value is a coin flip: `monospace` and `gainsboro` are
    the same token shape."""
    theme = parse(
        ':root { --luna-mono-font: "Fira Code", monospace; --luna-hint-font-size: 12; }'
    )
    assert theme.fonts == {"mono_font": '"Fira Code", monospace'}
    assert theme.sizes == {"hint_font_size": 12.0}


def test_a_size_that_is_not_a_number_is_skipped():
    theme = parse(":root { --luna-hint-font-size: large; }")
    assert theme.sizes == {}
    assert any("not a number" in w for w in theme.warnings)


def test_an_unknown_palette_key_is_skipped_not_fatal():
    """A theme written against a later LunaPY has to keep loading. Refusing the
    file would make every key added to the kit a breaking change for every theme
    on disk."""
    theme = parse(":root { --luna-invented-key: #FFFFFF; --luna-surface: #000000; }")
    assert theme is not None
    assert theme.colours == {"surface": "#000000"}
    assert any("invented_key" in w for w in theme.warnings)


def test_a_non_luna_property_is_skipped():
    theme = parse(":root { --other-thing: #FFFFFF; }")
    assert theme.colours == {}
    assert any("not a --luna- token" in w for w in theme.warnings)


def test_a_declaration_with_no_colon_is_skipped():
    theme = parse(":root { --luna-surface #000000; --luna-text: #FFFFFF; }")
    assert theme.colours == {"text": "#FFFFFF"}
    assert any("no colon" in w for w in theme.warnings)


# -- Syntax refusals -----------------------------------------------------


@pytest.mark.parametrize(
    "source, why",
    [
        (":root { --luna-surface: #000000;", "unbalanced braces"),
        (":root { --luna-surface: #000000; } }", "an extra brace"),
        ("/* never closed\n:root { --luna-surface: #000; }", "an unterminated comment"),
    ],
)
def test_a_syntax_error_refuses_the_whole_file(source, why, collect_warnings):
    """The previous theme stays in force, which is the same outcome a malformed
    theme file has always had."""
    assert parse(source, "broken") is None, why
    assert collect_warnings, "a refusal was silent"


# -- Line numbers --------------------------------------------------------


def test_a_warning_after_a_comment_block_names_the_right_line():
    """Comments are replaced by whitespace of the same shape rather than
    deleted. It is the one part of a hand-written parser that silently
    drifts."""
    source = "/*\n\n\n\n\n*/\n:root {\n  --luna-nope: #FFFFFF;\n}"
    theme = parse(source)
    assert any("line 8" in w for w in theme.warnings), theme.warnings


def test_two_identical_declarations_report_their_own_lines():
    """Looking a chunk up with `block.index(raw)` finds the first occurrence, so
    both copies would blame line 2. Pinned because the failure is invisible
    until a theme happens to repeat a declaration."""
    theme = parse(":root {\n  --luna-nope: #FFF;\n  --luna-nope: #FFF;\n}")
    assert [w.split(":")[0] for w in theme.warnings] == ["line 2", "line 3"]


# -- Rules pass through --------------------------------------------------


def test_everything_outside_root_is_stylesheet():
    """Qt's styling language is already restricted by construction — QSS sets
    properties and cannot construct anything — so the pass-through that would
    have been reckless in Avalonia is the safe default here."""
    theme = parse(
        ':root { --luna-surface: #000000; }\n'
        'QLabel[luna="section_header"] { font-weight: normal; }'
    )
    assert 'QLabel[luna="section_header"]' in theme.rules
    assert ":root" not in theme.rules


def test_a_theme_with_no_root_is_still_a_theme():
    theme = parse("QLabel { color: red; }")
    assert theme.colours == {}
    assert "QLabel" in theme.rules


# -- Files ---------------------------------------------------------------


def test_loading_from_a_file(tmp_path):
    (tmp_path / "nocturne.css").write_text(":root { --luna-surface: #12131A; }")
    theme = load(tmp_path / "nocturne.css")
    assert theme.name == "nocturne"
    assert theme.colours["surface"] == "#12131A"


def test_a_missing_file_is_none_not_an_error(tmp_path, collect_warnings):
    assert load(tmp_path / "absent.css") is None
    assert collect_warnings


def test_available_lists_names_without_parsing(tmp_path):
    (tmp_path / "nocturne.css").write_text(":root {")   # would refuse if parsed
    (tmp_path / "dawn.css").write_text(":root { }")
    assert available(tmp_path) == ["dawn", "nocturne"]


def test_available_on_a_missing_directory_is_empty(tmp_path):
    assert available(tmp_path / "nowhere") == []


def test_find_by_name(tmp_path):
    (tmp_path / "dawn.css").write_text(":root { --luna-surface: #FFFFFF; }")
    assert find(tmp_path, "dawn").colours["surface"] == "#FFFFFF"
    assert find(tmp_path, "absent") is None


# -- Applying ------------------------------------------------------------


def test_applying_a_theme_reaches_the_palette_and_the_stylesheet(app):
    from lunapy import theme as theme_module

    loaded = parse(":root { --luna-surface: #123456; }\nQLabel#x { color: red; }", "probe")
    theme_module.apply_theme(app, loaded, Variant.DARK)
    try:
        from PySide6.QtGui import QPalette

        assert app.palette().color(QPalette.ColorRole.Window).name().upper() == "#123456"
        assert "QLabel#x" in app.styleSheet()
        assert theme_module.loaded() is loaded
    finally:
        theme_module.apply(app, Variant.DARK)


def test_applying_a_plain_variant_forgets_the_loaded_theme(app):
    from lunapy import theme as theme_module

    theme_module.apply_theme(app, parse(":root { --luna-surface: #123456; }"), Variant.DARK)
    theme_module.apply(app, Variant.DARK)
    assert theme_module.loaded() is None


def test_a_theme_font_reaches_the_stylesheet(app):
    from lunapy import theme as theme_module

    loaded = parse(':root { --luna-mono-font: "Fira Code"; }')
    theme_module.apply_theme(app, loaded, Variant.DARK)
    try:
        assert "Fira Code" in app.styleSheet()
    finally:
        theme_module.apply(app, Variant.DARK)
