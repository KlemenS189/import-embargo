import argparse
import ast
import dataclasses
import enum
import json
from pathlib import Path
from typing import TypeAlias

IGNORE_LIST = {"__pycache__", ".mypy_cache", ".DS_Store", ".ruff_cache"}


@dataclasses.dataclass
class Config:
    allowed_import_modules: list[str] | None
    allowed_export_modules: list[str] | None
    bypass_export_check_for_modules: list[str]
    path: str


class ModuleTreeBuildingMode(enum.Enum):
    IMPORT = "IMPORT"
    EXPORT = "EXPORT"
    BYPASS = "BYPASS"


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
    return Path(f"{root_path}/{module_path}")


def build_module_from_path(path: Path, root_path: Path) -> str:
    return str(path.relative_to(root_path)).replace("/", ".").replace(".py", "")


def get_package_config(
    directory_path: Path, root_path: Path, config_lookup: ConfigLookup
) -> Config | None:
    potential_embargo_file = Path(f"{directory_path}/__embargo__.json")

    cached_config = config_lookup.get(str(potential_embargo_file))
    if cached_config is not None:
        return cached_config

    if not potential_embargo_file.exists():
        if directory_path == root_path:
            return None
        return get_package_config(directory_path.parent, root_path, config_lookup)

    json_config = json.loads(potential_embargo_file.read_text())
    config = Config(
        allowed_import_modules=json_config.get("allowed_import_modules"),
        allowed_export_modules=json_config.get("allowed_export_modules"),
        bypass_export_check_for_modules=json_config.get(
            "bypass_export_check_for_modules", []
        ),
        path=str(potential_embargo_file),
    )
    config_lookup[str(potential_embargo_file)] = config
    return config


def get_package_tree(path: Path) -> dict[str, dict | None]:
    """
    We want to recursively build a tree:
    {
        "dir_a": {
            "file.py": None
        },
        "dir_b": {}
    }
    if value of a key is None, then it means it's a file.
    """
    package_tree: dict[str, dict | None] = {}

    for item in path.iterdir():
        if item.name in IGNORE_LIST:
            continue
        if item.is_file() and item.name.endswith(".py"):
            package_tree[item.name] = None
        if item.is_dir() and "." not in item.name:
            package_tree[item.name] = get_package_tree(item)
    return package_tree


def get_files_in_dir(path: Path) -> set[Path]:
    files = set()

    for item in path.iterdir():
        if item.name in IGNORE_LIST:
            continue
        if item.is_file() and item.name.endswith(".py"):
            files.add(item)
        if item.is_dir() and "." not in item.name:
            new_files = get_files_in_dir(item)
            files = files.union(new_files)
    return files


def get_local_import_nodes(
    import_nodes: list[ast.ImportFrom], local_package_tree: dict
) -> list[ast.ImportFrom]:
    """
    Determines if import is local or from third party library
    """
    local_import_nodes = []
    for node in import_nodes:
        module = node.module
        if module is None:
            continue
        module_path = module.split(".")
        first_package = module_path[0]
        if first_package in local_package_tree:
            local_import_nodes.append(node)
    return local_import_nodes


def build_allowed_modules_tree(config: Config, mode: ModuleTreeBuildingMode) -> dict:
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
    match mode:
        case ModuleTreeBuildingMode.BYPASS:
            config_modules = config.bypass_export_check_for_modules
        case ModuleTreeBuildingMode.IMPORT:
            config_modules = config.allowed_import_modules  # type: ignore
        case _:
            config_modules = config.allowed_export_modules  # type: ignore
    for allowed_import in config_modules:
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


def get_filenames_to_check(filenames: list[str], app_root_path) -> list[Path]:
    all_files: list[Path] = []
    for filename in filenames:
        path = Path(f"{app_root_path}/{filename}")
        if path.is_dir():
            found_files = get_files_in_dir(path)
            all_files += found_files
        if path.is_file():
            all_files.append(Path(path))
    return all_files


def check_for_allowed_imports(
    filename: Path,
    app_root_path: Path,
    config_lookup: ConfigLookup,
    node: ast.ImportFrom,
) -> list[str]:
    """
    Checks if module X.py can import any other module.
    """

    violations: list[str] = []
    config = get_package_config(
        directory_path=filename.parent,
        root_path=app_root_path,
        config_lookup=config_lookup,
    )
    if config is None or config.allowed_import_modules is None:
        return []

    allowed_modules_tree = build_allowed_modules_tree(
        config=config, mode=ModuleTreeBuildingMode.IMPORT
    )
    if node.module is None:
        return []
    if is_operation_allowed(node.module, allowed_modules_tree) is True:
        return []

    violations.append(f"{filename}: {node.module}")
    violations.append(f"Allowed imports: {config.allowed_import_modules}")
    violations.append(f"Config file: {config.path}\n")
    return violations


def check_for_allowed_exports(
    importing_file: Path,
    app_root_path: Path,
    config_lookup: ConfigLookup,
    node: ast.ImportFrom,
) -> list[str]:
    """
    Checks if module X.py can be imported from other modules.
    """

    violations: list[str] = []

    path_of_imported_module = build_path_from_import(
        module_import=node.module or "", root_path=app_root_path
    )
    config = get_package_config(
        directory_path=path_of_imported_module.parent,
        root_path=app_root_path,
        config_lookup=config_lookup,
    )
    if config is None or config.allowed_export_modules is None:
        return []

    allowed_modules_tree = build_allowed_modules_tree(
        config=config, mode=ModuleTreeBuildingMode.EXPORT
    )
    bypass_modules_tree = build_allowed_modules_tree(
        config=config, mode=ModuleTreeBuildingMode.BYPASS
    )
    if node.module is None:
        return []
    if can_bypass_check(
        imported_from=build_module_from_path(
            path=importing_file, root_path=app_root_path
        ),
        bypass_modules_tree=bypass_modules_tree,
    ):
        return []
    if is_operation_allowed(node.module, allowed_modules_tree) is True:
        return []

    violations.append(f"{importing_file}: {node.module}")
    violations.append(f"Allowed exports: {config.allowed_export_modules}")
    violations.append(f"Config file: {config.path}\n")
    return violations


def check_for_violations(
    filename: Path,
    app_root_path: Path,
    local_packages_tree: dict,
    config_lookup: dict[str, Config],
) -> tuple[list[str], list[str]]:
    import_violations: list[str] = []
    export_violations: list[str] = []
    if not str(filename).endswith(".py"):
        print(f"Not checking file {filename}")
        return [], []

    import_nodes = get_import_nodes(str(filename))
    local_import_nodes = get_local_import_nodes(import_nodes, local_packages_tree)

    for node in local_import_nodes:
        #
        # Check for allowed imports
        #
        import_violations += check_for_allowed_imports(
            app_root_path=app_root_path,
            filename=filename,
            config_lookup=config_lookup,
            node=node,
        )

        #
        # Check for allowed exports
        #
        export_violations += check_for_allowed_exports(
            app_root_path=app_root_path,
            importing_file=filename,
            config_lookup=config_lookup,
            node=node,
        )

    return import_violations, export_violations


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument(
        "--app-root",
        dest="app_root",
        default="",
        help="Defines the root directory where your python application lives. "
        "Must be relative to the cwd path of execution of this script. Default value is current working directory. Example: --app-root=src",
    )
    args = parser.parse_args(argv)

    if not Path(args.app_root).exists():
        print(
            "--app-root argument does not point to root directory of python application"
        )
        exit(-1)

    path_of_execution = Path().cwd()
    app_root_path = Path(f"{path_of_execution}/{args.app_root}")

    packages_tree = get_package_tree(app_root_path)
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
            local_packages_tree=packages_tree,
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
        exit(-1)
