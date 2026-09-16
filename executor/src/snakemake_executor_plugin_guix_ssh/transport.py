import os
import shlex
from pathlib import Path, PurePosixPath
from threading import Lock, Semaphore
from typing import Iterable

from .commands import Commands
from .model import Host


class Transport:
    def __init__(self, commands: Commands, concurrency: int = 2) -> None:
        self.commands = commands
        self._deployed: set[tuple[tuple[str, int], str]] = set()
        self._lock = Lock()
        self._transfers = Semaphore(concurrency)

    def deploy_environment(self, host: Host, realized) -> None:
        key = (host.key, realized.digest)
        with self._lock:
            if key in self._deployed:
                return
        self.commands.guix_copy(host, realized.profile_store_path)
        self.commands.ssh(
            host,
            f"guix gc --references {shlex.quote(str(realized.profile_store_path))} "
            ">/dev/null",
        )
        with self._lock:
            self._deployed.add(key)

    @staticmethod
    def _safe_paths(paths: Iterable[str]) -> list[str]:
        safe = []
        for value in paths:
            path = Path(value)
            if path.parts and path.parts[0] == ".snakemake":
                continue
            if path.is_absolute() or ".." in path.parts:
                raise ValueError(f"job path must be workflow-relative: {value!r}")
            safe.append(str(path))
        return safe

    def stage_inputs(self, host: Host, job_dir: PurePosixPath, paths: Iterable[str]) -> None:
        paths = self._safe_paths(paths)
        incoming = job_dir / ".incoming"
        self.commands.ssh(host, f"mkdir -p {shlex.quote(str(incoming))}")
        if paths:
            with self._transfers:
                self.commands.rsync(
                    host, paths, f"{host.hostname}:{incoming}/"
                )
        script = (
            f"cd {shlex.quote(str(job_dir))} && "
            "find .incoming -mindepth 1 -maxdepth 1 -exec mv -- {} . \\; && "
            "rmdir .incoming"
        )
        self.commands.ssh(host, script)

    def retrieve_outputs(
        self, host: Host, job_dir: PurePosixPath, paths: Iterable[str]
    ) -> None:
        paths = self._safe_paths(paths)
        if paths:
            checks = " && ".join(
                f"test -e {shlex.quote(path)}" for path in paths
            )
            self.commands.ssh(
                host,
                f"cd {shlex.quote(str(job_dir))} && {checks}",
            )
        for value in paths:
            target = Path(value)
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.guix-ssh-{os.getpid()}.tmp")
            with self._transfers:
                self.commands.rsync(
                    host,
                    [f"{host.hostname}:{job_dir}/{value}"],
                    str(temporary),
                    relative=False,
                )
            os.replace(temporary, target)
