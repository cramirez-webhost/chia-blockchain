import argparse
import json
import logging
import os
import types
from pathlib import Path
from typing import Any, Dict, List

import testconfig

root_path = Path(__file__).parent.resolve()


def skip(path: Path) -> bool:
    return any(part.startswith(("_", ".")) for part in path.parts)


def subdirs(per: str) -> List[Path]:
    dirs: List[Path]

    if per == "directory":
        glob_pattern = "**/"
    elif per == "file":
        glob_pattern = "**/test_*.py"
    else:
        raise Exception(f"Unrecognized per: {per!r}")

    paths = [path for path in root_path.rglob(glob_pattern) if not skip(path=path)]

    if per == "directory":
        filtered_paths = []
        for path in paths:
            relative_path = path.relative_to(root_path)
            logging.info(f"Considering: {relative_path}")
            if len([f for f in path.glob("test_*.py")]) == 0:
                logging.info(f"Skipping {relative_path}: no tests collected")
                continue

            filtered_paths.append(path)

        paths = filtered_paths

    return sorted(paths)


def module_dict(module: types.ModuleType) -> Dict[str, Any]:
    return {k: v for k, v in module.__dict__.items() if not k.startswith("_")}


def dir_config(dir: Path) -> Dict[str, Any]:
    import importlib

    module_name = ".".join([*dir.relative_to(root_path).parts, "config"])
    try:
        return module_dict(importlib.import_module(module_name))
    except ModuleNotFoundError:
        return {}


# Overwrite with directory specific values
def update_config(parent: Dict[str, Any], child: Dict[str, Any]) -> Dict[str, Any]:
    if child is None:
        return parent
    conf = child
    for k, v in parent.items():
        if k not in child:
            conf[k] = v
    return conf


# args
arg_parser = argparse.ArgumentParser(description="Generate GitHub test matrix configuration")
arg_parser.add_argument("--per", type=str, choices=["directory", "file"], required=True)
arg_parser.add_argument("--verbose", "-v", action="store_true")
args = arg_parser.parse_args()

if args.verbose:
    logging.basicConfig(format="%(asctime)s:%(message)s", level=logging.DEBUG)

# main
test_paths = subdirs(per=args.per)

configuration = []

for path in test_paths:
    relative_path = path.relative_to(root_path)

    dir: Path
    if path.is_dir():
        dir = path
        path_for_cli = f"{os.fspath(relative_path)}/test_*.py"
    else:
        dir = path.parent
        path_for_cli = f"{os.fspath(relative_path)}"

    conf = update_config(module_dict(testconfig), dir_config(dir))

    if conf.get("custom_parallel_n") is not None:
        pytest_parallel_args = f"-n {conf['custom_parallel_n']}"
    else:
        pytest_parallel_args = "-n 4" if conf["parallel"] else "-n 0"

    for_matrix = {
        "check_resource_usage": conf["check_resource_usage"],
        "disable_pytest_monitor": "" if conf["check_resource_usage"] else "-p no:monitor",
        "job_timeout": conf["job_timeout"],
        "pytest_parallel_args": pytest_parallel_args,
        "checkout_blocks_and_plots": conf["checkout_blocks_and_plots"],
        "install_timelord": conf["install_timelord"],
        "path": os.fspath(path_for_cli),
        "name": ".".join(relative_path.with_suffix("").parts),
    }
    for_matrix = dict(sorted(for_matrix.items()))
    configuration.append(for_matrix)


configuration_json = json.dumps(configuration)

for line in json.dumps(configuration, indent=4).splitlines():
    logging.info(line)

print(f"{configuration_json}")
