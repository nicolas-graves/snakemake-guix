from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Mapping, Union


@dataclass(frozen=True)
class Host:
    hostname: str
    port: int
    workdir: PurePosixPath
    cpus: int | None = None
    mem_mb: int | None = None
    gpus: int | None = None

    @classmethod
    def parse(cls, value: str) -> "Host":
        try:
            hostname, port, workdir = value.split(":", 2)
            parsed_port = int(port)
        except (ValueError, TypeError) as error:
            raise ValueError(
                f"invalid Guix SSH host {value!r}; expected HOST:PORT:WORKDIR"
            ) from error
        if not hostname or not workdir or not 1 <= parsed_port <= 65535:
            raise ValueError(
                f"invalid Guix SSH host {value!r}; expected HOST:PORT:WORKDIR"
            )
        path = PurePosixPath(workdir)
        if not path.is_absolute():
            raise ValueError(f"remote workdir must be absolute, got {workdir!r}")
        return cls(hostname, parsed_port, path)

    @property
    def key(self) -> tuple[str, int]:
        return (self.hostname, self.port)


@dataclass
class Capacity:
    cpus: int
    mem_mb: int
    gpus: int = 0

    def requirement(self, job) -> tuple[int, int, int]:
        resources: Mapping[str, Union[int, str]] = job.resources
        return (
            job.threads,
            int(resources.get("mem_mb", 0)),
            int(resources.get("gpu", resources.get("gpus", 0))),
        )

    def feasible(self, job) -> bool:
        cpus, mem_mb, gpus = self.requirement(job)
        return cpus <= self.cpus and mem_mb <= self.mem_mb and gpus <= self.gpus

    def reserve(self, job) -> None:
        if not self.feasible(job):
            raise ValueError("job does not fit available host resources")
        cpus, mem_mb, gpus = self.requirement(job)
        self.cpus -= cpus
        self.mem_mb -= mem_mb
        self.gpus -= gpus

    def release(self, job) -> None:
        cpus, mem_mb, gpus = self.requirement(job)
        self.cpus += cpus
        self.mem_mb += mem_mb
        self.gpus += gpus
