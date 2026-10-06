import shlex
import shutil
import subprocess as sp
from pathlib import Path
from typing import Iterable, Optional

from .model import Host


class CommandError(RuntimeError):
    pass


class Commands:
    def __init__(
        self,
        identity_file: Optional[str] = None,
        ssh_args: Optional[str] = None,
        retries: int = 3,
    ) -> None:
        self.identity_file = str(Path(identity_file).expanduser()) if identity_file else None
        self.extra_ssh_args = shlex.split(ssh_args or "")
        self.retries = retries
        self._host_options: dict[str, list[str]] = {}

    def set_host_options(self, hostname: str, *, address: str, known_hosts: str) -> None:
        self._host_options[hostname] = [
            "-F", "/dev/null",
            "-o", f"HostName={address}",
            "-o", "User=root",
            "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "StrictHostKeyChecking=yes",
        ]

    def clear_host_options(self, hostname: str) -> None:
        self._host_options.pop(hostname, None)

    def ssh_args(self, host: Host) -> list[str]:
        identity = [] if self.identity_file is None else ["-i", self.identity_file]
        return [
            "-p",
            str(host.port),
            *identity,
            *self.extra_ssh_args,
            *self._host_options.get(host.hostname, []),
            host.hostname,
        ]

    def run(self, argv: list[str], **kwargs) -> sp.CompletedProcess:
        last = None
        for _ in range(self.retries):
            last = sp.run(argv, capture_output=True, text=True, **kwargs)
            if last.returncode == 0:
                return last
        assert last is not None
        raise CommandError(
            f"command failed after {self.retries} attempt(s): "
            f"{shlex.join(argv)}\n{last.stderr}"
        )

    def ssh(self, host: Host, script: str) -> sp.CompletedProcess:
        # OpenSSH concatenates remote argv into shell text, so pass one safely
        # quoted remote command instead of separate `bash -c` arguments.
        remote_command = shlex.join(["bash", "-c", script])
        return self.run(["ssh", *self.ssh_args(host), "--", remote_command])

    def preflight(self, host: Host) -> None:
        for executable in ("ssh", "rsync", "guix"):
            if shutil.which(executable) is None:
                raise CommandError(f"required local executable is unavailable: {executable}")
        # guix copy resolves the alias through SSH configuration, independently
        # of the command-line options passed to ssh and rsync.
        configured = self.run(["ssh", "-G", host.hostname]).stdout
        options = dict(line.split(None, 1) for line in configured.splitlines() if " " in line)
        effective = self.run(["ssh", "-G", *self.ssh_args(host)]).stdout
        effective_options = dict(line.split(None, 1) for line in effective.splitlines() if " " in line)
        for key in ("hostname", "user", "port"):
            if options.get(key) != effective_options.get(key):
                raise CommandError(
                    f"SSH alias {host.hostname!r} resolves different {key} for guix copy and ssh"
                )
        if int(options.get("port", "22")) != host.port:
            raise CommandError(
                f"SSH alias {host.hostname!r} must configure port {host.port} "
                "for guix copy as well as ssh and rsync"
            )
        if self.identity_file and self.identity_file not in configured:
            raise CommandError(
                f"SSH alias {host.hostname!r} must configure identity file "
                f"{self.identity_file!r} for guix copy"
            )
        workdir = shlex.quote(str(host.workdir))
        self.ssh(
            host,
            "command -v guix >/dev/null || { echo 'remote guix is unavailable' >&2; exit 1; }; "
            "command -v rsync >/dev/null || { echo 'remote rsync is unavailable' >&2; exit 1; }; "
            f"test -d {workdir} || {{ echo 'remote workdir does not exist' >&2; exit 1; }}; "
            f"test -w {workdir} || {{ echo 'remote workdir is not writable' >&2; exit 1; }}"
        )

    def guix_copy(self, host: Host, store_path: Path) -> sp.CompletedProcess:
        # `guix copy` accepts an SSH host (and honors ~/.ssh/config), not an
        # ssh:// URI.  Non-default ports therefore belong in SSH config.
        return self.run(
            ["guix", "copy", f"--to={host.hostname}", str(store_path)]
        )

    def rsync(
        self,
        host: Host,
        sources: Iterable[str],
        destination: str,
        *,
        relative: bool = True,
    ) -> sp.CompletedProcess:
        ssh_transport = shlex.join(["ssh", *self.ssh_args(host)[:-1]])
        relative_arg = ["--relative"] if relative else []
        return self.run(
            [
                "rsync",
                "--archive",
                "--protect-args",
                *relative_arg,
                "--exclude=/.snakemake/***",
                "-e",
                ssh_transport,
                *sources,
                destination,
            ]
        )
