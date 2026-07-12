import warnings
from copy import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Tuple, Union

from snakemake_interface_software_deployment_plugins import EnvSpecBase, EnvSpecSourceFile
from snakemake_software_deployment_plugin_guix.common import common_settings  # noqa: F401


@dataclass(eq=False)
class EnvSpec(EnvSpecBase):
    manifest_files: Tuple[EnvSpecSourceFile, ...] = field(default_factory=tuple)
    manifest_file: Optional[EnvSpecSourceFile] = None
    packages: Tuple[str, ...] = field(default_factory=tuple)
    channels_file: Optional[EnvSpecSourceFile] = None
    url: Optional[str] = None
    commit: Optional[str] = None
    branch: Optional[str] = None

    def __post_init__(self):
        self.manifest_files = self._coerce_manifest_files(self.manifest_files)
        if isinstance(self.manifest_file, (str, Path)):
            self.manifest_file = EnvSpecSourceFile(self.manifest_file)
        if isinstance(self.channels_file, (str, Path)):
            self.channels_file = EnvSpecSourceFile(self.channels_file)
        if self.manifest_file is not None:
            warnings.warn(
                "manifest_file= is deprecated; use manifest_files=[...] instead.",
                FutureWarning,
                stacklevel=2,
            )
            if not self.manifest_files:
                self.manifest_files = (self.manifest_file,)
            elif self.manifest_file not in self.manifest_files:
                self.manifest_files = (self.manifest_file,) + self.manifest_files
        self.packages = self._coerce_packages(self.packages)
        self.manifest_file = self.manifest_files[0] if self.manifest_files else None

    @staticmethod
    def _coerce_manifest_files(
        value: Union[
            None,
            EnvSpecSourceFile,
            str,
            Path,
            Tuple[Union[EnvSpecSourceFile, str, Path], ...],
            List[Union[EnvSpecSourceFile, str, Path]],
        ]
    ) -> Tuple[EnvSpecSourceFile, ...]:
        if value is None:
            return tuple()
        if isinstance(value, (str, Path, EnvSpecSourceFile)):
            value = (value,)
        return tuple(
            item if isinstance(item, EnvSpecSourceFile) else EnvSpecSourceFile(item)
            for item in value
        )

    @staticmethod
    def _coerce_packages(
        value: Union[None, str, Tuple[str, ...], List[str]]
    ) -> Tuple[str, ...]:
        if value is None:
            return tuple()
        if isinstance(value, str):
            return (value,)
        if isinstance(value, list):
            return tuple(value)
        return value

    def modify_identity_attributes(self, modify_func: Callable) -> "EnvSpec":
        copied = copy(self)
        copied.manifest_files = tuple(modify_func(f) for f in copied.manifest_files)
        copied.packages = tuple(modify_func(p) for p in copied.packages)
        copied.manifest_file = (
            copied.manifest_files[0] if copied.manifest_files else None
        )
        if copied.channels_file is not None:
            copied.channels_file = modify_func(copied.channels_file)
        copied._obj_hash = None
        if copied.within is not None:
            copied.within = copied.within.modify_identity_attributes(modify_func)
        if copied.fallback is not None:
            copied.fallback = copied.fallback.modify_identity_attributes(modify_func)
        return copied

    def modify_source_paths(self, modify_func: Callable) -> "EnvSpec":
        copied = copy(self)
        copied.manifest_files = tuple(modify_func(f) for f in copied.manifest_files)
        copied.manifest_file = (
            copied.manifest_files[0] if copied.manifest_files else None
        )
        if copied.channels_file is not None:
            copied.channels_file = modify_func(copied.channels_file)
        copied._obj_hash = None
        if copied.within is not None:
            copied.within = copied.within.modify_source_paths(modify_func)
        if copied.fallback is not None:
            copied.fallback = copied.fallback.modify_source_paths(modify_func)
        return copied

    @classmethod
    def env_cls(cls):
        from snakemake_software_deployment_plugin_guix.guixenv import Env
        return Env

    @classmethod
    def identity_attributes(cls) -> Iterable[str]:
        yield "manifest_files"
        yield "packages"
        yield "channels_file"
        yield "url"
        yield "commit"
        yield "branch"

    @classmethod
    def source_path_attributes(cls) -> Iterable[str]:
        # Yield the nullable scalar alias rather than manifest_files (tuple) because
        # the base class has_source_paths() checks `getattr(self, attr) is not None`.
        # Per-element rewriting is handled by the modify_source_paths override.
        yield "manifest_file"
        yield "channels_file"

    def __str__(self) -> str:
        if self.manifest_files:
            manifests = ", ".join(
                str(file.path_or_uri) for file in self.manifest_files
            )
            if self.packages:
                base = f"manifests=[{manifests}], packages=[{', '.join(self.packages)}]"
            else:
                base = manifests
        elif self.packages:
            base = " ".join(self.packages)
        else:
            base = "guix"
        if self.channels_file is not None:
            base += f" (channels={self.channels_file.path_or_uri})"
        elif self.url is not None or self.commit is not None or self.branch is not None:
            parts = []
            if self.url is not None:
                parts.append(f"url={self.url}")
            if self.commit is not None:
                parts.append(f"commit={self.commit}")
            if self.branch is not None:
                parts.append(f"branch={self.branch}")
            base += f" (time-machine: {', '.join(parts)})"
        return base
