import argparse
import ast
import dataclasses
import enum
import json
from pathlib import Path
from typing import TypeAlias

IGNORE_LIST = {"__pycache__", ".mypy_cache", ".DS_Store", ".ruff_cache"}


class ModuleTreeBuildingMode(enum.Enum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    BYPASS = "BYPASS"


@dataclasses.dataclass
class Config:
    setting: dict[ModuleTreeBuildingMode, list[str] | None]
    path: str


ConfigLookup: TypeAlias = dict[str, Config]


def get_import_nodes(filename: str) -> list[ast.ImportFrom]:
    with open(filename) as f:
        file = f.read()
    tree = ast.parse(file)

    return [node for node in tree.body if isinstance(node, ast.ImportFrom)]


def build_path_from_import(module_import: str, root_path: Path) -> Path:
    """
    Build an absolute path to a file based on a app root path and module import.
    """
    module_path = Path(module_import.replace(".", "/"))
    return root_path / module_path


def build_module_from_path(path: Path, root_path: Path) -> str:
    return str(path.relative_to(root_path)).replace("/", ".").replace(".py", "")


def get_package_config(
    directory_path: Path, root_path: Path, config_lookup: ConfigLookup
) -> Config | None:
    potential_embargo_file = Path(directory_path) / Path("__embargo__.json")

    cached_config = config_lookup.get(str(potential_embargo_file))
    if cached_config is not None:
        return cached_config

    if not potential_embargo_file.exists():
        if directory_path == root_path:
            return None
        return get_package_config(directory_path.parent, root_path, config_lookup)

    json_config = json.loads(potential_embargo_file.read_text())
    config = Config(
        path=str(potential_embargo_file),
        setting={},
    )
    for (which, name) in [
        (ModuleTreeBuildingMode.IMPORT, "allowed_import_modules"),
        (ModuleTreeBuildingMode.EXPORT, "allowed_export_modules"),
        (ModuleTreeBuildingMode.BYPASS, "bypass_export_check_for_modules"),
    ]:
        config.setting[which] = json_config.get(name)
    config_lookup[str(potential_embargo_file)] = config
    return config


def is_local_import(module_import: ast.ImportFrom) -> bool:
    """
    Determines if import is local or from third party library
    """
    module = module_import.module
    if module is None:
        return False
    module_path = module.split(".")
    first_package = module_path[0]

    return Path(first_package).is_dir() or Path(first_package + ".py").exists()


def build_allowed_modules_tree(
    config: Config, mode: ModuleTreeBuildingMode
) -> dict[str, dict]:
    """
    Example:
        allowed_import_packages=[
            "a.b.c",
            "a.d.e",
            "a.d.f",
            "x.y",
        ]
    Result:
        {
            "a": {
                "b": {
                    "c": {}
                },
                "d": {
                    "e": {}, "f": {}
                }
            },
            "x": {
                "y": {}
            }
        }
    """
    tree: dict[str, dict] = {}
    allowed = config.setting[mode] or {}  # type: ignore [var-annotated]

    for allowed_import in allowed:
        current_dict = tree
        for s in allowed_import.split("."):
            current_dict = current_dict.setdefault(s, {})
    return tree


def can_bypass_check(imported_from: str, bypass_modules_tree: dict[str, dict]) -> bool:
    return is_operation_allowed(
        imported_module=imported_from, allowed_modules_tree=bypass_modules_tree
    )


def is_operation_allowed(
    imported_module: str, allowed_modules_tree: dict[str, dict]
) -> bool:
    """
    Determines if imported module is allowed.

    If you import the following module:
        from a import b
    It least 'a' needs to be allowed in config.
    eg. allowed_modules_tree = ['a']

    If the following module is imported:
        from a import b
    and the allowed path is:
        allowed_modules_tree = ['a.c']
    the import will reported as violation as it has diverged from the 'a.c' path.
    """
    splitted_module_name = imported_module.split(".")
    current_dict: dict[str, dict] | None = allowed_modules_tree
    for name in splitted_module_name:
        current_dict = current_dict.get(name)  # type: ignore
        if current_dict is None:
            return False
        if current_dict == {}:
            return True
    return True


def get_filenames_to_check(filenames: list[str], app_root_path: Path) -> list[Path]:
    all_files: list[Path] = []
    for filename in filenames:
        path = app_root_path / Path(filename)
        if path.is_file():
            all_files.append(path)
        else:
            for path in path.rglob("*.py"):
                if not any(dir_name in IGNORE_LIST for dir_name in path.parts):
                    all_files.append(path)
    return all_files


def check_for_allowed(
    mode: ModuleTreeBuildingMode,
    file: Path,
    app_root_path: Path,
    config_lookup: ConfigLookup,
    node: ast.ImportFrom,
) -> list[str]:
    """
    Checks whether module X.py can import any other module when mode is ModuleTreeBuildingMode.IMPORT
    or whether module X.py can be imported from other modules when mode is ModuleTreeBuildingMode.EXPORT
    """
    violations: list[str] = []

    if mode == ModuleTreeBuildingMode.EXPORT:
        actual_path = build_path_from_import(
            module_import=node.module or "", root_path=app_root_path
        )
    elif mode == ModuleTreeBuildingMode.IMPORT:
        actual_path = file
    else:
        raise Exception("Invalid mode")

    config = get_package_config(
        directory_path=actual_path.parent,
        root_path=app_root_path,
        config_lookup=config_lookup,
    )
    if config is None or config.setting[mode] is None:
        return []

    allowed_modules_tree = build_allowed_modules_tree(config=config, mode=mode)

    if node.module is None:
        return []

    if mode == ModuleTreeBuildingMode.EXPORT:
        bypass_modules_tree = build_allowed_modules_tree(
            config=config, mode=ModuleTreeBuildingMode.BYPASS
        )
        if can_bypass_check(
            imported_from=build_module_from_path(path=file, root_path=app_root_path),
            bypass_modules_tree=bypass_modules_tree,
        ):
            return []

    if is_operation_allowed(node.module, allowed_modules_tree):
        return []

    violations.append(f"{file}: {node.module}")
    if mode == ModuleTreeBuildingMode.EXPORT:
        violations.append(
            f"Allowed exports: {config.setting[ModuleTreeBuildingMode.EXPORT]}"
        )
    else:
        violations.append(
            f"Allowed imports: {config.setting[ModuleTreeBuildingMode.IMPORT]}"
        )

    violations.append(f"Config file: {config.path}\n")
    return violations


def check_for_violations(
    filename: Path,
    app_root_path: Path,
    config_lookup: dict[str, Config],
) -> tuple[list[str], list[str]]:
    import_violations: list[str] = []
    export_violations: list[str] = []
    if not str(filename).endswith(".py"):
        print(f"Not checking file {filename}")
        return [], []

    import_nodes = get_import_nodes(str(filename))
    local_import_nodes = filter(is_local_import, import_nodes)

    for node in local_import_nodes:
        #
        # Check for allowed imports
        #
        import_violations += check_for_allowed(
            mode=ModuleTreeBuildingMode.IMPORT,
            app_root_path=app_root_path,
            file=filename,
            config_lookup=config_lookup,
            node=node,
        )

        #
        # Check for allowed exports
        #
        export_violations += check_for_allowed(
            mode=ModuleTreeBuildingMode.EXPORT,
            app_root_path=app_root_path,
            file=filename,
            config_lookup=config_lookup,
            node=node,
        )

    return import_violations, export_violations


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "filenames",
        nargs="*",
        help="List of files or directories. Example: src/module_a src/module_b",
    )
    parser.add_argument(
        "--app-root",
        dest="app_root",
        default=".",
        help="Defines the root directory where your python application lives."
        "Default value is current working directory. Example: --app-root=src",
    )
    args = parser.parse_args(argv)

    if not Path(args.app_root).exists():
        print(
            "--app-root argument does not point to root directory of python application"
        )
        exit(1)

    app_root_path = Path(args.app_root).resolve()

    filenames_to_check = get_filenames_to_check(
        args.filenames, app_root_path=app_root_path
    )

    import_violations: list[str] = []
    export_violations: list[str] = []
    config_lookup: dict[str, Config] = {}

    for file in filenames_to_check:
        imp_violations, exp_violations = check_for_violations(
            filename=file,
            app_root_path=app_root_path,
            config_lookup=config_lookup,
        )
        import_violations += imp_violations
        export_violations += exp_violations

    if len(import_violations) > 0:
        print(" ❌ Import violations detected\n")
        for violation in import_violations:
            print(violation)

    if len(export_violations) > 0:
        print(" ❌ Export violations detected\n")
        for violation in export_violations:
            print(violation)

    if len(import_violations) + len(export_violations) > 0:
        exit(1)
