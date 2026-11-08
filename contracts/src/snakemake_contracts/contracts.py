from __future__ import annotations

import os
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


class StorageWorkflowLike(Protocol):
    """The part of Snakemake's workflow object read by the public storage helpers."""

    @property
    def storage_provider_settings(self) -> Any: ...


StandaloneMode = Literal["required-config", "local-defaults"]
HttpPolicy = Literal["checked", "immutable"]


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

    def python(self, producer: str, name: str) -> str:
        """The file `producer` exports as importable module `name` (provides.yaml ``python:``).

        Declare it as the rule's ``python`` input (a list for several): the contracts wrapper puts
        its directory on PYTHONPATH, so the script does a plain ``import name``.
        """
        self._module_name()
        return str(python_export(producer, name, repo_root=self.repo_root))

    def pythonpath(self, *exports: str) -> str:
        """PYTHONPATH entries of `exports` (ctx.python paths), for a shell rule's
        ``PYTHONPATH={params.pythonpath:q}`` prefix."""
        return os.pathsep.join(dict.fromkeys(str(Path(path).resolve().parent) for path in exports))

    @cached_property
    def downloads(self) -> dict[str, dict[str, Any]]:
        """The module's ``downloads.yaml``, one mapping per source key."""

        path = self.module_dir / "downloads.yaml"
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict) or not all(isinstance(v, dict) for v in data.values()):
            raise ContractError(f"{path} must contain a mapping of source keys to mappings")
        return data

    def public_http(
        self,
        workflow: StorageWorkflowLike,
        *,
        policy: HttpPolicy,
        headers: dict[str, str] | None = None,
        check_remote: bool = True,
    ) -> dict[str, Any]:
        """Settings of a ``cached-http`` storage for anonymous public responses.

        Unpack them in a storage directive: ``storage tag: **ctx.public_http(workflow, policy="checked")``.
        ``policy`` applies while ``SNAKEMAKE_STORAGE_CACHED_HTTP_POLICY`` is unset or ``auto``;
        ``check_remote=False`` pins the source (``immutable``, no remote checks).
        """

        settings = _public_settings(workflow, "cached-http", policy if check_remote else "immutable")
        skip = os.environ.get("SNAKEMAKE_STORAGE_CACHED_HTTP_SKIP_REMOTE_CHECKS", "false").lower() in {"true", "1"}
        settings.update(check_interval=86400, skip_remote_checks=skip or not check_remote)
        if headers:
            settings["headers"] = dict(headers)
        return settings

    def public_browser(self, workflow: StorageWorkflowLike, *, policy: HttpPolicy) -> dict[str, Any]:
        """Settings of a ``browser-http`` storage serving the ``browser: true`` entries of ``downloads``.

        Each entry gives the file URL (``lien_primaire``), the page that links it (``lien_secondaire``)
        and the expected ``format``; responses share the ``cached-http`` cache.
        """

        settings = _public_settings(workflow, "browser-http", policy)
        settings["sources"] = {
            entry["lien_primaire"]: {
                "page": entry["lien_secondaire"],
                "format": entry["format"],
                "browser": True,
            }
            for entry in self.downloads.values()
            if entry.get("browser", False)
        }
        return settings


def _public_settings(workflow: StorageWorkflowLike, provider: str, policy: str) -> dict[str, Any]:
    default_cache = workflow.storage_provider_settings["cached-http"].get_settings().cache
    environment_policy = os.environ.get("SNAKEMAKE_STORAGE_CACHED_HTTP_POLICY", "auto")
    return {
        "provider": provider,
        "public_cache": True,
        "discard_response_cookies": True,
        "cache": os.environ.get("SNAKEMAKE_STORAGE_CACHED_HTTP_CACHE", default_cache),
        "policy": policy if environment_policy == "auto" else environment_policy,
    }


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


# provides.yaml key holding the module's importable files ({module name: relative path}), not an output.
PYTHON_EXPORTS = "python"


def _provides_file(module: str, repo_root: str | Path | None) -> tuple[Path, dict[str, Any]]:
    path = modules_dir(repo_root) / module / "provides.yaml"
    if not path.exists():
        raise FileNotFoundError(f"{path} not found")
    with path.open() as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ContractError(f"{path} must contain a mapping of logical keys to relative paths")
    return path, data


def _string_mapping(path: Path, data: Any, what: str) -> dict[str, str]:
    if not isinstance(data, dict):
        raise ContractError(f"{path}: {what} must be a mapping")
    bad = [k for k, v in data.items() if not isinstance(k, str) or not isinstance(v, str)]
    if bad:
        raise ContractError(f"{path} contains non-string keys/values: {bad}")
    return data


def load_provides(module: str, repo_root: str | Path | None = None) -> dict[str, str]:
    """The module's outputs: logical key -> path relative to its out/ directory."""
    path, data = _provides_file(module, repo_root)
    return _string_mapping(path, {k: v for k, v in data.items() if k != PYTHON_EXPORTS}, "outputs")


def load_python_exports(module: str, repo_root: str | Path | None = None) -> dict[str, str]:
    """The module's importable files: module name -> path relative to the module directory."""
    path, data = _provides_file(module, repo_root)
    exports = _string_mapping(path, data.get(PYTHON_EXPORTS) or {}, f"'{PYTHON_EXPORTS}'")
    wrong = [name for name, file in exports.items() if Path(file).name != f"{name}.py"]
    if wrong:
        raise ContractError(f"{path}: an export must be the file <name>.py: {wrong}")
    return exports


def python_export(module: str, name: str, repo_root: str | Path | None = None) -> Path:
    exports = load_python_exports(module, repo_root=repo_root)
    if name not in exports:
        raise KeyError(f"{module} exports no python module {name!r}; exports: {sorted(exports)}")
    return modules_dir(repo_root) / module / exports[name]


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
            load_python_exports(module, root)
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{module}: {exc}")
    return problems
