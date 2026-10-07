from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from pathlib import Path
from typing import Any, Literal, MutableMapping, Protocol

import yaml


@dataclass(frozen=True)
class ContractError(Exception):
    message: str

    def __str__(self) -> str:
        return self.message


class WorkflowLike(Protocol):
    """The small part of Snakemake's workflow object used by this module."""

    @property
    def snakefile(self) -> str | Path: ...

    def configfile(self, path: str) -> None: ...


StandaloneMode = Literal["required-config", "local-defaults"]


@dataclass(frozen=True)
class ModuleContext:
    """Paths and contract helpers for the active module Snakefile."""

    module_dir: Path
    repo_root: Path
    config: MutableMapping[str, Any]
    standalone: StandaloneMode

    def _directory(self, key: str, local_name: str) -> str:
        if self.standalone == "local-defaults":
            value = self.config.get(key)
            return str(value) if value is not None else str(self.module_dir / local_name)
        return str(self.config[key])

    @property
    def out_dir(self) -> str:
        return self._directory("out", "out")

    @property
    def data_dir(self) -> str:
        return self._directory("data", "data")

    @property
    def cache_dir(self) -> str:
        return self._directory("cache", ".cache")

    def _module_name(self) -> str:
        if self.module_dir.parent.name != "modules":
            raise ContractError(
                f"Snakefile directory {self.module_dir} is not under the expected "
                "<repo>/modules/<module> layout"
            )
        return self.module_dir.name

    @cached_property
    def _provided_outputs(self) -> dict[str, str]:
        return load_provides(self._module_name(), repo_root=self.repo_root)

    def out(self, key: str) -> str:
        mapping = self._provided_outputs
        if key not in mapping:
            module = self._module_name()
            raise KeyError(f"{module}:{key} not declared; available keys: {sorted(mapping)}")
        return str(Path(self.out_dir) / mapping[key])

    def require(self, producer: str, key: str) -> str:
        self._module_name()
        override = self.config.get(key)
        return str(override or provides(producer, key, repo_root=self.repo_root))


def module_context(
    workflow: WorkflowLike,
    config: MutableMapping[str, Any],
    *,
    configfile: str | Path = "config.yaml",
    standalone: StandaloneMode = "required-config",
) -> ModuleContext:
    """Build a context for a module, loading standalone config when appropriate."""

    if standalone not in ("required-config", "local-defaults"):
        raise ValueError(f"unsupported standalone mode: {standalone!r}")

    module_dir = Path(workflow.snakefile).resolve().parent
    config_path = (module_dir / configfile).resolve()
    if not config and (standalone == "required-config" or config_path.exists()):
        workflow.configfile(str(config_path))

    return ModuleContext(
        module_dir=module_dir,
        repo_root=module_dir.parent.parent,
        config=config,
        standalone=standalone,
    )


def _repo_root(repo_root: str | Path | None = None) -> Path:
    if repo_root is None:
        return Path(__file__).resolve().parents[2]
    return Path(repo_root)


def modules_dir(repo_root: str | Path | None = None) -> Path:
    return _repo_root(repo_root) / "modules"


def load_provides(module: str, repo_root: str | Path | None = None) -> dict[str, str]:
    path = modules_dir(repo_root) / module / "provides.yaml"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ContractError(f"{path} must contain a mapping of logical keys to relative paths")
    bad = [k for k, v in data.items() if not isinstance(k, str) or not isinstance(v, str)]
    if bad:
        raise ContractError(f"{path} contains non-string keys/values: {bad}")
    return data


def out_dir(module: str, repo_root: str | Path | None = None) -> Path:
    return modules_dir(repo_root) / module / "out"


def provides(module: str, key: str, repo_root: str | Path | None = None) -> str:
    mapping = load_provides(module, repo_root=repo_root)
    if key not in mapping:
        raise KeyError(f"{module}:{key} not declared; available keys: {sorted(mapping)}")
    return str(out_dir(module, repo_root=repo_root) / mapping[key])


def list_modules(repo_root: str | Path | None = None) -> list[str]:
    root = modules_dir(repo_root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir() and (p / "Snakefile").exists())


def mangle(name: str) -> str:
    return name.replace("-", "_").replace(".", "_")


def validate_repo(repo_root: str | Path | None = None) -> list[str]:
    root = _repo_root(repo_root)
    problems: list[str] = []
    for module in list_modules(root):
        p = modules_dir(root) / module / "provides.yaml"
        if not p.exists():
            continue
        try:
            load_provides(module, root)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{module}: {exc}")
    return problems
