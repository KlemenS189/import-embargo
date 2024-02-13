import pytest

from import_embargo.core import Config
from import_embargo.core import build_allowed_modules_tree
from import_embargo.core import is_import_allowed


@pytest.mark.parametrize(
    "imported_module, allowed_modules_tree, result",
    (
        ("a.b.c", {"a": {}}, True),
        ("b", {"a": {}}, False),
        ("a.c", {"a": {"b": {}}}, False),
    ),
)
def test_is_import_allowed(imported_module, allowed_modules_tree, result):
    assert (
        is_import_allowed(
            imported_module=imported_module, allowed_modules_tree=allowed_modules_tree
        )
        is result
    )


def test_build_allowed_modules_tree():
    config = Config(
        allowed_import_modules=[
            "a.b.c",
            "a.d.e",
            "a.d.f",
            "x.y",
        ],
        path="/test/test",
    )
    assert build_allowed_modules_tree(config) == {
        "a": {"b": {"c": {}}, "d": {"e": {}, "f": {}}},
        "x": {"y": {}},
    }
