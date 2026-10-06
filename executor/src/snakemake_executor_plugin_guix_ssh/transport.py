import os
import shlex
import shutil
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
    def _safe_paths(paths: Iterable[str], root: Path | None = None) -> list[str]:
        root = (root or Path.cwd()).resolve()
        safe = []
        seen: dict[str, str] = {}
        for value in paths:
            original = os.fspath(value)
            path = Path(original)
            if ".." in path.parts:
                raise ValueError(f"job path traverses the working directory: {original!r}")
            resolved = (path if path.is_absolute() else root / path).resolve()
            try:
                relative = resolved.relative_to(root)
            except ValueError as error:
                raise ValueError(f"job path is outside working directory {root}: {original!r}") from error
            if not relative.parts or relative.parts[0] == ".snakemake":
                continue
            mapped = relative.as_posix()
            previous = seen.get(mapped)
            if previous is not None and (
                Path(previous) if Path(previous).is_absolute() else root / previous
            ).resolve() != resolved:
                raise ValueError(f"distinct job paths map to {mapped!r}: {previous!r}, {original!r}")
            seen[mapped] = original
            if mapped not in safe:
                safe.append(mapped)
        return safe

    def stage_inputs(self, host: Host, job_dir: PurePosixPath, paths: Iterable[str], root: Path | None = None) -> None:
        paths = self._safe_paths(paths, root)
        incoming = job_dir / ".incoming"
        self.commands.ssh(host, f"mkdir -p {shlex.quote(str(incoming))}")
        if paths:
            source_paths = paths if root is None else [f"{root.resolve()}/./{path}" for path in paths]
            with self._transfers:
                self.commands.rsync(host, source_paths, f"{host.hostname}:{incoming}/")
        script = (
            f"cd {shlex.quote(str(job_dir))} && "
            "find .incoming -mindepth 1 -maxdepth 1 -exec mv -- {} . \\; && "
            "rmdir .incoming"
        )
        self.commands.ssh(host, script)

    def retrieve_outputs(
        self, host: Host, job_dir: PurePosixPath, paths: Iterable[str], root: Path | None = None
    ) -> None:
        root = (root or Path.cwd()).resolve()
        paths = self._safe_paths(paths, root)
        if paths:
            checks = " && ".join(
                f"test -e {shlex.quote(path)}" for path in paths
            )
            self.commands.ssh(
                host,
                f"cd {shlex.quote(str(job_dir))} && {checks}",
            )
        pending = []
        try:
            for value in paths:
                target = root / value
                target.parent.mkdir(parents=True, exist_ok=True)
                temporary = target.with_name(f".{target.name}.guix-ssh-{os.getpid()}.tmp")
                pending.append((temporary, target))
                with self._transfers:
                    self.commands.rsync(
                        host,
                        [f"{host.hostname}:{job_dir}/{value}"],
                        str(temporary),
                        relative=False,
                    )
            for temporary, target in pending:
                if temporary.is_dir() and target.is_dir():
                    backup = target.with_name(
                        f".{target.name}.guix-ssh-{os.getpid()}.old"
                    )
                    os.replace(target, backup)
                    try:
                        os.replace(temporary, target)
                    except OSError:
                        os.replace(backup, target)
                        raise
                    shutil.rmtree(backup)
                else:
                    os.replace(temporary, target)
        finally:
            for temporary, _ in pending:
                if temporary.is_dir():
                    shutil.rmtree(temporary)
                else:
                    temporary.unlink(missing_ok=True)
