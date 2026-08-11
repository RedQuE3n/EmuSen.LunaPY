"""One application for the whole run, and a theme reset between tests.

Qt permits exactly one `QApplication` per process, and a second one aborts
rather than raising — a test run that simply stops, with no failure reported.
So the fixture is session-scoped and every test takes it.
"""

import pytest

from lunapy import Variant
from lunapy import theme
from lunapy.testing import ui_app


@pytest.fixture(scope="session")
def app():
    return ui_app()


@pytest.fixture(autouse=True)
def dark_by_default(app):
    """Put the variant back after any test that changed it.

    `theme` keeps the active variant in module state, which is right for an
    application and a hazard for a suite: a test that switches to light and does
    not switch back leaves every later test asserting against a palette it did
    not choose. That failure is order-dependent, so it appears when an unrelated
    test is added and blames the wrong change.
    """
    yield
    theme.apply(app, Variant.DARK)
