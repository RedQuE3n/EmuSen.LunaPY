"""The founding rule, enforced: LunaPY imports PySide6 and the standard library.

LunaP arrived at this test at §22.7, after the toolkit had already been cut
loose from the project it grew inside and the rule had been maintained by hand
until then. It is here from the first commit instead, because the rule is
cheap to keep and expensive to restore — by the time an import of somebody's
domain model has been in the tree for a month, removing it is a refactor rather
than a deletion.

What this catches that review does not: an import added inside a function, in a
module nobody re-read, three levels down.
"""

import ast
import sys
from pathlib import Path

import pytest

PACKAGE = Path(__file__).resolve().parent.parent / "lunapy"

# The one third-party name the toolkit is allowed to know about. Adding to this
# list is a decision that belongs in docs/LunaPY.md §1 with its licence, not a
# one-line edit here.
PERMITTED = {"PySide6"}


def modules():
    return sorted(PACKAGE.glob("*.py"))


def imported_names(path: Path):
    """Every top-level module name this file imports, at any nesting depth.

    Walks the whole AST rather than the module body, so an import tucked inside
    a function or a `try` is caught too. Relative imports are skipped — those
    are LunaPY importing itself, which is the point.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                yield node.module.split(".")[0]


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_imports_only_qt_and_the_standard_library(path):
    offenders = {
        name
        for name in imported_names(path)
        if name not in PERMITTED and name not in sys.stdlib_module_names
    }
    assert not offenders, (
        f"{path.name} imports {sorted(offenders)}. LunaPY may import PySide6 and the "
        "standard library only — see docs/LunaPY.md §1."
    )


def test_the_harness_takes_no_test_framework():
    """`lunapy.testing` ships inside the package, so it may not import pytest.

    This is the specific case the rule exists for, and the one LunaP could not
    have: its harness used xunit's `Assert`, so it had to become a second
    package. Ours raises `AssertionError`, which costs nothing — and that only
    stays true if nobody reaches for `pytest.fail` the next time a message needs
    improving.
    """
    names = set(imported_names(PACKAGE / "testing.py"))
    assert "pytest" not in names and "unittest" not in names, (
        "lunapy/testing.py imports a test framework. It raises AssertionError instead "
        "precisely so it can live in the package — see docs/LunaPY.md §4."
    )


def test_the_guard_can_fail():
    """The sabotage. A rule nobody has seen go red is a rule nobody has tested.

    Written as a check of the detector rather than of the package: if
    `imported_names` ever stopped walking nested nodes, every test above would
    pass on a package that had quietly taken a dependency.
    """
    source = "def f():\n    import numpy\n"
    path = PACKAGE.parent / "_sabotage_layering.py"
    path.write_text(source)
    try:
        assert "numpy" in set(imported_names(path))
    finally:
        path.unlink()
