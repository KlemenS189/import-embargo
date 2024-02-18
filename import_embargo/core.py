import argparse
import ast
import dataclasses
import json
from pathlib import Path

IGNORE_LIST = {"__pycache__", ".mypy_cache", ".DS_Store", ".ruff_cache"}


@dataclasses.dataclass
class Config:
    allowed_import_modules: list[str]
    path: str


def get_import_nodes(filename: str) -> list[ast.ImportFrom]:
    with open(filename) as f:
        file = f.read()
    tree = ast.parse(file)

    return [node for node in tree.body if isinstance(node, ast.ImportFrom)]


def get_package_config(directory_path: Path, root_path: Path) -> Config | None:
    potential_embargo_file = Path(f"{directory_path}/__embargo__.json")
    if not potential_embargo_file.exists():
        if directory_path == root_path:
            return None
        return get_package_config(directory_path.parent, root_path)

    json_config = json.loads(potential_embargo_file.read_text())
    if "allowed_import_modules" not in json_config:
        raise ValueError(
            "'allowed_import_modules' key must be present in __embargo__.json"
        )
    return Config(
        allowed_import_modules=json_config["allowed_import_modules"],
        path=str(potential_embargo_file),
    )


def get_package_tree(path: Path) -> tuple[dict[Path, dict | None], set[Path]]:
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
    package_tree = {}

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
        module_path = node.module.split(".")
        first_package = module_path[0]
        if first_package in local_package_tree:
            local_import_nodes.append(node)
    return local_import_nodes


def build_allowed_modules_tree(config: Config) -> dict:
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
    tree = {}
    for allowed_import in config.allowed_import_modules:
        current_dict = tree
        for s in allowed_import.split("."):
            current_dict = current_dict.setdefault(s, {})
    return tree


def is_import_allowed(imported_module: str, allowed_modules_tree: dict) -> bool:
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
    current_dict = allowed_modules_tree
    for name in splitted_module_name:
        current_dict = current_dict.get(name)
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


def check_for_violations(
    filename: Path, app_root_path: Path, local_packages_tree: dict
) -> list[str]:
    violations = []
    if not str(filename).endswith(".py"):
        print(f"Not checking file {filename}")
        return []
    config = get_package_config(directory_path=filename.parent, root_path=app_root_path)
    if config is None:
        return []
    import_nodes = get_import_nodes(filename)
    local_import_nodes = get_local_import_nodes(import_nodes, local_packages_tree)
    allowed_modules_tree = build_allowed_modules_tree(config)
    has_violated = False
    for node in local_import_nodes:
        if is_import_allowed(node.module, allowed_modules_tree) is True:
            continue
        has_violated = True
        violations.append(f"{filename}: {node.module}")
    if has_violated is True:
        violations.append(f"Allowed imports: {config.allowed_import_modules}")
        violations.append(f"Config file: {config.path}")
        violations.append("")
    return violations


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--app-root", dest="app_root", default="")
    args = parser.parse_args(argv)

    if args.app_root is None:
        print("--app-root argument must be set")
        exit(-1)

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

    violations: list[str] = []

    for file in filenames_to_check:
        violations += check_for_violations(
            filename=file,
            app_root_path=app_root_path,
            local_packages_tree=packages_tree,
        )

    if len(violations) > 0:
        print(" ❌ Import violations detected\n")
        for violation in violations:
            print(violation)
        exit(-1)
