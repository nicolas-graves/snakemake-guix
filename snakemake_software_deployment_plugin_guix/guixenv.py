import os
import shlex
import subprocess as sp
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from snakemake_interface_software_deployment_plugins import EnvBase, SoftwareReport

from snakemake_software_deployment_plugin_guix.guixenvspec import EnvSpec
from snakemake_software_deployment_plugin_guix.settings import Settings


def _scheme_string(s: str) -> str:
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _software_name(item) -> str:
    if isinstance(item, dict):
        return str(item["name"])
    return str(getattr(item, "name", item))


class Env(EnvBase):
    spec: EnvSpec

    def __post_init__(self) -> None:
        self._temp_manifest_file: Optional[str] = None

    def _manifest_sources(self):
        return self.spec.manifest_files

    def _manifest_source_path(self, manifest_file) -> str:
        cached = manifest_file.cached
        if cached is not None:
            return str(cached)
        return str(manifest_file.path_or_uri)

    def _needs_aggregate_manifest(self) -> bool:
        return len(self._manifest_sources()) > 1 or (
            self._manifest_sources() and bool(self.spec.packages)
        )

    def _aggregate_manifest_content(self) -> str:
        parts = ['(use-modules (guix profiles) (gnu))']
        entries = []
        for manifest_file in self._manifest_sources():
            manifest_path = self._manifest_source_path(manifest_file)
            entries.append(f"(primitive-load {_scheme_string(manifest_path)})")
        if self.spec.packages:
            pkgs = " ".join(_scheme_string(pkg) for pkg in self.spec.packages)
            entries.append(f"(specifications->manifest (list {pkgs}))")

        if not entries:
            entries.append("(specifications->manifest (list))")

        if not self._needs_aggregate_manifest():
            return "\n".join(parts + entries) + "\n"

        entries_str = "\n  ".join(entries)
        parts.append(f"(concatenate-manifests (list\n  {entries_str}))")
        return "\n".join(parts) + "\n"

    def _manifest_path(self) -> str:
        manifest_sources = self._manifest_sources()
        if len(manifest_sources) == 1 and not self.spec.packages:
            return self._manifest_source_path(manifest_sources[0])

        if self._temp_manifest_file is None:
            fd, path = tempfile.mkstemp(suffix=".scm", prefix="guix-manifest-")
            with os.fdopen(fd, "w") as f:
                f.write(self._aggregate_manifest_content())
            self._temp_manifest_file = path
        return self._temp_manifest_file

    def decorate_shellcmd(self, cmd: str) -> str:
        manifest = self._manifest_path()
        settings: Optional[Settings] = self.settings

        use_time_machine = settings is not None and not settings.no_time_machine
        channels_file = settings.channels_file if settings is not None else None
        use_container = settings is not None and settings.container
        extra_args = settings.additional_args if settings is not None else None

        if use_time_machine and channels_file is not None:
            prefix = (
                f"guix time-machine -C {shlex.quote(str(channels_file))} "
                "-- guix shell"
            )
        else:
            prefix = "guix shell"

        if use_container:
            prefix += " --container"

        if extra_args:
            prefix += " " + " ".join(shlex.quote(a) for a in extra_args)

        return f"{prefix} -m {shlex.quote(manifest)} -- bash -c {shlex.quote(cmd)}"

    def contains_executable(self, executable: str) -> bool:
        cmd = self.decorate_shellcmd(f"which {shlex.quote(executable)}")
        result = self.run_cmd(cmd, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        return result.returncode == 0

    def record_hash(self, hash_object) -> None:
        for manifest_file in self._manifest_sources():
            manifest_path = self._manifest_source_path(manifest_file)
            with open(manifest_path, "rb") as f:
                hash_object.update(b"manifest:")
                hash_object.update(f.read())
                hash_object.update(b"\0")

        if self.spec.packages:
            for pkg in self.spec.packages:
                hash_object.update(b"package:")
                hash_object.update(pkg.encode())
                hash_object.update(b"\0")

        if not self._manifest_sources() and not self.spec.packages:
            hash_object.update(b"empty-manifest")

        settings: Optional[Settings] = self.settings
        if settings is not None:
            hash_object.update(str(settings.container).encode())
            hash_object.update(str(settings.no_time_machine).encode())
            if settings.channels_file is not None:
                with open(settings.channels_file, "rb") as f:
                    hash_object.update(f.read())

    def report_software(self) -> Iterable[SoftwareReport]:
        for manifest_file in self._manifest_sources():
            yield SoftwareReport(name=str(manifest_file.path_or_uri))
        for pkg in self.spec.packages:
            yield SoftwareReport(name=_software_name(pkg))
