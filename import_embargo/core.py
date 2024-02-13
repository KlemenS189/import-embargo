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


def get_package_tree(path: Path) -> dict:
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
    if not Path(f"{path}/__init__.py").exists():
        return {}

    for item in path.iterdir():
        if item.name in IGNORE_LIST:
            continue
        if item.is_file() and item.name.endswith(".py"):
            package_tree[item.name] = None
        if item.is_dir() and "." not in item.name:
            package_tree[item.name] = get_package_tree(item)
    return package_tree


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


def main(argv: list[str] | None = None):
    parser = argparse.ArgumentParser()
    parser.add_argument("filenames", nargs="*")
    parser.add_argument("--app-root", dest="app_root")
    args = parser.parse_args(argv)

    if args.app_root is None:
        print("--app-root argument must be set")
        exit(-1)

    if not Path(args.app_root).exists():
        print(
            "--app-root argument does not point to root directory of python application"
        )
        exit(-1)

    root_path = Path().cwd()
    app_root_path = Path(f"{root_path}/{args.app_root}")

    packages_tree = get_package_tree(app_root_path)

    violations: list[str] = []

    for filename in args.filenames:
        if not filename.endswith(".py"):
            print(f"Not checking file {filename}")
            continue
        filename_path = Path(filename)
        combined_path = f"{root_path}/{filename_path}"
        config = get_package_config(Path(combined_path).parent, app_root_path)
        if config is None:
            continue
        import_nodes = get_import_nodes(filename)
        local_import_nodes = get_local_import_nodes(import_nodes, packages_tree)
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
    if len(violations) > 0:
        print(" ❌ Import violations detected\n")
        for violation in violations:
            print(violation)
        exit(-1)
    exit(0)
