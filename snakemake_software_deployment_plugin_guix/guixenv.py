import os
import shlex
import subprocess as sp
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from snakemake_interface_software_deployment_plugins import EnvBase, SoftwareReport

from snakemake_software_deployment_plugin_guix.guixenvspec import EnvSpec
from snakemake_software_deployment_plugin_guix.settings import Settings


class Env(EnvBase):
    spec: EnvSpec

    def __post_init__(self) -> None:
        self._temp_manifest_file: Optional[str] = None

    def _manifest_path(self) -> str:
        if self.spec.manifest_file is not None:
            cached = self.spec.manifest_file.cached
            if cached is not None:
                return str(cached)
            return str(self.spec.manifest_file.path_or_uri)

        if self._temp_manifest_file is None:
            fd, path = tempfile.mkstemp(suffix=".scm", prefix="guix-manifest-")
            with os.fdopen(fd, "w") as f:
                pkgs = " ".join(f'"{p}"' for p in self.spec.packages)
                f.write(f"(specifications->manifest (list {pkgs}))\n")
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
        manifest = self._manifest_path()
        with open(manifest, "rb") as f:
            hash_object.update(f.read())

        settings: Optional[Settings] = self.settings
        if settings is not None:
            hash_object.update(str(settings.container).encode())
            hash_object.update(str(settings.no_time_machine).encode())
            if settings.channels_file is not None:
                with open(settings.channels_file, "rb") as f:
                    hash_object.update(f.read())

    def report_software(self) -> Iterable[SoftwareReport]:
        if self.spec.packages:
            for pkg in self.spec.packages:
                yield SoftwareReport(name=pkg)
        elif self.spec.manifest_file is not None:
            yield SoftwareReport(name=str(self.spec.manifest_file.path_or_uri))
