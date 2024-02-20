from operator import le
from pathlib import Path
import pytest

from import_embargo.core import (
    Config,
    ModuleTreeBuildingMode,
    get_filenames_to_check,
    get_import_nodes,
    main,
)
from import_embargo.core import build_allowed_modules_tree
from import_embargo.core import is_operation_allowed
from import_embargo.core import get_package_config


@pytest.mark.parametrize(
    "imported_module, allowed_modules_tree, result",
    (
        ("a.b.c", {"a": {}}, True),
        ("b", {"a": {}}, False),
        ("a.c", {"a": {"b": {}}}, False),
    ),
)
def test_is_operation_allowed(imported_module, allowed_modules_tree, result):
    assert (
        is_operation_allowed(
            imported_module=imported_module, allowed_modules_tree=allowed_modules_tree
        )
        is result
    )


def test_build_allowed_modules_tree():
    config = Config(
        setting={},
        path="/test/test",
    )
    config.setting[ModuleTreeBuildingMode.IMPORT] = [
        "a.b.c",
        "a.d.e",
        "a.d.f",
        "x.y",
    ]
    config.setting[ModuleTreeBuildingMode.EXPORT] = []
    config.setting[ModuleTreeBuildingMode.BYPASS] = []

    assert build_allowed_modules_tree(config, mode=ModuleTreeBuildingMode.IMPORT) == {
        "a": {"b": {"c": {}}, "d": {"e": {}, "f": {}}},
        "x": {"y": {}},
    }
    assert build_allowed_modules_tree(config, mode=ModuleTreeBuildingMode.EXPORT) == {}


def test_get_package_config():
    root_path = Path(".").cwd()

    config = get_package_config(
        directory_path=Path(
            f"{root_path}/tests/test_structure/module_c/hello.py"
        ).parent,
        config_lookup={},
        root_path=root_path.cwd(),
    )
    assert config is not None
    assert config.setting[ModuleTreeBuildingMode.IMPORT] == []

    config = get_package_config(
        directory_path=Path(
            f"{root_path}/tests/test_structure/module_a/submodule_a/service.py"
        ).parent,
        config_lookup={},
        root_path=root_path.cwd(),
    )
    assert config is not None
    assert config.setting[ModuleTreeBuildingMode.IMPORT] == []


def test_get_import_nodes():
    root = Path().cwd()
    test_file = Path(f"{root}/tests/test_structure/module_b/service.py")
    result = get_import_nodes(test_file)
    assert result is not None
    assert len(result) == 3
    first_node = result[0]
    assert first_node.module == "tests.test_structure.module_a.service"
    children = first_node.names
    assert len(children) == 1
    assert children[0].name == "is_weather_nice_today"

    second_node = result[1]
    assert second_node.module == "tests.test_structure.module_a"
    children = second_node.names
    assert children[0].name == "service"


def test_get_filenames_to_check():
    root_path = Path().cwd()

    filenames = get_filenames_to_check(
        app_root_path=root_path,
        filenames=[
            "tests/test_structure/module_c/hello.py",
            "tests/test_structure/module_b/service.py",
        ],
    )
    assert len(filenames) == 2

    filenames = get_filenames_to_check(
        app_root_path=root_path, filenames=["tests/test_structure/module_c"]
    )
    assert len(filenames) == 2

    filenames = get_filenames_to_check(
        app_root_path=root_path, filenames=["tests/test_structure/module_a"]
    )
    assert len(filenames) == 4

    filenames = get_filenames_to_check(app_root_path=root_path, filenames=["tests"])
    assert len(filenames) == 23


def test_main_with_fail_import():
    args = [
        "tests/test_structure/module_a",
        "tests/test_structure/module_b",
        "tests/test_structure/module_c",
    ]
    with pytest.raises(SystemExit) as err:
        main(args)
        assert err.value.code == -1


def test_main_with_fail_export():
    args = [
        "tests/test_structure/module_d/service_with_bad_import.py",
    ]

    with pytest.raises(SystemExit) as err:
        main(args)
        assert err.value.code == -1


@pytest.mark.parametrize(
    "args",
    (
        (
            [
                "tests/test_structure/module_b",
                "tests/test_structure/module_d/service.py",
                "tests/test_structure/module_f",
            ]
        ),
        [
            "tests/test_structure/module_f/private_submodule_f",
        ],
        [
            "tests/test_structure/module_f/private_submodule_f/__init__.py",
        ],
    ),
)
def test_main_happy_path(args):
    main(args)
