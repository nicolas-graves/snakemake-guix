"""Pytest plugin: every module's exported python files (provides.yaml ``python:``) are importable in tests.

The directories are appended to ``sys.path``, after the test's own ``sys.path.insert(0, ...)`` of its
module's scripts, and to ``PYTHONPATH`` for the scripts a test runs as subprocesses, as the
contracts wrapper puts them on a job's PYTHONPATH.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

from .contracts import list_modules, load_python_exports


def exported_directories(repo_root: Path) -> list[str]:
    directories: list[str] = []
    for module in list_modules(repo_root):
        if not (repo_root / "modules" / module / "provides.yaml").exists():
            continue
        for file in load_python_exports(module, repo_root).values():
            directory = str((repo_root / "modules" / module / file).resolve().parent)
            if directory not in directories:
                directories.append(directory)
    return directories


def _repo_root(start: Path) -> Path | None:
    for candidate in (start, *start.parents):
        if (candidate / "modules").is_dir():
            return candidate
    return None


def _export(start: Path) -> None:
    root = _repo_root(start)
    if root is None:
        return
    directories = exported_directories(root)
    sys.path.extend(d for d in directories if d not in sys.path)
    inherited = [p for p in os.environ.get("PYTHONPATH", "").split(os.pathsep) if p]
    os.environ["PYTHONPATH"] = os.pathsep.join([*inherited, *(d for d in directories if d not in inherited)])


@pytest.hookimpl(tryfirst=True)
def pytest_load_initial_conftests(early_config: pytest.Config, parser: pytest.Parser, args: list[str]) -> None:
    """Before the conftests load, so that they may import an export too."""
    _export(Path(early_config.invocation_params.dir))
