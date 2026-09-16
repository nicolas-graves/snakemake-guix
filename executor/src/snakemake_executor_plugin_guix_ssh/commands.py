import shlex
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
        self.identity_file = identity_file
        self.extra_ssh_args = shlex.split(ssh_args or "")
        self.retries = retries

    def ssh_args(self, host: Host) -> list[str]:
        identity = [] if self.identity_file is None else ["-i", self.identity_file]
        return [
            "-p",
            str(host.port),
            *identity,
            *self.extra_ssh_args,
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
