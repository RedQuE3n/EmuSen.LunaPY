"""The gallery, which is also a render test over the whole kit.

One window containing one of everything means `assert_laid_out` over it catches
a control that renders as nothing, without needing a test per control to notice.
That is the second reason the gallery earns its place, and LunaP did not have
it.
"""

import pytest

from lunapy import settings
from lunapy.gallery import GalleryWindow, gallery_content
from lunapy.palette import Variant
from lunapy.settings import SqliteSettingsStore
from lunapy.testing import assert_laid_out, show
from lunapy import theme


@pytest.fixture(autouse=True)
def isolated_store(tmp_path):
    settings.set_store(SqliteSettingsStore(tmp_path / "settings.db"))
    yield
    settings.set_store(None)


def test_the_gallery_lays_out(app):
    """If a control in the kit renders as one flat colour, this is what says so."""
    assert_laid_out(show(gallery_content(), 560, 700), "gallery")


@pytest.mark.parametrize("variant", [Variant.DARK, Variant.LIGHT])
def test_the_gallery_lays_out_in_both_variants(app, variant):
    """LunaP §23.1's lesson one level up: its harness pinned Dark, so a defect
    that only appeared in Light was invisible to every test it had. **A harness
    that fixes an environment variable cannot test behaviour across it.**"""
    theme.apply(app, variant)
    try:
        assert_laid_out(show(gallery_content(), 560, 700), f"gallery_{variant.value}")
    finally:
        theme.apply(app, Variant.DARK)


def test_the_two_variants_do_not_render_identically(app):
    """The other half of the same point: rendering in both proves nothing if the
    variant never reached the pixels."""
    from lunapy.testing import capture

    theme.apply(app, Variant.DARK)
    dark = capture(show(gallery_content(), 400, 500)).digest
    theme.apply(app, Variant.LIGHT)
    light = capture(show(gallery_content(), 400, 500)).digest
    theme.apply(app, Variant.DARK)
    assert dark != light


def test_the_gallery_window_opens(app):
    window = GalleryWindow()
    show(window, 560, 700)
    assert_laid_out(window, "gallery_window")
    window.close()
