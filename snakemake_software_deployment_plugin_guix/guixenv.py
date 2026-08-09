import os
import shlex
import subprocess as sp
import tempfile
from pathlib import Path
from typing import Iterable, Optional

from snakemake_interface_common.exceptions import WorkflowError
from snakemake_interface_software_deployment_plugins import (
    EnvBase,
    EnvSpecSourceFile,
    SoftwareReport,
)

from snakemake_software_deployment_plugin_guix.channels import classify_channels_value
from snakemake_software_deployment_plugin_guix.common import time_machine_supports_flag
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
        return self._source_path(manifest_file)

    @staticmethod
    def _source_path(source_file) -> str:
        cached = source_file.cached
        if cached is not None:
            return str(cached)
        return str(source_file.path_or_uri)

    def _effective_channels(self) -> Optional[str]:
        settings: Optional[Settings] = self.settings
        if settings is not None and settings.channels is not None:
            return self._resolve_channels_value(str(settings.channels))
        if self.spec.channels is None:
            return None
        channels = self.spec.channels
        if isinstance(channels, EnvSpecSourceFile):
            path = self._source_path(channels)
            if not os.path.isfile(path):
                raise WorkflowError(
                    f"guix software deployment: channels file {path!r} does not "
                    f"exist (from channels={channels.path_or_uri!r})."
                )
            return path
        return channels

    @staticmethod
    def _resolve_channels_value(value: str) -> str:
        if classify_channels_value(value) == "direct":
            return value
        if not os.path.isfile(value):
            raise WorkflowError(
                f"guix software deployment: --sdm-guix-channels file {value!r} "
                "does not exist."
            )
        return value

    def _effective_url(self) -> Optional[str]:
        settings: Optional[Settings] = self.settings
        if settings is not None and settings.url is not None:
            return settings.url
        return self.spec.url

    def _effective_commit(self) -> Optional[str]:
        settings: Optional[Settings] = self.settings
        if settings is not None and settings.commit is not None:
            return settings.commit
        return self.spec.commit

    def _effective_branch(self) -> Optional[str]:
        settings: Optional[Settings] = self.settings
        if settings is not None and settings.branch is not None:
            return settings.branch
        return self.spec.branch

    def _time_machine_pin(self):
        """Resolve the active time-machine pin: ("channels", value),
        ("refs", (url, commit, branch)), or None. Raises WorkflowError if
        channels and url/commit/branch are both effective, mirroring
        guix time-machine's own rejection of combining -C with
        --url/--commit/--branch.
        """
        channels = self._effective_channels()
        url = self._effective_url()
        commit = self._effective_commit()
        branch = self._effective_branch()
        refs = (url, commit, branch) if (url or commit or branch) else None

        if channels is not None and refs is not None:
            raise WorkflowError(
                "guix software deployment: channels and url/commit/branch "
                "are mutually exclusive guix time-machine pinning mechanisms "
                f"(effective channels={channels!r}, "
                f"effective url/commit/branch={refs!r}). "
                "Set only one mechanism for this rule."
            )
        if channels is not None:
            return ("channels", channels)
        if refs is not None:
            return ("refs", refs)
        return None

    @staticmethod
    def _require_time_machine_flag(flag: str) -> None:
        if time_machine_supports_flag(flag):
            return
        setting_name = {
            "--allow-untrusted-channels": "--sdm-guix-allow-untrusted-channels",
            "--unsafe-channel-evaluation": "--sdm-guix-unsafe-channel-evaluation",
        }[flag]
        raise WorkflowError(
            f"guix software deployment: your guix predates {flag} "
            f"({setting_name}) and is too old. Run `guix pull` now to "
            "avoid known vulnerabilities -- this is not optional."
        )

    def _use_time_machine(self) -> bool:
        settings: Optional[Settings] = self.settings
        if settings is not None and settings.no_time_machine:
            return False
        return self._time_machine_pin() is not None

    def _needs_aggregate_manifest(self) -> bool:
        return len(self._manifest_sources()) > 1 or (
            self._manifest_sources() and bool(self.spec.packages)
        )

    def _aggregate_manifest_content(self) -> str:
        parts = ["(use-modules (guix profiles) (gnu))"]
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

    def _uses_generated_manifest(self) -> bool:
        manifest_sources = self._manifest_sources()
        return not (len(manifest_sources) == 1 and not self.spec.packages)

    def _write_temp_manifest(self) -> str:
        fd, path = tempfile.mkstemp(suffix=".scm", prefix="guix-manifest-")
        with os.fdopen(fd, "w") as f:
            f.write(self._aggregate_manifest_content())
        return path

    def _manifest_path(self) -> str:
        manifest_sources = self._manifest_sources()
        if not self._uses_generated_manifest():
            return self._manifest_source_path(manifest_sources[0])

        if self._temp_manifest_file is None or not os.path.exists(
            self._temp_manifest_file
        ):
            self._temp_manifest_file = self._write_temp_manifest()
        return self._temp_manifest_file

    def decorate_shellcmd(self, cmd: str) -> str:
        uses_generated_manifest = self._uses_generated_manifest()
        manifest = (
            self._write_temp_manifest()
            if uses_generated_manifest
            else self._manifest_path()
        )
        settings: Optional[Settings] = self.settings

        use_container = settings is not None and settings.container
        extra_args = settings.additional_args if settings is not None else None

        if self._use_time_machine():
            pin_kind, pin_value = self._time_machine_pin()
            flags = []
            if pin_kind == "channels":
                flags.append(f"-C {shlex.quote(pin_value)}")
            else:
                url, commit, branch = pin_value
                if url is not None:
                    flags.append(f"--url={shlex.quote(url)}")
                if commit is not None:
                    flags.append(f"--commit={shlex.quote(commit)}")
                if branch is not None:
                    flags.append(f"--branch={shlex.quote(branch)}")
            if settings is not None and settings.allow_untrusted_channels:
                self._require_time_machine_flag("--allow-untrusted-channels")
                flags.append("--allow-untrusted-channels")
            if settings is not None and settings.unsafe_channel_evaluation:
                self._require_time_machine_flag("--unsafe-channel-evaluation")
                flags.append("--unsafe-channel-evaluation")
            prefix = "guix time-machine " + " ".join(flags) + " -- guix shell"
        else:
            prefix = "guix shell"

        if use_container:
            prefix += " --container"

        if extra_args:
            prefix += " " + " ".join(shlex.quote(a) for a in extra_args)

        decorated = f"{prefix} -m {shlex.quote(manifest)} -- bash -c {shlex.quote(cmd)}"
        if not uses_generated_manifest:
            return decorated

        manifest_arg = shlex.quote(manifest)
        cleanup = f"status=$?; rm -f {manifest_arg}; exit $status"
        return f"trap {shlex.quote(cleanup)} EXIT; {decorated}"

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
            hash_object.update(str(settings.allow_untrusted_channels).encode())
            hash_object.update(str(settings.unsafe_channel_evaluation).encode())

        if self._use_time_machine():
            pin_kind, pin_value = self._time_machine_pin()
            if pin_kind == "channels":
                if os.path.isfile(pin_value):
                    with open(pin_value, "rb") as f:
                        hash_object.update(b"channels:")
                        hash_object.update(f.read())
                        hash_object.update(b"\0")
                else:
                    hash_object.update(b"channels-uri:" + pin_value.encode())
                    hash_object.update(b"\0")
            else:
                url, commit, branch = pin_value
                hash_object.update(b"url:" + (url or "").encode() + b"\0")
                hash_object.update(b"commit:" + (commit or "").encode() + b"\0")
                hash_object.update(b"branch:" + (branch or "").encode() + b"\0")

    def report_software(self) -> Iterable[SoftwareReport]:
        for manifest_file in self._manifest_sources():
            yield SoftwareReport(name=str(manifest_file.path_or_uri))
        for pkg in self.spec.packages:
            yield SoftwareReport(name=_software_name(pkg))
